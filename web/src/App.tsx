import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
} from 'react';
import maplibregl, {
  type Map as MapLibreMap,
  type StyleSpecification,
} from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import {
  AlertTriangle,
  CalendarRange,
  CheckCircle2,
  Eye,
  Layers3,
  MapPinned,
  Maximize2,
  MoveHorizontal,
  Satellite,
  Trees,
  ZoomIn,
  ZoomOut,
} from 'lucide-react';

type Side = 'before' | 'after';
type LayerKey = 'rgb' | 'nir' | 'ndwi' | 'mndwi';

type Scene = {
  year: string;
  date: string;
  shortDate: string;
};

type ChangeRecord = {
  transect_id: number;
  before_date: string;
  after_date: string;
  apparent_displacement_m: number;
  quality: string;
};

type CompareTestState = {
  ready: boolean;
  mapCount: number;
  beforeYear: string;
  afterYear: string;
  selectedLayer: LayerKey;
  swipe: number;
  plotCount: number | null;
};

declare global {
  interface Window {
    __RAYONG_COMPARE_TEST__?: CompareTestState;
  }
}

const SCENES: Scene[] = [
  { year: '2018', date: '2018-02-06', shortDate: '6 ก.พ. 2018' },
  { year: '2021', date: '2021-12-27', shortDate: '27 ธ.ค. 2021' },
  { year: '2025', date: '2025-12-21', shortDate: '21 ธ.ค. 2025' },
];

const LAYER_OPTIONS: Array<{
  key: LayerKey;
  label: string;
  description: string;
}> = [
  { key: 'rgb', label: 'ภาพจริง', description: 'RGB' },
  { key: 'nir', label: 'พืชพรรณ', description: 'False color NIR' },
  { key: 'ndwi', label: 'ขอบน้ำ', description: 'NDWI' },
  { key: 'mndwi', label: 'น้ำ/ดินเลน', description: 'MNDWI' },
];

const STUDY_BOUNDS: [[number, number], [number, number]] = [
  [101.63962754434515, 12.650781002824594],
  [101.82185961897238, 12.778649590887627],
];

const IMAGE_COORDINATES: [
  [number, number],
  [number, number],
  [number, number],
  [number, number],
] = [
  [STUDY_BOUNDS[0][0], STUDY_BOUNDS[1][1]],
  [STUDY_BOUNDS[1][0], STUDY_BOUNDS[1][1]],
  [STUDY_BOUNDS[1][0], STUDY_BOUNDS[0][1]],
  [STUDY_BOUNDS[0][0], STUDY_BOUNDS[0][1]],
];

const BASE_STYLE: StyleSpecification = {
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
    {
      id: 'background',
      type: 'background',
      paint: { 'background-color': '#07110f' },
    },
    {
      id: 'osm-base',
      type: 'raster',
      source: 'osm',
      minzoom: 0,
      maxzoom: 19,
      paint: {
        'raster-opacity': 0.42,
        'raster-saturation': -0.45,
        'raster-contrast': 0.12,
      },
    },
  ],
};

function assetPath(path: string): string {
  return new URL(path, document.baseURI).toString();
}

const AOI_SOURCE = assetPath('data/rayong_coastal_analysis_aoi.geojson');
const PLOTS_SOURCE = assetPath('data/rayong_planting_plots_validated.geojson');
const BEFORE_COLOR = '#ff6b63';
const AFTER_COLOR = '#6ee7a8';

function sceneForYear(year: string): Scene {
  return SCENES.find((scene) => scene.year === year) ?? SCENES[0];
}

function rasterLayerId(year: string, layer: LayerKey): string {
  return `scene-${year}-${layer}`;
}

function shorelineLayerId(year: string): string {
  return `shoreline-${year}`;
}

