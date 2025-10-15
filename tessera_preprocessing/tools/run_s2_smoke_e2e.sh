#!/usr/bin/env bash
# run_s2_smoke_e2e.sh — End‑to‑end S2 smoke test: CPU mosaics → NPYs → publish
#
# This script wraps three phases for a short Sentinel‑2 test window:
#   1) s2_fast_processor.py (CPU preprocessing)
#   2) s2_stack (stack per‑band TIFFs into NPYs)
#   3) publish_to_s3.sh (push logs/metrics; optional NPYs)
#
# Requirements
#   - Python env with repo requirements installed
#   - awscli in PATH (only if publishing)
#
# Usage (example 3‑day smoke on 31TCH):
#   bash tessera_preprocessing/tools/run_s2_smoke_e2e.sh \
#     --roi_tiff /data/grids/31TCH_roi_10m.tiff \
#     --start 2024-04-15 --end 2024-04-17 \
#     --local-root /data/s2_out_smoke \
#     --npys-out /data/s2_npys_smoke \
#     --partition 31TCH_2024_SMOKE \
#     --s3 s3://tessera-test1/tessera/s2 \
#     --s3-npys s3://tessera-test1/tessera/s2_npys \
#     --dask-workers 1 --worker-mem 16 --threads 4 --chunksize 256 --mem-guard-frac 0.9
#
# Notes
#   - The CPU step is idempotent: re‑running fills only missing/invalid bands.
#   - For more days, just widen --start/--end and adjust workers/memory.

set -euo pipefail

usage() {
  cat >&2 <<USAGE
Usage: $0 \
  --roi_tiff PATH --start YYYY-MM-DD --end YYYY-MM-DD \
  --local-root PATH --npys-out PATH --partition ID \
  [--s3 s3://bucket/prefix] [--s3-npys s3://bucket/prefix] \
  [--dask-workers N] [--worker-mem GB] [--threads N] [--chunksize N] \
  [--mem-guard-frac F] [--min-coverage PCT] [--stac-endpoint URL] [--stac-collection ID] \
  [--cleanup-mosaics 0|1]
USAGE
}

# Defaults
ROI_TIFF=""; START=""; END=""; LOCAL_ROOT=""; NPYS_OUT=""; PARTITION=""
S3_PREFIX=""; S3_NPYS_PREFIX=""
DASK_WORKERS=1; WORKER_MEM=16; THREADS=4; CHUNKSIZE=256; MEM_GUARD_FRAC=0.9; MIN_COV=0
CLEANS=0
STAC_ENDPOINT="https://earth-search.aws.element84.com/v1"; STAC_COLLECTION="sentinel-2-l2a"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --roi_tiff) ROI_TIFF="$2"; shift 2;;
    --start) START="$2"; shift 2;;
    --end) END="$2"; shift 2;;
    --local-root) LOCAL_ROOT="$2"; shift 2;;
    --npys-out) NPYS_OUT="$2"; shift 2;;
    --partition) PARTITION="$2"; shift 2;;
    --s3) S3_PREFIX="$2"; shift 2;;
    --s3-npys) S3_NPYS_PREFIX="$2"; shift 2;;
    --dask-workers) DASK_WORKERS="$2"; shift 2;;
    --worker-mem) WORKER_MEM="$2"; shift 2;;
    --threads) THREADS="$2"; shift 2;;
    --chunksize) CHUNKSIZE="$2"; shift 2;;
    --mem-guard-frac) MEM_GUARD_FRAC="$2"; shift 2;;
    --min-coverage) MIN_COV="$2"; shift 2;;
    --stac-endpoint) STAC_ENDPOINT="$2"; shift 2;;
    --stac-collection) STAC_COLLECTION="$2"; shift 2;;
    --cleanup-mosaics) CLEANS="$2"; shift 2;;
    -h|--help) usage; exit 0;;
    *) echo "Unknown arg: $1" >&2; usage; exit 1;;
  esac
done

if [[ -z "$ROI_TIFF" || -z "$START" || -z "$END" || -z "$LOCAL_ROOT" || -z "$NPYS_OUT" || -z "$PARTITION" ]]; then
  usage; exit 2
fi

RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$LOCAL_ROOT" "$NPYS_OUT" "$LOCAL_ROOT/metrics" || true

# Always start a fresh E2E metrics file per wrapper run
E2E_JSONL="$LOCAL_ROOT/metrics/e2e.jsonl"
: > "$E2E_JSONL"

# Start a fresh S2 CPU metrics file for this wrapper run
S2_JSONL="$LOCAL_ROOT/metrics/s2_metrics.jsonl"
: > "$S2_JSONL"

