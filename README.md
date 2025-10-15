# Temporal Embeddings of Surface Spectra for Earth Representation and Analysis (TESSERA)
<a name="readme-top"></a>
<div>
    <a align="center">
        <img src="images/banner.png"> 
    </a>
    <p align="center">
        <div style="display: flex; justify-content: space-evenly; align-items: center; width: 100%;">
<!--             <a href="https://www.youtube.com/watch?v=eERBj4FUD3s" style="flex-grow: 1; text-align: center; padding: 0 10px;">View Our Talk 🌐</a>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; -->
            <a href="http://arxiv.org/abs/2506.20380" style="flex-grow: 1; text-align: center; padding: 0 10px;">View Our Paper :bookmark_tabs:</a>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;
            <a href="https://github.com/FrankFeng-23/btfm_project/issues" style="flex-grow: 1; text-align: center; padding: 0 10px;">Report Bug :hammer_and_wrench:</a>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;
            <a href="https://github.com/FrankFeng-23/btfm_project/issues" style="flex-grow: 1; text-align: center; padding: 0 10px;">Request Feature 🙋</a>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;
            <a href="https://svr-sk818-web.cl.cam.ac.uk/tessera/index.php/Acceptable_use_policy" style="flex-grow: 1; text-align: center; padding: 0 10px;">Acceptable Use Policy</a>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;
            <a href="https://svr-sk818-web.cl.cam.ac.uk/keshav/wiki/images/9/9d/TESSERA.m4a" style="flex-grow: 1; text-align: center; padding: 0 10px;">Podcast 🎧</a>
        </div>
    </p>
</div>

