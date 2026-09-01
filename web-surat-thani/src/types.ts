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
  primary_satellite_indicator?: string
  planting_establishment_signal?: string
  waterline_role?: string
  evidence_stack_qa_status?: string
  epochs: Epoch[]
}

export type ExecutiveSummary = {
  project: {
    province: string
    plot_code: string
    location: string
    primary_boundary_area_rai: number
    representative_intervention_date: string
    seedlings_total: number
  }
  executive_decision: {
    causal_erosion_reduction_claim: string
    vegetation_establishment: string
    coastal_vegetation_edge_expansion: string
    waterline_erosion_indicator: string
    control_intervention_exclusion: string
    field_uav_validation: string
    overall_monitoring_status: string
  }
  key_numbers: {
    optical_establishment: {
      median_ndvi_project_minus_control_change_2026_vs_2023: number
      green_fraction_ndvi_ge_0_32_project_minus_control_change_2026_vs_2023: number
      green_fraction_change_percentage_points: number
      threshold_sign_0_28_0_32_0_36: string
    }
    coastal_vegetation_edge: {
      project_median_change_2023_2026_m: number
      control_median_change_2023_2026_m: number
      project_minus_control_change_m: number
      project_pre_slope_m_per_year: number
      project_post_slope_m_per_year: number
      empirical_edge_instability_floor_m: number
    }
    waterline_sensitivity: {
      baseline_three_scene_project_minus_control_2023_2026_m: number
      tide_stage_single_scene_project_minus_control_2023_2026_m: number
      sensitivity_shift_m: number
      sign_reversal: boolean
    }
  }
  what_the_data_supports: string[]
  what_the_data_do_not_support: string[]
}

export type EvidenceManifest = {
  overall_status: string
  causal_erosion_reduction_claim: string
  remaining_hard_gates: string[]
  evidence_layers: Record<string, {
    qa?: string
    status?: string
    role?: string
    [key: string]: unknown
  }>
}

export type ViewState = {
  center: [number, number]
  zoom: number
  bearing: number
  pitch: number
}

export type TransectSelection = {
  id: string
  group: string
  classification: string
  confidence: string
  edgePositions: Record<string, number | null>
  edgeChanges: Record<string, number | null>
  thresholdSpread: Record<string, number | null>
}

export type LayerVisibility = {
  imagery: boolean
  vegetation: boolean
  waterline: boolean
  vegetationEdge: boolean
  projectBoundary: boolean
  controls: boolean
}
