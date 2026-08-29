import json
import re
from pathlib import Path

def parse_log(filepath):
    first_year = None
    last_year = None
    candidates = 0
    selected_dates = 0
    selected_scenes = 0
    exit_code = -1
    
    year_pattern = re.compile(r"(\w+) (\d{4}): discovered=(\d+) selected_dates=(\d+) selected_scenes=(\d+)")
    final_pattern = re.compile(r"^\w+: discovered=(\d+) selected_dates=(\d+) selected_scenes=(\d+) catalog=")
    complete_pattern = re.compile(r"Dry-run complete:")
    
    try:
        with open(filepath, "r") as f:
            for line in f:
                line = line.strip()
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
                    
                if complete_pattern.search(line):
                    exit_code = 0
    except Exception as e:
        pass

    return {
        "first_available_year": first_year,
        "last_available_year": last_year,
        "candidate_scenes": candidates,
        "selected_dates": selected_dates,
        "selected_scenes": selected_scenes,
        "exit_code": exit_code
    }

def main():
    summary = {
        "sentinel2": parse_log("s2_dryrun.log"),
        "landsat": parse_log("landsat_dryrun.log"),
        "sentinel1": parse_log("s1_dryrun.log")
    }
    
    out_file = Path("data/analysis/rayong/catalog_summary.json")
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"Summary written to {out_file}")

if __name__ == "__main__":
    main()
