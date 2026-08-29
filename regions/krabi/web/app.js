const PATHS = {
  geojson: "../data/aoi/krabi_pdd_plots.geojson",
  coverage: "../data/reuse/pdd22_krabi_coverage.csv",
  trends: "../analysis/vegetation_trends.csv",
  events: "../analysis/events.csv",
};

const SOURCE_BASE = "https://raw.githubusercontent.com/saratchai1/prasae/pdd22-satellite-refetch/data/pdd22_satellite/plots";
const SOURCE_TREE = "https://github.com/saratchai1/prasae/tree/pdd22-satellite-refetch/data/pdd22_satellite/plots";
const QA_COLORS = { GOOD: "#2d7b54", PARTIAL: "#b68b28", LOW_QA: "#c76631", NO_DATA: "#7d8580" };

let map;
let geoLayer;
let chart;
let geojson;
let coverage = [];
let trends = [];
let events = [];
let selectedPlot = "97-VSD";
let selectedPeriod = "2026-08";

function parseCsv(text) {
  const rows = [];
  let row = [], field = "", quoted = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i], n = text[i + 1];
    if (quoted) {
      if (c === '"' && n === '"') { field += '"'; i++; }
      else if (c === '"') quoted = false;
      else field += c;
    } else if (c === '"') quoted = true;
    else if (c === ',') { row.push(field); field = ""; }
    else if (c === '\n') { row.push(field.replace(/\r$/, "")); rows.push(row); row = []; field = ""; }
    else field += c;
  }
  if (field.length || row.length) { row.push(field); rows.push(row); }
  const headers = rows.shift();
  return rows.filter(r => r.some(v => v !== "")).map(r => Object.fromEntries(headers.map((h, i) => [h, r[i] ?? ""])));
}

function num(v) { const n = Number(v); return Number.isFinite(n) ? n : null; }
function qaPill(qa) { return `<span class="qa-pill qa-${qa}">${qa}</span>`; }

function rowsForPlot(plot) {
  return coverage.filter(r => r.plot_code === plot).sort((a, b) => a.month.localeCompare(b.month));
}

function latestRow(plot) {
  const rows = rowsForPlot(plot);
  return rows[rows.length - 1];
}

function initMap() {
  map = L.map("map", { zoomControl: true }).setView([7.945, 99.105], 12);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "&copy; OpenStreetMap contributors",
  }).addTo(map);

  geoLayer = L.geoJSON(geojson, {
    style: feature => {
      const qa = latestRow(feature.properties.plot_code)?.qa || "NO_DATA";
      return { color: QA_COLORS[qa], weight: 3, fillColor: QA_COLORS[qa], fillOpacity: 0.20 };
    },
    onEachFeature: (feature, layer) => {
      const p = feature.properties;
      layer.bindTooltip(p.plot_code, { sticky: true });
      layer.on("click", () => {
        selectedPlot = p.plot_code;
        document.querySelector("#plotSelect").value = selectedPlot;
        syncPeriods();
        renderAll();
      });
    },
  }).addTo(map);
  map.fitBounds(geoLayer.getBounds(), { padding: [20, 20] });
  document.querySelector("#fitAll").addEventListener("click", () => map.fitBounds(geoLayer.getBounds(), { padding: [20, 20] }));
}

function populatePlots() {
  const select = document.querySelector("#plotSelect");
  const codes = geojson.features.map(f => f.properties.plot_code).sort();
  select.innerHTML = codes.map(code => `<option value="${code}">${code}</option>`).join("");
  select.value = selectedPlot;
  select.addEventListener("change", e => {
    selectedPlot = e.target.value;
    syncPeriods();
    zoomSelected();
    renderAll();
  });
}

function syncPeriods() {
  const select = document.querySelector("#periodSelect");
  const rows = rowsForPlot(selectedPlot);
  const months = rows.map(r => r.month);
  if (!months.includes(selectedPeriod)) selectedPeriod = months[months.length - 1];
  select.innerHTML = months.map(month => `<option value="${month}">${month}</option>`).join("");
  select.value = selectedPeriod;
  select.onchange = e => { selectedPeriod = e.target.value; renderAll(); };
}

function zoomSelected() {
  let target;
  geoLayer.eachLayer(layer => {
    if (layer.feature?.properties?.plot_code === selectedPlot) target = layer;
  });
  if (target) map.fitBounds(target.getBounds(), { padding: [50, 50], maxZoom: 15 });
}

function renderMeta() {
  const feature = geojson.features.find(f => f.properties.plot_code === selectedPlot);
  const row = rowsForPlot(selectedPlot).find(r => r.month === selectedPeriod);
  const p = feature.properties;
  document.querySelector("#plotMeta").innerHTML = `
    <strong>${selectedPlot}</strong><br>
    อ.${p.district} / ต.${p.subdistrict}<br>
    KML area: ${Number(p.area_rai_attr).toFixed(2)} ไร่<br>
    PDD22 area: ${Number(row.pdd_area_rai).toFixed(2)} ไร่<br><br>
    ${selectedPeriod} ${qaPill(row.qa)}<br>
    Coverage: <b>${Number(row.coverage_pct).toFixed(2)}%</b><br>
    Median NDVI: <b>${Number(row.median_ndvi).toFixed(4)}</b><br>
    Median NDRE: <b>${Number(row.median_ndre).toFixed(4)}</b><br>
    Median MNDWI: <b>${Number(row.median_mndwi).toFixed(4)}</b>`;
}

