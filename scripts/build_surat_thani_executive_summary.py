#!/usr/bin/env python3
"""Synthesize the Surat Thani 37-STC evidence stack into one conservative summary.

This is intentionally a decision/evidence summary rather than a new analytical model.
It keeps vegetation establishment, vegetation-edge movement, and erosion/waterline
questions separate so a positive greenness signal cannot be misreported as proof of
shoreline protection.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/surat_thani_erosion_free_data_v1.json"
TIDE = ROOT / "web/public/data/surat_thani/tide_context.json"
FRONTAGE = ROOT / "web/public/data/surat_thani/project_frontage_summary.json"
COMPARATIVE = ROOT / "data/analysis/surat_thani/comparative_screening.json"
TIDE_SENS = ROOT / "data/analysis/surat_thani/tide_matched_sensitivity_summary.json"
VEG_EDGE = ROOT / "data/analysis/surat_thani/mangrove_edge_proxy_screening.json"
ESTABLISHMENT = ROOT / "data/analysis/surat_thani/planting_establishment_screening.json"
S1 = ROOT / "data/analysis/surat_thani/s1_relative_corroboration.json"
CONTROL_VERIFY = ROOT / "data/analysis/surat_thani/control_verification.json"
OUT = ROOT / "data/analysis/surat_thani/executive_summary.json"
WEB = ROOT / "web/public/data/surat_thani/executive_summary.json"
INTERNAL_WEB = ROOT / "data/processed/surat_thani/web/executive_summary.json"
MD = ROOT / "regions/surat_thani/EXECUTIVE_SUMMARY_TH.md"


def load(path: Path, required: bool = True) -> Any:
    if not path.exists():
        if required:
            raise FileNotFoundError(path)
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def fnum(value: Any) -> float | None:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if x == x and abs(x) != float("inf") else None


def main() -> int:
    config = load(CONFIG)
    tide = load(TIDE)
    frontage = load(FRONTAGE)
    comparative = load(COMPARATIVE)
    tide_sens = load(TIDE_SENS)
    veg = load(VEG_EDGE)
    establishment = load(ESTABLISHMENT)
    s1 = load(S1, required=False)
    verify = load(CONTROL_VERIFY)

    veg_primary = veg["primary_result"]
    veg_project = veg_primary["project_frontage"]
    veg_control = veg_primary["pooled_controls"]
    veg_net_contrast = fnum(veg_primary.get("project_minus_control_change_2023_2026_m"))
    veg_instability = fnum(veg.get("robustness", {}).get("empirical_edge_instability_floor_m"))
    veg_edge_status = (
        "NO_DETECTABLE_10M_SCALE_RELATIVE_EDGE_ADVANCE"
        if veg_net_contrast is not None and abs(veg_net_contrast) < max(veg_instability or 10.0, 10.0)
        else "RELATIVE_EDGE_CHANGE_REQUIRES_REVIEW"
    )

    est_robust = establishment["robustness"]
    ndvi_did = fnum(est_robust.get("median_ndvi_2026_vs_2023_did"))
    green_did = fnum(est_robust.get("primary_green_fraction_2026_vs_2023_did"))
    threshold_sign = est_robust.get("green_fraction_2026_vs_2023_did_sign_across_thresholds")
    p2023 = establishment["project_annual_metrics"]["2023"]
    p2026 = establishment["project_annual_metrics"]["2026"]
    ndvi_scene_range = max(
        fnum(p2023.get("single_scene_median_ndvi_range")) or 0.0,
        fnum(p2026.get("single_scene_median_ndvi_range")) or 0.0,
    )
    green_scene_range = max(
        fnum(p2023.get("single_scene_green_fraction_range")) or 0.0,
        fnum(p2026.get("single_scene_green_fraction_range")) or 0.0,
    )
    positive_est = ndvi_did is not None and green_did is not None and ndvi_did > 0 and green_did > 0 and threshold_sign == "CONSISTENT_POSITIVE"
    small_vs_scene = (
        positive_est
        and abs(ndvi_did) <= max(ndvi_scene_range, 1e-9)
        and abs(green_did) <= max(green_scene_range, 1e-9)
    )
    establishment_status = (
        "SMALL_POSITIVE_RELATIVE_OPTICAL_SIGNAL_WITHIN_SINGLE_SCENE_VARIABILITY"
        if small_vs_scene
        else "POSITIVE_RELATIVE_OPTICAL_SIGNAL"
        if positive_est
        else "MIXED_OR_NONPOSITIVE_OPTICAL_SIGNAL"
    )

    baseline_contrast = fnum(tide_sens.get("baseline_three_scene_composite", {}).get("project_minus_control_apparent_change_2023_2026_m"))
    matched_contrast = fnum(tide_sens.get("tide_matched_contrasts", {}).get("project_minus_control_apparent_change_2023_2026_m"))
    sensitivity_shift = fnum(tide_sens.get("sensitivity_delta", {}).get("net_contrast_matched_minus_baseline_m"))
    waterline_failed = baseline_contrast is not None and matched_contrast is not None and baseline_contrast * matched_contrast < 0
    waterline_status = "FAILED_SCENE_TIDE_ROBUSTNESS_SIGN_REVERSAL" if waterline_failed else "SUPPORTING_ONLY"

    s1_summary: dict[str, Any]
    if s1:
        s1_summary = {
            "status": s1.get("evidence_status", {}).get("claim_status"),
            "selected_track": s1.get("method", {}).get("selected_track_key"),
            "change_2026_vs_2023_in_within_scene_project_minus_control": s1.get("change_2026_vs_2023_in_within_scene_project_minus_control"),
            "interpretation": "Independent relative GRD diagnostic only; absolute SAR biomass/backscatter interpretation is not allowed because RTC/calibrated publication-grade processing was not used.",
        }
    else:
        s1_summary = {"status": "NOT_AVAILABLE_AT_SUMMARY_BUILD_TIME"}

    causal_status = "CURRENT_EVIDENCE_DOES_NOT_SUPPORT_CAUSAL_EROSION_REDUCTION_CLAIM"
    monitoring_status = "CONTINUE_MONITORING_SMALL_POSITIVE_VEGETATION_SIGNAL_BUT_NO_DETECTABLE_10M_EDGE_ADVANCE"

    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "project": {
            "province": "Surat Thani",
            "plot_code": "37-STC",
            "location": "Ban Lamet, Lamet Subdistrict, Chaiya District, Surat Thani",
            "primary_boundary_area_rai": 157.55,
            "representative_intervention_date": "2023-10-18",
            "seedlings_total": 142232,
        },
        "executive_decision": {
            "causal_erosion_reduction_claim": causal_status,
            "vegetation_establishment": establishment_status,
            "coastal_vegetation_edge_expansion": veg_edge_status,
            "waterline_erosion_indicator": waterline_status,
            "control_intervention_exclusion": verify.get("status"),
            "field_uav_validation": "REQUIRED_BEFORE_IMPACT_LANGUAGE",
            "overall_monitoring_status": monitoring_status,
        },
        "key_numbers": {
            "optical_establishment": {
                "median_ndvi_project_minus_control_change_2026_vs_2023": ndvi_did,
                "green_fraction_ndvi_ge_0_32_project_minus_control_change_2026_vs_2023": green_did,
                "green_fraction_change_percentage_points": None if green_did is None else round(green_did * 100.0, 2),
                "threshold_sign_0_28_0_32_0_36": threshold_sign,
                "project_single_scene_ndvi_range_2023_2026_max": round(ndvi_scene_range, 4),
                "project_single_scene_green_fraction_range_2023_2026_max": round(green_scene_range, 4),
            },
            "coastal_vegetation_edge": {
                "project_median_change_2023_2026_m": veg_project.get("median_change_2023_to_2026_m"),
                "control_median_change_2023_2026_m": veg_control.get("median_change_2023_to_2026_m"),
                "project_minus_control_change_m": veg_net_contrast,
                "project_pre_slope_m_per_year": veg_project.get("median_pre_2017_2023_slope_m_per_year"),
                "project_post_slope_m_per_year": veg_project.get("median_post_2024_2026_slope_m_per_year"),
                "empirical_edge_instability_floor_m": veg_instability,
                "threshold_net_contrasts_m": veg.get("robustness", {}).get("net_contrast_values_m"),
            },
            "waterline_sensitivity": {
                "baseline_three_scene_project_minus_control_2023_2026_m": baseline_contrast,
                "tide_stage_single_scene_project_minus_control_2023_2026_m": matched_contrast,
                "sensitivity_shift_m": sensitivity_shift,
                "sign_reversal": waterline_failed,
            },
            "first_pass_waterline_frontage": frontage.get("image_derived_water_land_boundary_screening"),
        },
        "evidence_stack": {
            "sentinel2_coastal_vegetation_edge": {
                "role": "PRIMARY_SATELLITE_SCREENING_INDICATOR",
                "status": veg_edge_status,
                "source": "data/analysis/surat_thani/mangrove_edge_proxy_screening.json",
            },
            "sentinel2_in_plot_establishment": {
                "role": "PLANTING_ESTABLISHMENT_SCREENING",
                "status": establishment_status,
                "source": "data/analysis/surat_thani/planting_establishment_screening.json",
            },
            "waterline": {
                "role": "SUPPORTING_CONTEXT_ONLY",
                "status": waterline_status,
                "source": "data/analysis/surat_thani/tide_matched_sensitivity_summary.json",
            },
            "tide": {
                "role": "SCENE_SCREENING_CONTEXT",
                "status": tide.get("waterline_gate", {}).get("status"),
                "ko_prap_distance_km": tide.get("station", {}).get("distance_from_project_centroid_km"),
            },
            "controls": {
                "role": "NO_KNOWN_INTERVENTION_REFERENCE",
                "status": verify.get("status"),
                "candidate_count": comparative.get("controls", {}).get("candidate_count"),
            },
            "sentinel1": s1_summary,
        },
        "what_the_data_supports": [
            "A small positive 2023-to-2026 optical greenness/green-pixel change is present inside 37-STC relative to the selected no-known-intervention controls, and the sign is positive across the tested NDVI thresholds.",
            "The size of that optical establishment signal is small and within the range of single-scene variability observed in the project, so it is a monitoring signal rather than confirmation of survival or canopy gain.",
            "No 10 m-scale relative seaward expansion of the persistent coastal-vegetation edge is detected from 2023 to 2026 at the primary threshold; the project and pooled controls both have median net change of about zero.",
            "The automated water-land boundary is not robust enough for an erosion-effect conclusion because the project-minus-control result reverses sign under tide-stage/scene selection.",
        ],
        "what_the_data_do_not_support": [
            "Do not state that planting has reduced coastal erosion based on the current satellite waterline analysis.",
            "Do not translate the small positive NDVI signal into a survival percentage or planted-tree count.",
            "Do not describe the 10 m NDVI vegetation edge as a species-confirmed mangrove boundary without UAV/field/orthophoto validation.",
            "Do not use the relative Sentinel-1 GRD diagnostic as calibrated biomass or absolute backscatter evidence.",
        ],
        "next_actions_ranked": [
            {"rank": 1, "action": "UAV/orthophoto validation of mangrove canopy/edge and sparse planting inside the PDD", "why": "resolves the main 10 m Sentinel-2 sub-pixel limitation and validates whether the detected greenness belongs to planted mangrove"},
            {"rank": 2, "action": "Field survival/height/canopy observations on representative 37-STC transects", "why": "converts the small optical establishment signal into biological evidence"},
            {"rank": 3, "action": "Manual bank-edge or stable geomorphic-edge digitization from higher-resolution imagery", "why": "provides an erosion indicator less tide-sensitive than the wet/dry waterline"},
            {"rank": 4, "action": "Repeat annual Sentinel-2 establishment and vegetation-edge metrics with the same February-April protocol", "why": "young planting may require more time before a 10 m-scale canopy/edge signal becomes detectable"},
            {"rank": 5, "action": "If SAR is needed for publication, rerun with calibrated RTC / incidence-angle-consistent processing", "why": "the current GRD analysis is intentionally only a relative diagnostic"},
        ],
        "source_files": {
            "config": str(CONFIG.relative_to(ROOT)),
            "tide_context": str(TIDE.relative_to(ROOT)),
            "frontage": str(FRONTAGE.relative_to(ROOT)),
            "waterline_comparative": str(COMPARATIVE.relative_to(ROOT)),
            "waterline_tide_sensitivity": str(TIDE_SENS.relative_to(ROOT)),
            "vegetation_edge": str(VEG_EDGE.relative_to(ROOT)),
            "planting_establishment": str(ESTABLISHMENT.relative_to(ROOT)),
            "sentinel1_relative": str(S1.relative_to(ROOT)) if S1.exists() else None,
            "control_verification": str(CONTROL_VERIFY.relative_to(ROOT)),
        },
    }

    for path in [OUT, WEB, INTERNAL_WEB]:
        write(path, payload)
    for path in [ROOT / "web/public/data/surat_thani/index.json", ROOT / "data/processed/surat_thani/web/index.json"]:
        if path.exists():
            idx = load(path)
            idx["executive_summary_file"] = "executive_summary.json"
            idx["executive_summary_status"] = causal_status
            idx["primary_satellite_indicator"] = "coastal_vegetation_edge_proxy"
            idx["planting_establishment_signal"] = establishment_status
            idx["waterline_role"] = "SUPPORTING_CONTEXT_ONLY_FAILED_ROBUSTNESS_TEST"
            write(path, idx)

    md = f"""# สรุปผู้บริหาร — 37-STC สุราษฎร์ธานี

