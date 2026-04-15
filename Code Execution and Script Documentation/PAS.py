# =============================================================================
# Step 0: Environment
# =============================================================================

'''
channels:
  - pytorch
  - huggingface
  - nvidia
  - defaults
dependencies:
  - _libgcc_mutex=0.1=main
  - _openmp_mutex=5.1=1_gnu
  - abseil-cpp=20211102.0=hd4dd3e8_0
  - aiohttp=3.8.3=py310h5eee18b_0
  - aiosignal=1.2.0=pyhd3eb1b0_0
  - arrow-cpp=11.0.0=h374c478_2
  - async-timeout=4.0.2=py310h06a4308_0
  - attrs=22.1.0=py310h06a4308_0
  - aws-c-common=0.6.8=h5eee18b_1
  - aws-c-event-stream=0.1.6=h6a678d5_6
  - aws-checksums=0.1.11=h5eee18b_2
  - aws-sdk-cpp=1.8.185=h721c034_1
  - blas=1.0=mkl
  - boost-cpp=1.82.0=hdb19cb5_1
  - bottleneck=1.3.5=py310ha9d4c09_0
  - brotlipy=0.7.0=py310h7f8727e_1002
  - bzip2=1.0.8=h7b6447c_0
  - c-ares=1.19.0=h5eee18b_0
  - ca-certificates=2023.05.30=h06a4308_0
  - certifi=2023.7.22=py310h06a4308_0
  - cffi=1.15.1=py310h5eee18b_3
  - charset-normalizer=2.0.4=pyhd3eb1b0_0
  - cryptography=41.0.2=py310h22a60cf_0
  - cuda-cudart=11.7.99=0
  - cuda-cupti=11.7.101=0
  - cuda-libraries=11.7.1=0
  - cuda-nvrtc=11.7.99=0
  - cuda-nvtx=11.7.91=0
  - cuda-runtime=11.7.1=0
  - dataclasses=0.8=pyh6d0b6a4_7
  - datasets=2.14.4=py_0
  - dill=0.3.7=py310h06a4308_0
  - faiss-gpu=1.8.0
  - ffmpeg=4.3=hf484d3e_0
  - filelock=3.9.0=py310h06a4308_0
  - freetype=2.12.1=h4a9f257_0
  - frozenlist=1.3.3=py310h5eee18b_0
  - fsspec=2023.4.0=py310h06a4308_0
  - gflags=2.2.2=he6710b0_0
  - giflib=5.2.1=h5eee18b_3
  - glog=0.5.0=h2531618_0
  - gmp=6.2.1=h295c915_3
  - gmpy2=2.1.2=py310heeb90bb_0
  - gnutls=3.6.15=he1e5248_0
  - grpc-cpp=1.48.2=he1ff14a_1
  - huggingface_hub=0.16.4=py_0
  - icu=73.1=h6a678d5_0
  - idna=3.4=py310h06a4308_0
  - importlib-metadata=6.0.0=py310h06a4308_0
  - intel-openmp=2023.1.0=hdb19cb5_46305
  - jinja2=3.1.2=py310h06a4308_0
  - jpeg=9e=h5eee18b_1
  - krb5=1.20.1=h143b758_1
  - lame=3.100=h7b6447c_0
  - lcms2=2.12=h3be6417_0
  - ld_impl_linux-64=2.38=h1181459_1
  - lerc=3.0=h295c915_0
  - libboost=1.82.0=ha8e66a6_1
  - libbrotlicommon=1.0.9=h5eee18b_7
  - libbrotlidec=1.0.9=h5eee18b_7
  - libbrotlienc=1.0.9=h5eee18b_7
  - libcublas=11.10.3.66=0
  - libcufft=10.7.2.124=h4fbf590_0
  - libcufile=1.7.2.10=0
  - libcurand=10.3.3.141=0
  - libcurl=8.2.1=h251f7ec_0
  - libcusolver=11.4.0.1=0
  - libcusparse=11.7.4.91=0
  - libdeflate=1.17=h5eee18b_0
  - libedit=3.1.20221030=h5eee18b_0
  - libev=4.33=h7f8727e_1
  - libevent=2.1.12=hdbd6064_1
  - libffi=3.4.4=h6a678d5_0
  - libgcc-ng=11.2.0=h1234567_1
  - libgomp=11.2.0=h1234567_1
  - libiconv=1.16=h7f8727e_2
  - libidn2=2.3.4=h5eee18b_0
  - libnghttp2=1.52.0=h2d74bed_1
  - libnpp=11.7.4.75=0
  - libnvjpeg=11.8.0.2=0
  - libpng=1.6.39=h5eee18b_0
  - libprotobuf=3.20.3=he621ea3_0
  - libssh2=1.10.0=hdbd6064_2
  - libstdcxx-ng=11.2.0=h1234567_1
  - libtasn1=4.19.0=h5eee18b_0
  - libthrift=0.15.0=h1795dd8_2
  - libtiff=4.5.1=h6a678d5_0
  - libunistring=0.9.10=h27cfd23_0
  - libuuid=1.41.5=h5eee18b_0
  - libwebp=1.2.4=h11a3e52_1
  - libwebp-base=1.2.4=h5eee18b_1
  - lz4-c=1.9.4=h6a678d5_0
  - markupsafe=2.1.1=py310h7f8727e_0
  - mkl=2023.1.0=h213fc3f_46343
  - mkl-service=2.4.0=py310h5eee18b_1
  - mkl_fft=1.3.6=py310h1128e8f_1
  - mkl_random=1.2.2=py310h1128e8f_1
  - mpc=1.1.0=h10f8cd9_1
  - mpfr=4.0.2=hb69a4c5_1
  - mpmath=1.3.0=py310h06a4308_0
  - multidict=6.0.2=py310h5eee18b_0
  - multiprocess=0.70.15=py310h06a4308_0
  - ncurses=6.4=h6a678d5_0
  - nettle=3.7.3=hbbd107a_1
  - networkx=3.1=py310h06a4308_0
  - numexpr=2.8.4=py310h85018f9_1
  - numpy=1.25.2=py310h5f9d8c6_0
  - numpy-base=1.25.2=py310hb5e798b_0
  - openh264=2.1.1=h4ff587b_0
  - openssl=3.0.10=h7f8727e_2
  - orc=1.7.4=hb3bc3d3_1
  - packaging=23.1=py310h06a4308_0
  - pandas=2.0.3=py310h1128e8f_0
  - pillow=9.4.0=py310h6a678d5_0
  - pip=23.2.1=py310h06a4308_0
  - pyarrow=11.0.0=py310h468efa6_1
  - pycparser=2.21=pyhd3eb1b0_0
  - pyopenssl=23.2.0=py310h06a4308_0
  - pysocks=1.7.1=py310h06a4308_0
  - python=3.10.12=h955ad1f_0
  - python-dateutil=2.8.2=pyhd3eb1b0_0
  - python-tzdata=2023.3=pyhd3eb1b0_0
  - python-xxhash=2.0.2=py310h5eee18b_1
  - pytorch=2.0.1=py3.10_cuda11.7_cudnn8.5.0_0
  - pytorch-cuda=11.7=h778d358_5
  - pytorch-mutex=1.0=cuda
  - pytz=2022.7=py310h06a4308_0
  - pyyaml=6.0=py310h5eee18b_1
  - re2=2022.04.01=h295c915_0
  - readline=8.2=h5eee18b_0
  - regex=2022.7.9=py310h5eee18b_0
  - requests=2.31.0=py310h06a4308_0
  - safetensors=0.3.2=py310hb02cf49_0
  - setuptools=68.0.0=py310h06a4308_0
  - six=1.16.0=pyhd3eb1b0_1
  - snappy=1.1.9=h295c915_0
  - sqlite=3.41.2=h5eee18b_0
  - sympy=1.11.1=py310h06a4308_0
  - tbb=2021.8.0=hdb19cb5_0
  - tk=8.6.12=h1ccaba5_0
  - tokenizers=0.13.2=py310h22610ee_1
  - torchtriton=2.0.0=py310
  - torchvision=0.15.2=py310_cu117
  - tqdm=4.65.0=py310h2f386ee_0
  - typing-extensions=4.7.1=py310h06a4308_0
  - typing_extensions=4.7.1=py310h06a4308_0
  - tzdata=2023c=h04d1e81_0
  - urllib3=1.26.16=py310h06a4308_0
  - utf8proc=2.6.1=h27cfd23_0
  - wheel=0.38.4=py310h06a4308_0
  - xxhash=0.8.0=h7f8727e_3
  - xz=5.4.2=h5eee18b_0
  - yaml=0.2.5=h7b6447c_0
  - yarl=1.8.1=py310h5eee18b_0
  - zipp=3.11.0=py310h06a4308_0
  - zlib=1.2.13=h5eee18b_0
  - zstd=1.5.5=hc292b87_0
  - pip:
      - asttokens==2.4.1
      - decorator==5.1.1
      - exceptiongroup==1.2.1
      - executing==2.0.1
      - ipython==8.25.0
      - jedi==0.19.1
      - matplotlib-inline==0.1.7
      - parso==0.8.4
      - pexpect==4.9.0
      - prompt-toolkit==3.0.47
      - protobuf==4.24.2
      - ptyprocess==0.7.0
      - pure-eval==0.2.2
      - pygments==2.18.0
      - sentencepiece==0.1.99
      - stack-data==0.6.3
      - traitlets==5.14.3
      - wcwidth==0.2.13
      - torch==2.0.1
      - torchvision==0.15.2
      - torchaudio==2.0.2
      - gradio==4.43
      - torchmetrics==0.9.3
      - pytorch-lightning==2.1.3
      - transformers==4.28.0
      - scikit-learn==1.4.0
      - tabulate==0.9.0
      - biopython==1.83
      - easydict==1.13
      - lmdb==1.4.1
      - multiprocess
      - pyspellchecker==0.8.2
'''

