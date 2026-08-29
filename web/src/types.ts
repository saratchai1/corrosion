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