อัปเดต: {payload['generated_at_utc']}

## ข้อสรุปหลัก

**หลักฐานที่มีในปัจจุบันยังไม่รองรับการสรุปเชิงเหตุและผลว่า การปลูกป่าชายเลนทำให้การกัดเซาะชายฝั่งลดลง**

อย่างไรก็ตาม การติดตามด้วย Sentinel-2 พบ **สัญญาณการเพิ่มขึ้นของพืชภายในแปลงเมื่อเทียบกับ control เล็กน้อย** หลังปี 2023:
- median NDVI แบบ project-minus-control change (2026 เทียบ 2023): **{ndvi_did:+.4f}**
- สัดส่วนพิกเซล NDVI ≥ 0.32 เพิ่มสุทธิ: **{green_did * 100:+.2f} จุดเปอร์เซ็นต์**
- เครื่องหมายของ green-fraction เป็นบวกครบเกณฑ์ NDVI 0.28 / 0.32 / 0.36

แต่ขนาดสัญญาณยังอยู่ในระดับความแปรปรวนระหว่างภาพบาง scene จึงควรเรียกว่า **small positive monitoring signal** ไม่ใช่หลักฐานยืนยัน survival หรือ canopy gain

## แนวขอบพืชชายฝั่ง

การวัดขอบพืชจาก Sentinel-2 ความละเอียด 10 ม. พบว่า 2023→2026:
- หน้าแปลง 37-STC: **{veg_project.get('median_change_2023_to_2026_m')} ม.**
- control รวม: **{veg_control.get('median_change_2023_to_2026_m')} ม.**
- project − control: **{veg_net_contrast} ม.**

