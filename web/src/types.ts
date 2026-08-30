export type Epoch = {
  targetYear: number
  actualYear: number
  dataset: string
  sensor: string
  dates: string[]
  sceneCount: number
  resolutionM: number
  tideStatus: string
  mndwiThreshold: number
  validFraction: number
  oceanFraction: number
  vegetationAreaHa: number
  image: string
  imageCoordinates: [[number, number], [number, number], [number, number], [number, number]]
  boundary: string
  vegetation: string
}

export type DataIndex = {
  title: string
  aoi: string
  analysis_crs: string
  tide_status: string
  disclaimer_th: string
  disclaimer_en: string
  epochs: Epoch[]
}

export type Summary = {
  epoch_count: number
  transect_count: number
  classified_transect_count: number
  apparent_erosion_length_km: number
  apparent_accretion_length_km: number
  stable_length_km: number
  median_net_change_m: number | null
  vegetation_proxy_change_ha: number
  vegetation_proxy_change_percent: number
  overall_confidence: string
  vegetation_proxy: Array<{ target_year: number; actual_year: number; area_ha: number }>
}

export type ProjectImpactSummary = {
  title: string
  years: number[]
  plot_count: number
  plot_ids: string[]
  official_participating_area_rai: number
  erosion_effect_conclusion: string
  conclusion_th: string
  confidence: string
  design: {
    pre: number[]
    intervention_ambiguous: number[]
    post: number[]
    season_window: string
    matched_control: string
  }
  project_yearly_metrics: Array<{
    year: number
    period_role: string
    mean_ndvi: number
    median_ndvi: number
    vegetation_fraction_ndvi_gte_0_35: number
    strong_vegetation_fraction_ndvi_gte_0_50: number
    water_fraction_mndwi_gt_0: number
    scene_dates: string
    scene_count: number
    sensor: string
  }>
  matched_control_comparison: Array<{
    year: number
    period_role: string
    impact_mean_ndvi: number
    control_mean_ndvi: number
    impact_vegetation_fraction: number
    control_vegetation_fraction: number
    impact_water_fraction: number
    control_water_fraction: number
    impact_pixel_count: number
    matched_control_pixel_count: number
  }>
  difference_in_differences: Array<{
    post_year: number
    ndvi_difference_in_differences: number
    vegetation_fraction_difference_in_differences: number
    water_fraction_difference_in_differences: number
  }>
  post_boundary_evidence: {
    status: string
    feature: string
    period: string
    transect_count: number
    within_20m_count: number
    apparent_inland_count: number
    apparent_seaward_count: number
    median_movement_m: number | null
    mean_movement_m: number | null
    confidence: string
    per_plot: Array<{
      plot_id: string
      transect_count: number
      median_movement_m: number | null
      mean_movement_m: number | null
      apparent_inland_count: number
      within_20m_count: number
      apparent_seaward_count: number
    }>
    unavailable_plot_ids: string[]
    unavailable_reason: string
  }
  plot_change_summary: Array<{
    plot_id: string
    valid_pixels_2023: number
    ndvi_change_2023_2025: number
    ndvi_change_2023_2026: number
    vegetation_fraction_change_2023_2025: number
    vegetation_fraction_change_2023_2026: number
    water_fraction_change_2023_2025: number
    water_fraction_change_2023_2026: number
    confidence: string
  }>
  limitations: string[]
}

export type TideAwareIndicatorResult = {
  transect_count: number
  classified_transect_count: number
  median_nsm_2023_2026_m: number | null
  median_epr_2023_2026_m_per_year: number | null
  median_lrr_m_per_year: number | null
  class_counts: Record<string, number>
}

export type TideAwarePlotIndicator = {
  treatment_transect_count: number
  candidate_control_count: number
  median_nsm_2023_2026_m: number | null
  candidate_control_median_nsm_2023_2026_m: number | null
  screening_difference_m: number | null
  class_counts: Record<string, number>
}

export type TideAwareSummary = {
  title: string
  evidence_level: string
  erosion_effect_conclusion: string
  allowed_claim_th: string
  plot_count: number
  plot_ids: string[]
  official_participating_area_rai: number
  years: number[]
  waterline_scene_selection: {
    status: string
    criterion: string
    target_tide_m_msl: number
    tide_spread_m: number
    maximum_delta_from_target_m: number
    maximum_secondary_bracket_minutes: number
    source_tier_counts: Record<string, number>
    selected_scenes: Array<{
      year: number
      date: string
      scene_id: string
      tide_level_m_msl: number
      tide_status: string
      tide_source_tier: string
      secondary_bracket_span_minutes: number | null
    }>
    scientific_limit: string
  }
  indicators: {
    waterline: TideAwareIndicatorResult & {
      role: string
      definition: string
    }
    mangrove_edge_proxy: TideAwareIndicatorResult & {
      role: string
      definition: string
      area_ha_by_year: Record<string, number>
    }
  }
  transects: {
    spacing_m: number
    half_length_m: number
    total_count: number
    treatment_count: number
    candidate_pool_count: number
    treatment_count_by_plot: Record<string, number>
    plots_without_treatment_transects: string[]
    plots_without_treatment_transects_explained_by_eligibility: string[]
    unresolved_missing_treatment_plot_ids: string[]
    position_convention: string
    screening_threshold_m: number
  }
  controls: {
    status: string
    target_count_per_plot: number
    selected_count: number
    selected_count_by_plot: Record<string, number>
    selection_basis: string
    unverified_factors: string[]
    screenable_plot_ids: string[]
    screenable_plots_without_candidate_controls: string[]
  }
  coastal_eligibility: {
    method: string
    reference_year: number
    reference_indicator: string
    maximum_frontage_distance_m: number
    screenable_plot_count: number
    screenable_plot_ids: string[]
    excluded_plot_count: number
    excluded_plot_ids: string[]
    manual_review_plot_count: number
    manual_review_plot_ids: string[]
    output_csv: string
    scientific_limit: string
  }
  per_plot: Array<{
    plot_id: string
    official_participating_area_rai: number
    waterline: TideAwarePlotIndicator
    mangrove_edge_proxy: TideAwarePlotIndicator
    coastal_eligibility: {
      eligibility_status: string
      coastal_erosion_scope: string
      treatment_transect_count: number
      distance_to_2026_waterline_m: number
      required_follow_up: string
    }
  }>
  limitations: string[]
}

export type ViewState = {
  center: [number, number]
  zoom: number
  bearing: number
  pitch: number
}

export type TransectSelection = {
  id: string
  positions: Record<string, number | null>
  netChange: number | null
  rate: number | null
  classification: string
  confidence: string
}
