import { useEffect, useRef } from 'react'
import * as maplibregl from 'maplibre-gl'
import type { Map as MapLibreMap } from 'maplibre-gl'
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url'
import type { Epoch, TransectSelection, ViewState } from './types'

maplibregl.setWorkerUrl(workerUrl)

export type LayerVisibility = {
  imagery: boolean
  boundary: boolean
  vegetation: boolean
  transects: boolean
  plots: boolean
}

type Props = {
  epoch: Epoch
  label: string
  layers: LayerVisibility
  opacity: number
  sharedView: ViewState
  onView: (value: ViewState) => void
  onTransect: (selection: TransectSelection) => void
  interactive?: boolean
  showControls?: boolean
  labelSide?: 'left' | 'right'
}

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
    { id: 'background', type: 'background', paint: { 'background-color': '#d9e5df' } },
    { id: 'osm', type: 'raster', source: 'osm', paint: { 'raster-saturation': -0.58, 'raster-opacity': 0.82 } },
  ],
}

function parsePositions(value: unknown): Record<string, number | null> {
  if (typeof value === 'string') return JSON.parse(value) as Record<string, number | null>
  return value as Record<string, number | null>
}

export default function MapPane({
  epoch,
  label,
  layers,
  opacity,
  sharedView,
  onView,
  onTransect,
  interactive = true,
  showControls = true,
  labelSide = 'left',
}: Props) {
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
      interactive,
    })
    mapRef.current = map
    if (showControls) {
      map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right')
      map.addControl(new maplibregl.AttributionControl({ compact: true }), 'bottom-right')
    }
    map.on('move', () => {
      if (internalMove.current) return
      const center = map.getCenter()
      onView({ center: [center.lng, center.lat], zoom: map.getZoom(), bearing: map.getBearing(), pitch: map.getPitch() })
    })
    return () => map.remove()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const map = mapRef.current
    if (!map || !map.loaded()) return
    const center = map.getCenter()
    if (
      Math.abs(center.lng - sharedView.center[0]) < 1e-7
      && Math.abs(center.lat - sharedView.center[1]) < 1e-7
      && Math.abs(map.getZoom() - sharedView.zoom) < 1e-4
      && Math.abs(map.getBearing() - sharedView.bearing) < 1e-4
      && Math.abs(map.getPitch() - sharedView.pitch) < 1e-4
    ) return
    internalMove.current = true
    map.jumpTo(sharedView)
    internalMove.current = false
  }, [sharedView])

  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    const handleClick = (event: maplibregl.MapLayerMouseEvent) => {
      const feature = event.features?.[0]
      if (!feature?.properties) return
      const props = feature.properties
      onTransect({
        id: String(props.transect_id),
        positions: parsePositions(props.positions_m),
        netChange: props.net_change_m === null ? null : Number(props.net_change_m),
        rate: props.rate_m_per_year === null ? null : Number(props.rate_m_per_year),
        classification: String(props.classification),
        confidence: String(props.confidence),
      })
    }
    const handleEnter = () => { map.getCanvas().style.cursor = 'pointer' }
    const handleLeave = () => { map.getCanvas().style.cursor = '' }
    const update = () => {
      if (!map.isStyleLoaded()) {
        map.once('load', update)
        return
      }
      for (const id of ['transect-hit', 'transects', 'plots-line', 'plots-fill', 'boundary', 'vegetation', 'imagery']) {
        if (map.getLayer(id)) map.removeLayer(id)
      }
      for (const id of ['transects', 'plots', 'boundary', 'vegetation', 'imagery']) {
        if (map.getSource(id)) map.removeSource(id)
      }
      map.addSource('imagery', { type: 'image', url: `data/${epoch.image}`, coordinates: epoch.imageCoordinates })
      map.addLayer({ id: 'imagery', type: 'raster', source: 'imagery', layout: { visibility: layers.imagery ? 'visible' : 'none' }, paint: { 'raster-opacity': opacity, 'raster-fade-duration': 0 } })
      map.addSource('vegetation', { type: 'geojson', data: `data/${epoch.vegetation}` })
      map.addLayer({ id: 'vegetation', type: 'fill', source: 'vegetation', layout: { visibility: layers.vegetation ? 'visible' : 'none' }, paint: { 'fill-color': '#64d17a', 'fill-opacity': 0.32, 'fill-outline-color': '#176b44' } })
      map.addSource('boundary', { type: 'geojson', data: `data/${epoch.boundary}` })
      map.addLayer({ id: 'boundary', type: 'line', source: 'boundary', layout: { visibility: layers.boundary ? 'visible' : 'none', 'line-cap': 'round', 'line-join': 'round' }, paint: { 'line-color': '#ff553f', 'line-width': ['interpolate', ['linear'], ['zoom'], 9, 2, 13, 4] } })
      map.addSource('plots', { type: 'geojson', data: 'data/project/plots.geojson' })
      map.addLayer({ id: 'plots-fill', type: 'fill', source: 'plots', layout: { visibility: layers.plots ? 'visible' : 'none' }, paint: { 'fill-color': '#bd72ff', 'fill-opacity': 0.18 } })
      map.addLayer({ id: 'plots-line', type: 'line', source: 'plots', layout: { visibility: layers.plots ? 'visible' : 'none' }, paint: { 'line-color': '#9c4ce0', 'line-width': ['interpolate', ['linear'], ['zoom'], 9, 1.5, 13, 3] } })
      map.addSource('transects', { type: 'geojson', data: 'data/transects.geojson' })
      map.addLayer({ id: 'transects', type: 'line', source: 'transects', layout: { visibility: layers.transects ? 'visible' : 'none' }, paint: { 'line-color': ['match', ['get', 'classification'], 'apparent_erosion', '#e74b3c', 'apparent_accretion', '#16a36a', 'stable', '#f0ad33', '#9babb1'], 'line-width': 1.1, 'line-opacity': 0.75 } })
      map.addLayer({ id: 'transect-hit', type: 'line', source: 'transects', layout: { visibility: layers.transects ? 'visible' : 'none' }, paint: { 'line-color': '#000000', 'line-width': 12, 'line-opacity': 0 } })
      map.on('click', 'transect-hit', handleClick)
      map.on('mouseenter', 'transect-hit', handleEnter)
      map.on('mouseleave', 'transect-hit', handleLeave)
    }
    update()
    return () => {
      map.off('load', update)
      map.off('click', 'transect-hit', handleClick)
      map.off('mouseenter', 'transect-hit', handleEnter)
      map.off('mouseleave', 'transect-hit', handleLeave)
    }
  }, [epoch, layers, opacity, onTransect])

  return (
    <div className={`map-pane label-${labelSide}`}>
      <div className="map-label"><span>{label}</span><strong>{epoch.targetYear}</strong><small>ภาพจริง {epoch.actualYear}</small></div>
      <div ref={container} className="map-canvas" />
    </div>
  )
}
