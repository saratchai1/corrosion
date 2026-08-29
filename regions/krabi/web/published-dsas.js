(() => {
  'use strict';

  const ASSET_ROOT = 'https://raw.githubusercontent.com/saratchai1/corrosion/main/regions/krabi/web/assets';
  const PROVINCE_ROOT = `${ASSET_ROOT}/province`;
  const PUBLISHED_ROOT = `${ASSET_ROOT}/published`;
  const DATA_VERSION = '4db6a570';
  const CLASS_ORDER = ['STRONG_RETREAT', 'RETREAT', 'RELATIVELY_STABLE', 'ACCRETION', 'STRONG_ACCRETION'];
  const COLORS = {
    STRONG_RETREAT: '#ff5c57',
    RETREAT: '#ff9e43',
    RELATIVELY_STABLE: '#d4ddd8',
    ACCRETION: '#23b888',
    STRONG_ACCRETION: '#66d69a'
  };
  const LABELS = {
    STRONG_RETREAT: 'ถอยร่นสูง',
    RETREAT: 'ถอยร่น',
    RELATIVELY_STABLE: 'ค่อนข้างคงที่',
    ACCRETION: 'งอกเพิ่ม',
    STRONG_ACCRETION: 'งอกเพิ่มสูง'
  };

  const state = {
    ready: false,
    featureCount: 0,
    drawnCount: 0,
    selectedTransectId: null,
    imageDimensions: null,
    activeClasses: new Set(CLASS_ORDER),
    opacity: 0.88,
    features: [],
    bbox: null,
    error: null
  };
  window.__KRABI_DSAS_TEST__ = state;

  const $ = (id) => document.getElementById(id);
  const canvas = $('mapCanvas');
  const stage = $('mapStage');
  const ctx = canvas.getContext('2d');
  const tooltip = $('tooltip');
  const errorBox = $('error');
  let selectedFeature = null;
  let hoveredFeature = null;
  let resizeTimer = null;

  function url(path) {
    return `${path}?v=${DATA_VERSION}`;
  }

  function fetchJson(path) {
    return fetch(url(path), {cache: 'no-store'}).then((response) => {
      if (!response.ok) throw new Error(`${response.status} ${response.statusText}: ${path}`);
      return response.json();
    });
  }

  function fail(message) {
    state.error = message;
    state.ready = false;
    errorBox.textContent = message;
    errorBox.hidden = false;
    $('loading').textContent = 'โหลดข้อมูลไม่สำเร็จ';
  }

  function format(value, digits = 2, suffix = '') {
    const number = Number(value);
    return Number.isFinite(number) ? `${number.toFixed(digits)}${suffix}` : '—';
  }

  function coordToPixel(lon, lat, bbox, width, height) {
    const [minX, minY, maxX, maxY] = bbox;
    return [
      ((lon - minX) / (maxX - minX)) * width,
      ((maxY - lat) / (maxY - minY)) * height
    ];
  }

  function ringPath(ring, bbox) {
    return ring.map(([lon, lat], index) => {
      const [x, y] = coordToPixel(lon, lat, bbox, 1900, 2350);
      return `${index === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(' ') + ' Z';
  }

  function geometryPath(geometry, bbox) {
    if (!geometry) return '';
    if (geometry.type === 'Polygon') return geometry.coordinates.map((ring) => ringPath(ring, bbox)).join(' ');
    if (geometry.type === 'MultiPolygon') return geometry.coordinates.flatMap((polygon) => polygon.map((ring) => ringPath(ring, bbox))).join(' ');
    return '';
  }

  function renderBoundary(boundary, bbox) {
    const svg = $('provinceBoundary');
    svg.innerHTML = '';
    boundary.features.forEach((feature) => {
      const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      path.setAttribute('d', geometryPath(feature.geometry, bbox));
      path.setAttribute('fill-rule', 'evenodd');
      svg.appendChild(path);
    });
  }

  function resizeCanvas() {
    const rect = stage.getBoundingClientRect();
    const dpr = Math.max(1, Math.min(window.devicePixelRatio || 1, 2));
    canvas.width = Math.round(rect.width * dpr);
    canvas.height = Math.round(rect.height * dpr);
    canvas.style.width = `${rect.width}px`;
    canvas.style.height = `${rect.height}px`;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    draw();
  }

  function pointRadius(feature) {
    const rate = Math.abs(Number(feature.properties.LRR || 0));
    if (rate >= 5) return 4.4;
    if (rate >= 2) return 3.7;
    if (rate >= 0.5) return 3.0;
    return 2.5;
  }

  function visible(feature) {
    return state.activeClasses.has(feature.properties.dashboard_rate_class);
  }

  function projectFeatures(width, height) {
    state.features.forEach((feature) => {
      const [lon, lat] = feature.geometry.coordinates;
      feature.__screen = coordToPixel(lon, lat, state.bbox, width, height);
    });
  }

  function draw() {
    if (!state.features.length || !state.bbox) return;
    const rect = stage.getBoundingClientRect();
    const width = rect.width;
    const height = rect.height;
    ctx.clearRect(0, 0, width, height);
    projectFeatures(width, height);

    let drawn = 0;
    state.features.forEach((feature) => {
      if (!visible(feature)) return;
      const [x, y] = feature.__screen;
      const cls = feature.properties.dashboard_rate_class;
      const color = COLORS[cls] || '#fff';
      const radius = pointRadius(feature);
      ctx.beginPath();
      ctx.arc(x, y, radius, 0, Math.PI * 2);
      ctx.fillStyle = color;
      ctx.globalAlpha = state.opacity;
      ctx.fill();
      ctx.globalAlpha = 1;
      ctx.lineWidth = selectedFeature === feature ? 2.4 : 0.8;
      ctx.strokeStyle = selectedFeature === feature ? '#ffffff' : 'rgba(0,0,0,.75)';
      ctx.stroke();
      drawn += 1;
    });
    state.drawnCount = drawn;
    $('visibleCount').textContent = `${drawn.toLocaleString('th-TH')} จุดแสดงอยู่`;
  }

  function nearestFeature(clientX, clientY, maxDistance = 12) {
    const rect = canvas.getBoundingClientRect();
    const x = clientX - rect.left;
    const y = clientY - rect.top;
    let nearest = null;
    let nearestDistance = maxDistance;
    for (const feature of state.features) {
      if (!visible(feature) || !feature.__screen) continue;
      const dx = feature.__screen[0] - x;
      const dy = feature.__screen[1] - y;
      const distance = Math.hypot(dx, dy);
      if (distance < nearestDistance) {
        nearest = feature;
        nearestDistance = distance;
      }
    }
    return nearest;
  }

  function showTooltip(feature, clientX, clientY) {
    if (!feature) {
      tooltip.hidden = true;
      return;
    }
    const props = feature.properties;
    tooltip.innerHTML = `<b>Transect ${props.TransectID}</b><br>${LABELS[props.dashboard_rate_class]}<br>LRR ${format(props.LRR)} m/yr · NSM ${format(props.NSM)} m`;
    const stageRect = stage.getBoundingClientRect();
    tooltip.style.left = `${clientX - stageRect.left}px`;
    tooltip.style.top = `${clientY - stageRect.top}px`;
    tooltip.hidden = false;
  }

  function selectFeature(feature) {
    selectedFeature = feature;
    if (!feature) return;
    const props = feature.properties;
    const [lon, lat] = feature.geometry.coordinates;
    state.selectedTransectId = props.TransectID;
    $('selectedTitle').textContent = `Transect ${props.TransectID}`;
    $('selectedRate').textContent = format(props.LRR);
    $('selectedEpr').textContent = `${format(props.EPR)} m/yr`;
    $('selectedNsm').textContent = `${format(props.NSM)} m`;
    $('selectedSce').textContent = `${format(props.SCE)} m`;
    $('selectedR2').textContent = format(props.LR2);
    $('selectedCi').textContent = `±${format(props.LCI90)} m/yr`;
    $('selectedCount').textContent = String(props.ShrCount ?? '—');
    $('selectedAzimuth').textContent = `${format(props.Azimuth)}°`;
    $('selectedCoords').textContent = `${lat.toFixed(4)}, ${lon.toFixed(4)}`;
    const badge = $('selectedClass');
    const cls = props.dashboard_rate_class;
    badge.textContent = LABELS[cls] || cls;
    badge.style.setProperty('--class-color', COLORS[cls] || '#ddd');
    draw();
  }

  function setMode(mode) {
    const all = $('showAll');
    const retreat = $('showRetreat');
    const accretion = $('showAccretion');
    [all, retreat, accretion].forEach((button) => button.classList.remove('active'));
    if (mode === 'retreat') {
      state.activeClasses = new Set(['STRONG_RETREAT', 'RETREAT']);
      retreat.classList.add('active');
    } else if (mode === 'accretion') {
      state.activeClasses = new Set(['ACCRETION', 'STRONG_ACCRETION']);
      accretion.classList.add('active');
    } else {
      state.activeClasses = new Set(CLASS_ORDER);
      all.classList.add('active');
    }
    document.querySelectorAll('.filter').forEach((button) => {
      button.classList.toggle('off', !state.activeClasses.has(button.dataset.class));
    });
    if (selectedFeature && !visible(selectedFeature)) selectedFeature = null;
    draw();
  }

  function bindControls() {
    $('showAll').addEventListener('click', () => setMode('all'));
    $('showRetreat').addEventListener('click', () => setMode('retreat'));
    $('showAccretion').addEventListener('click', () => setMode('accretion'));
    document.querySelectorAll('.filter').forEach((button) => {
      button.addEventListener('click', () => {
        const cls = button.dataset.class;
        if (state.activeClasses.has(cls)) state.activeClasses.delete(cls);
        else state.activeClasses.add(cls);
        button.classList.toggle('off', !state.activeClasses.has(cls));
        [$('showAll'), $('showRetreat'), $('showAccretion')].forEach((item) => item.classList.remove('active'));
        draw();
      });
    });
    $('pointOpacity').addEventListener('input', (event) => {
      state.opacity = Number(event.target.value) / 100;
      $('opacityValue').textContent = `${event.target.value}%`;
      draw();
    });
    canvas.addEventListener('pointermove', (event) => {
      hoveredFeature = nearestFeature(event.clientX, event.clientY);
      canvas.style.cursor = hoveredFeature ? 'pointer' : 'crosshair';
      showTooltip(hoveredFeature, event.clientX, event.clientY);
    });
    canvas.addEventListener('pointerleave', () => {
      hoveredFeature = null;
      tooltip.hidden = true;
    });
    canvas.addEventListener('click', (event) => {
      const feature = nearestFeature(event.clientX, event.clientY, 16);
      if (feature) selectFeature(feature);
    });
    window.addEventListener('resize', () => {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(resizeCanvas, 100);
    });
  }

  function renderDistribution(summary) {
    const counts = summary.dashboard_rate_class_counts;
    const total = summary.feature_count;
    $('distribution').innerHTML = CLASS_ORDER.map((key) => {
      const count = counts[key] || 0;
      const percent = total ? count / total * 100 : 0;
      return `<div class="dist-row"><span>${LABELS[key]}</span><div class="track"><div class="fill" style="--c:${COLORS[key]};width:${percent.toFixed(2)}%"></div></div><b>${count}</b></div>`;
    }).join('');
  }

  function hotspotButton(feature) {
    const props = feature.properties;
    const [lon, lat] = feature.geometry.coordinates;
    const cls = props.dashboard_rate_class;
    return `<button class="hotspot" type="button" data-id="${props.TransectID}" style="--c:${COLORS[cls]}"><i></i><span><b>Transect ${props.TransectID}</b>${lat.toFixed(4)}, ${lon.toFixed(4)} · ${LABELS[cls]}</span><strong>${format(props.LRR)}</strong></button>`;
  }

  function renderHotspots(features) {
    const retreat = [...features].sort((a, b) => Number(a.properties.LRR) - Number(b.properties.LRR)).slice(0, 10);
    const accretion = [...features].sort((a, b) => Number(b.properties.LRR) - Number(a.properties.LRR)).slice(0, 10);
    $('retreatHotspots').innerHTML = retreat.map(hotspotButton).join('');
    $('accretionHotspots').innerHTML = accretion.map(hotspotButton).join('');
    document.querySelectorAll('.hotspot').forEach((button) => {
      button.addEventListener('click', () => {
        const feature = state.features.find((item) => String(item.properties.TransectID) === button.dataset.id);
        if (!feature) return;
        state.activeClasses.add(feature.properties.dashboard_rate_class);
        document.querySelector(`.filter[data-class="${feature.properties.dashboard_rate_class}"]`)?.classList.remove('off');
        selectFeature(feature);
        stage.scrollIntoView({behavior: 'smooth', block: 'center'});
      });
    });
  }

  function preloadImage(path) {
    return new Promise((resolve, reject) => {
      const image = $('provinceImage');
      image.onload = () => {
        if (image.naturalWidth !== 1900 || image.naturalHeight !== 2350) {
          reject(new Error(`ภาพพื้นหลังมีขนาด ${image.naturalWidth}×${image.naturalHeight}`));
          return;
        }
        state.imageDimensions = [image.naturalWidth, image.naturalHeight];
        resolve();
      };
      image.onerror = () => reject(new Error('เปิดภาพจังหวัดไม่ได้'));
      image.src = url(path);
    });
  }

  async function init() {
    bindControls();
    try {
      const [manifest, boundary, summary, geojson] = await Promise.all([
        fetchJson(`${PROVINCE_ROOT}/province_imagery_manifest.json`),
        fetchJson(`${PROVINCE_ROOT}/krabi_province_boundary.geojson`),
        fetchJson(`${PUBLISHED_ROOT}/krabi_published_dsas_summary.json`),
        fetchJson(`${PUBLISHED_ROOT}/krabi_published_dsas_points.geojson`),
        preloadImage(`${PROVINCE_ROOT}/krabi_province_s2cloudless_2024.jpg`)
      ]);
      if (summary.feature_count !== 666 || geojson.features.length !== 666) {
        throw new Error(`จำนวนจุดไม่ผ่าน: summary=${summary.feature_count}, geojson=${geojson.features.length}`);
      }
      if (summary.invalid_geometry_count !== 0) throw new Error('มี geometry ไม่ถูกต้องใน summary');
      if (manifest.asset_status !== 'VALIDATED_STATIC_PROVINCE_IMAGERY') throw new Error('ภาพจังหวัดยังไม่ validated');

      state.features = geojson.features;
      state.featureCount = geojson.features.length;
      state.bbox = manifest.display_bbox_wgs84;
      renderBoundary(boundary, state.bbox);
      $('metricCount').textContent = summary.feature_count.toLocaleString('th-TH');
      $('metricMin').textContent = summary.rate_minimum.toFixed(2);
      $('metricMax').textContent = `+${summary.rate_maximum.toFixed(2)}`;
      $('metricMedian').textContent = summary.rate_median.toFixed(2);
      renderDistribution(summary);
      renderHotspots(state.features);
      resizeCanvas();
      const strongestRetreat = [...state.features].sort((a, b) => Number(a.properties.LRR) - Number(b.properties.LRR))[0];
      selectFeature(strongestRetreat);
      $('loading').hidden = true;
      state.ready = true;
    } catch (error) {
      fail(`เริ่มแผนที่ DSAS ไม่สำเร็จ: ${error.message}`);
    }
  }

  init();
})();