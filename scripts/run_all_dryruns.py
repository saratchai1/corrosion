import subprocess
import json
from pathlib import Path
import re

def run_cmd(cmd):
    print(f"Running: {cmd}")
    process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    
    first_year = None
    last_year = None
    candidates = 0
    selected_dates = 0
    selected_scenes = 0
    
    # Regex to capture year-by-year discoveries
    # e.g., sentinel2 2017: discovered=41 selected_dates=4 selected_scenes=4
    year_pattern = re.compile(r"(\w+) (\d{4}): discovered=(\d+) selected_dates=(\d+) selected_scenes=(\d+)")
    
    # Final summary line
    # e.g. sentinel2: discovered=1500 selected_dates=120 selected_scenes=120 catalog=...
    final_pattern = re.compile(r"^\w+: discovered=(\d+) selected_dates=(\d+) selected_scenes=(\d+) catalog=")

    while True:
        line = process.stdout.readline()
        if not line and process.poll() is not None:
            break
        if line:
            line = line.strip()
            print(line)
            
            m_year = year_pattern.search(line)
            if m_year:
                year = int(m_year.group(2))
                disc = int(m_year.group(3))
                if disc > 0:
                    if first_year is None:
                        first_year = year
                    last_year = year

            m_final = final_pattern.search(line)
            if m_final:
                candidates = int(m_final.group(1))
                selected_dates = int(m_final.group(2))
                selected_scenes = int(m_final.group(3))

    exit_code = process.wait()
    return {
        "first_available_year": first_year,
        "last_available_year": last_year,
        "candidate_scenes": candidates,
        "selected_dates": selected_dates,
        "selected_scenes": selected_scenes,
        "exit_code": exit_code
    }

def main():
    summary = {}
    
    cmds = {
        "sentinel2": "source .venv/bin/activate && python scripts/download_satellite_data_rayong.py sentinel2 --dry-run",
        "landsat": "source .venv/bin/activate && python scripts/download_satellite_data_rayong.py landsat --dry-run",
        "sentinel1": "source .venv/bin/activate && python scripts/download_satellite_data_rayong.py sentinel1 --dry-run",
    }
    
    for key, cmd in cmds.items():
        summary[key] = run_cmd(cmd)

    out_file = Path("data/analysis/rayong/catalog_summary.json")
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"Summary written to {out_file}")

if __name__ == "__main__":
    main()