function escapeHtml(value: unknown): string {
  return String(value ?? '—')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function addOperationalLayers(map: MapLibreMap, side: Side): void {
  SCENES.forEach((scene) => {
    LAYER_OPTIONS.forEach(({ key }) => {
      const sourceId = `source-${scene.year}-${key}`;
      map.addSource(sourceId, {
        type: 'image',
        url: assetPath(`data/layers/${scene.date}_${key}.png`),
        coordinates: IMAGE_COORDINATES,
      });
      map.addLayer({
        id: rasterLayerId(scene.year, key),
        type: 'raster',
        source: sourceId,
        paint: {
          'raster-opacity': 0,
          'raster-fade-duration': 0,
          'raster-resampling': 'linear',
        },
      });
    });
  });

  map.addSource('analysis-aoi', {
    type: 'geojson',
    data: AOI_SOURCE,
  });
  map.addLayer({
    id: 'analysis-aoi-line',
    type: 'line',
    source: 'analysis-aoi',
    paint: {
      'line-color': '#f6c85f',
      'line-width': 2,
      'line-dasharray': [3, 2],
      'line-opacity': 0.95,
    },
  });

  map.addSource('planting-plots', {
    type: 'geojson',
    data: PLOTS_SOURCE,
  });
  map.addLayer({
    id: 'planting-plots-fill',
    type: 'fill',
    source: 'planting-plots',
    paint: {
      'fill-color': '#20d7e8',
      'fill-opacity': 0.13,
    },
  });
  map.addLayer({
    id: 'planting-plots-line',
    type: 'line',
    source: 'planting-plots',
    paint: {
      'line-color': '#5ce6f0',
      'line-width': 2.3,
      'line-opacity': 0.95,
    },
  });

  const shorelineColor = side === 'before' ? BEFORE_COLOR : AFTER_COLOR;
  SCENES.forEach((scene) => {
    const sourceId = `shoreline-source-${scene.year}`;
    map.addSource(sourceId, {
      type: 'geojson',
      data: assetPath(`data/${scene.date}_water_edge.geojson`),
    });
    map.addLayer({
      id: shorelineLayerId(scene.year),
      type: 'line',
      source: sourceId,
      layout: { visibility: 'none' },
      paint: {
        'line-color': shorelineColor,
        'line-width': 2.5,
        'line-opacity': 0.96,
      },
    });
  });

  const showPlotPopup = (event: maplibregl.MapLayerMouseEvent) => {
    const properties = (event.features?.[0]?.properties ?? {}) as Record<
      string,
      unknown
    >;
    const plotId =
      properties.plotId ??
      properties.Plot_ID ??
      properties.plot_id ??
      properties.Name ??
      properties.name ??
      'แปลงปลูก';
    const area =
      properties.area_rai ??
      properties.Area_Rai ??
      properties.area ??
      properties.Shape_Area ??
      '—';
    const status = properties.status ?? properties.Status ?? 'Validated KMZ';

    new maplibregl.Popup({ offset: 14, maxWidth: '290px' })
      .setLngLat(event.lngLat)
      .setHTML(
        `<div class="plot-popup"><b>${escapeHtml(plotId)}</b><span>พื้นที่: ${escapeHtml(
          area,
        )} ไร่</span><span>สถานะ: ${escapeHtml(status)}</span></div>`,
      )
      .addTo(map);
  };

  map.on('mouseenter', 'planting-plots-fill', () => {
    map.getCanvas().style.cursor = 'pointer';
  });
  map.on('mouseleave', 'planting-plots-fill', () => {
    map.getCanvas().style.cursor = '';
  });
  map.on('click', 'planting-plots-fill', showPlotPopup);
}

function applyMapState(
  map: MapLibreMap,
  year: string,
  layer: LayerKey,
  showShoreline: boolean,
  showPlots: boolean,
  showAoi: boolean,
): void {
  if (!map.isStyleLoaded()) return;

  SCENES.forEach((scene) => {
    LAYER_OPTIONS.forEach(({ key }) => {
      const id = rasterLayerId(scene.year, key);
      if (map.getLayer(id)) {
        map.setPaintProperty(
          id,
          'raster-opacity',
          scene.year === year && key === layer ? 1 : 0,
        );
      }
    });

    const shorelineId = shorelineLayerId(scene.year);
    if (map.getLayer(shorelineId)) {
      map.setLayoutProperty(
        shorelineId,
        'visibility',
        showShoreline && scene.year === year ? 'visible' : 'none',
      );
    }
  });

  ['planting-plots-fill', 'planting-plots-line'].forEach((id) => {
    if (map.getLayer(id)) {
      map.setLayoutProperty(id, 'visibility', showPlots ? 'visible' : 'none');
    }
  });
  if (map.getLayer('analysis-aoi-line')) {
    map.setLayoutProperty(
      'analysis-aoi-line',
      'visibility',
      showAoi ? 'visible' : 'none',
    );
  }
}

function median(values: number[]): number | null {
  if (values.length === 0) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0
    ? (sorted[middle - 1] + sorted[middle]) / 2
    : sorted[middle];
}

function formatMeters(value: number | null): string {
  if (value === null) return '—';
  const formatted = new Intl.NumberFormat('th-TH', {
    maximumFractionDigits: 1,
  }).format(Math.abs(value));
  return `${value > 0 ? '+' : value < 0 ? '−' : ''}${formatted} m`;
}

export default function App() {
  const compareStageRef = useRef<HTMLDivElement>(null);
  const beforeContainerRef = useRef<HTMLDivElement>(null);
  const afterContainerRef = useRef<HTMLDivElement>(null);
  const beforeMapRef = useRef<MapLibreMap | null>(null);
  const afterMapRef = useRef<MapLibreMap | null>(null);

  const [beforeYear, setBeforeYear] = useState('2018');
  const [afterYear, setAfterYear] = useState('2025');
  const [selectedLayer, setSelectedLayer] = useState<LayerKey>('rgb');
  const [swipe, setSwipe] = useState(50);
  const [showShoreline, setShowShoreline] = useState(true);
  const [showPlots, setShowPlots] = useState(true);
  const [showAoi, setShowAoi] = useState(true);
  const [loaded, setLoaded] = useState({ before: false, after: false });
  const [plotCount, setPlotCount] = useState<number | null>(null);
  const [changeRecords, setChangeRecords] = useState<ChangeRecord[]>([]);

  const beforeScene = sceneForYear(beforeYear);
  const afterScene = sceneForYear(afterYear);
  const ready = loaded.before && loaded.after;

  const beforeIndex = SCENES.findIndex((scene) => scene.year === beforeYear);
  const afterIndex = SCENES.findIndex((scene) => scene.year === afterYear);

  const pairStats = useMemo(() => {
    const matching = changeRecords.filter(
      (record) =>
        record.before_date === beforeScene.date &&
        record.after_date === afterScene.date &&
        Number.isFinite(record.apparent_displacement_m),
    );
    return {
      count: matching.length,
      median: median(matching.map((record) => record.apparent_displacement_m)),
    };
  }, [afterScene.date, beforeScene.date, changeRecords]);

  const yearSpan = useMemo(() => {
    const elapsed =
      new Date(`${afterScene.date}T00:00:00Z`).getTime() -
      new Date(`${beforeScene.date}T00:00:00Z`).getTime();
    return (elapsed / (365.25 * 24 * 60 * 60 * 1000)).toFixed(1);
  }, [afterScene.date, beforeScene.date]);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      fetch(PLOTS_SOURCE).then((response) => response.json()),
      fetch(assetPath('data/apparent_change_by_transect.json')).then((response) =>
        response.json(),
      ),
    ])
      .then(([plots, records]) => {
        if (cancelled) return;
        const featureCount = Array.isArray(plots?.features)
          ? plots.features.length
          : null;
        setPlotCount(featureCount);
        setChangeRecords(Array.isArray(records) ? records : []);
      })
      .catch(() => {
        if (cancelled) return;
        setPlotCount(null);
        setChangeRecords([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!beforeContainerRef.current || !afterContainerRef.current) return;

    const beforeMap = new maplibregl.Map({
      container: beforeContainerRef.current,
      style: BASE_STYLE,
      bounds: STUDY_BOUNDS,
      fitBoundsOptions: { padding: 22, duration: 0 },
      attributionControl: false,
      dragRotate: false,
      pitchWithRotate: false,
      minZoom: 8,
      maxZoom: 18,
    });
    const afterMap = new maplibregl.Map({
      container: afterContainerRef.current,
      style: BASE_STYLE,
      bounds: STUDY_BOUNDS,
      fitBoundsOptions: { padding: 22, duration: 0 },
      attributionControl: false,
      dragRotate: false,
      pitchWithRotate: false,
      minZoom: 8,
      maxZoom: 18,
    });

    beforeMapRef.current = beforeMap;
    afterMapRef.current = afterMap;

    let synchronizing = false;
    const syncCamera = (source: MapLibreMap, target: MapLibreMap) => {
      if (synchronizing) return;
      synchronizing = true;
      const center = source.getCenter();
      target.jumpTo({
        center,
        zoom: source.getZoom(),
        bearing: source.getBearing(),
        pitch: source.getPitch(),
      });
      synchronizing = false;
    };
    const syncBeforeToAfter = () => syncCamera(beforeMap, afterMap);
    const syncAfterToBefore = () => syncCamera(afterMap, beforeMap);
    beforeMap.on('move', syncBeforeToAfter);
    afterMap.on('move', syncAfterToBefore);

    beforeMap.on('load', () => {
      addOperationalLayers(beforeMap, 'before');
      applyMapState(beforeMap, '2018', 'rgb', true, true, true);
      setLoaded((current) => ({ ...current, before: true }));
    });
    afterMap.on('load', () => {
      addOperationalLayers(afterMap, 'after');
      applyMapState(afterMap, '2025', 'rgb', true, true, true);
      setLoaded((current) => ({ ...current, after: true }));
    });

    const resizeObserver = new ResizeObserver(() => {
      beforeMap.resize();
      afterMap.resize();
    });
    if (compareStageRef.current) {
      resizeObserver.observe(compareStageRef.current);
    }

    return () => {
      resizeObserver.disconnect();
      beforeMap.off('move', syncBeforeToAfter);
      afterMap.off('move', syncAfterToBefore);
      beforeMap.remove();
      afterMap.remove();
      beforeMapRef.current = null;
      afterMapRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (loaded.before && beforeMapRef.current) {
      applyMapState(
        beforeMapRef.current,
        beforeYear,
        selectedLayer,
        showShoreline,
        showPlots,
        showAoi,
      );
    }
  }, [beforeYear, loaded.before, selectedLayer, showAoi, showPlots, showShoreline]);

  useEffect(() => {
    if (loaded.after && afterMapRef.current) {
      applyMapState(
        afterMapRef.current,
        afterYear,
        selectedLayer,
        showShoreline,
        showPlots,
        showAoi,
      );
    }
  }, [afterYear, loaded.after, selectedLayer, showAoi, showPlots, showShoreline]);

  useEffect(() => {
    window.__RAYONG_COMPARE_TEST__ = {
      ready,
      mapCount: Number(loaded.before) + Number(loaded.after),
      beforeYear,
      afterYear,
      selectedLayer,
      swipe,
      plotCount,
    };
  }, [afterYear, beforeYear, loaded.after, loaded.before, plotCount, ready, selectedLayer, swipe]);

  const updateSwipeFromClientX = (clientX: number) => {
    const rect = compareStageRef.current?.getBoundingClientRect();
    if (!rect || rect.width === 0) return;
    const percentage = ((clientX - rect.left) / rect.width) * 100;
    setSwipe(Math.round(Math.max(3, Math.min(97, percentage))));
  };

  const handleDividerPointerDown = (
    event: ReactPointerEvent<HTMLDivElement>,
  ) => {
    event.currentTarget.setPointerCapture(event.pointerId);
    updateSwipeFromClientX(event.clientX);
  };

  const handleDividerPointerMove = (
    event: ReactPointerEvent<HTMLDivElement>,
  ) => {
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      updateSwipeFromClientX(event.clientX);
    }
  };

  const handleDividerPointerUp = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  };

  const fitStudyArea = () => {
    beforeMapRef.current?.fitBounds(STUDY_BOUNDS, {
      padding: 22,
      duration: 450,
    });
  };

  const zoomBy = (delta: number) => {
    const map = beforeMapRef.current;
    if (!map) return;
    map.easeTo({ zoom: map.getZoom() + delta, duration: 250 });
  };

  const choosePair = (before: string, after: string) => {
    setBeforeYear(before);
    setAfterYear(after);
  };

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <header className="brand-block">
          <div className="brand-mark"><MapPinned size={19} /></div>
          <div>
            <p className="eyebrow">RAYONG COASTAL SCREENING</p>
            <h1>เปรียบเทียบชายฝั่ง<br />ก่อน–หลัง</h1>
          </div>
        </header>

        <div className="warning-card">
          <AlertTriangle size={19} />
          <div>
            <b>Tide-unverified screening</b>
            <span>เป็นขอบน้ำปรากฏจากภาพต่างวัน ไม่ใช่อัตรากัดเซาะทางวิศวกรรม</span>
          </div>
        </div>

        <section className="control-card">
          <div className="section-title">
            <CalendarRange size={17} />
            <div><b>ช่วงเวลาเปรียบเทียบ</b><span>สองภาพอยู่พิกัดและขอบเขตเดียวกัน</span></div>
          </div>

          <div className="year-grid">
            <label>
              <span>BEFORE</span>
              <select
                id="before-year"
                value={beforeYear}
                onChange={(event) => setBeforeYear(event.target.value)}
              >
                {SCENES.filter((_, index) => index < afterIndex).map((scene) => (
                  <option key={scene.year} value={scene.year}>
                    {scene.year} · {scene.shortDate}
                  </option>
                ))}
              </select>
            </label>
            <div className="year-arrow">→</div>
            <label>
              <span>AFTER</span>
              <select
                id="after-year"
                value={afterYear}
                onChange={(event) => setAfterYear(event.target.value)}
              >
                {SCENES.filter((_, index) => index > beforeIndex).map((scene) => (
                  <option key={scene.year} value={scene.year}>
                    {scene.year} · {scene.shortDate}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <div className="quick-pairs">
            <button type="button" data-pair="2018-2021" className={beforeYear === '2018' && afterYear === '2021' ? 'active' : ''} onClick={() => choosePair('2018', '2021')}>2018 → 2021</button>
            <button type="button" data-pair="2021-2025" className={beforeYear === '2021' && afterYear === '2025' ? 'active' : ''} onClick={() => choosePair('2021', '2025')}>2021 → 2025</button>
            <button type="button" data-pair="2018-2025" className={beforeYear === '2018' && afterYear === '2025' ? 'active' : ''} onClick={() => choosePair('2018', '2025')}>2018 → 2025</button>
          </div>

          <label className="swipe-control">
            <span><MoveHorizontal size={15} /> ตำแหน่งเส้นแบ่ง</span>
            <b>{swipe}%</b>
            <input
              data-testid="swipe-range"
              type="range"
              min="3"
              max="97"
              value={swipe}
              onChange={(event) => setSwipe(Number(event.target.value))}
            />
          </label>
        </section>

        <section className="control-card">
          <div className="section-title">
            <Layers3 size={17} />
            <div><b>ชั้นภาพดาวเทียม</b><span>ใช้ชั้นเดียวกันทั้ง BEFORE และ AFTER</span></div>
          </div>
          <div className="layer-grid">
            {LAYER_OPTIONS.map((option) => (
              <button
                type="button"
                key={option.key}
                data-layer={option.key}
                className={selectedLayer === option.key ? 'active' : ''}
                onClick={() => setSelectedLayer(option.key)}
              >
                <b>{option.label}</b>
                <span>{option.description}</span>
              </button>
            ))}
          </div>
        </section>

        <section className="control-card compact">
          <div className="section-title">
            <Eye size={17} />
            <div><b>ข้อมูลซ้อนทับ</b><span>จาก AOI และ KMZ แปลงปลูกที่ตรวจแล้ว</span></div>
          </div>
          <label className="toggle-row">
            <span><i className="line before-line" />เส้นขอบน้ำแต่ละปี</span>
            <input type="checkbox" checked={showShoreline} onChange={(event) => setShowShoreline(event.target.checked)} />
          </label>
          <label className="toggle-row">
            <span><i className="plot-box" />แปลงปลูกจาก KMZ</span>
            <input type="checkbox" checked={showPlots} onChange={(event) => setShowPlots(event.target.checked)} />
          </label>
          <label className="toggle-row">
            <span><i className="aoi-line" />ขอบเขตพื้นที่ศึกษา</span>
            <input type="checkbox" checked={showAoi} onChange={(event) => setShowAoi(event.target.checked)} />
          </label>
        </section>

        <section className="summary-grid">
          <article><Satellite size={16} /><span>ช่วงภาพ</span><b>{yearSpan} ปี</b></article>
          <article><Trees size={16} /><span>แปลง KMZ</span><b>{plotCount ?? '—'} แปลง</b></article>
          <article><MoveHorizontal size={16} /><span>Transect คู่นี้</span><b>{pairStats.count || '—'}</b></article>
          <article><CheckCircle2 size={16} /><span>มัธยฐานปรากฏ</span><b>{formatMeters(pairStats.median)}</b></article>
        </section>

        <p className="method-note">
          ค่าเคลื่อนที่เป็นผลคัดกรองจาก apparent water edge และจะแสดงเฉพาะคู่วันที่ที่มีผล transect อยู่ในชุดข้อมูล ห้ามใช้แทน shoreline ที่ปรับระดับน้ำแล้ว
        </p>
      </aside>

      <main className="workspace">
        <header className="workspace-header">
          <div>
            <p className="eyebrow">SYNCHRONIZED MAP SWIPE</p>
            <h2>{beforeYear} <span>เทียบกับ</span> {afterYear}</h2>
          </div>
          <div className={`ready-badge ${ready ? 'ready' : ''}`}>
            {ready ? <CheckCircle2 size={16} /> : <span className="spinner" />}
            {ready ? 'แผนที่ 2 ชั้นพร้อมใช้งาน' : 'กำลังโหลดภาพและ KMZ'}
          </div>
        </header>

        <section className="compare-card">
          <div className="compare-meta">
            <div><b>{beforeScene.shortDate}</b><span>BEFORE · {selectedLayer.toUpperCase()}</span></div>
            <div className="meta-center"><MoveHorizontal size={16} /><span>ลากวงกลมเพื่อเปิดภาพแต่ละปี</span></div>
            <div className="right"><b>{afterScene.shortDate}</b><span>AFTER · {selectedLayer.toUpperCase()}</span></div>
          </div>

          <div className="compare-stage" ref={compareStageRef}>
            <div id="before-map" className="map-layer" ref={beforeContainerRef} />
            <div
              id="after-pane"
              className="after-map-pane"
              style={{ clipPath: `inset(0 0 0 ${swipe}%)` }}
            >
              <div id="after-map" className="map-layer" ref={afterContainerRef} />
            </div>

            <div className="map-label before-label">
              <small>BEFORE</small><b>{beforeYear}</b><span>{beforeScene.shortDate}</span>
            </div>
            <div className="map-label after-label">
              <small>AFTER</small><b>{afterYear}</b><span>{afterScene.shortDate}</span>
            </div>

            <div
              className="compare-divider"
              style={{ left: `${swipe}%` }}
              onPointerDown={handleDividerPointerDown}
              onPointerMove={handleDividerPointerMove}
              onPointerUp={handleDividerPointerUp}
              onPointerCancel={handleDividerPointerUp}
              role="slider"
              aria-label="ตำแหน่งเส้นแบ่งภาพก่อนและหลัง"
              aria-valuemin={3}
              aria-valuemax={97}
              aria-valuenow={swipe}
              tabIndex={0}
            >
              <div className="divider-handle"><MoveHorizontal size={21} /></div>
            </div>

            <div className="map-controls" aria-label="เครื่องมือแผนที่">
              <button type="button" onClick={() => zoomBy(1)} aria-label="ซูมเข้า"><ZoomIn size={18} /></button>
              <button type="button" onClick={() => zoomBy(-1)} aria-label="ซูมออก"><ZoomOut size={18} /></button>
              <button type="button" onClick={fitStudyArea} aria-label="แสดงพื้นที่ทั้งหมด"><Maximize2 size={18} /></button>
            </div>

            <div className="map-legend">
              <span><i className="line before-line" />ขอบน้ำ {beforeYear}</span>
              <span><i className="line after-line" />ขอบน้ำ {afterYear}</span>
              <span><i className="plot-box" />แปลงปลูก KMZ</span>
              <span><i className="aoi-line" />AOI</span>
            </div>
          </div>

          <footer className="compare-footer">
            <span><b>วิธีใช้:</b> ซูมหรือเลื่อนฝั่งใดก็ได้ อีกฝั่งจะเคลื่อนพร้อมกัน</span>
            <span>Sentinel-2 · 10 m · apparent water edge · OSM context</span>
          </footer>
        </section>
      </main>
    </div>
  );
}
