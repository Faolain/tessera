# AWS: S2 run that uploads artifacts, prunes local storage, and auto‑terminates instance

This variant runs the Sentinel‑2 CPU preprocessing, uploads logs/metrics and artifacts to S3, deletes local output to minimize EBS usage, and then terminates the instance so the root EBS is deleted (DeleteOnTermination=true).

## Recommended launch template settings

Set these when creating the Launch Template:

```json
{
  "BlockDeviceMappings": [{
    "DeviceName": "/dev/xvda",
    "Ebs": { "VolumeSize": 750, "VolumeType": "gp3", "Iops": 6000, "Throughput": 250, "DeleteOnTermination": true }
  }],
  "InstanceInitiatedShutdownBehavior": "terminate"
}
```

With `InstanceInitiatedShutdownBehavior=terminate`, a normal shutdown will terminate the instance and delete the root EBS (since `DeleteOnTermination` is true).

IAM for the instance role:

- Minimum for uploads: `s3:PutObject`, `s3:PutObjectAcl`, `s3:ListBucket` scoped to your bucket/prefix.
- Optional convenience (if you want the script to set the shutdown behavior programmatically): `ec2:ModifyInstanceAttribute` on self.

## User‑data script (artifacts → S3, delete local, terminate)

Paste as user‑data. Adjust variables at the top (bucket/prefix, ROI, dates, sizing). It uploads artifacts as well as logs/metrics, then removes local output and terminates the instance.

```bash
#!/bin/bash
set -euxo pipefail
export DEBIAN_FRONTEND=noninteractive

# ==== CONFIGURE THESE ====
export S3_BUCKET_PREFIX="s3://YOUR_BUCKET/tessera/s2"     # Logs/metrics/artifacts root
export PARTITION_ID="31TCH_2024_ANNUAL"                   # Label for this run
export ROI_TIFF_S3="s3://YOUR_BUCKET/rois/31TCH.tiff"    # ROI template (10 m) in S3
export START_DATE="2024-01-01"
export END_DATE="2024-12-31"
export DASK_WORKERS=8
export WORKER_MEMORY_GB=16
export OUT_DIR="/data/s2_out"
export TEMP_DIR="/mnt/nvme/tmp"
export REPO_URL="https://github.com/ucam-eo/tessera.git"  # or your fork

# ==== SYSTEM PREP ====
apt-get update
apt-get install -y python3-venv python3-pip git awscli
mkdir -p "$TEMP_DIR" || true
mkdir -p "$OUT_DIR/metrics" /data/grids

# Optional: ensure that instance-initiated shutdown terminates the instance
# (requires ec2:ModifyInstanceAttribute; otherwise rely on LT setting)
TOKEN=$(curl -s -X PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 21600" || true)
IID=$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/instance-id || true)
REGION=$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/placement/region || true)
if [[ -n "$IID" && -n "$REGION" ]]; then
  aws ec2 modify-instance-attribute \
    --instance-id "$IID" \
    --instance-initiated-shutdown-behavior terminate \
    --region "$REGION" || true
fi

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

# Summarize metrics (human readable)
python tessera_preprocessing/tools/summarize_metrics.py \
  --metrics "$OUT_DIR/metrics/s2_metrics.jsonl" \
  > "$OUT_DIR/metrics/summary.txt" || true

# ==== PUBLISH EVERYTHING TO S3, THEN PRUNE LOCAL ====
bash tessera_preprocessing/tools/publish_to_s3.sh \
  --local-root "$OUT_DIR" \
  --partition-id "$PARTITION_ID" \
  --s3 "$S3_BUCKET_PREFIX" \
  --upload-outputs 1 \
  --delete-local 1

# ==== TERMINATE INSTANCE (deletes root EBS if DeleteOnTermination=true) ====
# Prefer to rely on InstanceInitiatedShutdownBehavior=terminate
shutdown -h now

# Fallback (requires ec2:TerminateInstances). Uncomment if desired:
# aws ec2 terminate-instances --instance-ids "$IID" --region "$REGION" || true
```

## Behavior

- Logs/metrics uploaded to: `s3://YOUR_BUCKET/tessera/s2/<partition_id>/<run_id>/logs|metrics`.
- Artifacts (mosaics/NPYs) uploaded to: `.../artifacts/`.
- Local output under `OUT_DIR` is deleted after upload.
- Instance shuts down; with the LT setting, EC2 terminates the instance and deletes the root EBS.

## Cost‑control tips

- Enable S3 lifecycle: transition `artifacts/` after N days to Glacier; keep `logs/` and `metrics/` long‑term.
- Use instance NVMe for `TEMP_DIR` to minimize EBS I/O and size.
- For many tiles, consider Spot with checkpointing (publish logs incrementally, then terminate).

