# Automated Protein Searching (APS)

APS is a reproducible computational workflow for prioritizing NAD+ kinase
(NADK) candidates within a Learn-Screen-Build-Test (LSBT) framework. The
reported NADK study used one computational screening cycle followed by
experimental testing of the complete 642-candidate library. The selected
enzyme met the predefined performance criterion, so no subsequent LSBT cycle
was initiated.

## 1. Workflow

| Step | Operation | Output |
|---|---|---|
| 1 | ProTrek text-to-protein retrieval using the NADK functional description | 569,792 preliminary candidates with a ProTrek machine score |
| 2 | MMseqs2 clustering at 50% sequence identity | 56,843 non-redundant representative sequences |
| 3 | ProstT5 embeddings and maximum cosine similarity to four verified NADK anchors | 14,222 candidates, approximately the top quartile by structural functional proximity |
| 4 | Background-only StandardScaler/UMAP fitting, candidate projection, and HDBSCAN density clustering | Reproducible functional-landscape coordinates and active regions |
| 5 | Machine-score ranking within active regions | Final 642-candidate NADK library |
| 6 | Performance-gated experimental feedback | Disabled for reproduction of the reported one-cycle study |
| 7 | Configuration validation, manifests, counts, hashes, and summary | Reproducibility records for every stage |

## 2. Package contents

```text
APS_article_aligned/
├── APS.py
├── environment.yml
├── README.md

```

The code package does not include protein databases, model weights, the
background structural database, anchor sequences, or experimental outcomes.
These research assets must be supplied as frozen, versioned inputs.

## 3. Required assets

Prepare the following paths before execution:

```text
external/ProTrek/                         official ProTrek repository
external/ProTrek/weights/ProTrek_650M/   frozen ProTrek model files
models/ProstT5/                           frozen ProstT5 model snapshot
data/protrek_sequence_index/
├── sequence.index                        inner-product FAISS index
└── ids.tsv                               ID, sequence, and length in index order
data/verified_nadk_anchors.fasta          four verified NADK anchors
data/ec_background_prostt5_embeddings.npz
```

The background NPZ archive must contain the arrays `labels` and
`representations`. It must be generated with the same ProstT5 snapshot,
sequence preprocessing, pooling rule, and numerical precision used for the
candidate and anchor embeddings. A background FASTA can be supplied instead,
in which case APS generates the embeddings with the configured ProstT5 model.

The FAISS index must use inner-product similarity, and row `n` of `ids.tsv`
must describe vector `n` in `sequence.index`. The ProTrek repository provides
the corresponding `generate_database.py` utility.

## 4. Environment

Create the pinned Conda environment:

```bash
conda env create -f environment.yml
conda activate aps-lsbt
```

The environment follows the ProTrek-compatible PyTorch and Transformers stack
and adds MMseqs2, ProstT5, UMAP, HDBSCAN, FAISS, YAML, and testing dependencies.
A CUDA-capable Linux workstation or cluster node is recommended for the full
569,792-sequence workflow.

## 5. Configuration

Copy the template and edit only the local asset paths and hardware settings:

```bash
cp config.example.yaml config.yaml
```

The study configuration uses these analysis-defining settings:

| Parameter | Value |
|---|---:|
| ProTrek prompt | `I need an enzyme that catalyzes the conversion of NAD+ to NADP+.` |
| Preliminary library | 569,792 sequences |
| MMseqs2 minimum sequence identity | 0.50 |
| Additional MMseqs2 coverage threshold | 0.0 |
| Representative library | 56,843 sequences |
| Verified anchors | 4 |
| Core subset | 14,222 sequences |
| UMAP metric | Euclidean |
| Final experimental library | 642 sequences |
| Random seed | 42 |
| Feedback for the reported cycle | Disabled |

All count values are audit checkpoints. The program calculates each result
from the supplied assets and never forces an intermediate count by discarding
or duplicating records.

### Background projection and active regions

`StandardScaler` and UMAP are fitted exclusively on the background structural
embeddings. Core candidates and verified anchors are then transformed into
that fixed coordinate system without refitting. HDBSCAN is applied to the core
candidates, and its non-noise density clusters define the active regions used
for final prioritization. Projected anchors are associated with the nearest
non-noise candidate cluster for landscape annotation.

The final candidates are ranked by the ProTrek machine score. Maximum
anchor cosine similarity and sequence identifier provide deterministic
tie-breaking.

## 6. Run

Validate all paths, identifiers, configuration fields, and model/index
contracts:

```bash
python APS.py --config config.yaml validate
```

Run the complete reported workflow:

```bash
python APS.py --config config.yaml run-all
```

Run individual stages when using an HPC scheduler or resuming from completed
outputs:

```bash
python APS.py --config config.yaml step1
python APS.py --config config.yaml step2
python APS.py --config config.yaml step3
python APS.py --config config.yaml step4
python APS.py --config config.yaml step5
python APS.py --config config.yaml summary
```

Each stage checks the required upstream files. Manifests contain the effective
parameters, SHA-256 hashes, and observed record counts.

## 7. Main outputs

| File | Description |
|---|---|
| `step1_protrek_scores.tsv` | ProTrek retrieval ranks and machine scores |
| `step1_candidates.fasta` | Preliminary candidate library |
| `step2_final_nonredundant.fasta` | MMseqs2 representative sequences |
| `step2_representative_scores.tsv` | Machine scores propagated to representatives |
| `step3_candidate_embeddings.npz` | Candidate ProstT5 embeddings |
| `step3_anchor_embeddings.npz` | Verified-anchor ProstT5 embeddings |
| `step3_core_subset.tsv` | Maximum individual-anchor similarity and structural rank |
| `step4_functional_landscape.tsv` | UMAP coordinates, density clusters, and active-region labels |
| `step4_active_clusters.json` | Anchor-to-cluster mapping and HDBSCAN settings |
| `step5_final_candidates.tsv` | Ranked 642-candidate library |
| `step5_final_candidates.fasta` | Sequences for synthesis and experimental validation |
| `pipeline_summary.json` | Final counts, top candidate, file paths, and SHA-256 hashes |
| `*.manifest.json` | Stage-specific provenance records |

With the frozen study assets, the audit checkpoints are 569,792 preliminary
candidates, 56,843 representatives, 14,222 core candidates, 642 final
candidates, and `Q8NQM1` as the highest-ranked candidate.

## 8. Conditional feedback

For reproduction of the reported NADK screening, keep `feedback.enabled: false`.
If a future target fails a prospectively defined performance criterion,
the feedback branch can be enabled for a subsequent LSBT cycle. Before doing
so, specify the performance metric, threshold and direction, minimum number of
QC-passed outcomes, reference-weight exponent, and the two reranking weights.

The outcomes TSV must contain unique `Sequence_ID` values, a `QC_Pass` field,
and the configured performance-metric column. The gate is evaluated first. If
the target is met, no new ranking is generated. If the target is not met, all
QC-passed tested proteins become performance-weighted ProTrek references;
higher-performing references receive greater influence, and the reference-
conditioned score is combined with the frozen baseline machine-score
percentile. This is a deterministic reranking operation and does not retrain
the ProTrek model.

Software resources:

- ProTrek: <https://github.com/westlake-repl/ProTrek>
- ProstT5: <https://huggingface.co/Rostlab/ProstT5>
- MMseqs2: <https://github.com/soedinglab/MMseqs2>
- UMAP: <https://umap-learn.readthedocs.io/>
- HDBSCAN: <https://hdbscan.readthedocs.io/>
