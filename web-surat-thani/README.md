# Surat Thani 37-STC Coastal & Mangrove Explorer

Standalone static web application for the Surat Thani 37-STC pilot.

## Isolation rule

This app is intentionally separate from the existing Samut Songkhram site:

- source root: `web-surat-thani/`
- intended branch: `web/surat-thani-coastal-change-v1`
- do not edit or deploy over the existing `web/` application
- use a separate Vercel project such as `surat-thani-37-stc-coastal-change`

The app reads generated Surat Thani products from `web/public/data/surat_thani/` during build. `npm run sync-data` copies those products into this app's `public/` directory and also publishes the current 157.55-rai PDD polygon as `project_boundary.geojson`.

## Run

```bash
cd web-surat-thani
npm install
npm run dev
```

## Build

```bash
npm run build
```

## Vercel

Create a new Vercel project with **Root Directory = `web-surat-thani`**. Do not attach this root to the existing Samut Songkhram project.

## Scientific display rules

- Coastal vegetation edge = primary satellite screening layer.
- Waterline = supporting context only; it failed the current tide/scene robustness test.
- Positive optical establishment signal is shown as small/monitoring-only, not survival or erosion reduction.
- Sentinel-1 is corroboration only, not biomass evidence.
- Causal erosion reduction remains unsupported until UAV/field/high-resolution geomorphic-edge validation.
