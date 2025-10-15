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
#!/usr/bin/env bash
  set -euxo pipefail
  export DEBIAN_FRONTEND=noninteractive

  # ==== CONFIGURE THESE ====

  export PARTITION_ID="31TCH_2024_SMOKE"
  export ROI_TIFF_S3="s3://tessera-test1/rois/31TCH_roi_10m.tiff"
  export S3_LOG_PREFIX="s3://tessera-test1/tessera/s2"       # logs/metrics live here
  export S3_S2_NPY_PREFIX="s3://tessera-test1/tessera/s2_npys"  # S2 NPYs live here
  export START_DATE="2024-04-15"
  export END_DATE="2024-04-17"   # inclusive (3-day smoke)
  export DASK_WORKERS="8"
  export WORKER_MEMORY_GB="4"
  export OUT_DIR="/data/s2_out_smoke"
  export NPY_DIR="/data/s2_npys_smoke"
  export TEMP_DIR="/mnt/nvme/tmp"
  export REPO_URL="https://github.com/Faolain/tessera.git"
  export REPO_BRANCH="feat/aws"
  export RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)"
  export DELETE_LOCAL_NPYS="1"   # set 0 to keep local NPYs

  # ==== SYSTEM PREP ====

  apt-get update
  apt-get install -y python3-venv python3-pip git unzip curl
  mkdir -p "$TEMP_DIR" "$OUT_DIR/metrics" /data/grids "$NPY_DIR"

  # AWS CLI v2 (apt awscli is unreliable on 22.04/24.04)

  ARCH="$(uname -m)"
  if [[ "$ARCH" == "x86_64" ]]; then
  URL="https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip"
  else
  URL="https://awscli.amazonaws.com/awscli-exe-linux-aarch64.zip"
  fi
  curl -sSL "$URL" -o /tmp/awscliv2.zip
  unzip -q /tmp/awscliv2.zip -d /tmp
  /tmp/aws/install --bin-dir /usr/local/bin --install-dir /usr/local/aws-cli --update
  aws --version

  # Ensure instance shutdown terminates (optional; needs ec2:ModifyInstanceAttribute)

  TOKEN=$(curl -s -X PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 21600" || true)
  IID=$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/instance-id || true)
  REGION=$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/placement/region || true)
  if [[ -n "$IID" && -n "$REGION" ]]; then
  aws ec2 modify-instance-attribute \
  --instance-id "$IID" \
  --instance-initiated-shutdown-behavior terminate \
  --region "$REGION" || true
  fi

  # ==== FETCH REPO AND ENV ====

  cd /root
  if [[ ! -d tessera ]]; then
  git clone --branch "$REPO_BRANCH" --single-branch "$REPO_URL" tessera
  fi
  cd tessera
  python3 -m venv /root/venv
  source /root/venv/bin/activate
  pip install --upgrade pip
  pip install -r requirements.txt

  # ==== ROI ====

  aws s3 cp "$ROI_TIFF_S3" /data/grids/roi.tiff --no-progress

# ==== RUN S2 CPU (AWS Earth Search by default) ====

  python tessera_preprocessing/s2_fast_processor.py \
  --input_tiff /data/grids/roi.tiff \
  --start_date "$START_DATE" --end_date "$END_DATE" \
  --output "$OUT_DIR" \
  --dask_workers "$DASK_WORKERS" --worker_memory "$WORKER_MEMORY_GB" \
  --chunksize 1024 --resolution 10 \
  --min_coverage 10 \
  --partition_id "$PARTITION_ID" \
  --metrics_jsonl "$OUT_DIR/metrics/s2_metrics.jsonl"

  # Optional human summary

  python tessera_preprocessing/tools/summarize_metrics.py \
  --metrics "$OUT_DIR/metrics/s2_metrics.jsonl" \

  > "$OUT_DIR/metrics/summary.txt" || true

  # ==== STACK S2 → NPYs ====

  ./tessera_preprocessing/s2_stack \
  --input "$OUT_DIR" \
  --output "$NPY_DIR" \
  --batch-size 8 --cache-level 1 --num-threads 8 --sample-rate 1

  # ==== PUBLISH LOGS/METRICS ONLY (no mosaics) ====

  bash tessera_preprocessing/tools/publish_to_s3.sh \
  --local-root "$OUT_DIR" \
  --partition-id "$PARTITION_ID" \
  --s3 "$S3_LOG_PREFIX" \
  --upload-outputs 0 \
  --delete-local 1

  # ==== PUBLISH S2 NPYs ====

  aws s3 sync "$NPY_DIR" "${S3_S2_NPY_PREFIX}/${PARTITION_ID}/${RUN_ID}/" \
  --no-progress --only-show-errors

  # Optional: delete NPYs after upload to reclaim EBS

  if [[ "$DELETE_LOCAL_NPYS" == "1" ]]; then
  rm -rf "$NPY_DIR"
  fi

  echo "Logs     → ${S3_LOG_PREFIX}/${PARTITION_ID}/${RUN_ID}/logs/"
  echo "S2 NPYs  → ${S3_S2_NPY_PREFIX}/${PARTITION_ID}/${RUN_ID}/"

  # ==== TERMINATE ====

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

