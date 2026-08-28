# Satellite data workflow status

Generated on 2026-08-28 for branch `data/samut-songkhram-satellite-v1`.

- Repository was empty at initialization; no verified SEG030/project AOI existed.
- Provisional AOI added for Samut Songkhram coast / Mae Klong mouth / Don Hoi Lot reference area.
- Git LFS tracking rules prepared, but runtime `git lfs env` and no-cost quota could not be verified through the GitHub API environment.
- Therefore **no raster binaries were pushed**.
- STAC download/catalog scripts, validation, compositing, preview helpers, catalogs, manifests and documentation are included.
- Run the reproduction commands in `docs/DOWNLOAD_AND_REPRODUCE.md` from a network-enabled clone to populate scene catalogs and AOI-only COGs.
