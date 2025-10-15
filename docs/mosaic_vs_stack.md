# TESSERA Preprocessing: Mosaic vs. Stack (and why both matter for d‑pixel)

This note summarizes how the CPU mosaics are produced from Sentinel‑1/2, how the temporal stacks are built, and why both stages are required before generating d‑pixel tiles.

## TL;DR

- Mosaic = per‑date spatial merge to the ROI template grid. It resamples/reprojects each raw item, applies quality logic (S2 SCL‐based selection), and writes one GeoTIFF per band/date (S2) or per polarization/orbit/date (S1).
- Stack = across‑dates temporal concatenation. It reads those mosaics and packs them into NPY arrays with companion DOY and masks, which the model consumes.
- On a single MGRS tile, many dates have just one item; the mosaic often degenerates to “clip to ROI and write,” but it still enforces alignment and pixel selection rules. You don’t manually discard overlaps.

---

## The Mosaic Step (CPU)

Common behavior (S1 and S2):
- Locks output to your ROI template’s grid so all dates line up exactly: CRS, transform, width, height from the ROI TIFF.
- Clips to the ROI bounds, writes tiled GeoTIFF with nodata=0, applies ROI mask.
- Groups inputs by date; if multiple items overlap your ROI on the same date, merges them on CPU.
- Skips days with insufficient valid coverage over the ROI.

S2 specifics:
- Loads items via STAC + `stackstac` on the ROI grid.
- Uses SCL to build a per‑pixel tile selection (valid if not cloud/shadow/water/etc.), then mosaics each band by picking pixels from the selected tile; preserves an SCL mosaic with the original class values.
- Writes one file per band/date in band‑named folders (10 bands used):
  - `blue/2024-05-12_mosaic.tiff`, `green/...`, `red/...`, `rededge1/...`, `rededge2/...`, `rededge3/...`, `nir/...`, `nir08/...`, `swir16/...`, `swir22/...` and an SCL GeoTIFF.
- Intentionally ignores other assets (e.g., QA60, AOT, WVP, angles) for the global embedding pipeline.

S1 specifics:
- Per date and orbit (ascending/descending) and per polarization (VV, VH):
  - Converts amplitude → dB, then `+50` offset and `×200` scaling to store as int16 (compact, consistent).
  - Applies the ROI mask; merges multiple items when present.
- Writes files like: `2022-03-14_vv_ascending.tiff`, `2022-03-14_vh_ascending.tiff`, `..._descending.tiff`.

Pointers in repo:
- ROI template and grid: `tessera_preprocessing/s1_fast_processor.py`, `tessera_preprocessing/s2_fast_processor.py` (functions `load_roi`, `write_tiff`).
- S2 SCL selection and mosaic: `process_scl`, `create_scl_mosaic`, `smart_mosaic` in `s2_fast_processor.py`.
- S1 amplitude→dB and mosaic: `amplitude_to_db`, `mosaic_tiffs` in `s1_fast_processor.py`.

Why still useful on a single MGRS tile:
- Even when one item covers the date, mosaic standardizes the grid/CRS/resolution, applies SCL‑based selection logic (if >1 item), and guarantees consistent nodata handling.

---

## The Stack Step (Temporal)

What it does:
- Reads the per‑date mosaics and packs them along time (T) into large NPYs for efficient, memory‑mapped inference.
- Produces deterministic ordering by date, stores day‑of‑year arrays, and aligns masks to each time slice.

Outputs expected by downstream code:
- S2:
  - `bands.npy` with shape `(T, H, W, 10)` in the fixed band order listed above.
  - `masks.npy` with shape `(T, H, W)`.
  - `doys.npy` with shape `(T,)`.
  - Note: SCL is used to create mosaics and may be stored per date as GeoTIFF, but it is not included inside `bands.npy`.
- S1:
  - `sar_ascending.npy` with shape `(T_a, H, W, 2)` for VV/VH.
  - `sar_ascending_doy.npy` with shape `(T_a,)`.
  - `sar_descending.npy` with shape `(T_d, H, W, 2)` and `sar_descending_doy.npy` with shape `(T_d,)`.

Band information retention:
- No band info is lost. S2 channels are preserved as the last axis in a fixed order; S1 stores both polarizations explicitly. DOY arrays accompany every temporal slice.

---

## Running the Stacker Independently

This repo supports running “CPU mosaics → stack to NPYs” as separate steps (see README smoke tests).

- S2 stacker expects per‑band folders under the input root, each containing `YYYY‑MM‑DD_mosaic.tiff`:

```bash
./tessera_preprocessing/s2_stack \
  --input  /path/to/s2_cpu_mosaics \
  --output /path/to/s2_npys \
  --batch-size 8 --cache-level 1 --num-threads 8 --sample-rate 1
```

- S1 stacker expects per‑date polarization/orbit TIFFs under one directory:

```bash
./tessera_preprocessing/s1_stack \
  --input-dir  /path/to/s1_cpu_mosaics \
  --output-dir /path/to/s1_npys \
  --parallel 16 --rate 1
```

---

## From Stacks to d‑pixel

- `dpixel_retiler.py` consumes the stacked NPYs and re‑tiles them into subfolders with:
  - `bands.npy`, `masks.npy`, `doys.npy`, `sar_ascending.npy`, `sar_ascending_doy.npy`, `sar_descending.npy`, `sar_descending_doy.npy`, plus a `roi.tiff` per tile.
- These invariants (common grid, fixed channel order, aligned temporal indices) are what the embedding model expects during inference.

---

## Practical Notes

- On simple MGRS cases, many dates reduce to writing a single item as the mosaic; still keep the mosaic step to enforce grid/CRS/ROI/nodata consistency and to benefit from SCL‑based selection on days with overlapping items.
- If a day’s valid coverage inside the ROI is below the threshold, it is skipped to avoid contaminating the time series with poor pixels.

---

## Related Files

- `tessera_preprocessing/s2_fast_processor.py` — S2 CPU mosaics (SCL logic, per‑band writes, coverage gating).
- `tessera_preprocessing/s1_fast_processor.py` — S1 CPU mosaics (amplitude→dB, per‑orbit/pol writes, coverage gating).
- `tessera_preprocessing/s1_s2_stacker.sh` — Shell wrapper invoking Rust stackers on the mosaics.
- `tessera_preprocessing/dpixel_retiler.py` — Splits large NPYs into model‑ready tiles.
- `README.md` — End‑to‑end flow and smoke‑test examples.