---

## Optional: Add end‑to‑end benchmark metrics (wrapper; test‑only)

Why: The native S2 processor already logs detailed CPU‑side metrics, but the Rust `s2_stack` phase has no built‑in metrics. If you want coarse, end‑to‑end numbers for tuning (not for auditing), you can wrap both steps with a very light measurer. It records per‑step wall time, approximate proc‑tree CPU seconds, a max RSS sample, and bytes delta under the output directories.

Important caveats
- These numbers are approximate. Wrapping adds a tiny amount of overhead and uses directory size deltas; pre‑existing files or concurrent writers can skew results.
- Treat as benchmarking aids only. Do not use as authoritative accounting or for scientific reporting.

Patch (minimal): Replace the two run blocks and add a short summary/validation. Variables below are the same ones defined earlier in this user‑data.

```bash
# ==== RUN S2 CPU (with wrapper metrics) ====
python tessera_preprocessing/tools/measure_subprocess.py \
  --jsonl "$OUT_DIR/metrics/e2e.jsonl" \
  --name s2_cpu --bytes-root "$OUT_DIR" \
  --log "$OUT_DIR/s2_cpu_wrapper.log" -- \
  python tessera_preprocessing/s2_fast_processor.py \
    --input_tiff /data/grids/roi.tiff \
    --start_date "$START_DATE" --end_date "$END_DATE" \
    --output "$OUT_DIR" \
    --dask_workers "$DASK_WORKERS" --worker_memory "$WORKER_MEMORY_GB" \
    --chunksize 1024 --resolution 10 \
    --min_coverage 10 \
    --partition_id "$PARTITION_ID" \
    --metrics_jsonl "$OUT_DIR/metrics/s2_metrics.jsonl"

# Optional CPU‑only summary (unchanged)
python tessera_preprocessing/tools/summarize_metrics.py \
  --metrics "$OUT_DIR/metrics/s2_metrics.jsonl" \
  > "$OUT_DIR/metrics/summary.txt" || true

# ==== STACK S2 → NPYs (with wrapper metrics) ====
python tessera_preprocessing/tools/measure_subprocess.py \
  --jsonl "$OUT_DIR/metrics/e2e.jsonl" \
  --name s2_stack --bytes-root "$NPY_DIR" \
  --log "$NPY_DIR/s2_stack_wrapper.log" -- \
  ./tessera_preprocessing/s2_stack \
    --input "$OUT_DIR" \
    --output "$NPY_DIR" \
    --batch-size 8 --cache-level 1 --num-threads 8 --sample-rate 1

# Validate stacked NPYs and summarize e2e
python tessera_preprocessing/tools/validate_s2_npys.py --npys "$NPY_DIR" --jsonl "$OUT_DIR/metrics/e2e.jsonl" || true
python tessera_preprocessing/tools/summarize_e2e.py --e2e "$OUT_DIR/metrics/e2e.jsonl" > "$OUT_DIR/metrics/summary_e2e.txt" || true

# ==== PUBLISH LOGS/METRICS ONLY (publisher also uploads e2e.jsonl if present) ====
bash tessera_preprocessing/tools/publish_to_s3.sh \
  --local-root "$OUT_DIR" \
  --partition-id "$PARTITION_ID" \
  --s3 "$S3_LOG_PREFIX" \
  --upload-outputs 0 \
  --delete-local 1

# ==== PUBLISH S2 NPYs (unchanged) ====
aws s3 sync "$NPY_DIR" "${S3_S2_NPY_PREFIX}/${PARTITION_ID}/${RUN_ID}/" \
  --no-progress --only-show-errors
```

Alternative: use the one‑shot wrapper
- Instead of patching the user‑data, call the wrapper which already does all of the above, including e2e metrics and optional S3 uploads:
  - `bash tessera_preprocessing/tools/run_s2_smoke_e2e.sh --roi_tiff /data/grids/roi.tiff --start "$START_DATE" --end "$END_DATE" --local-root "$OUT_DIR" --npys-out "$NPY_DIR" --partition "$PARTITION_ID" --s3 "$S3_LOG_PREFIX" --s3-npys "$S3_S2_NPY_PREFIX" --dask-workers "$DASK_WORKERS" --worker-mem "$WORKER_MEMORY_GB" --threads 4 --chunksize 256 --mem-guard-frac 0.9`

Disable/Remove
- Simply delete the three wrapper blocks above to revert to native behavior; CPU‑only metrics remain available via `--metrics_jsonl` and `summarize_metrics.py`.
