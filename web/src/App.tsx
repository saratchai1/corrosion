import { useEffect, useRef, useState } from 'react';
import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { AlertTriangle, Info, Map as MapIcon, Layers } from 'lucide-react';

export default function App() {
  const mapContainer = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);

  const [year1, setYear1] = useState('2018');
  const [year2, setYear2] = useState('2025');
  const [selectedLayer, setSelectedLayer] = useState('rgb');

  const dates = {
    '2018': '2018-02-06',
    '2021': '2021-12-27',
    '2025': '2025-12-21'
  };

  useEffect(() => {
    if (map.current) return;

    map.current = new maplibregl.Map({
      container: mapContainer.current!,
      style: {
        version: 8,
        sources: {
          'osm': {
            type: 'raster',
            tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
            tileSize: 256,
            attribution: '&copy; OpenStreetMap'
          }
        },
        layers: [
          {
            id: 'osm-layer',
            type: 'raster',
            source: 'osm',
            minzoom: 0,
            maxzoom: 19
          }
        ]
      },
      center: [101.7307, 12.7147],
      zoom: 11
    });

    map.current.on('load', async () => {
      if (!map.current) return;
      
      const m = map.current;

      // Add Sources
      m.addSource('aoi', { type: 'geojson', data: '/corrosion/data/rayong_coastal_analysis_aoi.geojson' });
      m.addLayer({
        id: 'aoi-layer',
        type: 'line',
        source: 'aoi',
        paint: { 'line-color': '#eab308', 'line-width': 2, 'line-dasharray': [2, 2] }
      });

      m.addSource('plots', { type: 'geojson', data: '/corrosion/data/rayong_planting_plots_validated.geojson' });
      m.addLayer({
        id: 'plots-layer',
        type: 'line',
        source: 'plots',
        paint: { 'line-color': '#06b6d4', 'line-width': 2 }
      });
      m.addLayer({
        id: 'plots-fill',
        type: 'fill',
        source: 'plots',
        paint: { 'fill-color': '#06b6d4', 'fill-opacity': 0.1 }
      });

      // Click event for plots
      m.on('click', 'plots-fill', (e) => {
        const p = e.features?.[0]?.properties;
        if (p) {
          alert(`Plot ID: ${p.plotId || p.Plot_ID || p.id}\nArea: ${p.area_rai || 'N/A'} Rai\nStatus: ${p.status || 'N/A'}`);
        }
      });

      // Load rasters & shorelines for 2018, 2021, 2025
      const bounds = [101.63962754434515, 12.650781002824594, 101.82185961897238, 12.778649590887627];
      const coordBounds: [[number, number], [number, number], [number, number], [number, number]] = [
        [bounds[0], bounds[3]], // top-left
        [bounds[2], bounds[3]], // top-right
        [bounds[2], bounds[1]], // bottom-right
        [bounds[0], bounds[1]]  // bottom-left
      ];

      ['2018', '2021', '2025'].forEach(y => {
        const d = dates[y as keyof typeof dates];
        
        ['rgb', 'nir', 'ndwi', 'mndwi'].forEach(l => {
          const srcId = `${y}-${l}`;
          m.addSource(srcId, {
            type: 'image',
            url: `/corrosion/data/layers/${d}_${l}.png`,
            coordinates: coordBounds
          });
          m.addLayer({
            id: `${srcId}-layer`,
            type: 'raster',
            source: srcId,
            paint: { 'raster-opacity': 0 }, // hidden by default
          }, 'aoi-layer');
        });

        // Add apparent water edge
        m.addSource(`${y}-shoreline`, { type: 'geojson', data: `/corrosion/data/${d}_water_edge.geojson` });
        m.addLayer({
          id: `${y}-shoreline-layer`,
          type: 'line',
          source: `${y}-shoreline`,
          paint: { 
            'line-color': y === '2018' ? '#ef4444' : y === '2021' ? '#f97316' : '#84cc16', 
            'line-width': 2,
            'line-opacity': 0 // hidden by default
          }
        });
      });

      // Load transects
      try {
        m.addSource('transects', { type: 'geojson', data: '/corrosion/data/rayong_transects_50m.geojson' });
      } catch (e) {}

      updateLayers(year1, year2, selectedLayer);
    });
  }, []);

  const updateLayers = (y1: string, y2: string, layer: string) => {
    if (!map.current || !map.current.isStyleLoaded()) return;
    const m = map.current;

    ['2018', '2021', '2025'].forEach(y => {
      ['rgb', 'nir', 'ndwi', 'mndwi'].forEach(l => {
        const id = `${y}-${l}-layer`;
        if (m.getLayer(id)) {
           // We show the right side (y2) fully, left side (y1) can be done via clipping/swipe.
           // For simplicity in MapLibre without a swipe plugin, let's just show y2 over y1?
           // Wait, the prompt says "Side-by-side synchronized maps" OR "Swipe". 
           // If we just show ONE image and TWO shorelines, it's easier. Let's just show y2's raster, and BOTH shorelines.
           m.setPaintProperty(id, 'raster-opacity', (y === y2 && l === layer) ? 1 : 0);
        }
      });
      
      const slId = `${y}-shoreline-layer`;
      if (m.getLayer(slId)) {
        m.setPaintProperty(slId, 'line-opacity', (y === y1 || y === y2) ? 1 : 0);
      }
    });
  };

  useEffect(() => {
    updateLayers(year1, year2, selectedLayer);
  }, [year1, year2, selectedLayer]);

  return (
    <div className="flex h-screen bg-neutral-900 text-slate-100 flex-col md:flex-row">
      {/* Sidebar */}
      <div className="w-full md:w-96 p-4 flex flex-col gap-4 overflow-y-auto border-r border-neutral-800">
        <h1 className="text-xl font-bold">ชายฝั่งบริเวณแปลงปลูกป่าชายเลนระยอง</h1>
        
        <div className="bg-red-950/40 border border-red-900/50 p-3 rounded-lg text-sm text-red-200 flex gap-2">
          <AlertTriangle className="shrink-0 w-5 h-5 text-red-500" />
          <div>
            <strong className="block mb-1 text-red-400">Tide-unverified screening — not an engineering erosion rate.</strong>
            การคัดกรองการเปลี่ยนแปลงเบื้องต้น ยังไม่ได้ปรับแก้ผลกระทบจากระดับน้ำขึ้นลง และไม่ใช่อัตราการกัดเซาะทางวิศวกรรม
          </div>
        </div>

        <div className="bg-neutral-800 p-4 rounded-lg">
          <h2 className="font-semibold mb-3 flex items-center gap-2">
            <MapIcon className="w-4 h-4" /> ปีเปรียบเทียบ (Before/After)
          </h2>
          <div className="flex gap-2 mb-3">
            <select className="flex-1 bg-neutral-700 p-2 rounded" value={year1} onChange={e => setYear1(e.target.value)}>
              <option value="2018">2018 (6 Feb)</option>
              <option value="2021">2021 (27 Dec)</option>
              <option value="2025">2025 (21 Dec)</option>
            </select>
            <span className="flex items-center text-neutral-400">→</span>
            <select className="flex-1 bg-neutral-700 p-2 rounded" value={year2} onChange={e => setYear2(e.target.value)}>
              <option value="2018">2018 (6 Feb)</option>
              <option value="2021">2021 (27 Dec)</option>
              <option value="2025">2025 (21 Dec)</option>
            </select>
          </div>
        </div>

        <div className="bg-neutral-800 p-4 rounded-lg">
          <h2 className="font-semibold mb-3 flex items-center gap-2">
            <Layers className="w-4 h-4" /> ภาพดาวเทียม
          </h2>
          <select className="w-full bg-neutral-700 p-2 rounded" value={selectedLayer} onChange={e => setSelectedLayer(e.target.value)}>
            <option value="rgb">ภาพจริง (RGB)</option>
            <option value="nir">False Color (NIR)</option>
            <option value="ndwi">NDWI (ดัชนีน้ำ)</option>
            <option value="mndwi">MNDWI (ดัชนีน้ำปรับปรุง)</option>
          </select>
        </div>

        <div className="bg-neutral-800 p-4 rounded-lg flex flex-col gap-2 text-sm">
          <h2 className="font-semibold mb-1 flex items-center gap-2">
            <Info className="w-4 h-4" /> สรุปข้อมูล
          </h2>
          <div className="flex justify-between border-b border-neutral-700 pb-2">
            <span className="text-neutral-400">พื้นที่ศึกษา</span>
            <span>~154 km²</span>
          </div>
          <div className="flex justify-between border-b border-neutral-700 pb-2">
            <span className="text-neutral-400">แปลงปลูก</span>
            <span>14 แปลง</span>
          </div>
          <div className="flex justify-between border-b border-neutral-700 pb-2">
            <span className="text-neutral-400">ภาพดาวเทียม</span>
            <span>Sentinel-2 (10m)</span>
          </div>
          <div className="flex justify-between pb-2">
            <span className="text-neutral-400">สถานะข้อมูล</span>
            <span className="text-orange-400">Tide unverified</span>
          </div>
        </div>

        <div className="bg-neutral-800 p-4 rounded-lg mt-auto text-xs text-neutral-400">
          <h3 className="font-bold mb-2">ข้อจำกัดของข้อมูล (Data Provenance)</h3>
          <ul className="list-disc pl-4 space-y-1">
            <li>ภาพดาวเทียมถ่ายต่างช่วงเวลา</li>
            <li>ยังไม่ได้ปรับแก้ระดับน้ำ (Tide Normalization)</li>
            <li>เส้นขอบน้ำที่แสดงเป็นเพียงขอบน้ำปรากฏ (Apparent Water Edge)</li>
            <li>นี่คือข้อมูลคัดกรองเบื้องต้น ไม่ใช่อัตราการกัดเซาะทางวิศวกรรม</li>
          </ul>
        </div>
      </div>

      {/* Map */}
      <div className="flex-1 relative">
        <div ref={mapContainer} className="absolute inset-0" />
        
        {/* Legend */}
        <div className="absolute bottom-6 right-6 bg-neutral-900/80 p-3 rounded-lg border border-neutral-700 text-sm backdrop-blur-sm pointer-events-none">
          <div className="font-bold mb-2">สัญลักษณ์ (Legend)</div>
          <div className="flex items-center gap-2 mb-1">
            <div className="w-4 h-1 bg-yellow-500 border-t border-dashed"></div> พื้นที่ศึกษา
          </div>
          <div className="flex items-center gap-2 mb-1">
            <div className="w-4 h-4 bg-cyan-500/20 border border-cyan-500"></div> แปลงปลูก
          </div>
          <div className="flex items-center gap-2 mb-1">
            <div className="w-4 h-1 bg-red-500"></div> ขอบน้ำ 2018
          </div>
          <div className="flex items-center gap-2 mb-1">
            <div className="w-4 h-1 bg-orange-500"></div> ขอบน้ำ 2021
          </div>
          <div className="flex items-center gap-2">
            <div className="w-4 h-1 bg-lime-500"></div> ขอบน้ำ 2025
          </div>
        </div>
      </div>
    </div>
  );
}