# =============================================================================
# GLOBAL IMPORTS & CONFIGURATION
# =============================================================================
import os
import sys
import pickle
import shutil
import random
import subprocess
import numpy as np
import pandas as pd
import umap
import hdbscan
from Bio import SeqIO
from sklearn.preprocessing import StandardScaler
from sklearn.metrics.pairwise import cosine_similarity

# Global Computation Settings
THREADS = 96
IDENTITY_THRESHOLD = 0.5 
UMAP_N_NEIGHBORS = 15
UMAP_MIN_DIST = 0.1
UMAP_METRIC = 'euclidean'


# =============================================================================
# Step 1: Natural Language-Based Preliminary Screening
# =============================================================================
#
# Overview:
# ---------
# This step, we use the pre-trained tri-modal protein language model 
# [ProTrek](https://github.com/westlake-repl/ProTrek) to perform a 
# function-oriented preliminary screening through sequence database, 
# in order to get an initial candidate library based on semantic matching.
#
# Recommended databases:
# - UniProt full sequence database (Swiss-Prot)
# - Any customized protein sequence database (.fasta)
#
# -------------
# What you need to prepare before you submit the job:
# - ProTrek environment (already installed on server)
# - ProTrek pre-trained model weights (deployed locally)
# - Input Database: A local .fasta file containing the protein sequences.
# - Input parameters: Target enzyme functional description (Text Prompt)
# - Output: step1_candidates.fasta
#
# 
# =============================================================================
# Step 2: Sequence Clustering and Redundancy Removal
# =============================================================================
#
# Overview:
# ---------
# This step, we use [MMseqs2](https://github.com/soedinglab/MMseqs2) to 
# eliminate highly homologous sequences from the candidate library generated 
# in Step 1. This significantly reduces computational costs for downstream 
# structural embedding processes while preserving sequence diversity.
#
# -------------
# What you need to prepare before you submit the job:
# - MMseqs2 software (already installed on server and added to PATH)
# - Input parameters: step1_candidates.fasta
# - Output: step2_clustered_rep_seq.fasta
#
# =============================================================================

