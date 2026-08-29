from __future__ import annotations

import importlib.util
import json
import zipfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WRAPPER_PATH = REPO_ROOT / "scripts" / "download_krabi_satellite_data.py"
AOI_PATH = REPO_ROOT / "regions" / "krabi" / "data" / "aoi" / "krabi_pdd_plots.geojson"
KMZ_PATH = REPO_ROOT / "regions" / "krabi" / "data" / "aoi" / "krabi_pdd_plots.kmz"
EXPECTED_CODES = {"97-VSD", "98-VSD", "99-VSD", "100-VSD"}


def load_wrapper_module():
    spec = importlib.util.spec_from_file_location("download_krabi_satellite_data", WRAPPER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_geojson_contains_expected_krabi_plots():
    obj = json.loads(AOI_PATH.read_text(encoding="utf-8"))
    assert obj["type"] == "FeatureCollection"
    codes = {feature["properties"]["plot_code"] for feature in obj["features"]}
    assert codes == EXPECTED_CODES
    assert len(obj["features"]) == 4


def test_krabi_aoi_union_is_valid_multipolygon():
    wrapper = load_wrapper_module()
    geom, union = wrapper.load_krabi_aoi(AOI_PATH)
    assert geom["type"] == "MultiPolygon"
    assert union.is_valid
    assert not union.is_empty
    assert len(union.geoms) == 4

    minx, miny, maxx, maxy = union.bounds
    assert 99.08 < minx < 99.09
    assert 7.90 < miny < 7.91
    assert 99.12 < maxx < 99.13
    assert 7.98 < maxy < 7.99


def test_kmz_contains_doc_kml_and_all_plot_codes():
    assert KMZ_PATH.exists()
    with zipfile.ZipFile(KMZ_PATH) as archive:
        assert "doc.kml" in archive.namelist()
        kml = archive.read("doc.kml").decode("utf-8")

    for code in EXPECTED_CODES:
        assert f"<name>{code}</name>" in kml
    assert "http://www.opengis.net/kml/2.2" in kml
