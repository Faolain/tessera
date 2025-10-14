**Sentinel‑2 Tile ROI Utility**

Create a per‑tile ROI template (10 m GeoTIFF) from the public Sentinel‑2 tiling grid, then use it to run the S2 CPU smoke test or month‑long runs.

What this provides
- `util/fetch_s2_tile_and_make_roi.py`: pulls the public S2 grid (GeoParquet), extracts a tile (default `31TCH`), writes vector outputs (GeoJSON/GPKG) and optionally a 10 m ROI TIFF.
- Keeps the core pipeline unchanged; this is an optional helper you can run once, locally or on EC2.

Dependencies (install once, separate from main requirements)
- These are only needed for this utility (not required by the pipeline):
  - `pip install geopandas pyogrio shapely rasterio fiona numpy pyarrow requests`

Quick start (local)
1) Make the ROI TIFF for tile `31TCH`:
   - `python util/fetch_s2_tile_and_make_roi.py --tile 31TCH --make_roi_tiff`
   - By default (or if the provided `--out_dir` is not writable), outputs are written under `<repo_root>/data/grids`.
   - Outputs:
     - `<repo_root>/data/grids/31TCH.geojson`, `<repo_root>/data/grids/31TCH.gpkg`
     - `<repo_root>/data/grids/31TCH_roi_10m.tiff` (if `--make_roi_tiff`)
2) Upload ROI TIFF to S3 (example bucket/prefix):
   - `aws s3 cp <repo_root>/data/grids/31TCH_roi_10m.tiff s3://YOUR_BUCKET/rois/31TCH_roi_10m.tiff`

EC2 smoke test (3‑day, cheap) using the ROI
- Use `docs/aws_s2_run_and_publish.md` and set:
  - `S3_BUCKET_PREFIX="s3://YOUR_BUCKET/tessera/s2"`
  - `ROI_TIFF_S3="s3://YOUR_BUCKET/rois/31TCH_roi_10m.tiff"`
  - `START_DATE`/`END_DATE` to a 3‑day window (e.g., `2024-04-10` → `2024-04-12`)
- Recommended instance: `m7i.xlarge` (4 vCPU, 16 GB RAM), 150 GB gp3; attach an IAM role with `s3:PutObject` + `s3:ListBucket` to your bucket.

Alternative: generate the ROI inside user‑data
- If you don’t want to pre‑upload the ROI, you can generate it on the instance before running S2. Insert this block after creating the venv (requires `geopandas` and `pyogrio`):

```
pip install geopandas pyogrio shapely rasterio fiona numpy
python - <<'PY'
import geopandas as gpd
from shapely.ops import unary_union
from tessera_preprocessing.convert_shp_to_tiff import shp_to_tiff
url = "https://raw.githubusercontent.com/maawoo/sentinel-2-grid-geoparquet/main/sentinel-2-grid.parquet"
gdf = gpd.read_file(url, engine="pyogrio")
tile = gdf[gdf["tile"].astype(str).str.upper().str.lstrip('T') == "31TCH"]
assert len(tile) == 1, f"Expected one feature for 31TCH, got {len(tile)}"
tile.to_file("/data/grids/31TCH.geojson", driver="GeoJSON")
tiff,_ = shp_to_tiff("/data/grids/31TCH.geojson", tiff_path="/data/grids/roi.tiff", pixel_size=10)
print("ROI:", tiff)
PY
```

Where results land on S3 (after the run)
- Logs/metrics publisher writes to:
  - `s3://<bucket>/tessera/s2/<PARTITION_ID>/<run_id>/{logs,metrics}`
  - `<run_id>` is an auto UTC timestamp folder per run.
  - Open `summary.txt` and `dask-report-*.html` for quick health/perf.

Notes
- Using a GeoPackage of the full grid for reproducibility is reasonable (tens of MB). Prefer fetching from a public source at run time or store the GPKG in S3 rather than committing large data into the repo.
- You can build ROIs for any tile by changing `--tile` (e.g., `32TLP`, `18TYN`).