# MODULE 2.1: Full-Library Clustering
def run_module_2_1_cluster(db_path, output_prefix="step2_clustered"):
    print(f"[Module 2.1] Starting Full-Library Clustering: {db_path}")
    tmp_dir = "tmp_cluster/"
    os.makedirs(tmp_dir, exist_ok=True)

    cluster_cmd = [
        "mmseqs", "easy-cluster", db_path, output_prefix, tmp_dir,
        "--min-seq-id", str(IDENTITY_THRESHOLD), "--threads", str(THREADS)
    ]
    subprocess.run(cluster_cmd, check=True)
    if os.path.exists(tmp_dir): shutil.rmtree(tmp_dir)
    return f"{output_prefix}_rep_seq.fasta"

# MODULE 2.2: Representative Sequence Finalization
def run_module_2_2_finalize(input_rep_fasta, output_fasta="step2_final_nonredundant.fasta"):
    print(f"[Module 2.2] Finalizing non-redundant pool: {output_fasta}")
    records = list(SeqIO.parse(input_rep_fasta, "fasta"))
    SeqIO.write(records, output_fasta, "fasta")
    print(f"-> Total unique representatives: {len(records)}")
    return output_fasta

# =============================================================================
# Step 3: ProstT5 Structural Embedding and Information Scoring
# =============================================================================
#
# Overview:
# ---------
# Generates structural embeddings for the representative sequences using the 
# ProstT5 model. Calculates the cosine similarity between the candidate 
# embeddings and the centroid of known reference anchors. Retains the top 25% 
# of sequences based on the computed similarity scores.
#
# -------------
# What you need to prepare before you submit the job:
# - ProstT5 environment (PyTorch, Transformers installed on server)
# - ProstT5 pre-trained model weights (deployed locally from Hugging Face)
# - Input file: step2_final_nonredundant.fasta, reference_anchors.pkl
#   (reference_anchors.pkl is a user-provided prior dataset. 
#    It contains the sequences of highly active target enzymes (such as the known NADK) validated through wet-lab experiments, 
#    along with their structural embedding vectors derived from ProstT5. 
#    It serves as a reference for the center-of-mass coordinates of the entire functional landscape.)
# - Output: step3_embeddings.pkl, step3_core_subset.csv
#
# =============================================================================

