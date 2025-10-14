# AWS: Run Sentinel‑2 CPU preprocessing and publish logs/metrics to S3

This guide shows how to run the S2 CPU step on a single EC2 instance (LocalCluster) and then push logs and metrics to S3, without changing any pipeline code or shell wrappers. You can keep using the existing S1/S2 downloaders independently.

## Prerequisites

- An S3 bucket (enable versioning and an optional lifecycle policy).
- An instance profile/role with minimal S3 permissions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:PutObject","s3:PutObjectAcl"],
      "Resource": "arn:aws:s3:::YOUR_BUCKET/YOUR_PREFIX/*"
    },
    {
      "Effect": "Allow",
      "Action": ["s3:ListBucket"],
      "Resource": "arn:aws:s3:::YOUR_BUCKET"
    }
  ]
}
```

## Instance sizing (single MGRS tile)

- Test (1–3 months window): 8 vCPU, 32–64 GB RAM (e.g., `m7i.2xlarge`/`r7i.2xlarge`).
- Annual (1 year): 16 vCPU, 64–128 GB RAM (e.g., `r7i.4xlarge`).
- Storage: 500 GB–1 TB gp3 if you keep GeoTIFFs + NPYs locally; otherwise smaller if you publish to S3 and prune.

## User‑data script (runs S2 then publishes logs/metrics)

Paste the script below as EC2 user‑data for an Ubuntu AMI. It installs dependencies, runs S2 against AWS Earth Search, summarizes metrics, and then pushes logs/metrics to S3 using the included publisher script.

Adjust variables at the top (S3 bucket/prefix, ROI path, dates, workers).

```bash
#!/bin/bash
set -euxo pipefail
export DEBIAN_FRONTEND=noninteractive

# ==== CONFIGURE THESE ====
export S3_BUCKET_PREFIX="s3://tessera-test1/tessera/s2"   # where logs/metrics go
export PARTITION_ID="31TCH_2024Q2"                      # label for this run
export ROI_TIFF_S3="s3://tessera-test1/rois/31TCH.tiff"  # ROI template (10 m) in S3
export START_DATE="2024-04-01"
export END_DATE="2024-06-30"
export DASK_WORKERS=4
export WORKER_MEMORY_GB=12
export OUT_DIR="/data/s2_out"
export TEMP_DIR="/mnt/nvme/tmp"
export REPO_URL="https://github.com/ucam-eo/tessera.git"  # or your fork/zip source

# ==== SYSTEM PREP ====
apt-get update
apt-get install -y python3-venv python3-pip git awscli
mkdir -p "$TEMP_DIR" || true
mkdir -p "$OUT_DIR/metrics" /data/grids

# ==== FETCH REPO ====
cd /root
if [[ ! -d tessera ]]; then
  git clone "$REPO_URL"
fi
cd tessera

python3 -m venv /root/venv
source /root/venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# ==== ROI ====
aws s3 cp "$ROI_TIFF_S3" /data/grids/roi.tiff --no-progress

# ==== RUN S2 ====
python tessera_preprocessing/s2_fast_processor.py \
  --input_tiff /data/grids/roi.tiff \
  --start_date "$START_DATE" --end_date "$END_DATE" \
  --output "$OUT_DIR" \
  --stac_endpoint https://earth-search.aws.element84.com/v1 \
  --stac_collection sentinel-2-l2a \
  --dask_workers "$DASK_WORKERS" --worker_memory "$WORKER_MEMORY_GB" \
  --chunksize 1024 --resolution 10 \
  --min_coverage 10 \
  --partition_id "$PARTITION_ID" \
  --metrics_jsonl "$OUT_DIR/metrics/s2_metrics.jsonl"

# Summarize metrics (optional human-readable)
python tessera_preprocessing/tools/summarize_metrics.py \
  --metrics "$OUT_DIR/metrics/s2_metrics.jsonl" \
  > "$OUT_DIR/metrics/summary.txt" || true

# ==== PUBLISH LOGS/METRICS TO S3 ====
bash tessera_preprocessing/tools/publish_to_s3.sh \
  --local-root "$OUT_DIR" \
  --partition-id "$PARTITION_ID" \
  --s3 "$S3_BUCKET_PREFIX" \
  --upload-outputs 0 \
  --delete-local 0

# Optional: power off after completion
# shutdown -h now
```

## Notes

- The publisher is in `tessera_preprocessing/tools/publish_to_s3.sh`. It uploads logs and metrics to:
  `s3://<bucket>/<prefix>/<partition_id>/<run_id>/logs|metrics`, plus `manifest.json`.
- Set `--upload-outputs 1` if you also want to sync the mosaics/NPYs to S3 (larger transfer).
- Keep `--delete-local 0` during testing. Flip to `1` to reclaim EBS after a successful upload.
- Dask dashboard is written to `dask-report-<partition_id>.html` and included in the upload.
- For different tiles or windows, change `PARTITION_ID`, ROI, and dates only.

## Compare runs later

1) Download two `s2_metrics.jsonl` files from S3 (e.g., baseline vs new code).
2) Run the summarizer on each and compare:

```bash
python tessera_preprocessing/tools/summarize_metrics.py --metrics runA.jsonl
python tessera_preprocessing/tools/summarize_metrics.py --metrics runB.jsonl
```

Look at CPU hours, max RSS, days processed, useful write rate, and SCL valid% stats.

