#!/usr/bin/env python3
"""
Fetch a Sentinel-2 MGRS tile from the public GeoParquet grid and optionally
generate a 10 m ROI GeoTIFF for pre-processing.

Outputs:
  - <OUT_DIR>/<TILE>.geojson
  - <OUT_DIR>/<TILE>.gpkg
  - <OUT_DIR>/<TILE>_roi_10m.tiff  (if --make_roi_tiff)

Dependencies (utility-only):
  pip install geopandas pyogrio shapely rasterio fiona numpy

Example:
  python util/fetch_s2_tile_and_make_roi.py --tile 31TCH --out_dir /data/grids --make_roi_tiff
  aws s3 cp /data/grids/31TCH_roi_10m.tiff s3://YOUR_BUCKET/rois/31TCH_roi_10m.tiff
"""

import argparse
from pathlib import Path
import sys
import numpy as np

import geopandas as gpd
from shapely.ops import unary_union

try:
    import rasterio
    from rasterio.features import rasterize
    from rasterio.transform import from_origin
except Exception:
    rasterio = None

DEFAULT_URL = "https://raw.githubusercontent.com/maawoo/sentinel-2-grid-geoparquet/main/sentinel-2-grid.parquet"


def _pick_tile_column(columns):
    # Be robust to different column namings
    cands = [
        "tile", "Tile", "TILE",
        "Name", "name",
        "MGRS_TILE", "mgrs", "mgrs_tile", "TILE_ID",
    ]
    for c in cands:
        if c in columns:
            return c
    raise RuntimeError(f"Could not find a tile code column in {list(columns)}")


def _normalize_codes(series):
    vals = series.astype(str).str.upper().str.strip()
    return vals, vals.str.lstrip("T")


def _determine_utm_epsg(lon, lat):
    zone = int((lon + 180) // 6) + 1
    if 56 <= lat < 64 and 3 <= lon < 12:  # Norway special
        zone = 32
    if 72 <= lat < 84:  # Svalbard specials
        if 0 <= lon < 9:
            zone = 31
        elif 9 <= lon < 21:
            zone = 33
        elif 21 <= lon < 33:
            zone = 35
        elif 33 <= lon < 42:
            zone = 37
    north = lat >= 0
    return 32600 + zone if north else 32700 + zone


def _make_roi_tiff(gdf, out_tiff: Path, pixel_size: float = 10.0):
    if rasterio is None:
        raise RuntimeError("rasterio is required for --make_roi_tiff; install rasterio and fiona")

    gdf_wgs84 = gdf.to_crs(4326)
    geom_union = unary_union(gdf_wgs84.geometry)
    centroid = geom_union.centroid
    lon, lat = float(centroid.x), float(centroid.y)
    utm_epsg = _determine_utm_epsg(lon, lat)

    gdf_utm = gdf_wgs84.to_crs(utm_epsg)
    geom_utm = unary_union(gdf_utm.geometry)

    minx, miny, maxx, maxy = geom_utm.bounds
    width = int(np.ceil((maxx - minx) / pixel_size))
    height = int(np.ceil((maxy - miny) / pixel_size))
    if width <= 0 or height <= 0:
        raise ValueError(f"Invalid raster dims from bounds {geom_utm.bounds} at pixel_size={pixel_size}")

    transform = from_origin(minx, maxy, pixel_size, pixel_size)
    mask = rasterize(
        [(geom_utm, 255)],
        out_shape=(height, width),
        transform=transform,
        fill=0,
        dtype="uint8",
        all_touched=False,
    )

    out_tiff.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        out_tiff,
        "w",
        driver="GTiff",
        height=height,
        width=width,
        count=1,
        dtype=mask.dtype,
        crs=f"EPSG:{utm_epsg}",
        transform=transform,
    ) as dst:
        dst.write(mask, 1)
    return str(out_tiff), utm_epsg, width, height


