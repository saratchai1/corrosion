import { useEffect, useRef } from 'react'
import * as maplibregl from 'maplibre-gl'
import type { Map as MapLibreMap } from 'maplibre-gl'
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url'
import type { Epoch, LayerVisibility, TransectSelection, ViewState } from './types'

maplibregl.setWorkerUrl(workerUrl)

const DATA = 'data/surat_thani/'

const style: maplibregl.StyleSpecification = {
  version: 8,
  sources: {
    osm: {
      type: 'raster',
      tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
      tileSize: 256,
      attribution: '© OpenStreetMap contributors',
    },
  },
  layers: [
    { id: 'background', type: 'background', paint: { 'background-color': '#dbe8e4' } },
    { id: 'osm', type: 'raster', source: 'osm', paint: { 'raster-saturation': -0.65, 'raster-opacity': 0.78 } },
  ],
}

type Props = {
  epoch: Epoch
  label: string
  layers: LayerVisibility
  opacity: number
  sharedView: ViewState
  onView: (value: ViewState) => void
  onTransect: (value: TransectSelection) => void
  showControls?: boolean
  labelSide?: 'left' | 'right'
}

function parseObject(value: unknown): Record<string, number | null> {
  if (!value) return {}
  if (typeof value === 'string') {
    try { return JSON.parse(value) as Record<string, number | null> } catch { return {} }
  }
  return value as Record<string, number | null>
}

