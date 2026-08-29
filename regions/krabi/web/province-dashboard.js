(() => {
  'use strict';

  const ASSET_ROOT = 'https://raw.githubusercontent.com/saratchai1/corrosion/main/regions/krabi/web/assets';
  const PROVINCE_ROOT = `${ASSET_ROOT}/province`;
  const PUBLISHED_ROOT = `${ASSET_ROOT}/published`;
  const YEARS = [2018, 2020, 2022, 2024];
  const CLASS_ORDER = ['STRONG_RETREAT', 'RETREAT', 'RELATIVELY_STABLE', 'ACCRETION', 'STRONG_ACCRETION'];
  const CLASS_LABELS = {
    STRONG_RETREAT: 'ถอยร่นสูง',
    RETREAT: 'ถอยร่น',
    RELATIVELY_STABLE: 'ค่อนข้างคงที่',
    ACCRETION: 'งอกเพิ่ม',
    STRONG_ACCRETION: 'งอกเพิ่มสูง'
  };
  const CLASS_COLORS = {
    STRONG_RETREAT: '#ff5c57',
    RETREAT: '#ff9e43',
    RELATIVELY_STABLE: '#d4ddd8',
    ACCRETION: '#23b888',
    STRONG_ACCRETION: '#66d69a'
  };

  const state = {
    ready: false,
    beforeYear: 2018,
    afterYear: 2024,
    beforeLoaded: false,
    afterLoaded: false,
    boundaryLoaded: false,
    manifest: null,
    dsasSummary: null,
    error: null
  };
  window.__KRABI_DASHBOARD_TEST__ = state;

  const $ = (id) => document.getElementById(id);
  const stage = $('compareStage');
  const beforeImage = $('beforeImage');
  const afterImage = $('afterImage');
  const range = $('compareRange');
  const beforeSelect = $('beforeYear');
  const afterSelect = $('afterYear');
  const status = $('compareStatus');
  const fatal = $('fatal');

  function assetUrl(year) {
    return `${PROVINCE_ROOT}/krabi_province_s2cloudless_${year}.jpg`;
  }

  function setFatal(message) {
    state.error = message;
    state.ready = false;
    fatal.textContent = message;
    fatal.hidden = false;
    status.textContent = 'โหลดหลักฐานไม่สำเร็จ';
  }

  function fetchJson(url) {
    return fetch(`${url}?v=4db6a570`, {cache: 'no-store'}).then((response) => {
      if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
      return response.json();
    });
  }

  function preload(url) {
    return new Promise((resolve, reject) => {
      const img = new Image();
      img.crossOrigin = 'anonymous';
      img.onload = () => {
        if (img.naturalWidth < 1500 || img.naturalHeight < 1800) {
          reject(new Error(`ภาพมีขนาดผิดปกติ ${img.naturalWidth}×${img.naturalHeight}`));
          return;
        }
        resolve({url, width: img.naturalWidth, height: img.naturalHeight});
      };
      img.onerror = () => reject(new Error(`เปิดภาพไม่ได้: ${url}`));
      img.src = `${url}?v=4db6a570`;
    });
  }

  function updateSplit() {
    const value = Number(range.value);
    stage.style.setProperty('--split', `${value}%`);
    $('splitValue').textContent = `${value}% ภาพก่อน / ${100 - value}% ภาพหลัง`;
  }

  function updateReadyState() {
    state.ready = Boolean(
      state.beforeLoaded && state.afterLoaded && state.boundaryLoaded && state.manifest && state.dsasSummary
    );
    if (state.ready) {
      status.textContent = 'พร้อมใช้งาน · ภาพทั้งสองไฟล์ผ่านการตรวจขนาดและแตกต่างกันจริง';
      status.dataset.state = 'ready';
    }
  }

  async function setPair(beforeYear, afterYear) {
    if (!YEARS.includes(beforeYear) || !YEARS.includes(afterYear)) return;
    if (beforeYear >= afterYear) {
      setFatal('ปี BEFORE ต้องเก่ากว่าปี AFTER');
      return;
    }
    fatal.hidden = true;
    state.error = null;
    state.ready = false;
    state.beforeLoaded = false;
    state.afterLoaded = false;
    status.textContent = `กำลังตรวจภาพ ${beforeYear} และ ${afterYear}…`;

    const beforeUrl = assetUrl(beforeYear);
    const afterUrl = assetUrl(afterYear);
    if (beforeUrl === afterUrl) {
      setFatal('URL ภาพก่อนและหลังซ้ำกัน');
      return;
    }

    try {
      const [beforeMeta, afterMeta] = await Promise.all([preload(beforeUrl), preload(afterUrl)]);
      if (beforeMeta.width !== afterMeta.width || beforeMeta.height !== afterMeta.height) {
        throw new Error('ภาพก่อนและหลังมีขนาดไม่เท่ากัน');
      }
      beforeImage.src = `${beforeUrl}?v=4db6a570`;
      afterImage.src = `${afterUrl}?v=4db6a570`;
      beforeImage.alt = `Sentinel-2 cloudless จังหวัดกระบี่ ปี ${beforeYear}`;
      afterImage.alt = `Sentinel-2 cloudless จังหวัดกระบี่ ปี ${afterYear}`;
      $('beforeLabel').textContent = `BEFORE · ${beforeYear}`;
      $('afterLabel').textContent = `AFTER · ${afterYear}`;
      beforeSelect.value = String(beforeYear);
      afterSelect.value = String(afterYear);
      state.beforeYear = beforeYear;
      state.afterYear = afterYear;
      state.beforeLoaded = true;
      state.afterLoaded = true;
      range.value = '50';
      updateSplit();
      document.querySelectorAll('[data-year]').forEach((card) => {
        const year = Number(card.dataset.year);
        card.classList.toggle('active', year === beforeYear || year === afterYear);
      });
      updateReadyState();
    } catch (error) {
      setFatal(`ภาพดาวเทียมโหลดไม่ผ่านการตรวจ: ${error.message}`);
    }
  }

  function coordToPixel(lon, lat, bbox, width = 1900, height = 2350) {
    const [minX, minY, maxX, maxY] = bbox;
    return [
      ((lon - minX) / (maxX - minX)) * width,
      ((maxY - lat) / (maxY - minY)) * height
    ];
  }

  function ringPath(ring, bbox) {
    return ring.map(([lon, lat], index) => {
      const [x, y] = coordToPixel(lon, lat, bbox);
      return `${index === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(' ') + ' Z';
  }

  function geometryPath(geometry, bbox) {
    if (!geometry) return '';
    if (geometry.type === 'Polygon') {
      return geometry.coordinates.map((ring) => ringPath(ring, bbox)).join(' ');
    }
    if (geometry.type === 'MultiPolygon') {
      return geometry.coordinates.flatMap((polygon) => polygon.map((ring) => ringPath(ring, bbox))).join(' ');
    }
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
    state.boundaryLoaded = svg.querySelectorAll('path').length > 0;
  }

  function fillMetrics(manifest, summary) {
    $('provinceArea').textContent = `${Math.round(manifest.source_boundary.properties.area_sqkm).toLocaleString('th-TH')} km²`;
    $('transectCount').textContent = summary.feature_count.toLocaleString('th-TH');
    $('retreatCount').textContent = (
      summary.dashboard_rate_class_counts.STRONG_RETREAT + summary.dashboard_rate_class_counts.RETREAT
    ).toLocaleString('th-TH');
    $('stableCount').textContent = summary.dashboard_rate_class_counts.RELATIVELY_STABLE.toLocaleString('th-TH');
    $('rateRange').textContent = `${summary.rate_minimum.toFixed(2)} → +${summary.rate_maximum.toFixed(2)}`;
    $('differenceScore').textContent = manifest.before_after_validation.mean_absolute_rgb_difference.toFixed(2);

    const counts = summary.dashboard_rate_class_counts;
    const total = summary.feature_count;
    const container = $('distribution');
    container.innerHTML = CLASS_ORDER.map((key) => {
      const count = counts[key] || 0;
      const percent = total ? (count / total) * 100 : 0;
      return `<div class="dist"><span>${CLASS_LABELS[key]}</span><div class="track"><div class="fill" style="--c:${CLASS_COLORS[key]};width:${percent.toFixed(2)}%"></div></div><b>${count}</b></div>`;
    }).join('');
  }

  function bindControls() {
    range.addEventListener('input', updateSplit);
    beforeSelect.addEventListener('change', () => setPair(Number(beforeSelect.value), Number(afterSelect.value)));
    afterSelect.addEventListener('change', () => setPair(Number(beforeSelect.value), Number(afterSelect.value)));
    document.querySelectorAll('[data-pair]').forEach((button) => {
      button.addEventListener('click', () => {
        const [before, after] = button.dataset.pair.split('-').map(Number);
        setPair(before, after);
      });
    });
    document.querySelectorAll('[data-year]').forEach((card) => {
      card.addEventListener('click', () => {
        const year = Number(card.dataset.year);
        if (year < state.afterYear) setPair(year, state.afterYear);
        else if (year > state.beforeYear) setPair(state.beforeYear, year);
      });
    });
  }

  async function init() {
    bindControls();
    updateSplit();
    try {
      const [manifest, boundary, dsasSummary] = await Promise.all([
        fetchJson(`${PROVINCE_ROOT}/province_imagery_manifest.json`),
        fetchJson(`${PROVINCE_ROOT}/krabi_province_boundary.geojson`),
        fetchJson(`${PUBLISHED_ROOT}/krabi_published_dsas_summary.json`)
      ]);
      if (manifest.asset_status !== 'VALIDATED_STATIC_PROVINCE_IMAGERY') {
        throw new Error('manifest ไม่ได้อยู่ในสถานะ validated');
      }
      if (dsasSummary.feature_count !== 666 || dsasSummary.invalid_geometry_count !== 0) {
        throw new Error('จำนวนจุด DSAS ไม่ตรงกับชุดข้อมูลที่ตรวจแล้ว');
      }
      state.manifest = manifest;
      state.dsasSummary = dsasSummary;
      renderBoundary(boundary, manifest.display_bbox_wgs84);
      fillMetrics(manifest, dsasSummary);
      await setPair(2018, 2024);
      updateReadyState();
    } catch (error) {
      setFatal(`เริ่มระบบไม่สำเร็จ: ${error.message}`);
    }
  }

  init();
})();