<!--  ![Version](https://img.shields.io/badge/version-alpha-red) -->
![PyPI version](https://img.shields.io/pypi/v/geotessera?label=PyPI%20version&color=blue)
![License](https://img.shields.io/badge/License-MIT-blue.svg)


## Table of Contents

  - [Introduction](#introduction)
  - [Representation Visualization](#representation-visualization)
  - [Global Embeddings Access](#global-embeddings-access)
  - [Hardware Requirements](#hardware-requirements)
  - [Data Preprocessing](#data-preprocessing)
  - [Inference](#inference)
  - [Metrics & Benchmarking](#metrics--benchmarking)
  - [Downstream Tasks](#downstream-tasks)
  - [Citation](#citation)
  - [Acknowledgments](#acknowledgments)
  - [Star History](#star-history)

## Introduction

Satellite remote sensing enables a wide range of downstream applications, including habitat mapping, carbon accounting, and strategies for conservation and sustainable land use. However, satellite time series are voluminous and often corrupted, making them challenging to use: the scientific community's ability to extract actionable insights is often constrained by the scarcity of labelled training datasets and the computational burden of processing temporal data.

Our work introduces TESSERA, an open foundation model that preserves spectral-temporal signals in 128-dimensional latent representations at 10-meter resolution globally. It uses self-supervised learning to summarise petabytes of Earth observation data. We compare our work with state-of-the-art task-specific models and other foundation models in five diverse downstream tasks and find that TESSERA closely matches or outperforms these baselines. By preserving temporal phenological signals that are typically lost in conventional approaches, TESSERA enables new insights into ecosystem dynamics, agricultural food systems, and environmental change detection. Moreover, our open-source implementation supports reproducibility and extensibility, while the privacy-preserving design allows researchers to maintain data sovereignty.

To our knowledge, TESSERA is unprecedented in its ease of use, scale, and accuracy: no other foundation model provides analysis-ready outputs, is open, and provides global, annual coverage at 10m resolution using only spectral-temporal features at pixel level.

## Representation Visualization

Below are some visualization results of the TESSERA representation map (using the first three channels as RGB):

![repr_demo](images/repr_demo.png)


## Global Embeddings Access

We are currently generating global 10m resolution embeddings, which can be directly downloaded and used for downstream applications, saving significant computational time and resources. We are starting with embeddings for 2024 and will progressively extending coverage backwards year by year until 2017. The current coverage map is below:

<img src="https://github.com/ucam-eo/tessera-coverage-map/blob/main/map.png"> 


**Access Global Embeddings:** https://github.com/ucam-eo/geotessera

<span style="color:red;">This text is redWe strongly recommend that you quickly review the entire tutorial before running the pipeline.</span> 

## Hardware Requirements

### 1. Storage Requirements

Running this pipeline requires substantial storage space. Although the pipeline cleans up some intermediate files after processing, the downloaded raw Sentinel-2 and Sentinel-1 files will still occupy considerable disk space. For example, processing a 100km×100km area from 2022 to output a TESSERA Representation map (10m resolution) requires at least 1TB of storage.

### 2. Memory Requirements

Thanks to Microsoft Planetary Computer, most of the geo-preprocessing has been done. Still, we recommend having at least 128GB of RAM.

### 3. CPU and GPU

The pipeline has no strict requirements for CPU and GPU, but more CPU cores and more powerful GPUs can significantly speed up inference. When processing a 110km×110km area from 2022, our tests using a 128-core CPU and a single NVIDIA A30 GPU for inference (CPU and GPU each handling 50% of the inference) took approximately 10 hours to complete.

### 4. Operating System

For the data preprocessing pipeline, we support almost all Linux and macOS systems. For Windows, we recommend using WSL.

For the model inference part, we have only tested it on Linux and Windows WSL, and they are working.

## Data Preprocessing

### Overview

In this step, we stack a full year of Sentinel-1 and Sentinel-2 data along the time dimension to generate a composite. For Sentinel-2, the composite shape is (T,H,W,B), where T is the number of valid observations in that year, and B is the number of bands (we selected 10 bands). For Sentinel-1, we extracted both ascending and descending orbit data. Taking the ascending orbit as an example, the composite shape is (T',H,W,B'), where T' is the number of valid ascending observations in that year, and B' is 2 because we only obtain VV and VH bands.

We source Sentinel-1 and Sentinel-2 data from Microsoft's Planetary Computer, which has been preprocessed to a large extent and can be used directly. This saves a lot of data preprocessing trouble.
- Sentinel-1 data source: https://planetarycomputer.microsoft.com/dataset/sentinel-1-rtc
- Sentinel-2 data source: https://planetarycomputer.microsoft.com/dataset/sentinel-2-l2a

Currently, our pipeline only accepts TIFF format input. The resolution of the tiff file can vary, but up to 10m granularity as this is the highest resolution for Sentinel-2 imagery. For valid ROI areas within the TIFF, the value is 1; otherwise, it's 0. If you only have a shapefile, that's fine too - we provide a `convert_shp_to_tiff.py` script.

### Download Source Code

First, create an empty working directory:

```bash
mkdir tessera_project
cd tessera_project
git clone https://github.com/FrankFeng-23/btfm_project.git
```

For easier pipeline operation, we recommend placing the data output directory at the same level as `tessera_infer` and `tessera_preprocessing`:

```
tessera_project
 ┣ tessera_infer
 ┣ tessera_preprocessing
 ┣ my_data
   ┣ roi.shp (your shapefile)
   ┗ roi.tiff (we recommend generating this using convert_shp_to_tiff.py)
```

The `roi.tiff` can be generated using `convert_shp_to_tiff.py` located in `tessera_preprocessing/convert_shp_to_tiff.py`. To use it, simply specify the path to your shapefile in the main function, and it will output a TIFF with the same name in the same directory.

### Python Environment

We need some geographic processing packages (fortunately, we won't be using GDAL, as configuring the environment is a nightmare) and some machine learning packages (PyTorch, but you'll need to install this yourself since the hardware on each computer is different). We've put some common packages in `requirements.txt`, which you can install as follows:

```bash
pip install -r requirements.txt
```

### Script Configuration

We use Microsoft's Planetary Computer, which eliminates much of the hassle of data preprocessing, especially for Sentinel-1. The script configuration is very simple. First, navigate to the `tessera_preprocessing` folder:

```bash
cd tessera_preprocessing
```

Then modify the following:

```bash
# === Basic Configuration ===
INPUT_TIFF="/absolute/path/to/your/data_dir/roi.tiff"
OUT_DIR="/absolute/path/to/your/data_dir"

export TEMP_DIR="/absolute/path/to/your/temp_dir"     # Temporary file directory

mkdir -p "$OUT_DIR"

# Python environment path
PYTHON_ENV="/absolute/path/to/your/python_env/bin/python"

# === Sentinel-1 & Sentinel-2 Processing Configuration ===
YEAR=2022 # Range [2017-2024]
RESOLUTION=10.0  # Resolution of the input TIFF, also the output resolution (meters)
```

Note that the `RESOLUTION` needs to match the resolution of your input TIFF; otherwise, there may be misalignments in geographic coverage. Below the above configuration, there are some additional configurations that you can modify according to your computer's performance.

First, give permission to `s1_s2_downloader.sh`:

```bash
chmod +x s1_s2_downloader.sh
```

Then, we can run:

```bash
bash s1_s2_downloader.sh
```

Due to network conditions, processing some tiles may time out. Our script includes sophisticated timeout management to avoid these issues. However, sometimes some tiles may still fail. Running the above command again usually resolves this.

If all Sentinel-1 and Sentinel-2 data are generated correctly, they can be stacked along the time dimension. For this step, we use two Rust-generated executables, making it very fast. You can open `s1_s2_stacker.sh` and edit the following:

```bash
# === Basic Configuration ===
BASE_DIR="/absolute/path/to/your/data_dir"
OUT_DIR="${BASE_DIR}/data_processed"
DOWNSAMPLE_RATE=1
```

Normally, we don't modify `DOWNSAMPLE_RATE`, which keeps it from performing any downsampling during stacking. The `BASE_DIR` in the above snippet is the same as the `OUT_DIR` you modified in `s1_s2_downloader.sh`.

Similarly, give permission to `s1_s2_stacker.sh`:

```bash
chmod +x s1_s2_stacker.sh
```

Then you can execute the stacking:

```bash
bash s1_s2_stacker.sh
```

After success, you will get some `.npy` files in `/absolute/path/to/your/data_dir/data_processed`. Usually, these `.npy` files are quite large, so we will patchify them into smaller, more manageable units.

Execute:

```bash
python dpixel_retiler.py \
    --tiff_path /absolute/path/to/your/data_dir/roi.tif \
    --d_pixel_dir /absolute/path/to/your/data_dir/data_processed \
    --patch_size 500 \
    --out_dir /absolute/path/to/your/data_dir/retiled_d_pixel \
    --num_workers 16 \
    --overwrite \
    --block_size 2000
```

You can change the above `patch_size` and `block_size` yourself. The above configuration is a recommended configuration for a TIFF with a shape of (5000,5000) and a 10m resolution.

If the above code runs smoothly, you can get some subfolders in `my_data/retiled_d_pixel`.

## Inference

### Overview

Once the data preprocessing is complete, we can start inference. Before proceeding, please check if there are subfolders in the `my_data/retiled_d_pixel` folder like:
```
retiled_d_pixel
 ┣ 0_3500_500_4000
 ┣ 0_4000_500_4500
 ┣ 0_4500_500_5000
 ┣ 0_5000_500_5500
 ┣ 0_5500_500_6000
 ┣ 0_6000_500_6500
```

Each subfolder should contain the following files:
```
0_3500_500_4000
 ┣ bands.npy
 ┣ doys.npy
 ┣ masks.npy
 ┣ roi.tiff
 ┣ sar_ascending.npy
 ┣ sar_ascending_doy.npy
 ┣ sar_descending.npy
 ┗ sar_descending_doy.npy
```

If these files exist, you can start inference. Otherwise, check if the first step completed successfully.

## Metrics & Benchmarking

This repository includes low‑overhead, opt‑in metrics for CPU preprocessing so you can estimate wall time, CPU hours, memory headroom, and throughput before refactoring.

- General tips
  - Use a fast local/NVMe temp directory to reduce I/O stalls: `export TEMP_DIR=/fast/tmp`.
  - The processors save a Dask performance report next to the output as `dask-report-<partition_id>.html`.
  - You can also wrap the entire command with your system `/usr/bin/time -p` (or GNU time) to capture whole‑process timing.

### Sentinel‑2 (S2) CPU metrics

- Enable metrics JSONL when running preprocessing:
  - `python tessera_preprocessing/s2_fast_processor.py --input_tiff /path/roi.tif --start_date 2020-01-01 --end_date 2020-12-31 --output /data/s2_out --stac_endpoint https://earth-search.aws.element84.com/v1 --stac_collection sentinel-2-l2a --dask_workers 8 --worker_memory 16 --metrics_jsonl /data/s2_out/metrics/s2_metrics.jsonl`
  - Optional tunables (new): `--threads_per_worker 2|4`, `--mem_guard_frac 0.6`, `--mem_guard_cap_gb 32`, and Dask spilling knobs `--dask_mem_target 0.6 --dask_mem_spill 0.75 --dask_mem_pause 0.9 --dask_mem_terminate 0.99`.
- Optional whole‑process timing (CPU hours, max RSS) using system time:
  - `/usr/bin/time -p sh -c 'python tessera_preprocessing/s2_fast_processor.py ...same args...'`
- Summarize S2 run:
  - `python tessera_preprocessing/tools/summarize_metrics.py --metrics /data/s2_out/metrics/s2_metrics.jsonl`
- Summary includes:
  - CPU hours (sum over process tree), max RSS, days processed, useful write rate (MiB/s), total bytes written (GiB), and SCL valid% (mean/median/p10/p90).

### Sentinel‑1 (S1) CPU metrics

- Enable metrics JSONL when running preprocessing:
  - `python tessera_preprocessing/s1_fast_processor.py --input_tiff /path/roi.tif --start_date 2020-01-01 --end_date 2020-12-31 --output /data/s1_out --orbit_state both --dask_workers 8 --worker_memory 16 --workers 8 --metrics_jsonl /data/s1_out/metrics/s1_metrics.jsonl`
  - Optional tunables (new): `--threads_per_worker 2|4` and optional Dask spilling knobs `--dask_mem_target ... --dask_mem_spill ... --dask_mem_pause ... --dask_mem_terminate ...`.
- Optional whole‑process timing (CPU hours, max RSS) using system time:
  - `/usr/bin/time -p sh -c 'python tessera_preprocessing/s1_fast_processor.py ...same args...'`
- Summarize S1 run:
  - `python tessera_preprocessing/tools/summarize_s1_metrics.py --metrics /data/s1_out/metrics/s1_metrics.jsonl`
- Summary includes:
  - CPU hours (proc‑tree), max RSS, processed groups (date+orbit), useful write rate, total bytes written (GiB), outcome counts (both VV/VH, VV‑only, VH‑only, failed), and per‑item tallies (processed/skipped/no_data/failed).

Inference requires PyTorch. Since each system may have slightly different CUDA versions, we can't provide a Docker-encapsulated Python environment like we did for data preprocessing. Fortunately, the Python environment for inference is much simpler to configure than for data preprocessing, as it doesn't use geographic processing packages like GDAL or SNAP.

### Pytorch Preparation

If you haven't installed Pytorch, you can refer to the steps below. Otherwise, you can ignore this section.

First, check your system's CUDA version:

```bash
nvidia-smi
```

Then visit https://pytorch.org/ and select the appropriate version to install based on your CUDA version, for example:

```bash
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128
```

### Model Weight

Next, download the model weights from [Google Drive](https://drive.google.com/drive/folders/18RPptbUkCIgUfw1aMdMeOrFML_ZVMszn?usp=sharing) (please request for access) and place the `.pt` file in the `tessera_infer/checkpoints` directory:

```
tessera_infer
 ┗ checkpoints
     ┗ best_model_fsdp_20250427_084307.pt
 ┗ configs
 ┗ src
```

### Configure Bash Script

To simplify inference configuration, we provide `tessera_infer/infer_all_tiles.sh`. You only need to edit a few parameters:

a. Base data directory:
```bash
BASE_DATA_DIR="your_data_directory"
```
This is your data storage folder, the same as `BASE_DATA_DIR` in the previous bash, e.g., `/maps/usr/tessera_project/my_data`

b. Python environment:
```bash
export PYTHON_ENV="your_python_path"
```
Write the absolute path to your Python environment here, e.g., `/home/user/anaconda3/envs/tessera_env/bin/python`

c. CPU/GPU split:
```bash
CPU_GPU_SPLIT="1:1"  # Format: CPU:GPU ratio
```
The script supports simultaneous inference using both CPU and GPU. This ratio specifies the proportion of `retiled_patches` each device will handle. Default is 1:1 (even split). For GPU-only inference, set to 0:1.

d. CPU Related Settings

```bash
MAX_CONCURRENT_PROCESSES_CPU=20
```
Maximum number of CPU processes for tile inference. For example, if set to 20, it will process 20 tiles simultaneously.

```bash
AVAILABLE_CORES=$((TOTAL_CPU_CORES / 2)) # Use 50% of the cores
```
Number of CPU cores to use. Please modify this value if necessary to avoid consuming too many CPU resources!

e. GPU Related Settings:
```bash
MAX_CONCURRENT_PROCESSES_GPU=1
```
Maximum number of GPU processes for inference. If the system has only 1 GPU, set this to 1.

```bash
GPU_BATCH_SIZE=1024  # Larger for GPU, if this takes too much memory, reduce it
```
Number of samples to process at once during PyTorch inference. If this value consumes too much GPU memory or causes an OOM error on the GPU, please reduce it accordingly.

f. Other Settings
There are other parameters available for configuration. Please adjust them as needed.

### Start Inference

Once everything is ready, navigate to the `tessera_infer` folder:

```bash
cd tessera_infer
```

Then give permission to `infer_all_tiles.sh`:

```bash
chmod +x infer_all_tiles.sh
```

Then run it:

```bash
bash infer_all_tiles.sh
```

If successful, you should see logs like:

```
(base) zf281@daintree:/scratch/zf281/tessera_project/tessera_infer$ bash infer_all_tiles.sh
[INFO] Total CPU cores: 256, Using: 192
[INFO] CPU:GPU split ratio = 1:1 (total: 2)

==== SETUP DIRECTORIES ====
[SUCCESS] Created necessary directories

==== SCANNING TILES ====
[INFO] Tile directory: /scratch/zf281/jovana/retiled_d_pixel
[INFO] Output directory: /scratch/zf281/jovana/representation_retiled
[SUCCESS] Found 226 tiles total
[INFO] Sample tiles:
  - 0_3500_500_4000
  - 0_4000_500_4500
  - 0_4500_500_5000
  - ...
```

At the same time, a `logs` folder will be generated in the `tessera_infer` folder with more detailed logging for each CPU and GPU process.

### Stitch Final Representation Map

Inference usually takes a long time, depending on your ROI size and hardware performance. Once completed, you can find many `.npy` files in `my_data/representation_retiled`:

```
representation_retiled
 ┣ 0_3500_500_4000.npy
 ┣ 0_4000_500_4500.npy
 ┣ 0_4500_500_5000.npy
 ┣ 0_5000_500_5500.npy
 ┣ 0_5500_500_6000.npy
 ┣ 0_6000_500_6500.npy
 ┣ 0_6500_500_7000.npy
 ┣ 0_7000_500_7500.npy
 ┣ 1000_0_1500_500.npy
 ┣ 1000_1000_1500_1500.npy
 ┣ 1000_1500_1500_2000.npy
 ┣ 1000_2000_1500_2500.npy
```

The final step is to stitch them together using `tessera_infer/stitch_tiled_representation.py`:

```bash
python stitch_tiled_representation.py \
--d_pixel_retiled_path /path/to/d_pixel_retiled \
--representation_retiled_path /path/to/representation_retiled \
--downstream_tiff /path/to/downstream.tiff \
--out_dir /path/to/output_directory
```

For example:

```bash
python stitch_tiled_representation.py \
--d_pixel_retiled_path /maps/usr/tessera_project/my_data/d_pixel_retiled \
--representation_retiled_path /maps/usr/tessera_project/my_data/representation_retiled \
--downstream_tiff /maps/usr/tessera_project/my_data/downstream.tiff \
--out_dir /maps/usr/tessera_project/my_data
```

Finally, you'll get a stitched representation map in the `my_data` directory with the shape (H,W,128), where H and W match your initial `roi.tiff`. The representation map is a NumPy array. If you want to convert it to TIFF for viewing in software like QGIS, you can use the `tessera_infer/convert_npy2tiff.py` script. Just modify the main function with:

```python
npy_path = "/maps/usr/tessera_project/my_data/stitched_representation.npy"  # Change to the actual npy file path
ref_tiff_path = "/maps/usr/tessera_project/my_data/roi.tiff"  # Change to the actual reference tiff file path
out_dir = "/maps/usr/tessera_project/my_data/"  # Change to the actual output directory
```

## Quick ROI + AWS Smoke Test

Create a per‑tile ROI once and run a short, low‑cost Sentinel‑2 CPU test on AWS.

1) Install utility‑only dependencies (separate from pipeline requirements):

```bash
pip install geopandas pyogrio shapely rasterio fiona numpy pyarrow requests
# or with uv
uv pip install -q geopandas pyogrio shapely rasterio fiona numpy pyarrow requests
```

2) Create a 10 m ROI TIFF for MGRS tile 31TCH:

```bash
python util/fetch_s2_tile_and_make_roi.py --tile 31TCH --make_roi_tiff
```

What you should see

- <repo_root>/data/grids/31TCH.geojson
- <repo_root>/data/grids/31TCH.gpkg
- <repo_root>/data/grids/31TCH_roi_10m.tiff

3) Upload the ROI once to your bucket (example uses tessera-test1):

```bash
aws s3 cp <repo_root>/data/grids/31TCH_roi_10m.tiff s3://tessera-test1/rois/31TCH_roi_10m.tiff
```

4) Launch the 3‑day smoke test on EC2

- Use the user‑data in `docs/aws_s2_run_and_publish.md` and set:
  - `S3_BUCKET_PREFIX="s3://tessera-test1/tessera/s2"`
  - `ROI_TIFF_S3="s3://tessera-test1/rois/31TCH_roi_10m.tiff"`

Recommended instance for the smoke test: `m7i.xlarge` (4 vCPU, 16 GB RAM) with ~150 GB gp3 and an instance role that allows `s3:PutObject` and `s3:ListBucket` to your bucket.

### S2 smoke test: stack to NPYs and publish (local or EC2)

Once your CPU mosaics write successfully, stack to NPYs and (optionally) publish logs/metrics and NPYs to S3. You can run the individual commands or the one‑shot wrapper.

- Individual commands (useful for debugging):

```bash
# 0) (Optional) If a band was skipped (e.g., B04/red), rerun with smaller chunks
python tessera_preprocessing/s2_fast_processor.py \
  --input_tiff /data/grids/roi.tiff \
  --start_date 2024-04-15 --end_date 2024-04-17 \
  --output /data/s2_out_smoke \
  --dask_workers 1 --worker_memory 16 --threads_per_worker 4 \
  --chunksize 256 --mem_guard_frac 0.9 --min_coverage 0 \
  --partition_id 31TCH_2024_SMOKE

# 1) Stack per‑band TIFFs → NPYs
./tessera_preprocessing/s2_stack \
  --input /data/s2_out_smoke \
  --output /data/s2_npys_smoke \
  --batch-size 8 --cache-level 1 --num-threads 8 --sample-rate 1

# 2) Validate shapes
python - << 'PY'
import os, numpy as np
root='/data/s2_npys_smoke'
for f in ('bands.npy','masks.npy','doys.npy'):
    p=os.path.join(root,f); a=np.load(p, mmap_mode='r'); print(f, a.shape, a.dtype)
PY

# 3) Summarize CPU metrics
python tessera_preprocessing/tools/summarize_metrics.py --metrics /data/s2_out_smoke/metrics/s2_metrics.jsonl

# 4) Publish logs/metrics (optional)
bash tessera_preprocessing/tools/publish_to_s3.sh \
  --local-root /data/s2_out_smoke \
  --partition-id 31TCH_2024_SMOKE \
  --s3 s3://tessera-test1/tessera/s2 \
  --upload-outputs 0

# 5) Publish NPYs (optional)
aws s3 sync /data/s2_npys_smoke s3://tessera-test1/tessera/s2_npys/31TCH_2024_SMOKE/$(date -u +%Y%m%dT%H%M%SZ)/ --only-show-errors --no-progress
```

- One‑shot wrapper (recommended after you confirm the ROI and dates):

```bash
bash tessera_preprocessing/tools/run_s2_smoke_e2e.sh \
  --roi_tiff /data/grids/31TCH_roi_10m.tiff \
  --start 2024-04-15 --end 2024-04-17 \
  --local-root /data/s2_out_smoke \
  --npys-out /data/s2_npys_smoke \
  --partition 31TCH_2024_SMOKE \
  --s3 s3://tessera-test1/tessera/s2 \
  --s3-npys s3://tessera-test1/tessera/s2_npys \
  --dask-workers 1 --worker-mem 16 --threads 4 --chunksize 256 --mem-guard-frac 0.9 \
  [--cleanup-mosaics 0|1]
```

Tuning for more days
- Increase `--end` range and (optionally) `--dask-workers` when memory allows.
- If you see a band skipped by the memory guard, reduce `--chunksize` (e.g., 512→256) or increase instance RAM.
- Keep BLAS threads at 1 to avoid oversubscription: `OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1` (wrapper sets these).

End‑to‑end metrics (optional, included in wrapper)

- The wrapper now records step metrics for both phases to `e2e.jsonl` under `--local-root/metrics/` via `tessera_preprocessing/tools/measure_subprocess.py`. It tracks per‑step wall time, approximate proc‑tree CPU seconds, max RSS across the process tree, and bytes written under the tracked output directories.
- Validate the stacked NPYs and capture their shapes with `tessera_preprocessing/tools/validate_s2_npys.py`. The wrapper appends a `npy_validate` event to `e2e.jsonl` and prints a one‑line summary.
- To summarize end‑to‑end, use:
  - `python tessera_preprocessing/tools/summarize_e2e.py --e2e /data/s2_out_smoke/metrics/e2e.jsonl`
- The S3 publisher (`tools/publish_to_s3.sh`) uploads `e2e.jsonl` and `summary_e2e.txt` alongside existing logs/metrics.

Observability checklist (quick sanity during a run)
- Tail wrapper logs:
  - `tail -n 120 /data/s2_out_smoke/s2_<PARTITION>_detail.log`
  - `tail -n 80 /data/s2_npys_smoke/s2_stack_wrapper.log`
- Summaries (always fresh per wrapper run):
  - `python tessera_preprocessing/tools/summarize_metrics.py --metrics /data/s2_out_smoke/metrics/s2_metrics.jsonl`
  - `python tessera_preprocessing/tools/summarize_e2e.py --e2e /data/s2_out_smoke/metrics/e2e.jsonl`
- Dask report (HTML): `/data/s2_out_smoke/dask-report-<PARTITION>.html`

Notes on dates and metrics files
- Date-only `--start/--end` cover full days in UTC: start at `T00:00:00Z` and end at the next midnight (exclusive). For a single day you can use `--start 2024-04-16 --end 2024-04-16`.
- The wrapper truncates `metrics/s2_metrics.jsonl` and `metrics/e2e.jsonl` at start, so each run’s summaries reflect only the current run. If you need to manually clear them before re-running, use:
  - `: > /data/s2_out_smoke/metrics/s2_metrics.jsonl && : > /data/s2_out_smoke/metrics/e2e.jsonl`

Optional cleanup
- Add `--cleanup-mosaics 1` to remove the per-band mosaics (blue/green/red/…/scl) under `--local-root` after a successful stack + validation. Temporary directories created under `/tmp` are already cleaned by the CPU step.

## Downstream tasks

If you want to reproduce the downstream tasks in the paper, you can visit https://github.com/ucam-eo/tessera-downstream-task. There are many examples provided there.

## Citation

If you use TESSERA in your research, please cite the [arXiv paper](https://arxiv.org/abs/2506.20380):

```bibtex
@misc{feng2025tesseratemporalembeddingssurface,
      title={TESSERA: Temporal Embeddings of Surface Spectra for Earth Representation and Analysis}, 
      author={Zhengpeng Feng et al.},
      year={2025},
      eprint={2506.20380},
      archivePrefix={arXiv},
      primaryClass={cs.LG},
      url={https://arxiv.org/abs/2506.20380}, 
}
```

## Acknowledgments
We would like to express our gratitude to [DAWN](https://www.hpc.cam.ac.uk/d-w-n), the fastest artificial intelligence supercomputer at Cambridge, and AMD for their generous support in this project. This work would not have been possible without their computational resources and technical assistance.


## Star History
[![Star History Chart](https://api.star-history.com/svg?repos=ucam-eo/tessera&type=Date)](https://www.star-history.com/#ucam-eo/tessera&Date)