# MODULE 3.1: Sequence Pre-processing
def preprocess_for_embedding(input_fasta):
    print("[Module 3.1] Sanitizing sequences for ProstT5 encoding...")
    clean_fasta = "step3_input_sanitized.fasta"
    records = [r for r in SeqIO.parse(input_fasta, "fasta") if len(r.seq.ungap("*")) > 0]
    SeqIO.write(records, clean_fasta, "fasta")
    return clean_fasta

# MODULE 3.2: Structural Embedding Generation
def run_module_3_2_inference(input_fasta, model_path="ProstT5_Local"):

    print(f"[Module 3.2] Calling ProstT5 engine to encode {input_fasta}...")
    output_pkl = "step3_embeddings.pkl" 
    return output_pkl

# MODULE 3.3: Functional Similarity Characterization
def select_core_subset_by_similarity(emb_pkl, anchor_pkl, retention=0.25):

    print(f"[Module 3.3] Selecting core subset via functional similarity (Top {retention*100}%)...")
    
    with open(emb_pkl, "rb") as f: res_dis = pickle.load(f)
    with open(anchor_pkl, "rb") as f: res_ref = pickle.load(f)

    candidate_matrix = np.array(res_dis["representations"])
    anchor_centroid = np.mean(res_ref["representations"], axis=0).reshape(1, -1)
    
    similarities = cosine_similarity(candidate_matrix, anchor_centroid).flatten()
    sorted_idx = np.argsort(similarities)[::-1]
    cutoff = int(len(sorted_idx) * retention)
    
    core_subset = pd.DataFrame({
        "Sequence_ID": [res_dis["labels"][i] for i in sorted_idx[:cutoff]],
        "Similarity": similarities[sorted_idx[:cutoff]]
    })
    core_subset.to_csv("step3_core_subset.csv", index=False)
    print(f"-> Captured {len(core_subset)} core functional candidates.")
    return core_subset


# =============================================================================
# Step 4: Manifold Projection and Spatial Clustering
# =============================================================================
#
# Overview:
# ---------
# Fits a UMAP dimensionality reduction model on the structural background 
# database (EC Background) and projects the candidate embeddings into this 
# coordinate space. Applies the HDBSCAN algorithm with a dynamically 
# calculated minimum cluster size to assign cluster labels.
#
# -------------
# What you need to prepare before you submit the job:
# - Python environment with `umap-learn`, `scikit-learn`, `matplotlib`, `pandas`
# - Input: step3_embeddings.pkl, reference_anchors.pkl, ec_background.pkl
#   (ec_background.pkl is a global background library used to construct bias-free manifold spaces. 
#    It contains protein structure embedding vectors that have been randomly sampled 
#    from UniProt or are widely distributed by EC number.)
# - Output: step4_functional_landscape.csv, step4_final_targets.fasta
#
# =============================================================================

