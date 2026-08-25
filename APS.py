#!/usr/bin/env python3
"""Active Protein Searching (APS) pipeline for NADK candidate prioritization.

The workflow follows a block-structured Step / Module organization. All
data-specific paths and selection parameters are read from YAML, and every
stage writes auditable outputs and provenance records.

Current-study workflow:
  Step 1  ProTrek text-to-protein retrieval
  Step 2  MMseqs2 redundancy reduction
  Step 3  ProstT5 embedding + maximum similarity to individual NADK anchors
  Step 4  background-fitted UMAP + density-defined active regions
  Step 5  ProTrek machine-score ranking + final 642-candidate library
  Step 6  optional performance-gated feedback
  Step 7  audit manifests and command-line controller
"""

# =============================================================================
# Step 0: Environment, global imports and configuration
# =============================================================================
#
# The executable environment is defined in environment.yml.  The ProTrek
# repository and model weights remain external assets and their exact Git/model
# revisions and SHA-256 checksums must be reported with the archived release.
#
# =============================================================================

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import random
import re
import shutil
import subprocess
import sys
import time
from typing import Any, Iterable, Mapping, Sequence

import numpy as np


PIPELINE_VERSION = "1.0.0"
STANDARD_AMINO_ACIDS = set("ACDEFGHIKLMNPQRSTVWYX")


# MODULE 0.1: Optional dependency loading
def require(module_name: str, purpose: str):
    """Import a stage-specific dependency with an actionable message."""
    try:
        return __import__(module_name, fromlist=["*"])
    except ImportError as exc:
        raise SystemExit(
            f"Missing dependency '{module_name}', required for {purpose}. "
            "Create the environment with: conda env create -f environment.yml"
        ) from exc


# MODULE 0.2: YAML configuration context
class PipelineContext:
    def __init__(self, config_path: str | Path):
        yaml = require("yaml", "configuration loading")
        self.config_path = Path(config_path).resolve()
        self.project_root = self.config_path.parent
        with open(self.config_path, encoding="utf-8") as handle:
            self.config = yaml.safe_load(handle)
        if not isinstance(self.config, dict):
            raise ValueError("The YAML root must be a mapping")
        self.output_dir = self.resolve_path(self.get("project.output_dir"))
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.seed = int(self.get("project.random_seed", 42))
        random.seed(self.seed)
        np.random.seed(self.seed)

    def get(self, dotted_key: str, default: Any = None, required: bool = False) -> Any:
        value: Any = self.config
        for part in dotted_key.split("."):
            if not isinstance(value, Mapping) or part not in value:
                if required:
                    raise KeyError(f"Missing required configuration key: {dotted_key}")
                return default
            value = value[part]
        if required and value is None:
            raise KeyError(f"Configuration key must not be null: {dotted_key}")
        return value

    def resolve_path(self, value: str | Path) -> Path:
        path = Path(value)
        return (
            path.resolve()
            if path.is_absolute()
            else (self.project_root / path).resolve()
        )

    def path(self, dotted_key: str, required: bool = True) -> Path | None:
        value = self.get(dotted_key, required=required)
        if value is None:
            return None
        return self.resolve_path(value)

    def output(self, filename: str) -> Path:
        return self.output_dir / filename


# MODULE 0.3: General file and provenance utilities
def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    return str(value)


def write_manifest(
    ctx: PipelineContext,
    stage: str,
    parameters: Mapping[str, Any],
    inputs: Sequence[str | Path],
    outputs: Sequence[str | Path],
    counts: Mapping[str, int] | None = None,
) -> Path:
    payload = {
        "pipeline_version": PIPELINE_VERSION,
        "stage": stage,
        "created_unix": time.time(),
        "configuration": str(ctx.config_path),
        "configuration_sha256": sha256_file(ctx.config_path),
        "parameters": json_safe(parameters),
        "inputs": [
            {"path": str(Path(path).resolve()), "sha256": sha256_file(path)}
            for path in inputs
            if Path(path).is_file()
        ],
        "outputs": [
            {"path": str(Path(path).resolve()), "sha256": sha256_file(path)}
            for path in outputs
            if Path(path).is_file()
        ],
        "counts": dict(counts or {}),
    }
    destination = ctx.output(f"{stage}.manifest.json")
    destination.write_text(
        json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
    )
    return destination


