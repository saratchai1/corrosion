# Samut Songkhram Sentinel-2 Super-Resolution Trial

This experiment tests whether LDSR-S2 is useful for the Samut Songkhram coastal/mangrove workflow without treating model-generated 2.5 m pixels as new sensor measurements.

## Fixed first-pass scene

- Scene: `S2A_47PPQ_20250115_0_L2A`
- Catalog AOI bad-quality/cloud proxy: ~0.02%
- Native bands used by LDSR-S2: B04, B03, B02, B08 (Red, Green, Blue, NIR), all 10 m
- Test patch: 128 x 128 native pixels (~1.28 x 1.28 km) around the Mae Klong coastal test point
- Output grid: 512 x 512 at 2.5 m

## What is compared

1. Native Sentinel-2 10 m (shown with nearest-neighbor enlargement only for display)
2. Bicubic interpolation to a 2.5 m grid
3. LDSR-S2 latent-diffusion super-resolution to a 2.5 m grid

The script also downsamples the 2.5 m results back to 10 m and computes per-band MAE/RMSE/bias against the original Sentinel-2 patch. This is a radiometric consistency check, not proof that the generated sub-10 m structures are spatially true.

## Important limitation for dNBR/MNDWI

LDSR-S2 itself super-resolves only the 10 m RGB+NIR bands. Sentinel-2 B11/B12 SWIR bands are native 20 m. Therefore a dNBR or MNDWI product displayed on a 2.5 m grid is **not automatically a true 2.5 m multispectral product** unless the SWIR bands are super-resolved with a model designed for them (for example the newer ESA OpenSR SEN2SR family) and validated separately.

## Run

```bash
pip install -U "geoai-py[sr]" requests rasterio pyproj matplotlib numpy
python experiments/s2_superres/trial.py --sampling-steps 20
```

For a heavier uncertainty run:

```bash
python experiments/s2_superres/trial.py \
  --sampling-steps 100 \
  --uncertainty \
  --n-variations 5
```

The branch also contains a GitHub Actions smoke test that runs the small patch automatically and uploads the generated trial outputs as an artifact.

## Acceptance rule for this project

Do not use LDSR-S2 alone to claim 2.5 m positional accuracy, count small objects, or measure sub-10 m shoreline/mangrove geometry. Use it first as a visualization/feature-enhancement candidate. Promote it to quantitative analysis only after comparison with independent higher-resolution truth (drone orthomosaic, surveyed boundary, or other suitable high-resolution imagery) and after checking uncertainty and downsample-back spectral consistency.
