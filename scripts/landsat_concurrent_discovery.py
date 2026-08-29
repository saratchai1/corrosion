#!/usr/bin/env python3
"""Bounded concurrent Landsat STAC discovery."""
import asyncio
import httpx
import json
import logging
from pathlib import Path
from dateutil import parser
from shapely.geometry import shape

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

AOI_PATH = "data/aoi/rayong_coastal_analysis_aoi.geojson"
CATALOG_PATH = Path("data/catalog/rayong_landsat_scenes.csv")
SUMMARY_PATH = Path("data/analysis/rayong/catalog_summary.json")
CHECKPOINT_DIR = Path("data/catalog/.landsat_checkpoints")

STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1/search"

async def fetch_year(year, aoi_bounds, semaphore, client):
    checkpoint = CHECKPOINT_DIR / f"landsat_{year}.json"
    if checkpoint.exists():
        with open(checkpoint) as f:
            return json.load(f)
            
    async with semaphore:
        logger.info(f"[{year}] Starting STAC query...")
        start_date = f"{year}-01-01T00:00:00Z"
        end_date = f"{year}-12-31T23:59:59Z"
        
        payload = {
            "collections": ["landsat-c2-l2"],
            "bbox": aoi_bounds,
            "datetime": f"{start_date}/{end_date}",
            "limit": 100,
            "query": {"eo:cloud_cover": {"lt": 50}}
        }
        
        items = []
        try:
            resp = await client.post(STAC_URL, json=payload, timeout=30.0)
            resp.raise_for_status()
            data = resp.json()
            items.extend(data.get("features", []))
            
            # Follow pagination if necessary (rare for a single year Landsat with CC<50)
            next_link = next((l for l in data.get("links", []) if l["rel"] == "next"), None)
            while next_link:
                # Planetary Computer uses GET for next links or POST depending on the link
                resp = await client.get(next_link["href"], timeout=30.0)
                resp.raise_for_status()
                data = resp.json()
                items.extend(data.get("features", []))
                next_link = next((l for l in data.get("links", []) if l["rel"] == "next"), None)
                
        except Exception as e:
            logger.error(f"[{year}] Failed: {e}")
            return {"year": year, "discovered": 0, "error": str(e), "features": []}
            
        logger.info(f"[{year}] Discovered {len(items)} scenes.")
        
        result = {"year": year, "discovered": len(items), "error": None, "features": items}
        with open(checkpoint, "w") as f:
            json.dump(result, f)
            
        return result

async def main():
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    
    with open(AOI_PATH) as f:
        aoi_data = json.load(f)
    geom = shape(aoi_data["features"][0]["geometry"])
    bounds = list(geom.bounds)
    
    years = list(range(1984, 2027))
    semaphore = asyncio.Semaphore(5) # Bounded concurrency of 5
    
    limits = httpx.Limits(max_connections=10, max_keepalive_connections=5)
    async with httpx.AsyncClient(limits=limits) as client:
        tasks = [fetch_year(y, bounds, semaphore, client) for y in years]
        results = await asyncio.gather(*tasks)
        
    total_discovered = sum(r["discovered"] for r in results if not r["error"])
    errors = sum(1 for r in results if r["error"])
    
    logger.info(f"Completed Landsat discovery. Total: {total_discovered}. Errors: {errors}")
    
    # Update catalog summary
    with open(SUMMARY_PATH) as f:
        summary = json.load(f)
        
    summary["landsat"]["status"] = "DISCOVERY_COMPLETE" if errors == 0 else "PARTIAL_DISCOVERY"
    summary["landsat"]["total_discovered"] = total_discovered
    
    with open(SUMMARY_PATH, "w") as f:
        json.dump(summary, f, indent=2)

if __name__ == "__main__":
    asyncio.run(main())