def read_tsv(path: str | Path) -> list[dict[str, str]]:
    with open(path, encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def write_tsv(
    path: str | Path,
    rows: Sequence[Mapping[str, Any]],
    fieldnames: Sequence[str] | None = None,
) -> None:
    if not rows:
        raise ValueError(f"Refusing to write an empty table: {path}")
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    columns = list(fieldnames or rows[0].keys())
    with open(destination, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=columns, delimiter="\t", extrasaction="ignore"
        )
        writer.writeheader()
        writer.writerows(rows)


def audit_expected_count(ctx: PipelineContext, key: str, actual: int) -> None:
    expected = ctx.get(f"audit.expected_counts.{key}")
    if expected is None:
        return
    message = f"[Audit] {key}: observed={actual:,}; expected={int(expected):,}"
    if actual == int(expected):
        print(message + " [OK]")
        return
    if bool(ctx.get("audit.enforce_expected_counts", False)):
        raise ValueError(message + " [MISMATCH]")
    print("WARNING: " + message + " [MISMATCH]")


def safe_remove_directory(target: Path, allowed_parent: Path) -> None:
    """Remove only an explicitly resolved work directory below output_dir."""
    target = target.resolve()
    allowed_parent = allowed_parent.resolve()
    if target == allowed_parent or allowed_parent not in target.parents:
        raise ValueError(f"Unsafe temporary-directory target: {target}")
    if target.exists():
        shutil.rmtree(target)


# MODULE 0.4: FASTA and embedding archive utilities
def read_fasta(path: str | Path) -> list[tuple[str, str, str]]:
    records: list[tuple[str, str, str]] = []
    description: str | None = None
    chunks: list[str] = []
    with open(path, encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith(">"):
                if description is not None:
                    records.append(
                        (description.split()[0], description, "".join(chunks))
                    )
                description, chunks = line[1:].strip(), []
            else:
                chunks.append(line)
    if description is not None:
        records.append((description.split()[0], description, "".join(chunks)))
    if not records:
        raise ValueError(f"No FASTA records found in {path}")
    identifiers = [record[0] for record in records]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError(f"FASTA identifiers must be unique: {path}")
    return records


def write_fasta(records: Iterable[tuple[str, str, str]], path: str | Path) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with open(destination, "w", encoding="utf-8", newline="\n") as handle:
        for _, description, sequence in records:
            handle.write(f">{description}\n")
            for start in range(0, len(sequence), 80):
                handle.write(sequence[start : start + 80] + "\n")


def save_embeddings(
    path: str | Path,
    labels: Sequence[str],
    sequences: Sequence[str],
    representations: np.ndarray,
) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        destination,
        labels=np.asarray(labels, dtype=str),
        sequences=np.asarray(sequences, dtype=str),
        representations=np.asarray(representations, dtype=np.float32),
    )


def load_embeddings(path: str | Path) -> dict[str, np.ndarray]:
    with np.load(path, allow_pickle=False) as archive:
        required = {"labels", "representations"}
        if not required.issubset(archive.files):
            raise ValueError(f"{path} must contain {sorted(required)}")
        return {key: archive[key] for key in archive.files}


def normalize_rows(matrix: np.ndarray) -> np.ndarray:
    matrix = np.asarray(matrix, dtype=np.float64)
    if matrix.ndim != 2:
        raise ValueError("Embedding matrix must be 2-D")
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    if np.any(~np.isfinite(matrix)) or np.any(norms == 0):
        raise ValueError("Embedding matrix must be finite and contain no zero vectors")
    return matrix / norms


def percentile_ranks(values: Sequence[float]) -> np.ndarray:
    """Average-tie percentile rank on (0, 1], higher input = higher rank."""
    values = np.asarray(values, dtype=float)
    if not np.all(np.isfinite(values)):
        raise ValueError("Scores contain missing or non-finite values")
    order = np.argsort(values, kind="mergesort")
    ranks = np.empty(values.size, dtype=float)
    sorted_values = values[order]
    start = 0
    while start < values.size:
        end = start + 1
        while end < values.size and sorted_values[end] == sorted_values[start]:
            end += 1
        ranks[order[start:end]] = ((start + 1 + end) / 2.0) / values.size
        start = end
    return ranks


# =============================================================================
# Step 1: Natural language-based preliminary screening with ProTrek
# =============================================================================
#
# Workflow:
# - encode the NADK functional description with the official ProTrek model;
# - retrieve sequence embeddings from a versioned FAISS index, or directly score
#   a smaller versioned FASTA;
# - retain the prespecified top-N/threshold candidates;
# - export the per-sequence ProTrek score called "machine score" in Fig. 3.
#
# =============================================================================


# MODULE 1.1: Official ProTrek model loading
def load_protrek_model(ctx: PipelineContext):
    torch = require("torch", "ProTrek inference")
    repository_root = ctx.path("protrek.repository_root")
    if not repository_root.is_dir():
        raise FileNotFoundError(f"ProTrek repository not found: {repository_root}")
    sys.path.insert(0, str(repository_root))
    try:
        module = __import__(
            "model.ProTrek.protrek_trimodal_model",
            fromlist=["ProTrekTrimodalModel"],
        )
    except ImportError as exc:
        raise SystemExit(
            "Cannot import the official ProTrek model. Verify repository_root "
            "and install the official repository dependencies."
        ) from exc
    model_config = {
        "protein_config": str(ctx.path("protrek.protein_config")),
        "text_config": str(ctx.path("protrek.text_config")),
        "structure_config": str(ctx.path("protrek.structure_config")),
        "from_checkpoint": str(ctx.path("protrek.checkpoint")),
    }
    model = module.ProTrekTrimodalModel(**model_config)
    device = str(ctx.get("protrek.device", "cuda:0"))
    model = model.eval().to(device)
    return torch, model


# MODULE 1.2A: Scalable FAISS retrieval from an official-format index
def run_module_1_2_faiss_retrieval(ctx: PipelineContext) -> list[dict[str, Any]]:
    faiss = require("faiss", "ProTrek FAISS retrieval")
    torch, model = load_protrek_model(ctx)
    index_dir = ctx.path("protrek.faiss_index_dir")
    index_path = index_dir / "sequence.index"
    ids_path = index_dir / "ids.tsv"
    if not index_path.is_file() or not ids_path.is_file():
        raise FileNotFoundError(
            f"Expected official-format sequence.index and ids.tsv in {index_dir}"
        )
    top_n = int(ctx.get("protrek.selection.top_n", required=True))
    index = faiss.read_index(str(index_path))
    if int(index.metric_type) != int(faiss.METRIC_INNER_PRODUCT):
        raise ValueError("The ProTrek sequence index must use inner-product similarity")
    if top_n > int(index.ntotal):
        raise ValueError(f"top_n={top_n} exceeds FAISS index size={index.ntotal}")
    nprobe = int(ctx.get("protrek.faiss_nprobe", 2048))
    if hasattr(index, "nprobe"):
        index.nprobe = min(nprobe, int(getattr(index, "nlist", nprobe)))
    prompt = str(ctx.get("protrek.prompt", required=True))
    with torch.inference_mode():
        text_embedding = model.get_text_repr([prompt]).detach().cpu().numpy()
    if text_embedding.shape != (1, int(index.d)) or np.any(
        ~np.isfinite(text_embedding)
    ):
        raise ValueError(
            "ProTrek text embedding is non-finite or incompatible with the FAISS index"
        )
    distances, indices = index.search(text_embedding.astype(np.float32), top_n)
    retrieved_indices = indices[0].astype(int)
    raw_scores = distances[0].astype(float)
    if np.any(retrieved_indices < 0):
        raise ValueError(
            "FAISS returned invalid indices; check index/search parameters"
        )
    model_temperature = model.temperature
    temperature = float(
        model_temperature.detach().cpu().item()
        if hasattr(model_temperature, "detach")
        else model_temperature
    )
    if not math.isfinite(temperature) or temperature <= 0:
        raise ValueError(f"Invalid ProTrek temperature: {temperature}")
    selected = {
        int(index_value): (rank + 1, float(raw_score), float(raw_score / temperature))
        for rank, (index_value, raw_score) in enumerate(
            zip(retrieved_indices, raw_scores)
        )
    }
    records_by_rank: dict[int, dict[str, Any]] = {}
    with open(ids_path, encoding="utf-8") as handle:
        for line_index, line in enumerate(handle):
            if line_index not in selected:
                continue
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 2:
                raise ValueError(f"Malformed ids.tsv line {line_index + 1}")
            rank, inner_product, machine_score = selected[line_index]
            records_by_rank[rank] = {
                "Sequence_ID": parts[0],
                "Sequence": parts[1],
                "Length": int(parts[2]) if len(parts) > 2 else len(parts[1]),
                "ProTrek_Inner_Product": inner_product,
                "Machine_Score": machine_score,
                "Retrieval_Rank": rank,
            }
    if len(records_by_rank) != top_n:
        raise ValueError(
            f"Retrieved {top_n} FAISS indices but resolved {len(records_by_rank)} ids.tsv rows"
        )
    return [records_by_rank[rank] for rank in range(1, top_n + 1)]


# MODULE 1.2B: Direct scoring mode for smaller/custom FASTA databases
def run_module_1_2_direct_fasta_scoring(ctx: PipelineContext) -> list[dict[str, Any]]:
    torch, model = load_protrek_model(ctx)
    records = read_fasta(ctx.path("inputs.sequence_database_fasta"))
    prompt = str(ctx.get("protrek.prompt", required=True))
    batch_size = int(ctx.get("protrek.batch_size", 8))
    maximum_length = int(ctx.get("protrek.maximum_sequence_length", 2048))
    if batch_size < 1 or maximum_length < 1:
        raise ValueError(
            "ProTrek batch size and maximum sequence length must be positive"
        )
    with torch.inference_mode():
        text_embedding = model.get_text_repr([prompt])
        rows: list[dict[str, Any]] = []
        for start in range(0, len(records), batch_size):
            batch = records[start : start + batch_size]
            if any(len(record[2]) > maximum_length for record in batch):
                offenders = [
                    record[0] for record in batch if len(record[2]) > maximum_length
                ]
                raise ValueError(
                    f"Sequences exceed ProTrek length limit {maximum_length}: {offenders[:5]}"
                )
            sequence_embedding = model.get_protein_repr([record[2] for record in batch])
            scores = (
                (sequence_embedding @ text_embedding.T / model.temperature)
                .squeeze(1)
                .detach()
                .cpu()
                .numpy()
            )
            for record, score in zip(batch, scores):
                rows.append(
                    {
                        "Sequence_ID": record[0],
                        "Sequence": record[2],
                        "Length": len(record[2]),
                        "ProTrek_Inner_Product": "",
                        "Machine_Score": float(score),
                    }
                )
    rows.sort(key=lambda row: (-float(row["Machine_Score"]), row["Sequence_ID"]))
    for rank, row in enumerate(rows, start=1):
        row["Retrieval_Rank"] = rank
    return rows


# MODULE 1.3: Prespecified preliminary-library selection and export
def run_step_1(ctx: PipelineContext) -> Path:
    print("\n[Step 1] ProTrek natural-language preliminary screening")
    retrieval_mode = str(ctx.get("protrek.retrieval_mode", "faiss_index"))
    if retrieval_mode == "faiss_index":
        ranked_rows = run_module_1_2_faiss_retrieval(ctx)
        input_paths = [
            ctx.path("protrek.faiss_index_dir") / "sequence.index",
            ctx.path("protrek.faiss_index_dir") / "ids.tsv",
        ]
    elif retrieval_mode == "direct_fasta":
        ranked_rows = run_module_1_2_direct_fasta_scoring(ctx)
        input_paths = [ctx.path("inputs.sequence_database_fasta")]
    else:
        raise ValueError("protrek.retrieval_mode must be faiss_index or direct_fasta")

    selection_mode = str(ctx.get("protrek.selection.mode", "top_n"))
    if selection_mode == "top_n":
        top_n = int(ctx.get("protrek.selection.top_n", required=True))
        if top_n > len(ranked_rows):
            raise ValueError(
                f"Requested top_n={top_n:,}, but only {len(ranked_rows):,} sequences were scored"
            )
        selected = ranked_rows[:top_n]
    elif selection_mode == "score_threshold":
        threshold = float(ctx.get("protrek.selection.score_threshold", required=True))
        selected = [
            row for row in ranked_rows if float(row["Machine_Score"]) >= threshold
        ]
    else:
        raise ValueError("protrek.selection.mode must be top_n or score_threshold")
    if not selected:
        raise ValueError("ProTrek selection produced zero candidates")
    scores_path = ctx.output("step1_protrek_scores.tsv")
    fasta_path = ctx.output("step1_candidates.fasta")
    write_tsv(scores_path, selected)
    write_fasta(
        ((row["Sequence_ID"], row["Sequence_ID"], row["Sequence"]) for row in selected),
        fasta_path,
    )
    audit_expected_count(ctx, "step1_candidates", len(selected))
    write_manifest(
        ctx,
        "step1_protrek",
        {
            "retrieval_mode": retrieval_mode,
            "prompt": ctx.get("protrek.prompt"),
            "selection": ctx.get("protrek.selection"),
            "faiss_nprobe": ctx.get("protrek.faiss_nprobe"),
        },
        input_paths,
        [scores_path, fasta_path],
        {"selected_candidates": len(selected)},
    )
    print(f"-> Exported {len(selected):,} preliminary candidates")
    return fasta_path


# =============================================================================
# Step 2: Sequence clustering and redundancy removal with MMseqs2
# =============================================================================
#
# MMseqs2 clustering is executed with explicit identity, coverage, coverage-mode
# and thread settings. Representative sequences retain their ProTrek scores.
#
# =============================================================================


# MODULE 2.1: Full-library clustering
def run_module_2_1_cluster(ctx: PipelineContext, db_path: Path) -> Path:
    executable_name = str(ctx.get("mmseqs.executable", "mmseqs"))
    executable = shutil.which(executable_name)
    if not executable:
        raise SystemExit(f"MMseqs2 executable not found: {executable_name}")
    output_prefix = ctx.output("step2_clustered")
    temporary_dir = ctx.output("work_mmseqs_tmp")
    temporary_dir.mkdir(parents=True, exist_ok=True)
    command = [
        executable,
        "easy-cluster",
        str(db_path),
        str(output_prefix),
        str(temporary_dir),
        "--min-seq-id",
        str(float(ctx.get("mmseqs.minimum_sequence_identity", required=True))),
        "-c",
        str(float(ctx.get("mmseqs.alignment_coverage", required=True))),
        "--cov-mode",
        str(int(ctx.get("mmseqs.coverage_mode", required=True))),
        "--threads",
        str(int(ctx.get("mmseqs.threads", max(1, os.cpu_count() or 1)))),
    ]
    print("[Module 2.1] " + " ".join(command))
    subprocess.run(command, check=True)
    representative_fasta = Path(str(output_prefix) + "_rep_seq.fasta")
    if not representative_fasta.is_file():
        raise FileNotFoundError(
            f"MMseqs2 representative FASTA missing: {representative_fasta}"
        )
    if bool(ctx.get("mmseqs.remove_temporary_directory", True)):
        safe_remove_directory(temporary_dir, ctx.output_dir)
    return representative_fasta


# MODULE 2.2: Representative-sequence finalization and score propagation
def run_module_2_2_finalize(ctx: PipelineContext, representative_fasta: Path) -> Path:
    records = read_fasta(representative_fasta)
    final_fasta = ctx.output("step2_final_nonredundant.fasta")
    write_fasta(records, final_fasta)
    step1_scores = {
        row["Sequence_ID"]: row
        for row in read_tsv(ctx.output("step1_protrek_scores.tsv"))
    }
    missing = [record[0] for record in records if record[0] not in step1_scores]
    if missing:
        raise ValueError(f"Representative IDs missing ProTrek scores: {missing[:5]}")
    representative_scores = [step1_scores[record[0]] for record in records]
    representative_scores.sort(
        key=lambda row: (-float(row["Machine_Score"]), row["Sequence_ID"])
    )
    write_tsv(ctx.output("step2_representative_scores.tsv"), representative_scores)
    print(f"[Module 2.2] Finalized {len(records):,} non-redundant representatives")
    return final_fasta


def run_step_2(ctx: PipelineContext) -> Path:
    print("\n[Step 2] MMseqs2 clustering and redundancy removal")
    input_fasta = ctx.output("step1_candidates.fasta")
    representative_fasta = run_module_2_1_cluster(ctx, input_fasta)
    final_fasta = run_module_2_2_finalize(ctx, representative_fasta)
    count = len(read_fasta(final_fasta))
    audit_expected_count(ctx, "step2_representatives", count)
    outputs = [
        final_fasta,
        ctx.output("step2_representative_scores.tsv"),
    ]
    for suffix in ("_cluster.tsv", "_all_seqs.fasta", "_rep_seq.fasta"):
        candidate = Path(str(ctx.output("step2_clustered")) + suffix)
        if candidate.is_file():
            outputs.append(candidate)
    write_manifest(
        ctx,
        "step2_mmseqs",
        ctx.get("mmseqs", {}),
        [input_fasta, ctx.output("step1_protrek_scores.tsv")],
        outputs,
        {"representatives": count},
    )
    return final_fasta


# =============================================================================
# Step 3: ProstT5 structural embedding and individual-anchor scoring
# =============================================================================
#
# Functional proximity is the maximum cosine similarity between each candidate
# embedding and the individual verified NADK-anchor embeddings.
#
# =============================================================================


# MODULE 3.1: Sequence sanitization
def sanitize_sequence(sequence: str) -> str:
    sequence = re.sub(r"[\s*.-]", "", sequence.upper())
    sequence = re.sub(r"[UZOB]", "X", sequence)
    invalid = sorted(set(sequence) - STANDARD_AMINO_ACIDS)
    if invalid:
        raise ValueError(f"Unsupported amino-acid symbols: {invalid}")
    if not sequence:
        raise ValueError("Empty sequence after sanitization")
    return sequence


def preprocess_for_embedding(
    ctx: PipelineContext, input_fasta: Path, output_fasta: Path
) -> list[tuple[str, str, str]]:
    maximum_length = int(ctx.get("prostt5.maximum_sequence_length", 1000))
    long_policy = str(ctx.get("prostt5.long_sequence_policy", "error"))
    if maximum_length < 1:
        raise ValueError("prostt5.maximum_sequence_length must be positive")
    if long_policy not in {"error", "skip"}:
        raise ValueError("prostt5.long_sequence_policy must be error or skip")
    cleaned: list[tuple[str, str, str]] = []
    qc_rows: list[dict[str, Any]] = []
    for identifier, description, sequence in read_fasta(input_fasta):
        clean_sequence = sanitize_sequence(sequence)
        status = "accepted"
        reason = ""
        if len(clean_sequence) > maximum_length:
            status = "excluded"
            reason = f"length>{maximum_length}"
            if long_policy == "error":
                raise ValueError(
                    f"{identifier} has {len(clean_sequence)} residues; "
                    f"configured ProstT5 limit is {maximum_length}"
                )
        qc_rows.append(
            {
                "Sequence_ID": identifier,
                "Original_Length": len(sequence),
                "Sanitized_Length": len(clean_sequence),
                "QC_Status": status,
                "QC_Reason": reason,
            }
        )
        if status == "accepted":
            cleaned.append((identifier, description, clean_sequence))
    if not cleaned:
        raise ValueError("No sequences passed ProstT5 preprocessing")
    write_fasta(cleaned, output_fasta)
    write_tsv(output_fasta.with_suffix(".qc.tsv"), qc_rows)
    return cleaned


# MODULE 3.2: Batched ProstT5 structural-embedding generation
def run_module_3_2_inference(
    ctx: PipelineContext,
    input_fasta: Path,
    output_npz: Path,
    sanitized_fasta: Path,
) -> Path:
    torch = require("torch", "ProstT5 embedding")
    transformers = require("transformers", "ProstT5 embedding")
    records = preprocess_for_embedding(ctx, input_fasta, sanitized_fasta)
    model_path = str(ctx.path("prostt5.model_path"))
    tokenizer = transformers.T5Tokenizer.from_pretrained(
        model_path, do_lower_case=False
    )
    model = transformers.T5EncoderModel.from_pretrained(model_path)
    device = torch.device(str(ctx.get("prostt5.device", "cuda:0")))
    model = model.to(device)
    if bool(ctx.get("prostt5.use_half_precision", True)) and device.type == "cuda":
        model = model.half()
    else:
        model = model.float()
    model.eval()
    batch_size = int(ctx.get("prostt5.batch_size", 8))
    if batch_size < 1:
        raise ValueError("prostt5.batch_size must be positive")
    representations: list[np.ndarray] = []
    for start in range(0, len(records), batch_size):
        batch = records[start : start + batch_size]
        model_inputs = ["<AA2fold> " + " ".join(record[2]) for record in batch]
        encoded = tokenizer.batch_encode_plus(
            model_inputs,
            add_special_tokens=True,
            padding="longest",
            return_tensors="pt",
        )
        input_ids = encoded.input_ids.to(device)
        attention_mask = encoded.attention_mask.to(device)
        with torch.inference_mode():
            hidden = model(
                input_ids=input_ids, attention_mask=attention_mask
            ).last_hidden_state
        for index, record in enumerate(batch):
            sequence_length = len(record[2])
            non_padding_tokens = int(attention_mask[index].sum().item())
            expected_tokens = sequence_length + 2  # prefix + residues + EOS
            if non_padding_tokens != expected_tokens:
                raise ValueError(
                    f"Unexpected ProstT5 tokenization for {record[0]}: "
                    f"observed {non_padding_tokens}, expected {expected_tokens}"
                )
            # Position 0 is the <AA2fold> control token.  EOS and padding are
            # excluded; positions 1..sequence_length correspond to residues.
            embedding = hidden[index, 1 : sequence_length + 1].float().mean(dim=0)
            representations.append(embedding.detach().cpu().numpy())
        print(
            f"[Module 3.2] Embedded {min(start + batch_size, len(records)):,}/{len(records):,}"
        )
    save_embeddings(
        output_npz,
        [record[0] for record in records],
        [record[2] for record in records],
        np.vstack(representations),
    )
    return output_npz


# MODULE 3.3: Maximum cosine similarity to individual verified anchors
def maximum_anchor_similarity(
    candidate_matrix: np.ndarray,
    anchor_matrix: np.ndarray,
    batch_size: int = 8192,
) -> tuple[np.ndarray, np.ndarray]:
    candidates = normalize_rows(candidate_matrix)
    anchors = normalize_rows(anchor_matrix)
    maxima: list[np.ndarray] = []
    best_anchor: list[np.ndarray] = []
    for start in range(0, candidates.shape[0], batch_size):
        block = candidates[start : start + batch_size] @ anchors.T
        maxima.append(np.max(block, axis=1))
        best_anchor.append(np.argmax(block, axis=1))
    return np.concatenate(maxima), np.concatenate(best_anchor)


def select_core_subset_by_similarity(
    ctx: PipelineContext, candidate_npz: Path, anchor_npz: Path
) -> Path:
    candidates = load_embeddings(candidate_npz)
    anchors = load_embeddings(anchor_npz)
    expected_anchor_ids = [
        str(value) for value in ctx.get("inputs.expected_anchor_ids", [])
    ]
    actual_anchor_ids = anchors["labels"].astype(str).tolist()
    if expected_anchor_ids and actual_anchor_ids != expected_anchor_ids:
        raise ValueError(
            "Anchor order/identity mismatch. Expected "
            f"{expected_anchor_ids}, observed {actual_anchor_ids}"
        )
    similarities, best_indices = maximum_anchor_similarity(
        candidates["representations"],
        anchors["representations"],
        int(ctx.get("core_selection.similarity_batch_size", 8192)),
    )
    selection_mode = str(ctx.get("core_selection.mode", "top_n"))
    if selection_mode == "top_n":
        keep_count = int(ctx.get("core_selection.top_n", required=True))
    elif selection_mode == "fraction":
        fraction = float(ctx.get("core_selection.fraction", 0.25))
        keep_count = int(math.ceil(len(similarities) * fraction))
    else:
        raise ValueError("core_selection.mode must be top_n or fraction")
    if keep_count < 1 or keep_count > len(similarities):
        raise ValueError("Invalid core-subset size")
    labels = candidates["labels"].astype(str)
    anchor_labels = anchors["labels"].astype(str)
    order = np.lexsort((labels, -similarities))[:keep_count]
    protrek_scores = {
        row["Sequence_ID"]: float(row["Machine_Score"])
        for row in read_tsv(ctx.output("step2_representative_scores.tsv"))
    }
    rows = []
    for rank, index in enumerate(order, start=1):
        identifier = str(labels[index])
        if identifier not in protrek_scores:
            raise ValueError(f"Missing ProTrek score for {identifier}")
        rows.append(
            {
                "Sequence_ID": identifier,
                "Maximum_Anchor_Cosine": float(similarities[index]),
                "Best_Anchor_ID": str(anchor_labels[best_indices[index]]),
                "Structural_Similarity_Rank": rank,
                "Machine_Score": protrek_scores[identifier],
            }
        )
    output = ctx.output("step3_core_subset.tsv")
    write_tsv(output, rows)
    return output


def run_step_3(ctx: PipelineContext) -> Path:
    print("\n[Step 3] ProstT5 embedding and individual-anchor similarity")
    candidate_npz = run_module_3_2_inference(
        ctx,
        ctx.output("step2_final_nonredundant.fasta"),
        ctx.output("step3_candidate_embeddings.npz"),
        ctx.output("step3_candidates_sanitized.fasta"),
    )
    anchor_npz = run_module_3_2_inference(
        ctx,
        ctx.path("inputs.verified_anchor_fasta"),
        ctx.output("step3_anchor_embeddings.npz"),
        ctx.output("step3_anchors_sanitized.fasta"),
    )
    core_path = select_core_subset_by_similarity(ctx, candidate_npz, anchor_npz)
    core_count = len(read_tsv(core_path))
    audit_expected_count(ctx, "step3_core_subset", core_count)
    write_manifest(
        ctx,
        "step3_prostt5_anchor",
        {
            "prostt5": ctx.get("prostt5"),
            "core_selection": ctx.get("core_selection"),
            "similarity_definition": "maximum cosine over individual verified anchors",
        },
        [
            ctx.output("step2_final_nonredundant.fasta"),
            ctx.path("inputs.verified_anchor_fasta"),
            ctx.output("step2_representative_scores.tsv"),
        ],
        [candidate_npz, anchor_npz, core_path],
        {
            "candidate_embeddings": len(load_embeddings(candidate_npz)["labels"]),
            "anchors": len(load_embeddings(anchor_npz)["labels"]),
            "core_candidates": core_count,
        },
    )
    print(f"-> Retained {core_count:,} core candidates")
    return core_path


# =============================================================================
# Step 4: Background-fitted UMAP and dynamic spatial density clustering
# =============================================================================
#
# The StandardScaler and UMAP reducer are fitted exclusively on the EC
# background embeddings. Candidates and anchors are transformed into this
# fixed coordinate system. HDBSCAN is fitted to core candidates only. Its
# non-noise density clusters define the active regions; projected anchors are
# annotated with the cluster of their nearest non-noise candidate.
#
# =============================================================================


# MODULE 4.1: Background embedding preparation and unbiased projection
def prepare_background_embeddings(ctx: PipelineContext) -> Path:
    configured_npz = ctx.path("inputs.ec_background_embedding_npz", required=False)
    if configured_npz is not None and configured_npz.is_file():
        return configured_npz
    background_fasta = ctx.path("inputs.ec_background_fasta", required=False)
    if background_fasta is None or not background_fasta.is_file():
        raise FileNotFoundError(
            "Provide inputs.ec_background_embedding_npz or inputs.ec_background_fasta"
        )
    return run_module_3_2_inference(
        ctx,
        background_fasta,
        ctx.output("step4_ec_background_embeddings.npz"),
        ctx.output("step4_ec_background_sanitized.fasta"),
    )


def subset_embedding_rows(
    archive: Mapping[str, np.ndarray], selected_ids: set[str]
) -> tuple[np.ndarray, np.ndarray]:
    labels = archive["labels"].astype(str)
    mask = np.asarray([label in selected_ids for label in labels], dtype=bool)
    found = set(labels[mask])
    if found != selected_ids:
        raise ValueError(
            f"Embedding archive missing IDs: {sorted(selected_ids - found)[:5]}"
        )
    return labels[mask], archive["representations"][mask]


def project_to_stable_functional_landscape(
    ctx: PipelineContext,
    background_matrix: np.ndarray,
    candidate_matrix: np.ndarray,
    anchor_matrix: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    preprocessing = require("sklearn.preprocessing", "background standardization")
    umap_module = require("umap", "UMAP projection")
    joblib = require("joblib", "model serialization")
    matrices = {
        "background": np.asarray(background_matrix),
        "candidate": np.asarray(candidate_matrix),
        "anchor": np.asarray(anchor_matrix),
    }
    dimensions = set()
    for name, matrix in matrices.items():
        if matrix.ndim != 2 or matrix.shape[0] == 0:
            raise ValueError(f"{name} embedding matrix must be non-empty and 2-D")
        if np.any(~np.isfinite(matrix)):
            raise ValueError(f"{name} embedding matrix contains non-finite values")
        dimensions.add(matrix.shape[1])
    if len(dimensions) != 1:
        raise ValueError(f"Embedding dimensions do not match: {sorted(dimensions)}")
    scaler = preprocessing.StandardScaler().fit(background_matrix)
    background_scaled = scaler.transform(background_matrix)
    candidate_scaled = scaler.transform(candidate_matrix)
    anchor_scaled = scaler.transform(anchor_matrix)
    reducer = umap_module.UMAP(
        n_neighbors=int(ctx.get("landscape.umap_n_neighbors", 15)),
        min_dist=float(ctx.get("landscape.umap_min_dist", 0.1)),
        metric=str(ctx.get("landscape.umap_metric", "euclidean")),
        random_state=ctx.seed,
        transform_seed=ctx.seed,
    )
    reducer.fit(background_scaled)
    candidate_coordinates = reducer.transform(candidate_scaled)
    anchor_coordinates = reducer.transform(anchor_scaled)
    joblib.dump(scaler, ctx.output("step4_background_scaler.joblib"))
    joblib.dump(reducer, ctx.output("step4_background_fitted_umap.joblib"))
    return candidate_coordinates, anchor_coordinates


# MODULE 4.2: Dynamic candidate clustering and density-defined active regions
def infer_active_clusters(
    candidate_labels: Sequence[int],
    candidate_coordinates: np.ndarray,
    anchor_coordinates: np.ndarray,
) -> tuple[list[int], list[int], list[float]]:
    labels = np.asarray(candidate_labels, dtype=int)
    candidates = np.asarray(candidate_coordinates, dtype=float)
    anchors = np.asarray(anchor_coordinates, dtype=float)
    non_noise = np.flatnonzero(labels >= 0)
    if non_noise.size == 0:
        raise ValueError("HDBSCAN found no non-noise candidate cluster")
    active_clusters = sorted(set(labels[non_noise].tolist()))
    assignments: list[int] = []
    distances: list[float] = []
    for anchor in anchors:
        squared = np.sum((candidates[non_noise] - anchor) ** 2, axis=1)
        nearest_position = int(np.argmin(squared))
        candidate_index = int(non_noise[nearest_position])
        assignments.append(int(labels[candidate_index]))
        distances.append(float(math.sqrt(squared[nearest_position])))
    return active_clusters, assignments, distances


def characterization_spatial_clusters(
    ctx: PipelineContext,
    candidate_labels: np.ndarray,
    candidate_coordinates: np.ndarray,
    anchor_labels: np.ndarray,
    anchor_coordinates: np.ndarray,
) -> tuple[Path, list[int]]:
    hdbscan_module = require("hdbscan", "spatial density clustering")
    mode = str(ctx.get("landscape.hdbscan_min_cluster_size_mode", "dynamic_fraction"))
    if mode == "dynamic_fraction":
        fraction = float(ctx.get("landscape.hdbscan_min_cluster_size_fraction", 0.01))
        minimum = int(ctx.get("landscape.hdbscan_min_cluster_size_minimum", 10))
        minimum_cluster_size = max(
            minimum, int(math.ceil(len(candidate_labels) * fraction))
        )
    elif mode == "fixed":
        minimum_cluster_size = int(ctx.get("landscape.hdbscan_min_cluster_size", 50))
    else:
        raise ValueError("Unknown HDBSCAN min-cluster-size mode")
    configured_min_samples = ctx.get("landscape.hdbscan_min_samples")
    min_samples = (
        None if configured_min_samples is None else int(configured_min_samples)
    )
    clusterer = hdbscan_module.HDBSCAN(
        min_cluster_size=minimum_cluster_size,
        min_samples=min_samples,
        cluster_selection_method=str(
            ctx.get("landscape.hdbscan_cluster_selection_method", "eom")
        ),
    )
    cluster_labels = clusterer.fit_predict(candidate_coordinates)
    probabilities = getattr(clusterer, "probabilities_", np.ones(len(cluster_labels)))
    active_clusters, assignments, anchor_distances = infer_active_clusters(
        cluster_labels, candidate_coordinates, anchor_coordinates
    )
    rows: list[dict[str, Any]] = []
    for identifier, coordinate, cluster, probability in zip(
        candidate_labels, candidate_coordinates, cluster_labels, probabilities
    ):
        rows.append(
            {
                "Sequence_ID": str(identifier),
                "Source": "Candidate",
                "UMAP_1": float(coordinate[0]),
                "UMAP_2": float(coordinate[1]),
                "Cluster_ID": int(cluster),
                "Cluster_Probability": float(probability),
                "Active_Region": int(int(cluster) in active_clusters),
                "Nearest_Candidate_Distance": "",
            }
        )
    for identifier, coordinate, cluster, distance in zip(
        anchor_labels, anchor_coordinates, assignments, anchor_distances
    ):
        rows.append(
            {
                "Sequence_ID": str(identifier),
                "Source": "Verified_Anchor",
                "UMAP_1": float(coordinate[0]),
                "UMAP_2": float(coordinate[1]),
                "Cluster_ID": int(cluster),
                "Cluster_Probability": "",
                "Active_Region": 1,
                "Nearest_Candidate_Distance": distance,
            }
        )
    output = ctx.output("step4_functional_landscape.tsv")
    write_tsv(output, rows)
    ctx.output("step4_active_clusters.json").write_text(
        json.dumps(
            {
                "active_clusters": active_clusters,
                "anchor_assignments": {
                    str(identifier): int(cluster)
                    for identifier, cluster in zip(anchor_labels, assignments)
                },
                "hdbscan_min_cluster_size": minimum_cluster_size,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return output, active_clusters


def run_step_4(ctx: PipelineContext) -> Path:
    print("\n[Step 4] Background-fitted UMAP and spatial density clustering")
    candidate_archive = load_embeddings(ctx.output("step3_candidate_embeddings.npz"))
    anchor_archive = load_embeddings(ctx.output("step3_anchor_embeddings.npz"))
    core_ids = {
        row["Sequence_ID"] for row in read_tsv(ctx.output("step3_core_subset.tsv"))
    }
    candidate_labels, candidate_matrix = subset_embedding_rows(
        candidate_archive, core_ids
    )
    background_path = prepare_background_embeddings(ctx)
    background_archive = load_embeddings(background_path)
    candidate_xy, anchor_xy = project_to_stable_functional_landscape(
        ctx,
        background_archive["representations"],
        candidate_matrix,
        anchor_archive["representations"],
    )
    output, active_clusters = characterization_spatial_clusters(
        ctx,
        candidate_labels,
        candidate_xy,
        anchor_archive["labels"].astype(str),
        anchor_xy,
    )
    landscape_rows = read_tsv(output)
    active_count = sum(
        row["Source"] == "Candidate" and row["Active_Region"] == "1"
        for row in landscape_rows
    )
    write_manifest(
        ctx,
        "step4_landscape",
        ctx.get("landscape", {}),
        [
            ctx.output("step3_candidate_embeddings.npz"),
            ctx.output("step3_anchor_embeddings.npz"),
            ctx.output("step3_core_subset.tsv"),
            background_path,
        ],
        [
            output,
            ctx.output("step4_active_clusters.json"),
            ctx.output("step4_background_scaler.joblib"),
            ctx.output("step4_background_fitted_umap.joblib"),
        ],
        {
            "core_candidates": len(candidate_labels),
            "background_sequences": len(background_archive["labels"]),
            "active_clusters": len(active_clusters),
            "active_region_candidates": active_count,
        },
    )
    print(
        f"-> Active clusters: {active_clusters}; eligible candidates: {active_count:,}"
    )
    return output


# =============================================================================
# Step 5: Functional-score ranking and final 642-candidate library
# =============================================================================
#
# Figure 3 defines the machine score as the PLM-derived functional score.  The
# final candidates are therefore ranked primarily by the ProTrek machine score
# within the density-defined active regions. Maximum anchor cosine is retained as
# a deterministic tie-breaker and an auditable secondary field.
#
# =============================================================================


# MODULE 5.1: Extract and rank candidates from active regions
def rank_final_candidates(
    eligible_rows: Sequence[Mapping[str, Any]], target_size: int
) -> list[dict[str, Any]]:
    if len(eligible_rows) < target_size:
        raise ValueError(
            f"Only {len(eligible_rows)} active-region candidates; cannot select {target_size}"
        )
    ranked = [dict(row) for row in eligible_rows]
    ranked.sort(
        key=lambda row: (
            -float(row["Machine_Score"]),
            -float(row["Maximum_Anchor_Cosine"]),
            str(row["Sequence_ID"]),
        )
    )
    selected = ranked[:target_size]
    for rank, row in enumerate(selected, start=1):
        row["Final_Rank"] = rank
    return selected


def run_step_5(ctx: PipelineContext) -> Path:
    print("\n[Step 5] Final machine-score ranking and target-library extraction")
    landscape = {
        row["Sequence_ID"]: row
        for row in read_tsv(ctx.output("step4_functional_landscape.tsv"))
        if row["Source"] == "Candidate"
    }
    core_rows = read_tsv(ctx.output("step3_core_subset.tsv"))
    eligible = []
    for row in core_rows:
        landscape_row = landscape.get(row["Sequence_ID"])
        if landscape_row and landscape_row["Active_Region"] == "1":
            eligible.append(
                {
                    "Sequence_ID": row["Sequence_ID"],
                    "Machine_Score": float(row["Machine_Score"]),
                    "Maximum_Anchor_Cosine": float(row["Maximum_Anchor_Cosine"]),
                    "Best_Anchor_ID": row["Best_Anchor_ID"],
                    "Cluster_ID": int(landscape_row["Cluster_ID"]),
                    "UMAP_1": float(landscape_row["UMAP_1"]),
                    "UMAP_2": float(landscape_row["UMAP_2"]),
                }
            )
    target_size = int(ctx.get("final_selection.target_size", 642))
    selected = rank_final_candidates(eligible, target_size)
    output_tsv = ctx.output("step5_final_candidates.tsv")
    output_fasta = ctx.output("step5_final_candidates.fasta")
    write_tsv(output_tsv, selected)
    source_records = {
        record[0]: record
        for record in read_fasta(ctx.output("step2_final_nonredundant.fasta"))
    }
    missing = [
        row["Sequence_ID"]
        for row in selected
        if row["Sequence_ID"] not in source_records
    ]
    if missing:
        raise ValueError(
            f"Selected IDs missing from representative FASTA: {missing[:5]}"
        )
    write_fasta((source_records[row["Sequence_ID"]] for row in selected), output_fasta)
    audit_expected_count(ctx, "step5_final_library", len(selected))
    expected_top = ctx.get("audit.expected_top_candidate")
    if expected_top and selected[0]["Sequence_ID"] != expected_top:
        message = (
            f"Top candidate is {selected[0]['Sequence_ID']}, expected {expected_top}. "
            "Check database/model/config versions."
        )
        if bool(ctx.get("audit.enforce_expected_counts", False)):
            raise ValueError(message)
        print("WARNING: " + message)
    write_manifest(
        ctx,
        "step5_final_library",
        {
            "target_size": target_size,
            "primary_rank": "Machine_Score (ProTrek sequence-text score)",
            "tie_breaker": "Maximum_Anchor_Cosine, then Sequence_ID",
        },
        [
            ctx.output("step4_functional_landscape.tsv"),
            ctx.output("step3_core_subset.tsv"),
            ctx.output("step2_final_nonredundant.fasta"),
        ],
        [output_tsv, output_fasta],
        {"eligible_active_region": len(eligible), "final_library": len(selected)},
    )
    print(f"-> Exported final library of {len(selected):,} candidates")
    return output_tsv


# =============================================================================
# Step 6: Optional performance-gated feedback for a subsequent LSBT cycle
# =============================================================================
#
# The reported NADK screen completed one LSBT cycle. Accordingly,
# feedback.enabled is false in the study configuration. The conditional branch
# is available for a prospectively specified subsequent cycle.
#
# =============================================================================


# MODULE 6.1: Frozen ProTrek embeddings for the proposed feedback operation
def prepare_feedback_protrek_embeddings(ctx: PipelineContext) -> Path:
    configured_npz = ctx.path("feedback.protrek_sequence_embedding_npz", required=False)
    if configured_npz is not None:
        if not configured_npz.is_file():
            raise FileNotFoundError(
                f"Configured feedback ProTrek embedding archive not found: {configured_npz}"
            )
        load_embeddings(configured_npz)
        return configured_npz
    torch, model = load_protrek_model(ctx)
    records = read_fasta(ctx.output("step2_final_nonredundant.fasta"))
    batch_size = int(ctx.get("feedback.embedding_batch_size", 8))
    maximum_length = int(ctx.get("feedback.maximum_sequence_length", 2048))
    if batch_size < 1 or maximum_length < 1:
        raise ValueError(
            "Feedback embedding batch size and maximum length must be positive"
        )
    representations: list[np.ndarray] = []
    with torch.inference_mode():
        for start in range(0, len(records), batch_size):
            batch = records[start : start + batch_size]
            offenders = [
                record[0] for record in batch if len(record[2]) > maximum_length
            ]
            if offenders:
                raise ValueError(
                    f"Sequences exceed the configured ProTrek limit {maximum_length}: "
                    f"{offenders[:5]}"
                )
            embedding = model.get_protein_repr([record[2] for record in batch])
            representations.append(embedding.float().detach().cpu().numpy())
        output = ctx.output("step6_protrek_sequence_embeddings.npz")
        save_embeddings(
            output,
            [record[0] for record in records],
            [record[2] for record in records],
            np.vstack(representations),
        )
    return output


# MODULE 6.2: Performance-weighted experimental-reference construction
def performance_reference_weights(
    activities: Sequence[float],
    *,
    higher_is_better: bool,
    exponent: float = 1.0,
) -> np.ndarray:
    values = np.asarray(activities, dtype=float)
    if values.ndim != 1 or values.size < 2:
        raise ValueError("At least two activity measurements are required")
    if np.any(~np.isfinite(values)) or np.any(values <= 0):
        raise ValueError("Activity measurements must be positive and finite")
    if not math.isfinite(exponent) or exponent <= 0:
        raise ValueError("Reference-weight exponent must be positive and finite")
    quality = np.log10(values)
    if not higher_is_better:
        quality = -quality
    return percentile_ranks(quality) ** exponent


def feedback_weighted_similarity(
    candidate_matrix: np.ndarray,
    reference_matrix: np.ndarray,
    reference_weights: np.ndarray,
    batch_size: int = 4096,
) -> tuple[np.ndarray, np.ndarray]:
    candidates = normalize_rows(candidate_matrix)
    references = normalize_rows(reference_matrix)
    weights = np.asarray(reference_weights, dtype=float)
    if (
        weights.shape != (references.shape[0],)
        or np.any(~np.isfinite(weights))
        or np.any(weights <= 0)
    ):
        raise ValueError("Reference weights must be positive and match references")
    maxima: list[np.ndarray] = []
    best: list[np.ndarray] = []
    for start in range(0, candidates.shape[0], batch_size):
        cosine = candidates[start : start + batch_size] @ references.T
        weighted = np.clip(cosine, 0.0, 1.0) * weights[None, :]
        maxima.append(np.max(weighted, axis=1))
        best.append(np.argmax(weighted, axis=1))
    return np.concatenate(maxima), np.concatenate(best)


def run_step_6_feedback(ctx: PipelineContext) -> Path | None:
    if not bool(ctx.get("feedback.enabled", False)):
        print(
            "\n[Step 6] Feedback disabled: the reported study completed one LSBT cycle"
        )
        return None
    print("\n[Step 6] Performance-gated feedback ranking for a subsequent cycle")
    outcomes_path = ctx.path("feedback.cycle1_outcomes_tsv")
    outcomes = read_tsv(outcomes_path)
    metric_column = str(ctx.get("feedback.performance_metric_column", required=True))
    target_operator = str(
        ctx.get("feedback.performance_target_operator", required=True)
    )
    if target_operator not in {"greater_or_equal", "less_or_equal"}:
        raise ValueError(
            "feedback.performance_target_operator must be greater_or_equal or less_or_equal"
        )
    required = {"Sequence_ID", metric_column, "QC_Pass"}
    if not outcomes or not required.issubset(outcomes[0]):
        raise ValueError(f"Feedback outcomes must contain {sorted(required)}")
    outcome_ids = [row["Sequence_ID"] for row in outcomes]
    if len(outcome_ids) != len(set(outcome_ids)):
        raise ValueError("Feedback outcomes contain duplicate Sequence_ID values")
    passed = [
        row
        for row in outcomes
        if row["QC_Pass"].strip().lower() in {"1", "true", "yes", "pass", "passed"}
    ]
    minimum_passed = int(ctx.get("feedback.minimum_qc_passed", required=True))
    if minimum_passed < 2 or len(passed) < minimum_passed:
        raise ValueError(
            f"At least {minimum_passed} QC-passed outcomes are required; observed {len(passed)}"
        )
    activities = np.asarray([float(row[metric_column]) for row in passed])
    if np.any(~np.isfinite(activities)) or np.any(activities <= 0):
        raise ValueError(f"{metric_column} values must be positive and finite")
    target_value = float(ctx.get("feedback.performance_target_value", required=True))
    if not math.isfinite(target_value) or target_value <= 0:
        raise ValueError(
            "feedback.performance_target_value must be positive and finite"
        )
    higher_is_better = target_operator == "greater_or_equal"
    observed_best = float(
        np.max(activities) if higher_is_better else np.min(activities)
    )
    target_met = (
        observed_best >= target_value
        if higher_is_better
        else observed_best <= target_value
    )
    gate_output = ctx.output("step6_gate_decision.json")
    gate_output.write_text(
        json.dumps(
            {
                "performance_metric": metric_column,
                "operator": target_operator,
                "target_value": target_value,
                "observed_best": observed_best,
                "target_met": target_met,
                "qc_passed_outcomes": len(passed),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    if target_met:
        write_manifest(
            ctx,
            "step6_gate",
            ctx.get("feedback", {}),
            [outcomes_path],
            [gate_output],
            {"qc_passed_outcomes": len(passed), "subsequent_cycle_started": 0},
        )
        print("-> Performance target met; no subsequent LSBT cycle was initiated")
        return None

    exponent = float(ctx.get("feedback.reference_weight_exponent", required=True))
    weights = performance_reference_weights(
        activities,
        higher_is_better=higher_is_better,
        exponent=exponent,
    )
    reference_rows = passed
    feedback_embedding_path = prepare_feedback_protrek_embeddings(ctx)
    archive = load_embeddings(feedback_embedding_path)
    labels = archive["labels"].astype(str)
    index_by_id = {label: index for index, label in enumerate(labels)}
    reference_ids = [row["Sequence_ID"] for row in reference_rows]
    missing = [
        identifier for identifier in reference_ids if identifier not in index_by_id
    ]
    if missing:
        raise ValueError(f"Feedback references missing embeddings: {missing[:5]}")
    tested_ids = {row["Sequence_ID"] for row in outcomes}
    untested_indices = np.asarray(
        [index for index, label in enumerate(labels) if label not in tested_ids],
        dtype=int,
    )
    if untested_indices.size == 0:
        raise ValueError("No untested candidates remain for feedback ranking")
    reference_indices = np.asarray(
        [index_by_id[identifier] for identifier in reference_ids]
    )
    feedback_scores, best_indices = feedback_weighted_similarity(
        archive["representations"][untested_indices],
        archive["representations"][reference_indices],
        weights,
        int(ctx.get("feedback.similarity_batch_size", 4096)),
    )
    protrek_scores = {
        row["Sequence_ID"]: float(row["Machine_Score"])
        for row in read_tsv(ctx.output("step2_representative_scores.tsv"))
    }
    untested_ids = labels[untested_indices].tolist()
    complete_mask = np.asarray(
        [identifier in protrek_scores for identifier in untested_ids]
    )
    untested_ids = [
        identifier for identifier, keep in zip(untested_ids, complete_mask) if keep
    ]
    feedback_scores = feedback_scores[complete_mask]
    best_indices = best_indices[complete_mask]
    frozen_percentile = percentile_ranks(
        [protrek_scores[identifier] for identifier in untested_ids]
    )
    feedback_percentile = percentile_ranks(feedback_scores)
    frozen_weight = float(ctx.get("feedback.frozen_score_weight", required=True))
    feedback_weight = float(ctx.get("feedback.feedback_score_weight", required=True))
    if (
        not 0 <= frozen_weight <= 1
        or not 0 <= feedback_weight <= 1
        or not math.isclose(frozen_weight + feedback_weight, 1.0, abs_tol=1e-9)
    ):
        raise ValueError("Feedback score weights must sum to 1")
    updated_scores = (
        frozen_weight * frozen_percentile + feedback_weight * feedback_percentile
    )
    rows = []
    for (
        identifier,
        frozen_rank,
        feedback_score,
        feedback_rank,
        updated,
        best_index,
    ) in zip(
        untested_ids,
        frozen_percentile,
        feedback_scores,
        feedback_percentile,
        updated_scores,
        best_indices,
    ):
        rows.append(
            {
                "Sequence_ID": identifier,
                "Frozen_Machine_Score": protrek_scores[identifier],
                "Frozen_Score_Percentile": float(frozen_rank),
                "Feedback_Weighted_Similarity": float(feedback_score),
                "Feedback_Score_Percentile": float(feedback_rank),
                "Best_Experimental_Reference": reference_ids[int(best_index)],
                "Updated_Score": float(updated),
            }
        )
    rows.sort(key=lambda row: (-row["Updated_Score"], row["Sequence_ID"]))
    for rank, row in enumerate(rows, start=1):
        row["Updated_Rank"] = rank
    output = ctx.output("step6_feedback_ranking.tsv")
    write_tsv(output, rows)
    write_manifest(
        ctx,
        "step6_feedback",
        ctx.get("feedback", {}),
        [outcomes_path, feedback_embedding_path],
        [gate_output, output],
        {
            "qc_passed_outcomes": len(passed),
            "weighted_references": len(reference_ids),
            "untested_ranked": len(rows),
        },
    )
    return output


# =============================================================================
# Step 7: Reproducibility audit and pipeline controller
# =============================================================================


# MODULE 7.1: Input/configuration validation
def validate_configuration(ctx: PipelineContext) -> Path:
    retrieval_mode = str(ctx.get("protrek.retrieval_mode", "faiss_index"))
    if retrieval_mode not in {"faiss_index", "direct_fasta"}:
        raise ValueError("protrek.retrieval_mode must be faiss_index or direct_fasta")
    required_file_keys = ["inputs.verified_anchor_fasta", "protrek.checkpoint"]
    if retrieval_mode == "direct_fasta":
        required_file_keys.append("inputs.sequence_database_fasta")
    for key in required_file_keys:
        path = ctx.path(key)
        if not path.is_file():
            raise FileNotFoundError(f"Required file for {key} not found: {path}")
    required_directory_keys = [
        "protrek.repository_root",
        "protrek.protein_config",
        "protrek.text_config",
        "protrek.structure_config",
        "prostt5.model_path",
    ]
    for key in required_directory_keys:
        path = ctx.path(key)
        if not path.is_dir():
            raise FileNotFoundError(f"Required directory for {key} not found: {path}")
    if retrieval_mode == "faiss_index":
        index_dir = ctx.path("protrek.faiss_index_dir")
        for filename in ("sequence.index", "ids.tsv"):
            if not (index_dir / filename).is_file():
                raise FileNotFoundError(index_dir / filename)
    background_npz = ctx.path("inputs.ec_background_embedding_npz", required=False)
    background_fasta = ctx.path("inputs.ec_background_fasta", required=False)
    if not (background_npz is not None and background_npz.is_file()) and not (
        background_fasta is not None and background_fasta.is_file()
    ):
        raise FileNotFoundError(
            "Provide an existing EC background embedding NPZ or background FASTA"
        )
    anchors = read_fasta(ctx.path("inputs.verified_anchor_fasta"))
    expected_anchor_ids = [
        str(value) for value in ctx.get("inputs.expected_anchor_ids", required=True)
    ]
    if len(expected_anchor_ids) != 4 or len(set(expected_anchor_ids)) != 4:
        raise ValueError("The APS workflow requires four unique expected anchor IDs")
    if [record[0] for record in anchors] != expected_anchor_ids:
        raise ValueError(
            "verified_anchor_fasta IDs/order do not match expected_anchor_ids"
        )
    selection_mode = str(ctx.get("protrek.selection.mode", "top_n"))
    if selection_mode not in {"top_n", "score_threshold"}:
        raise ValueError("protrek.selection.mode must be top_n or score_threshold")
    if selection_mode == "top_n" and int(ctx.get("protrek.selection.top_n", 0)) < 1:
        raise ValueError("protrek.selection.top_n must be positive")
    core_mode = str(ctx.get("core_selection.mode", "top_n"))
    if core_mode not in {"top_n", "fraction"}:
        raise ValueError("core_selection.mode must be top_n or fraction")
    if core_mode == "top_n" and int(ctx.get("core_selection.top_n", 0)) < 1:
        raise ValueError("core_selection.top_n must be positive")
    if (
        core_mode == "fraction"
        and not 0 < float(ctx.get("core_selection.fraction", 0)) <= 1
    ):
        raise ValueError("core_selection.fraction must be in (0, 1]")
    prompt = str(ctx.get("protrek.prompt", required=True)).strip()
    if not prompt:
        raise ValueError("protrek.prompt must not be empty")
    identity = float(ctx.get("mmseqs.minimum_sequence_identity", required=True))
    coverage = float(ctx.get("mmseqs.alignment_coverage", required=True))
    coverage_mode = int(ctx.get("mmseqs.coverage_mode", required=True))
    if not 0 <= identity <= 1 or not 0 <= coverage <= 1:
        raise ValueError("MMseqs2 identity and alignment coverage must be in [0, 1]")
    if coverage_mode not in range(6):
        raise ValueError("mmseqs.coverage_mode must be an integer from 0 to 5")
    if int(ctx.get("mmseqs.threads", required=True)) < 1:
        raise ValueError("mmseqs.threads must be positive")
    target_size = int(ctx.get("final_selection.target_size", required=True))
    if target_size < 1:
        raise ValueError("final_selection.target_size must be positive")
    if core_mode == "top_n" and int(ctx.get("core_selection.top_n", 0)) < target_size:
        raise ValueError(
            "The core subset must be at least as large as the final library"
        )
    umap_neighbors = int(ctx.get("landscape.umap_n_neighbors", required=True))
    umap_min_dist = float(ctx.get("landscape.umap_min_dist", required=True))
    if umap_neighbors < 2 or umap_min_dist < 0:
        raise ValueError(
            "UMAP n_neighbors must be at least 2 and min_dist must be non-negative"
        )
    hdbscan_mode = str(
        ctx.get("landscape.hdbscan_min_cluster_size_mode", required=True)
    )
    if hdbscan_mode == "dynamic_fraction":
        cluster_fraction = float(
            ctx.get("landscape.hdbscan_min_cluster_size_fraction", required=True)
        )
        cluster_minimum = int(
            ctx.get("landscape.hdbscan_min_cluster_size_minimum", required=True)
        )
        if not 0 < cluster_fraction <= 1 or cluster_minimum < 2:
            raise ValueError(
                "Dynamic HDBSCAN fraction must be in (0, 1] and minimum at least 2"
            )
    elif hdbscan_mode == "fixed":
        if int(ctx.get("landscape.hdbscan_min_cluster_size", required=True)) < 2:
            raise ValueError("HDBSCAN min_cluster_size must be at least 2")
    else:
        raise ValueError("Unknown HDBSCAN min-cluster-size mode")
    hdbscan_min_samples = ctx.get("landscape.hdbscan_min_samples")
    if hdbscan_min_samples is not None and int(hdbscan_min_samples) < 1:
        raise ValueError("HDBSCAN min_samples must be null or positive")
    if str(
        ctx.get("landscape.hdbscan_cluster_selection_method", required=True)
    ) not in {
        "eom",
        "leaf",
    }:
        raise ValueError("HDBSCAN cluster_selection_method must be eom or leaf")
    feedback_enabled = bool(ctx.get("feedback.enabled", False))
    if feedback_enabled:
        outcomes_path = ctx.path("feedback.cycle1_outcomes_tsv")
        if not outcomes_path.is_file():
            raise FileNotFoundError(outcomes_path)
        operator = str(ctx.get("feedback.performance_target_operator", required=True))
        if operator not in {"greater_or_equal", "less_or_equal"}:
            raise ValueError(
                "feedback.performance_target_operator must be greater_or_equal or less_or_equal"
            )
        metric_column = str(
            ctx.get("feedback.performance_metric_column", required=True)
        ).strip()
        if not metric_column:
            raise ValueError("feedback.performance_metric_column must not be empty")
        target_value = float(
            ctx.get("feedback.performance_target_value", required=True)
        )
        exponent = float(ctx.get("feedback.reference_weight_exponent", required=True))
        minimum_passed = int(ctx.get("feedback.minimum_qc_passed", required=True))
        frozen_weight = float(ctx.get("feedback.frozen_score_weight", required=True))
        feedback_weight = float(
            ctx.get("feedback.feedback_score_weight", required=True)
        )
        if target_value <= 0 or not math.isfinite(target_value):
            raise ValueError(
                "feedback.performance_target_value must be positive and finite"
            )
        if exponent <= 0 or not math.isfinite(exponent):
            raise ValueError(
                "feedback.reference_weight_exponent must be positive and finite"
            )
        if minimum_passed < 2:
            raise ValueError("feedback.minimum_qc_passed must be at least 2")
        if (
            not 0 <= frozen_weight <= 1
            or not 0 <= feedback_weight <= 1
            or not math.isclose(frozen_weight + feedback_weight, 1.0, abs_tol=1e-9)
        ):
            raise ValueError(
                "Feedback score weights must be within [0, 1] and sum to 1"
            )
    report = {
        "pipeline_version": PIPELINE_VERSION,
        "config_path": str(ctx.config_path),
        "config_sha256": sha256_file(ctx.config_path),
        "anchor_count": len(anchors),
        "anchor_ids": [record[0] for record in anchors],
        "retrieval_mode": retrieval_mode,
        "feedback_enabled": feedback_enabled,
    }
    output = ctx.output("step0_input_validation.json")
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return output


# MODULE 7.2: Final audit summary
def write_pipeline_summary(ctx: PipelineContext) -> Path:
    files = {
        "step1_candidates": ctx.output("step1_candidates.fasta"),
        "step2_representatives": ctx.output("step2_final_nonredundant.fasta"),
        "step3_core_subset": ctx.output("step3_core_subset.tsv"),
        "step4_landscape": ctx.output("step4_functional_landscape.tsv"),
        "step5_final_library": ctx.output("step5_final_candidates.tsv"),
    }
    missing = [name for name, path in files.items() if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Cannot summarize; required stage outputs unavailable: {missing}")
    counts = {
        "step1_candidates": len(read_fasta(files["step1_candidates"])),
        "step2_representatives": len(read_fasta(files["step2_representatives"])),
        "step3_core_subset": len(read_tsv(files["step3_core_subset"])),
        "step5_final_library": len(read_tsv(files["step5_final_library"])),
    }
    gate_path = ctx.output("step6_gate_decision.json")
    gate_decision = (
        json.loads(gate_path.read_text(encoding="utf-8"))
        if gate_path.is_file()
        else None
    )
    summary = {
        "pipeline_version": PIPELINE_VERSION,
        "counts": counts,
        "expected_counts": ctx.get("audit.expected_counts", {}),
        "top_candidate": read_tsv(files["step5_final_library"])[0]["Sequence_ID"],
        "feedback_gate": gate_decision,
        "feedback_executed": bool(
            ctx.get("feedback.enabled", False)
            and gate_decision is not None
            and gate_decision.get("target_met") is False
            and ctx.output("step6_feedback_ranking.tsv").is_file()
        ),
        "files": {
            name: {"path": str(path), "sha256": sha256_file(path)}
            for name, path in files.items()
        },
    }
    output = ctx.output("pipeline_summary.json")
    output.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return output


# MODULE 7.3: Complete workflow
def run_all(ctx: PipelineContext) -> None:
    validate_configuration(ctx)
    run_step_1(ctx)
    run_step_2(ctx)
    run_step_3(ctx)
    run_step_4(ctx)
    run_step_5(ctx)
    run_step_6_feedback(ctx)
    summary = write_pipeline_summary(ctx)
    print(f"\nAPS workflow complete. Audit summary: {summary}")


# MODULE 7.4: Command-line interface
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Block-structured APS workflow",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--config", required=True, help="YAML configuration file")
    parser.add_argument("--version", action="version", version=PIPELINE_VERSION)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name, description in (
        ("validate", "validate configuration and input assets"),
        ("run-all", "run Steps 1-6 and write the final audit"),
        ("step1", "run ProTrek retrieval"),
        ("step2", "run MMseqs2 clustering"),
        ("step3", "run ProstT5 and anchor scoring"),
        ("step4", "run background UMAP and clustering"),
        ("step5", "select the final 642 candidates"),
        ("feedback", "run optional subsequent-cycle feedback ranking"),
        ("summary", "write the final audit summary"),
    ):
        subparsers.add_parser(name, help=description)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    ctx = PipelineContext(args.config)
    commands = {
        "validate": validate_configuration,
        "run-all": run_all,
        "step1": run_step_1,
        "step2": run_step_2,
        "step3": run_step_3,
        "step4": run_step_4,
        "step5": run_step_5,
        "feedback": run_step_6_feedback,
        "summary": write_pipeline_summary,
    }
    commands[args.command](ctx)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