ดังนั้น **ยังไม่พบการขยายตัวออกทะเลของขอบพืชที่ตรวจจับได้ในระดับ 10 ม.** ทั้งนี้ต้นปลูกอายุน้อย/บางสามารถอยู่ต่ำกว่าขนาดพิกเซลได้

## เหตุผลที่ไม่ใช้ waterline เป็นหลักฐานหลัก

ผลขอบน้ำ–แผ่นดินเปลี่ยนจาก project-minus-control **{baseline_contrast:+.2f} ม.** ใน composite 3 ภาพ/ปี เป็น **{matched_contrast:+.2f} ม.** เมื่อคัด scene ตาม tide stage หรือเปลี่ยนไป **{sensitivity_shift:+.2f} ม.** และกลับเครื่องหมาย

จึงถือว่า waterline **ไม่ผ่าน robustness test** สำหรับการกล่าวอ้างผลของโครงการ และใช้ได้เพียงเป็นข้อมูลประกอบ

## สิ่งที่ควรทำต่อ

1. UAV/orthophoto ตรวจ canopy, sparse seedlings และ mangrove edge ภายในแปลง
2. เก็บ survival/height/canopy ภาคสนามบน transect ตัวแทน
3. digitize bank edge หรือ stable geomorphic edge จากภาพความละเอียดสูง
4. รัน Sentinel-2 protocol เดิมซ้ำทุกปี เพื่อรอให้ canopy/edge signal เกินข้อจำกัด 10 ม.
5. หากจะใช้ SAR ในรายงานวิชาการ ให้ใช้ calibrated RTC processing แทน GRD relative diagnostic

## ภาษาที่ใช้ได้ตอนนี้

> ข้อมูลดาวเทียมพบสัญญาณการเพิ่มขึ้นของความเขียวภายในแปลง 37-STC เล็กน้อยเมื่อเทียบกับพื้นที่อ้างอิง แต่ยังไม่พบการขยายตัวของขอบพืชในระดับความละเอียด 10 เมตร และผล waterline มีความไวต่อระดับน้ำ/การเลือกภาพสูง จึงยังไม่สามารถสรุปว่าการปลูกช่วยลดการกัดเซาะชายฝั่งได้โดยตรง จำเป็นต้องยืนยันด้วย UAV/ภาพความละเอียดสูงและข้อมูลภาคสนาม
"""
    MD.parent.mkdir(parents=True, exist_ok=True)
    MD.write_text(md, encoding="utf-8")

    print(json.dumps({
        "causal_status": causal_status,
        "establishment_status": establishment_status,
        "ndvi_did": ndvi_did,
        "green_fraction_did": green_did,
        "vegetation_edge_status": veg_edge_status,
        "waterline_status": waterline_status,
        "s1_status": s1_summary.get("status"),
        "outputs": [str(p.relative_to(ROOT)) for p in [OUT, WEB, MD]],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
