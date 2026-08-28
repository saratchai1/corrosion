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