def main():
    ap = argparse.ArgumentParser("Fetch Sentinel-2 grid (GeoParquet), extract a tile, and optionally build a 10 m ROI TIFF")
    ap.add_argument("--url", default=DEFAULT_URL, help="Remote GeoParquet URL")
    ap.add_argument("--tile", default="31TCH", help="MGRS tile code (e.g., 31TCH)")
    ap.add_argument("--out_dir", default=None, help="Output directory (default: <repo_root>/data/grids; falls back there if the provided path is not writable)")
    ap.add_argument("--write_shapefile", action="store_true", help="Also write ESRI Shapefile (.shp)")
    ap.add_argument("--make_roi_tiff", action="store_true", help="Also rasterize ROI TIFF at 10 m")
    ap.add_argument("--pixel_size", type=float, default=10.0, help="ROI TIFF pixel size (meters)")
    args = ap.parse_args()

    # Resolve output directory with a safe fallback to <repo_root>/data/grids
    repo_root = Path(__file__).resolve().parents[1]
    default_out = repo_root / "data" / "grids"

    def ensure_dir(p: Path) -> Path:
        try:
            p.mkdir(parents=True, exist_ok=True)
            return p
        except OSError as e:
            # Fallback to repo-level data/grids if the requested path is not writable (e.g., /data on macOS)
            fb = default_out
            fb.mkdir(parents=True, exist_ok=True)
            print(f"[info] Cannot create '{p}': {e}. Using fallback '{fb}'.")
            return fb

    out_dir = ensure_dir(Path(args.out_dir) if args.out_dir else default_out)

    # Load GeoParquet robustly: prefer local cache via requests + pyarrow
    repo_root = Path(__file__).resolve().parents[1]
    cache_dir = repo_root / "data" / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cached = cache_dir / Path(args.url).name

    def _download(url: str, dst: Path):
        try:
            import requests
            with requests.get(url, stream=True, timeout=60) as r:
                r.raise_for_status()
                tmp = dst.with_suffix(dst.suffix + ".tmp")
                with open(tmp, "wb") as f:
                    for chunk in r.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            f.write(chunk)
                tmp.replace(dst)
            return True
        except Exception as e:
            print(f"[warn] Failed HTTP download of GeoParquet: {e}", file=sys.stderr)
            return False

    gdf = None
    # 1) If cache exists, try pyarrow path first
    if cached.exists():
        try:
            gdf = gpd.read_parquet(cached)
        except Exception as e:
            print(f"[warn] Cached parquet read failed ({e}); will retry alternatives", file=sys.stderr)
            gdf = None

    # 2) If not loaded, download to cache then read via pyarrow
    if gdf is None:
        if not cached.exists():
            _download(args.url, cached)
        if cached.exists():
            try:
                gdf = gpd.read_parquet(cached)
            except Exception as e:
                print(f"[warn] pyarrow parquet read failed ({e}); trying GDAL/pyogrio", file=sys.stderr)
                gdf = None

    # 3) Final fallback: try reading remote via pyogrio (requires GDAL Parquet)
    if gdf is None:
        try:
            gdf = gpd.read_file(args.url, engine="pyogrio", driver="Parquet")
        except Exception as e:
            print(f"[error] Could not open remote GeoParquet via GDAL: {e}", file=sys.stderr)
            raise SystemExit("Install pyarrow (pip install pyarrow) or ensure GDAL has Parquet support.")

    # Ensure geometry column is properly set (handle common patterns if parquet lacks GeoPandas metadata)
    try:
        geom_name = getattr(gdf, "geometry", None)
        if geom_name is None or (hasattr(gdf, "geometry") and gdf.geometry.name not in gdf.columns):
            raise AttributeError
    except Exception:
        # Try common fallbacks
        from shapely import from_wkb, from_wkt
        if "wkb_geometry" in gdf.columns:
            gdf["geometry"] = gdf["wkb_geometry"].apply(lambda b: from_wkb(b) if b is not None else None)
            gdf.set_geometry("geometry", inplace=True)
        elif "WKT" in gdf.columns:
            gdf["geometry"] = gdf["WKT"].apply(lambda s: from_wkt(s) if s else None)
            gdf.set_geometry("geometry", inplace=True)
        elif "geom" in gdf.columns:
            try:
                gdf.set_geometry("geom", inplace=True)
            except Exception:
                pass
        # Last resort: let GeoPandas guess; if it fails, downstream will error clearly

    col = _pick_tile_column(gdf.columns)
    vals, vals_noT = _normalize_codes(gdf[col])
    want = args.tile.upper()
    mask = (vals == want) | (vals_noT == want.lstrip("T"))
    sub = gdf[mask]
    if len(sub) == 0:
        raise SystemExit(f"No features matched tile '{args.tile}' in column '{col}'.")

    base = out_dir / args.tile.upper()
    geojson = base.with_suffix(".geojson")
    gpkg = base.with_suffix(".gpkg")
    sub.to_file(geojson, driver="GeoJSON")
    sub.to_file(gpkg, driver="GPKG")
    print(f"Wrote: {geojson}")
    print(f"Wrote: {gpkg}")

    if args.write_shapefile:
        shp_path = base.with_suffix(".shp")
        sub.to_file(shp_path, driver="ESRI Shapefile")
        print(f"Wrote: {shp_path}")

    if args.make_roi_tiff:
        roi_tiff = out_dir / f"{args.tile.upper()}_roi_{int(args.pixel_size)}m.tiff"
        tiff_path, epsg, w, h = _make_roi_tiff(sub, roi_tiff, pixel_size=args.pixel_size)
        print(f"Wrote ROI TIFF: {tiff_path} (CRS=EPSG:{epsg}, size={w}x{h})")


if __name__ == "__main__":
    main()
