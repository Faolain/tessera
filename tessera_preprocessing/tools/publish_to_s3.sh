#!/usr/bin/env bash
# publish_to_s3.sh — push S2 logs/metrics (and optionally artifacts) to S3
#
# Lightweight, opt-in uploader that does not modify pipeline behavior.
#
# Usage:
#   bash tessera_preprocessing/tools/publish_to_s3.sh \
#     --local-root /data/s2_out \
#     --partition-id 31TCH_2024 \
#     --s3 s3://your-bucket/tessera/s2 \
#     [--upload-outputs 0|1] [--delete-local 0|1]
#
# Layout on S3:
#   s3://<bucket>/<prefix>/<partition_id>/<run_id>/
#     logs/     → s2_<partition_id>_detail.log, dask-report-*.html
#     metrics/  → s2_metrics.jsonl, summary.txt (optional)
#     artifacts/→ optional sync of local outputs (disabled by default)
#     manifest.json

set -euo pipefail

usage() {
  echo "Usage: $0 --local-root PATH --partition-id ID --s3 s3://bucket/prefix [--upload-outputs 0|1] [--delete-local 0|1]" >&2
}

LOCAL_ROOT=""
PARTITION_ID=""
S3_DST=""
UPLOAD_OUTPUTS=0
DELETE_LOCAL=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --local-root) LOCAL_ROOT="$2"; shift 2;;
    --partition-id) PARTITION_ID="$2"; shift 2;;
    --s3) S3_DST="$2"; shift 2;;
    --upload-outputs) UPLOAD_OUTPUTS="$2"; shift 2;;
    --delete-local) DELETE_LOCAL="$2"; shift 2;;
    -h|--help) usage; exit 0;;
    *) echo "Unknown arg: $1" >&2; usage; exit 1;;
  esac
done

if [[ -z "${LOCAL_ROOT}" || -z "${PARTITION_ID}" || -z "${S3_DST}" ]]; then
  usage; exit 1
fi

if ! command -v aws >/dev/null 2>&1; then
  echo "awscli not found in PATH" >&2
  exit 2
fi

RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)"
HOSTNAME_SAFE="$(hostname | tr ' /' '__')"
EXPORT_DIR="${LOCAL_ROOT}/_run_exports/${RUN_ID}_${PARTITION_ID}"
mkdir -p "${EXPORT_DIR}" || true

# Collect primary files
LOG_FILE="${LOCAL_ROOT}/s2_${PARTITION_ID}_detail.log"
DASK_REPORT="$(ls -1 ${LOCAL_ROOT}/dask-report-${PARTITION_ID}.html 2>/dev/null || true)"
METRICS="${LOCAL_ROOT}/metrics/s2_metrics.jsonl"

[[ -f "${LOG_FILE}" ]] && cp -f "${LOG_FILE}" "${EXPORT_DIR}/"
[[ -f "${METRICS}" ]] && cp -f "${METRICS}" "${EXPORT_DIR}/"
[[ -f "${DASK_REPORT}" ]] && cp -f "${DASK_REPORT}" "${EXPORT_DIR}/"

# Optional human-readable summary
if [[ -f "tessera_preprocessing/tools/summarize_metrics.py" && -f "${METRICS}" ]]; then
  python tessera_preprocessing/tools/summarize_metrics.py --metrics "${METRICS}" > "${EXPORT_DIR}/summary.txt" || true
fi

# Manifest
cat > "${EXPORT_DIR}/manifest.json" <<EOF
{
  "run_id": "${RUN_ID}",
  "partition_id": "${PARTITION_ID}",
  "host": "${HOSTNAME_SAFE}",
  "local_root": "${LOCAL_ROOT}",
  "s3_dst": "${S3_DST}",
  "ts_utc": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF

BASE_S3="${S3_DST%/}/${PARTITION_ID}/${RUN_ID}"

# Upload logs + metrics + manifest
aws s3 cp "${EXPORT_DIR}/" "${BASE_S3}/logs/" --recursive --only-show-errors --no-progress

# Optional: upload artifacts (skip logs/metrics)
if [[ "${UPLOAD_OUTPUTS}" == "1" ]]; then
  aws s3 sync "${LOCAL_ROOT}/" "${BASE_S3}/artifacts/" \
    --exclude "_run_exports/*" --exclude "metrics/*" \
    --exclude "dask-report-*.html" --exclude "s2_*_detail.log" \
    --only-show-errors --no-progress
fi

# Optional: delete local outputs after confirmed upload
if [[ "${DELETE_LOCAL}" == "1" ]]; then
  find "${LOCAL_ROOT}" -maxdepth 1 -mindepth 1 \
    ! -name "_run_exports" \
    -exec rm -rf {} +
fi

echo "Published to ${BASE_S3}"

