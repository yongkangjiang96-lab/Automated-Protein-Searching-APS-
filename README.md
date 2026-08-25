[README.md](https://github.com/user-attachments/files/31416892/README.md)
# Automated-Protein-Searching (APS) workflow

This package turns the block-structured `APS.py` supplied with the manuscript
into an executable and auditable implementation of the workflow described in
Supplementary Method 5.  It preserves the original Step/Module organization,
retains scientifically valid logic, corrects mismatches, and fills in the
previously missing retrieval, active-region selection, final ranking, feedback,
configuration, and provenance components.

The package reproduces **methods**, not unpublished results by itself.  The
frozen sequence database, ProTrek index, model weights, EC background database,
anchor FASTA, and experimental outcomes are external research assets and must be
provided by the authors.

## 1. Workflow implemented

| Step | Executable operation | Article alignment |
|---|---|---|
| 1 | Encode the NADK text query with ProTrek and retrieve/rank proteins | Exports the ProTrek sequence-text value as the machine score |
| 2 | MMseqs2 clustering at 50% identity with explicit coverage fields | Produces non-redundant representatives and preserves their machine scores |
| 3 | ProstT5 embedding and cosine scoring against four verified NADK anchors | Uses the **maximum over individual anchors**, not similarity to an anchor centroid |
| 4 | Fit `StandardScaler` and UMAP only on EC background embeddings; transform candidates/anchors; HDBSCAN on candidates | Prevents candidate information from influencing the background map |
| 5 | Union the density clusters linked to verified anchors and rank candidates inside them | Selects the final 642 primarily by ProTrek machine score |
| 6 | Optional weighted positive-reference update for a later cycle | Disabled for the reported one-cycle study |
| 7 | Validation, manifests, SHA-256 checksums, count audits, and CLI | Makes deviations from reported counts visible |

## 2. Important numerical correction for the manuscript

The manuscript connects three claims that are not exactly compatible:

- 56,843 MMseqs2 representatives;
- retention of the “top 25%”;
- 14,222 retained core sequences.

Recommended article wording:

> The 14,222 highest-ranked sequences (approximately 25.02% of the 56,843
> non-redundant representatives) were retained as the core subset.

If “top 25%” is intended to be exact, change the code/configuration to retain
14,211 and update every downstream count/result.  Do not claim both criteria as
exact unless the upstream denominator is corrected and documented.

## 3. Required external assets

Create the following project layout or edit the YAML paths:

```text
APS_article_aligned/
├── APS.py
├── config.yaml
├── environment.yml
├── external/
│   └── ProTrek/
│       └── weights/ProTrek_650M/...
├── models/
│   └── ProstT5/...
├── data/
│   ├── verified_nadk_anchors.fasta
│   ├── protrek_sequence_index/
│   │   ├── sequence.index
│   │   └── ids.tsv
│   └── ec_background_prostt5_embeddings.npz
└── results/
```

The anchor FASTA must contain the exact identifiers, in this order:

```text
A1AEE5
A7ZQ55
A8A3C1
P0A7B3
```

For every released asset, archive the source URL/release date, accession or
database version, model revision, file size, and SHA-256 checksum.  Those values
cannot be reconstructed from candidate counts and should not be invented.

## 4. Installation

Clone the official ProTrek repository into `external/ProTrek`, obtain the
ProTrek-650M weights according to its documentation, and place a frozen local
ProstT5 snapshot under `models/ProstT5`.

```bash
conda env create -f environment.yml
conda activate aps-article-aligned
cp config.example.yaml config.yaml
```

GPU builds are platform-specific.  If the CUDA 11.7 pins are not compatible
with the target machine, preserve the Python/library versions but install the
matching official PyTorch and FAISS build for that CUDA driver.  Report the
actual exported environment used for the final run:

```bash
conda env export --from-history > environment.lock.yml
python -m pip freeze > requirements.lock.txt
mmseqs version > mmseqs.version.txt
```

## 5. Build or validate the ProTrek search index

The scalable mode expects the official ProTrek database format:
`sequence.index` plus `ids.tsv`.  The official repository provides the index
builder:

```bash
python external/ProTrek/scripts/generate_database.py \
  --fasta data/frozen_sequence_database.fasta \
  --save_dir data/protrek_sequence_index
```

The final publication archive must also state whether the index is exact or
approximate and record relevant FAISS parameters (`nlist`, `nprobe`, metric,
index size).  With an approximate IVF index, demonstrate top-candidate stability
against a higher-`nprobe` or exact-search subset before treating ranks as fixed.

## 6. Configuration and validation

Edit `config.yaml`; then validate paths and the four anchor identifiers before
allocating GPU time:

```bash
python APS.py --config config.yaml validate
python -m pytest -q
```

The validator intentionally does not download or silently replace missing
assets.  This prevents accidental mixing of model/database versions.

## 7. Run the workflow

Run all stages:

```bash
python APS.py --config config.yaml run-all
```

Or run one stage at a time for cluster schedulers and checkpointed analyses:

```bash
python APS.py --config config.yaml step1
python APS.py --config config.yaml step2
python APS.py --config config.yaml step3
python APS.py --config config.yaml step4
python APS.py --config config.yaml step5
python APS.py --config config.yaml summary
```

Enable `feedback.enabled: true` and run `feedback` only for a prospectively
defined later cycle with a complete outcome table.  Do not enable it when
reproducing the reported one-cycle analysis.

## 8. Principal output files

| File | Meaning |
|---|---|
| `step1_protrek_scores.tsv` | Preliminary ProTrek rank and machine score |
| `step1_candidates.fasta` | Prespecified preliminary library |
| `step2_final_nonredundant.fasta` | MMseqs2 representative sequences |
| `step2_representative_scores.tsv` | Propagated ProTrek scores for representatives |
| `step3_candidate_embeddings.npz` | Candidate ProstT5 embeddings |
| `step3_anchor_embeddings.npz` | Verified-anchor ProstT5 embeddings |
| `step3_core_subset.tsv` | Maximum individual-anchor similarity and core rank |
| `step4_functional_landscape.tsv` | UMAP coordinates, density cluster, and active-region status |
| `step4_active_clusters.json` | Anchor-to-cluster assignments and final dynamic cluster size |
| `step5_final_candidates.tsv/.fasta` | Final ranked 642-candidate library |
| `*.manifest.json` | Parameters, counts, input/output checksums |
| `pipeline_summary.json` | Final count and top-candidate audit |

The reported reconstruction should produce 569,792, 56,843, 14,222, and 642
sequences at Steps 1, 2, 3, and 5, respectively, with Q8NQM1 ranked first.  These
are **audit expectations, not values forced by the code**.  A mismatch indicates
that the database, model weights, index, preprocessing, parameters, or article
description differs and must be resolved rather than overwritten.

## 9. Methods text aligned with this implementation

The following concise wording is suitable after the authors fill in all frozen
asset versions and the absolute HDBSCAN value produced by the configured rule:

> The NADK functional query was encoded with ProTrek-650M, and database
> sequences were ranked by the temperature-scaled sequence-text similarity
> (machine score). The top 569,792 sequences were clustered with MMseqs2 at 50%
> sequence identity (`-c 0`, `--cov-mode 0`, reflecting the supplied script's
> absence of an additional coverage threshold), yielding 56,843 representatives.
> Candidate and four verified NADK-anchor sequences were embedded separately
> with a frozen ProstT5 model. For each candidate, we calculated the maximum
> cosine similarity to any individual anchor and retained the 14,222
> highest-ranked candidates (approximately 25.02%). A StandardScaler and UMAP
> model were fitted exclusively to the EC-background embeddings; candidates and
> anchors were then projected without refitting. Core candidates were clustered
> by HDBSCAN using the preregistered dynamic minimum-cluster-size rule [insert
> resulting value]. Each anchor was linked to its nearest non-noise candidate,
> and the union of the corresponding density clusters defined the active region.
> Candidates in the active region were ranked by the frozen ProTrek machine
> score; maximum anchor similarity and sequence ID were deterministic
> tie-breakers, and the top 642 formed the experimental library. Random seed,
> software/model/database versions, FAISS/MMseqs2/UMAP/HDBSCAN parameters, and
> SHA-256 checksums are archived with the run manifests.

## 10. Feedback data contract and limitations

If a second LSBT cycle is genuinely needed, `cycle1_outcomes_tsv` must contain:

```text
Sequence_ID    Catalytic_Efficiency    QC_Pass
```

The code calculates or loads frozen ProTrek sequence embeddings, selects the top
quartile of QC-passed tested proteins as positive functional references, gives
better performers greater percentile-based weight, combines the new ProTrek-
space similarity percentile with the frozen ProTrek text-score percentile, and
ranks untested candidates.  The default 0.50/0.50 combination and top-quartile
definition are transparent operational proposals, **not parameters established
by the current experiment**.  They must be prospectively justified,
sensitivity-tested, and kept out of claims about the already completed cycle.

## 11. Reproducibility boundaries

- Do not fit UMAP or the scaler on candidates, anchors, or their concatenation
  with the background.
- Do not replace individual-anchor maxima with similarity to an averaged anchor.
- Do not hard-code a cluster label: HDBSCAN label numbers have no biological
  meaning and can change with data/order/library versions.
- Do not silently truncate long sequences; apply and report a prespecified QC
  rule.
- Do not report exact reproduction unless all input/model/index checksums and
  reported intermediate counts agree.
- Set `audit.enforce_expected_counts: true` only after the frozen provenance is
  complete; otherwise use warnings to diagnose the mismatch.

## 12. Software references

- ProTrek official repository: <https://github.com/westlake-repl/ProTrek>
- ProTrek article: <https://www.nature.com/articles/s41587-025-02836-0>
- ProstT5 model card: <https://huggingface.co/Rostlab/ProstT5>
- MMseqs2: <https://github.com/soedinglab/MMseqs2>
- UMAP: <https://umap-learn.readthedocs.io/>
- HDBSCAN: <https://hdbscan.readthedocs.io/>