# MODULE 4.1: Background Calibration & Core Subset Filtering
def align_multimodal_data(ref_path, discover_path, ec_path, core_subset_csv="step3_core_subset.csv"):
    print("[Module 4.1] Calibrating feature space and filtering core subset...")
    res_ref = pickle.load(open(ref_path, "rb"))
    res_dis = pickle.load(open(discover_path, "rb"))
    res_ec = pickle.load(open(ec_path, "rb"))

    if os.path.exists(core_subset_csv):
        print(f"-> Applying filter from {core_subset_csv}...")
        core_df = pd.read_csv(core_subset_csv)
        valid_ids = set(core_df["Sequence_ID"])
        
        filtered_repr, filtered_labels = [], []
        for rep, label in zip(res_dis["representations"], res_dis["labels"]):
            if label in valid_ids:
                filtered_repr.append(rep)
                filtered_labels.append(label)
                
        res_dis["representations"] = np.array(filtered_repr)
        res_dis["labels"] = filtered_labels
        print(f"-> Retained {len(filtered_labels)} core sequences for projection.")
    else:
        print("-> WARNING: Core subset CSV not found. Proceeding with full dataset.")

    scaler = StandardScaler().fit(res_ec["representations"])
    
    merged_repr = np.concatenate([
        scaler.transform(res_ref["representations"]),
        scaler.transform(res_dis["representations"]),
        scaler.transform(res_ec["representations"])
    ], axis=0)

    source_tags = (["Reference"] * len(res_ref["representations"]) +
                   ["Candidate"] * len(res_dis["representations"]) +
                   ["EC_Background"] * len(res_ec["representations"]))
                   
    merged_labels = res_ref["labels"] + res_dis["labels"] + res_ec["labels"]
    
    return merged_repr, source_tags, merged_labels

# MODULE 4.2: Unbiased Manifold Projection
def project_to_stable_functional_landscape(aligned_matrix, source_tags):
    print("[Module 4.2] Projecting sequences to stable functional landscape...")
    
    indices_bg = [i for i, tag in enumerate(source_tags) if tag == "EC_Background"]
    indices_targets = [i for i, tag in enumerate(source_tags) if tag != "EC_Background"]
    
    reducer = umap.UMAP(
        n_neighbors=UMAP_N_NEIGHBORS, 
        min_dist=UMAP_MIN_DIST,
        metric=UMAP_METRIC,
        random_state=42
    )
    reducer.fit(aligned_matrix[indices_bg]) 
    
    coords_targets = reducer.transform(aligned_matrix[indices_targets])
    
    final_coords = np.zeros((aligned_matrix.shape[0], 2))
    final_coords[indices_bg] = reducer.embedding_
    final_coords[indices_targets] = coords_targets
    
    return final_coords

# MODULE 4.3: Dynamic Spatial Density Clustering 
def characterization_spatial_clusters(embedding_2d, source_tags, merged_labels):
    dynamic_min_size = max(10, len(embedding_2d) // 100)
    print(f"[Module 4.3] Clustering via HDBSCAN (Dynamic min_cluster_size: {dynamic_min_size})...")
    
    clusterer = hdbscan.HDBSCAN(min_cluster_size=dynamic_min_size)
    spatial_labels = clusterer.fit_predict(embedding_2d)
    
    df_results = pd.DataFrame({
        "Sequence_ID": merged_labels,
        "Source": source_tags,
        "UMAP_1": embedding_2d[:, 0], 
        "UMAP_2": embedding_2d[:, 1],
        "Cluster_ID": spatial_labels
    })
    
    df_results.to_csv("step4_functional_landscape.csv", index=False)
    print("-> Functional landscape exported successfully.")
    return df_results

# MODULE 4.4: Target Sequence Extraction
def extract_final_targets(landscape_csv, source_fasta="step2_final_nonredundant.fasta", target_cluster=0):
    print(f"[Module 4.4] Extracting sequences for Cluster {target_cluster} to FASTA...")
    
    df = pd.read_csv(landscape_csv)
    target_ids = set(df[(df["Source"] == "Candidate") & (df["Cluster_ID"] == target_cluster)]["Sequence_ID"])
    
    final_records = []
    for record in SeqIO.parse(source_fasta, "fasta"):
        if record.id in target_ids:
            final_records.append(record)
            
    output_fasta = "step4_final_targets.fasta"
    SeqIO.write(final_records, output_fasta, "fasta")
    print(f"-> Exported {len(final_records)} final target sequences for wet-lab validation.")
    return output_fasta