function renderChart() {
  const rows = rowsForPlot(selectedPlot);
  const labels = rows.map(r => r.month);
  const ndvi = rows.map(r => num(r.median_ndvi));
  const ndre = rows.map(r => num(r.median_ndre));
  const coverageData = rows.map(r => num(r.coverage_pct));
  if (chart) chart.destroy();
  chart = new Chart(document.querySelector("#spectralChart"), {
    type: "line",
    data: {
      labels,
      datasets: [
        { label: "Median NDVI", data: ndvi, yAxisID: "spectral", tension: .25, pointRadius: 4 },
        { label: "Median NDRE", data: ndre, yAxisID: "spectral", tension: .25, pointRadius: 3 },
        { label: "Coverage %", data: coverageData, yAxisID: "coverage", borderDash: [5, 4], pointRadius: 2, tension: .15 },
      ],
    },
    options: {
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      scales: {
        spectral: { position: "left", suggestedMin: 0, suggestedMax: .7, title: { display: true, text: "Spectral index" } },
        coverage: { position: "right", min: 0, max: 100, grid: { drawOnChartArea: false }, title: { display: true, text: "Coverage %" } },
      },
      plugins: { legend: { position: "bottom" } },
    },
  });
}

function renderFinding() {
  const trend = trends.find(r => r.plot_code === selectedPlot);
  const event = events.find(r => r.plot_code === selectedPlot);
  const latest = latestRow(selectedPlot);
  const trendText = trend.median_ndvi_trend === "NO_CLEAR_LINEAR_TREND"
    ? "ยังไม่พบ linear decline/increase ที่ชัดเจนจากชุดเวลานี้"
    : `NDVI trend: ${trend.median_ndvi_trend}`;
  const eventHtml = event ? `
    <div class="finding-card"><b>Temporary dip flag</b><p>${event.drop_month}: NDVI ${event.ndvi_drop} (${event.drop_qa}) → ฟื้นเป็น ${event.ndvi_recovery} ใน ${event.recovery_month} (${event.recovery_qa})</p></div>` :
    `<div class="finding-card"><b>Dip screening</b><p>ไม่พบ drop ≥ 0.10 ที่ตามด้วย recovery ≥ 0.10 ตาม rule ปัจจุบัน</p></div>`;
  document.querySelector("#finding").innerHTML = `
    <div class="finding-card"><b>Trend</b><p>${trendText} (slope ${Number(trend.median_ndvi_slope_per_year).toFixed(4)}/yr, R² ${Number(trend.median_ndvi_r2).toFixed(3)})</p></div>
    ${eventHtml}
    <div class="finding-card"><b>Latest observation</b><p>${latest.month}: ${qaPill(latest.qa)} coverage ${Number(latest.coverage_pct).toFixed(1)}%, NDVI ${Number(latest.median_ndvi).toFixed(4)}</p></div>
    <div class="finding-card"><b>Interpretation</b><p>ใช้เป็น screening เพื่อเลือกช่วงเวลา/แปลงไปตรวจต่อ ไม่ใช้ NDVI เพียงตัวเดียวสรุปการกัดเซาะหรือการตายของป่า</p></div>`;
}

function renderImages() {
  const row = rowsForPlot(selectedPlot).find(r => r.month === selectedPeriod);
  const base = `${SOURCE_BASE}/${selectedPlot}/${selectedPeriod}`;
  const source = `${SOURCE_TREE}/${selectedPlot}/${selectedPeriod}`;
  document.querySelector("#rgbImage").src = `${base}/rgb.png`;
  document.querySelector("#ndviImage").src = `${base}/ndvi.png`;
  document.querySelector("#sourceLink").href = source;
  document.querySelector("#imageNote").innerHTML = `${selectedPlot} / ${selectedPeriod} — ${qaPill(row.qa)} coverage ${Number(row.coverage_pct).toFixed(2)}%. ภาพเป็น visualization ที่ประมวลผลไว้แล้ว; ไม่ใช่ georeferenced raster สำหรับวัดระยะ shoreline.`;
}

function renderAll() {
  renderMeta();
  renderChart();
  renderFinding();
  renderImages();
}

async function main() {
  try {
    const [geoRes, covRes, trendRes, eventRes] = await Promise.all([
      fetch(PATHS.geojson), fetch(PATHS.coverage), fetch(PATHS.trends), fetch(PATHS.events),
    ]);
    if (![geoRes, covRes, trendRes, eventRes].every(r => r.ok)) throw new Error("One or more data files could not be loaded");
    geojson = await geoRes.json();
    coverage = parseCsv(await covRes.text());
    trends = parseCsv(await trendRes.text());
    events = parseCsv(await eventRes.text());
    populatePlots();
    syncPeriods();
    initMap();
    renderAll();
  } catch (error) {
    console.error(error);
    document.querySelector("main").insertAdjacentHTML("afterbegin", `<div class="panel" style="padding:18px;margin-bottom:14px">โหลดข้อมูลไม่สำเร็จ: ${error.message}. เปิดผ่าน HTTP server/GitHub Pages ไม่ใช่ file://</div>`);
  }
}

main();
