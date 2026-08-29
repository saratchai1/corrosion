import { useEffect, useRef } from 'react'
import * as maplibregl from 'maplibre-gl'
import type { FeatureCollection, MultiPolygon, Polygon } from 'geojson'
import type { GeoJSONSource, Map as MapLibreMap, MapLayerMouseEvent } from 'maplibre-gl'
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url'

maplibregl.setWorkerUrl(workerUrl)

const mapStyle: maplibregl.StyleSpecification = {
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
    { id: 'background', type: 'background', paint: { 'background-color': '#dce7e2' } },
    { id: 'osm', type: 'raster', source: 'osm', paint: { 'raster-saturation': -0.62, 'raster-opacity': 0.83 } },
  ],
}

type PlotFeatureCollection = FeatureCollection<Polygon | MultiPolygon, {
  plot_id: string
  official_participating_area_rai: number
  geometry_area_rai: number
}>

function boundsOf(collection: PlotFeatureCollection): maplibregl.LngLatBoundsLike {
  let west = 180
  let south = 90
  let east = -180
  let north = -90
  const visit = (value: unknown): void => {
    if (!Array.isArray(value)) return
    if (typeof value[0] === 'number' && typeof value[1] === 'number') {
      west = Math.min(west, value[0])
      south = Math.min(south, value[1])
      east = Math.max(east, value[0])
      north = Math.max(north, value[1])
      return
    }
    value.forEach(visit)
  }
  collection.features.forEach((feature) => visit(feature.geometry.coordinates))
  return [[west, south], [east, north]]
}

export default function ProjectMap() {
  const container = useRef<HTMLDivElement>(null)
  const mapRef = useRef<MapLibreMap | null>(null)

  useEffect(() => {
    if (!container.current) return
    const map = new maplibregl.Map({
      container: container.current,
      style: mapStyle,
      center: [99.93, 13.3],
      zoom: 10.5,
      attributionControl: false,
    })
    mapRef.current = map
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right')
    map.addControl(new maplibregl.AttributionControl({ compact: true }), 'bottom-right')

    const handleClick = (event: MapLayerMouseEvent) => {
      const feature = event.features?.[0]
      if (!feature?.properties) return
      const properties = feature.properties
      new maplibregl.Popup({ closeButton: false, offset: 8 })
        .setLngLat(event.lngLat)
        .setHTML(`<strong>${String(properties.plot_id)}</strong><br><span>พื้นที่ทางการ ${Number(properties.official_participating_area_rai).toFixed(2)} ไร่</span>`)
        .addTo(map)
    }
    const handleEnter = () => { map.getCanvas().style.cursor = 'pointer' }
    const handleLeave = () => { map.getCanvas().style.cursor = '' }

    map.on('load', async () => {
      const response = await fetch('data/project/plots.geojson')
      const plots = await response.json() as PlotFeatureCollection
      map.addSource('project-plots', { type: 'geojson', data: plots })
      map.addLayer({
        id: 'project-plots-fill',
        type: 'fill',
        source: 'project-plots',
        paint: {
          'fill-color': ['match', ['get', 'plot_id'], '87-VSD', '#f0ad33', '#a666dd'],
          'fill-opacity': 0.48,
        },
      })
      map.addLayer({
        id: 'project-plots-line',
        type: 'line',
        source: 'project-plots',
        paint: { 'line-color': '#6f299d', 'line-width': 2.4 },
      })
      const source = map.getSource('project-plots') as GeoJSONSource
      source.setData(plots)
      map.fitBounds(boundsOf(plots), { padding: 42, duration: 0, maxZoom: 13 })
      map.on('click', 'project-plots-fill', handleClick)
      map.on('mouseenter', 'project-plots-fill', handleEnter)
      map.on('mouseleave', 'project-plots-fill', handleLeave)
    })

    return () => {
      map.off('click', 'project-plots-fill', handleClick)
      map.off('mouseenter', 'project-plots-fill', handleEnter)
      map.off('mouseleave', 'project-plots-fill', handleLeave)
      map.remove()
    }
  }, [])

  return <div ref={container} className="project-map-canvas" aria-label="แผนที่ขอบเขตแปลงปลูกป่าชายเลน 9 แปลง" />
}