export default function MapPane({ epoch, label, layers, opacity, sharedView, onView, onTransect, showControls = true, labelSide = 'left' }: Props) {
  const container = useRef<HTMLDivElement>(null)
  const mapRef = useRef<MapLibreMap | null>(null)
  const internalMove = useRef(false)

  useEffect(() => {
    if (!container.current) return
    const map = new maplibregl.Map({
      container: container.current,
      style,
      center: sharedView.center,
      zoom: sharedView.zoom,
      bearing: sharedView.bearing,
      pitch: sharedView.pitch,
      attributionControl: false,
    })
    mapRef.current = map
    if (showControls) {
      map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right')
      map.addControl(new maplibregl.AttributionControl({ compact: true }), 'bottom-right')
    }
    map.on('move', () => {
      if (internalMove.current) return
      const c = map.getCenter()
      onView({ center: [c.lng, c.lat], zoom: map.getZoom(), bearing: map.getBearing(), pitch: map.getPitch() })
    })
    return () => map.remove()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const map = mapRef.current
    if (!map || !map.loaded()) return
    const c = map.getCenter()
    if (Math.abs(c.lng - sharedView.center[0]) < 1e-7 && Math.abs(c.lat - sharedView.center[1]) < 1e-7 && Math.abs(map.getZoom() - sharedView.zoom) < 1e-4) return
    internalMove.current = true
    map.jumpTo(sharedView)
    internalMove.current = false
  }, [sharedView])

  useEffect(() => {
    const map = mapRef.current
    if (!map) return

    const click = (event: maplibregl.MapLayerMouseEvent) => {
      const p = event.features?.[0]?.properties
      if (!p) return
      onTransect({
        id: String(p.transect_id ?? ''),
        group: String(p.analysis_group ?? ''),
        classification: String(p.classification ?? ''),
        confidence: String(p.confidence ?? ''),
        edgePositions: parseObject(p.edge_positions_m_from_inland),
        edgeChanges: parseObject(p.edge_change_relative_2023_m),
        thresholdSpread: parseObject(p.threshold_spread_m_by_year),
      })
    }
    const enter = () => { map.getCanvas().style.cursor = 'pointer' }
    const leave = () => { map.getCanvas().style.cursor = '' }

    const update = () => {
      if (!map.isStyleLoaded()) { map.once('load', update); return }

      if (map.getLayer('edge-hit')) {
        map.off('click', 'edge-hit', click)
        map.off('mouseenter', 'edge-hit', enter)
        map.off('mouseleave', 'edge-hit', leave)
      }
      for (const id of ['edge-hit','control-edge','project-edge','plot-line','plot-fill','waterline','vegetation','imagery']) if (map.getLayer(id)) map.removeLayer(id)
      for (const id of ['edge','plot','waterline','vegetation','imagery']) if (map.getSource(id)) map.removeSource(id)

      map.addSource('imagery', { type: 'image', url: `${DATA}${epoch.image}`, coordinates: epoch.imageCoordinates })
      map.addLayer({ id: 'imagery', type: 'raster', source: 'imagery', layout: { visibility: layers.imagery ? 'visible' : 'none' }, paint: { 'raster-opacity': opacity, 'raster-fade-duration': 0 } })

      map.addSource('vegetation', { type: 'geojson', data: `${DATA}${epoch.vegetation}` })
      map.addLayer({ id: 'vegetation', type: 'fill', source: 'vegetation', layout: { visibility: layers.vegetation ? 'visible' : 'none' }, paint: { 'fill-color': '#51c878', 'fill-opacity': 0.25, 'fill-outline-color': '#1f7650' } })

      map.addSource('waterline', { type: 'geojson', data: `${DATA}${epoch.boundary}` })
      map.addLayer({ id: 'waterline', type: 'line', source: 'waterline', layout: { visibility: layers.waterline ? 'visible' : 'none', 'line-cap': 'round' }, paint: { 'line-color': '#ff755e', 'line-width': 2, 'line-opacity': 0.72, 'line-dasharray': [2, 2] } })

      map.addSource('plot', { type: 'geojson', data: `${DATA}project_boundary.geojson` })
      map.addLayer({ id: 'plot-fill', type: 'fill', source: 'plot', layout: { visibility: layers.projectBoundary ? 'visible' : 'none' }, paint: { 'fill-color': '#9b7ef4', 'fill-opacity': 0.13 } })
      map.addLayer({ id: 'plot-line', type: 'line', source: 'plot', layout: { visibility: layers.projectBoundary ? 'visible' : 'none' }, paint: { 'line-color': '#d8caff', 'line-width': 2.5 } })

      map.addSource('edge', { type: 'geojson', data: `${DATA}coastal_vegetation_edge_transects.geojson` })
      map.addLayer({ id: 'project-edge', type: 'line', source: 'edge', filter: ['==', ['get', 'analysis_group'], 'PROJECT_37_STC'], layout: { visibility: layers.vegetationEdge ? 'visible' : 'none' }, paint: { 'line-color': '#ffd166', 'line-width': ['interpolate', ['linear'], ['zoom'], 10, 1.7, 14, 3.4], 'line-opacity': 0.9 } })
      map.addLayer({ id: 'control-edge', type: 'line', source: 'edge', filter: ['!=', ['get', 'analysis_group'], 'PROJECT_37_STC'], layout: { visibility: layers.controls ? 'visible' : 'none' }, paint: { 'line-color': '#6fd7ff', 'line-width': 1.5, 'line-opacity': 0.7, 'line-dasharray': [2, 1.5] } })
      map.addLayer({ id: 'edge-hit', type: 'line', source: 'edge', layout: { visibility: (layers.vegetationEdge || layers.controls) ? 'visible' : 'none' }, paint: { 'line-color': '#000', 'line-width': 12, 'line-opacity': 0 } })
      map.on('click', 'edge-hit', click)
      map.on('mouseenter', 'edge-hit', enter)
      map.on('mouseleave', 'edge-hit', leave)
    }

    update()
    return () => {
      map.off('load', update)
      if (map.getLayer('edge-hit')) {
        map.off('click', 'edge-hit', click)
        map.off('mouseenter', 'edge-hit', enter)
        map.off('mouseleave', 'edge-hit', leave)
      }
    }
  }, [epoch, layers, opacity, onTransect])

  return <div className={`map-pane label-${labelSide}`}>
    <div className="map-label"><span>{label}</span><strong>{epoch.targetYear}</strong><small>{epoch.sensor} · {epoch.resolutionM} m</small></div>
    <div ref={container} className="map-canvas" />
  </div>
}