# Conservative, safe defaults for small instances
export TMPDIR="${TMPDIR:-/tmp}"
export TEMP_DIR="${TEMP_DIR:-$TMPDIR}"
export GDAL_CACHEMAX=${GDAL_CACHEMAX:-256}
export GDAL_DISABLE_READDIR_ON_OPEN=${GDAL_DISABLE_READDIR_ON_OPEN:-EMPTY_DIR}
export VSI_CACHE=${VSI_CACHE:-TRUE}
export VSI_CACHE_SIZE=${VSI_CACHE_SIZE:-200000000}
export CPL_VSIL_CURL_ALLOWED_EXTENSIONS=${CPL_VSIL_CURL_ALLOWED_EXTENSIONS:-".tif,.tiff,.jp2,.json"}
export AWS_NO_SIGN_REQUEST=${AWS_NO_SIGN_REQUEST:-YES}
export OMP_NUM_THREADS=${OMP_NUM_THREADS:-1}
export OPENBLAS_NUM_THREADS=${OPENBLAS_NUM_THREADS:-1}
export MKL_NUM_THREADS=${MKL_NUM_THREADS:-1}
export NUMEXPR_MAX_THREADS=${NUMEXPR_MAX_THREADS:-1}

echo "[run_s2_smoke_e2e] Phase 1/3: CPU preprocessing…"
python tessera_preprocessing/tools/measure_subprocess.py \
  --jsonl "$E2E_JSONL" \
  --name s2_cpu \
  --bytes-root "$LOCAL_ROOT" \
  --log "$LOCAL_ROOT/s2_cpu_wrapper.log" -- \
  python tessera_preprocessing/s2_fast_processor.py \
    --input_tiff "$ROI_TIFF" \
    --start_date "$START" --end_date "$END" \
    --output "$LOCAL_ROOT" \
    --dask_workers "$DASK_WORKERS" --worker_memory "$WORKER_MEM" \
    --threads_per_worker "$THREADS" \
    --chunksize "$CHUNKSIZE" --mem_guard_frac "$MEM_GUARD_FRAC" \
    --min_coverage "$MIN_COV" \
    --stac_endpoint "$STAC_ENDPOINT" --stac_collection "$STAC_COLLECTION" \
    --partition_id "$PARTITION" \
    --metrics_jsonl "$S2_JSONL"

echo "[run_s2_smoke_e2e] Phase 2/3: Stack TIFFs → NPYs…"
python tessera_preprocessing/tools/measure_subprocess.py \
  --jsonl "$E2E_JSONL" \
  --name s2_stack \
  --bytes-root "$NPYS_OUT" \
  --log "$NPYS_OUT/s2_stack_wrapper.log" -- \
  ./tessera_preprocessing/s2_stack \
    --input "$LOCAL_ROOT" \
    --output "$NPYS_OUT" \
    --batch-size 8 --cache-level 1 --num-threads "$((THREADS*2))" --sample-rate 1

if [[ -f tessera_preprocessing/tools/summarize_metrics.py ]]; then
  echo "[run_s2_smoke_e2e] Metrics summary:"
  python tessera_preprocessing/tools/summarize_metrics.py --metrics "$LOCAL_ROOT/metrics/s2_metrics.jsonl" || true
fi

# Record NPY validation and E2E summary if tools available
if [[ -f tessera_preprocessing/tools/validate_s2_npys.py ]]; then
  python tessera_preprocessing/tools/validate_s2_npys.py --npys "$NPYS_OUT" --jsonl "$E2E_JSONL" || true
fi
if [[ -f tessera_preprocessing/tools/summarize_e2e.py ]]; then
  echo "[run_s2_smoke_e2e] E2E summary:"
  python tessera_preprocessing/tools/summarize_e2e.py --e2e "$E2E_JSONL" || true
fi

if [[ -n "$S3_PREFIX" ]]; then
  echo "[run_s2_smoke_e2e] Phase 3/3: Publish logs/metrics to S3…"
  bash tessera_preprocessing/tools/publish_to_s3.sh \
    --local-root "$LOCAL_ROOT" \
    --partition-id "$PARTITION" \
    --s3 "$S3_PREFIX" \
    --upload-outputs 0
fi

if [[ -n "$S3_NPYS_PREFIX" ]]; then
  if ! command -v aws >/dev/null 2>&1; then
    echo "awscli not found; skipping NPY upload" >&2
  else
    echo "[run_s2_smoke_e2e] Upload NPYs to S3…"
    aws s3 sync "$NPYS_OUT/" "${S3_NPYS_PREFIX%/}/${PARTITION}/${RUN_ID}/" --only-show-errors --no-progress
  fi
fi

# Optional: cleanup mosaics after successful stack and validation
if [[ "$CLEANS" == "1" ]]; then
  if [[ -f "$NPYS_OUT/bands.npy" && -f "$NPYS_OUT/masks.npy" ]]; then
    echo "[run_s2_smoke_e2e] Cleanup enabled: removing per-band mosaics under $LOCAL_ROOT"
    # Restrictive allowlist: only remove known band dirs produced by s2_fast_processor
    for d in blue green red rededge1 rededge2 rededge3 nir nir08 swir16 swir22 scl; do
      if [[ -d "$LOCAL_ROOT/$d" ]]; then
        rm -rf "$LOCAL_ROOT/$d"
      fi
    done
  else
    echo "[run_s2_smoke_e2e] Cleanup requested but NPYs not found; skipping deletion" >&2
  fi
fi

echo "[run_s2_smoke_e2e] Done. Local NPYs at: $NPYS_OUT"
