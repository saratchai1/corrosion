const state = {
  manifest: null,
  summary: null,
  plots: null,
  waterChange: null,
  coverage: [],
  sclAudit: null,
  consensus: null,
  map: null,
  plotLayer: null,
  gainLayer: null,
  lossLayer: null,
  plotFeatureLayers: new Map(),
  waterChart: null,
  vegetationChart: null,
};

const byId = (id) => document.getElementById(id);

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatNumber(value, digits = 0) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
  return new Intl.NumberFormat("th-TH", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(Number(value));
}

function formatArea(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "—";
  if (Math.abs(number) >= 1_000_000) return `${formatNumber(number / 1_000_000, 2)} กม²`;
  return `${formatNumber(number, 0)} ตร.ม.`;
}

function formatPercent(value, digits = 2) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "—";
  return `${formatNumber(number, digits)}%`;
}

function formatSignedArea(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "—";
  const prefix = number > 0 ? "+" : "";
  return `${prefix}${formatNumber(number, 0)} ตร.ม.`;
}

function isoToLocal(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("th-TH", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Asia/Bangkok",
  }).format(date);
}

async function fetchJson(path) {
  const response = await fetch(path, { cache: "no-store" });
  if (!response.ok) throw new Error(`โหลด ${path} ไม่สำเร็จ (${response.status})`);
  return response.json();
}

function setStatus(text, kind) {
  const pill = byId("statusPill");
  pill.textContent = text;
  pill.className = `status status-${kind}`;
}

function renderHeader() {
  const { manifest, summary } = state;
  const branch = manifest.branch || "—";
  const sha = manifest.git_sha && manifest.git_sha !== "local" ? manifest.git_sha.slice(0, 8) : "local";
  const build = `สร้าง ${isoToLocal(manifest.generated_utc)} · ${branch}@${sha}`;
  byId("buildInfo").textContent = build;
  byId("footerBuild").textContent = build;

  const waterStatus = summary.executive.water_status;
  if (waterStatus === "NO_LARGE_PERSISTENT_WATER_GAIN_SIGNAL") {
    setStatus("ไม่พบสัญญาณน้ำรุกขนาดใหญ่", "pass");
  } else {
    setStatus("มีพื้นที่ candidate ที่ต้องตรวจ", "review");
  }
}

function renderKpis() {
  const { pilot, executive, water } = state.summary;
  const consensusMeta = state.consensus;
  const retained = consensusMeta.retained_scene_count ?? pilot.scene_count;
  const excluded = consensusMeta.excluded_scene_count ?? 0;

  byId("kpiPlots").textContent = formatNumber(pilot.plot_count);
  byId("kpiScenes").textContent = formatNumber(retained);
  byId("kpiScenesNote").textContent = excluded
    ? `ตัดภาพ coverage ต่ำ ${formatNumber(excluded)} ภาพ`
    : "ไม่มีภาพ coverage ต่ำ";
  byId("kpiPeriod").textContent = `${pilot.first_observation_year}–${pilot.last_observation_year}`;
  byId("kpiGain").textContent = formatArea(water.candidate_water_gain_m2);
  byId("kpiGainPct").textContent = `${formatPercent(water.candidate_water_gain_pct_comparable)} ของพื้นที่เทียบได้`;
  byId("kpiLoss").textContent = formatArea(water.candidate_water_loss_m2);
  byId("kpiLossPct").textContent = `${formatPercent(water.candidate_water_loss_pct_comparable)} ของพื้นที่เทียบได้`;
  byId("kpiPriority").textContent = executive.recommended_field_priority.length
    ? executive.recommended_field_priority.join(", ")
    : "ไม่มี";
}

function renderExecutive() {
  const { executive, water, vegetation } = state.summary;
  byId("executiveHeadline").textContent = executive.headline_th;
  const waterTrend = water.clear_single_scene_linear_trend
    ? "scene-level series มีแนวโน้มที่ต้องตรวจเพิ่ม"
    : "scene-level series ไม่พบแนวโน้มเชิงเส้นชัดเจน";
  byId("executiveDetail").textContent =
    `พืชพรรณทั้ง ${vegetation.plots.length} แปลงไม่พบ persistent linear decline ตามเกณฑ์อนุรักษนิยม; ` +
    `${waterTrend}. พื้นที่น้ำเพิ่มแบบ consensus อยู่ที่ ${formatArea(water.candidate_water_gain_m2)} ` +
    `และยังไม่ใช้เป็นอัตราการกัดเซาะ.`;
}

function plotWaterRecord(plotCode) {
  return state.summary.water.plot_screening.find((row) => row.plot_code === plotCode);
}

function vegetationRecord(plotCode) {
  return state.summary.vegetation.plots.find((row) => row.plot_code === plotCode);
}

function vegetationEvent(plotCode) {
  return state.summary.vegetation.temporary_dip_events.find((row) => row.plot_code === plotCode);
}

function plotPopup(feature) {
  const props = feature.properties || {};
  const water = plotWaterRecord(props.plot_code) || {};
  const vegetation = vegetationRecord(props.plot_code) || {};
  return `
    <div class="map-popup">
      <strong>${escapeHtml(props.plot_code)}</strong>
      <span>${escapeHtml(props.village || "—")} · ${escapeHtml(props.subdistrict || "—")}</span>
      <span>พื้นที่ ${formatNumber(props.area_rai_geom_source, 1)} ไร่</span>
      <span>น้ำเพิ่ม ${formatArea(water.candidate_water_gain_m2)}</span>
      <span>NDVI: ${escapeHtml(vegetation.ndvi_trend || "—")}</span>
    </div>`;
}

function renderPlotDetail(feature) {
  const props = feature.properties || {};
  const water = plotWaterRecord(props.plot_code) || {};
  const vegetation = vegetationRecord(props.plot_code) || {};
  const event = vegetationEvent(props.plot_code);
  byId("featureTitle").textContent = `แปลง ${props.plot_code}`;
  byId("featureDetail").innerHTML = `
    <dl class="detail-list">
      <div><dt>พื้นที่</dt><dd>${formatNumber(props.area_rai_geom_source, 2)} ไร่</dd></div>
      <div><dt>ที่ตั้ง</dt><dd>${escapeHtml(props.village || "—")}, ${escapeHtml(props.subdistrict || "—")}, ${escapeHtml(props.district || "—")}</dd></div>
      <div><dt>พื้นที่เทียบได้</dt><dd>${formatArea(water.comparable_area_m2)}</dd></div>
      <div><dt>Candidate water gain</dt><dd>${formatArea(water.candidate_water_gain_m2)}</dd></div>
      <div><dt>Candidate water loss</dt><dd>${formatArea(water.candidate_water_loss_m2)}</dd></div>
      <div><dt>NDVI trend</dt><dd>${escapeHtml(vegetation.ndvi_trend || "—")}</dd></div>
      <div><dt>NDVI ล่าสุดที่ QA ดี</dt><dd>${formatNumber(vegetation.latest_good_ndvi, 3)} (${escapeHtml(vegetation.latest_good_month || "—")})</dd></div>
    </dl>
    <div class="detail-callout ${water.screening_flag === "NO_LARGE_WATER_GAIN_SIGNAL" ? "callout-pass" : "callout-review"}">
      ${water.screening_flag === "NO_LARGE_WATER_GAIN_SIGNAL"
        ? "ไม่พบสัญญาณน้ำรุกขนาดใหญ่ภายในขอบเขตแปลง"
        : "มีสัญญาณน้ำเพิ่มที่ควรตรวจภาคสนาม"}
    </div>
    ${event ? `<div class="detail-event"><b>Vegetation event</b><br>${escapeHtml(event.drop_month)}: NDVI ${formatNumber(event.ndvi_before, 3)} → ${formatNumber(event.ndvi_drop, 3)} และฟื้นใน ${escapeHtml(event.recovery_month)} (${escapeHtml(event.priority)})</div>` : ""}
  `;
}

function renderChangeDetail(feature) {
  const props = feature.properties || {};
  const isGain = props.change_type === "water_gain";
  byId("featureTitle").textContent = isGain ? "Candidate water gain" : "Candidate water loss";
  byId("featureDetail").innerHTML = `
    <dl class="detail-list">
      <div><dt>ประเภท</dt><dd>${escapeHtml(props.change_type)}</dd></div>
      <div><dt>พื้นที่ polygon</dt><dd>${formatArea(props.area_m2_projected)}</dd></div>
      <div><dt>Baseline</dt><dd>${escapeHtml(props.baseline || "—")}</dd></div>
      <div><dt>Latest</dt><dd>${escapeHtml(props.latest || "—")}</dd></div>
      <div><dt>สถานะ</dt><dd>${escapeHtml(props.analysis_status || "—")}</dd></div>
    </dl>
    <div class="detail-callout callout-review">
      ${isGain
        ? "อาจเกิดจากน้ำรุก น้ำท่วมชั่วคราว การกัดเซาะ หรือความต่างของระดับน้ำ/การจำแนก"
        : "อาจเกิดจากตะกอนงอก น้ำลง พื้นที่แห้ง หรือความต่างของการจำแนก"}
    </div>`;
}

function initMap() {
  state.map = L.map("map", { zoomControl: true, preferCanvas: true });
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
  }).addTo(state.map);

  state.plotLayer = L.geoJSON(state.plots, {
    style: { color: "#175b42", weight: 2.5, fillColor: "#61a685", fillOpacity: 0.20 },
    onEachFeature: (feature, layer) => {
      const code = feature.properties?.plot_code;
      if (code) state.plotFeatureLayers.set(code, layer);
      layer.bindPopup(plotPopup(feature));
      layer.on("click", () => renderPlotDetail(feature));
    },
  }).addTo(state.map);

  const gainFeatures = {
    type: "FeatureCollection",
    features: state.waterChange.features.filter((feature) => feature.properties?.change_type === "water_gain"),
  };
  const lossFeatures = {
    type: "FeatureCollection",
    features: state.waterChange.features.filter((feature) => feature.properties?.change_type === "water_loss"),
  };

  state.gainLayer = L.geoJSON(gainFeatures, {
    style: { color: "#c33d2e", weight: 1.5, fillColor: "#e05d49", fillOpacity: 0.48 },
    onEachFeature: (feature, layer) => layer.on("click", () => renderChangeDetail(feature)),
  }).addTo(state.map);
  state.lossLayer = L.geoJSON(lossFeatures, {
    style: { color: "#246fa8", weight: 1.5, fillColor: "#4e95c8", fillOpacity: 0.42 },
    onEachFeature: (feature, layer) => layer.on("click", () => renderChangeDetail(feature)),
  }).addTo(state.map);

  const bounds = state.plotLayer.getBounds();
  if (state.gainLayer.getLayers().length) bounds.extend(state.gainLayer.getBounds());
  if (state.lossLayer.getLayers().length) bounds.extend(state.lossLayer.getBounds());
  if (bounds.isValid()) state.map.fitBounds(bounds.pad(0.12));

  const toggles = [
    ["togglePlots", "plotLayer"],
    ["toggleGain", "gainLayer"],
    ["toggleLoss", "lossLayer"],
  ];
  toggles.forEach(([id, key]) => {
    byId(id).addEventListener("change", (event) => {
      const layer = state[key];
      if (event.target.checked) layer.addTo(state.map);
      else state.map.removeLayer(layer);
    });
  });
}

function waterChartData() {
  return state.summary.water.annual_consensus
    .slice()
    .sort((a, b) => a.year - b.year);
}

function renderWaterChart() {
  const rows = waterChartData();
  const context = byId("waterChart").getContext("2d");
  state.waterChart = new Chart(context, {
    type: "bar",
    data: {
      labels: rows.map((row) => String(row.year)),
      datasets: [
        {
          label: "Consensus water (ha)",
          data: rows.map((row) => Number(row.water_area_m2) / 10_000),
          backgroundColor: "rgba(34, 111, 151, 0.72)",
          borderColor: "#226f97",
          borderWidth: 1,
          borderRadius: 5,
        },
        {
          label: "Variable edge (ha)",
          data: rows.map((row) => Number(row.variable_water_area_m2) / 10_000),
          type: "line",
          borderColor: "#b1702a",
          backgroundColor: "rgba(177, 112, 42, .12)",
          pointBackgroundColor: "#b1702a",
          pointRadius: 3,
          tension: 0.25,
          yAxisID: "y1",
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { position: "bottom" },
        tooltip: {
          callbacks: {
            afterBody: (items) => {
              const row = rows[items[0].dataIndex];
              return [
                `ภาพที่ใช้: ${row.acquisition_count}`,
                `วันที่: ${row.acquisition_dates.join(", ")}`,
                `uncertainty เฉลี่ย: ${formatNumber(row.mean_uncertainty, 3)}`,
              ];
            },
          },
        },
      },
      scales: {
        y: { beginAtZero: true, title: { display: true, text: "พื้นที่น้ำ (เฮกตาร์)" } },
        y1: {
          beginAtZero: true,
          position: "right",
          grid: { drawOnChartArea: false },
          title: { display: true, text: "ขอบน้ำแปรผัน (เฮกตาร์)" },
        },
      },
    },
  });
}

const qaColors = {
  GOOD: "#2c7a52",
  PARTIAL: "#b27a22",
  LOW_QA: "#c65b31",
  NO_DATA: "#7b8580",
};

function renderVegetationChart(plotCode) {
  const rows = state.coverage
    .filter((row) => row.plot_code === plotCode)
    .sort((a, b) => String(a.month).localeCompare(String(b.month)));
  const context = byId("vegetationChart").getContext("2d");
  if (state.vegetationChart) state.vegetationChart.destroy();
  state.vegetationChart = new Chart(context, {
    type: "line",
    data: {
      labels: rows.map((row) => row.month),
      datasets: [
        {
          label: `Median NDVI · ${plotCode}`,
          data: rows.map((row) => row.median_ndvi),
          borderColor: "#275f45",
          backgroundColor: "rgba(39, 95, 69, .10)",
          pointBackgroundColor: rows.map((row) => qaColors[row.qa] || "#7b8580"),
          pointBorderColor: rows.map((row) => qaColors[row.qa] || "#7b8580"),
          pointRadius: rows.map((row) => (row.qa === "GOOD" ? 4 : 5)),
          pointHoverRadius: 7,
          tension: 0.25,
          spanGaps: false,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: "bottom" },
        tooltip: {
          callbacks: {
            afterBody: (items) => {
              const row = rows[items[0].dataIndex];
              return [`QA: ${row.qa}`, `Coverage: ${formatPercent(row.coverage_pct)}`, `Scenes: ${row.scene_count}`];
            },
          },
        },
      },
      scales: {
        y: { suggestedMin: 0.2, suggestedMax: 0.7, title: { display: true, text: "NDVI" } },
        x: { ticks: { maxRotation: 45, minRotation: 0 } },
      },
    },
  });
}

function initPlotSelect() {
  const select = byId("plotSelect");
  state.summary.pilot.plot_codes.forEach((code) => {
    const option = document.createElement("option");
    option.value = code;
    option.textContent = code;
    select.append(option);
  });
  select.addEventListener("change", () => renderVegetationChart(select.value));
  renderVegetationChart(select.value);
}

function trendLabel(value) {
  const labels = {
    NO_CLEAR_LINEAR_TREND: "ไม่พบแนวโน้มชัดเจน",
    INCREASING: "เพิ่มขึ้น",
    DECREASING: "ลดลง",
    INSUFFICIENT: "ข้อมูลไม่พอ",
  };
  return labels[value] || value || "—";
}

function renderPlotTable() {
  const body = byId("plotTableBody");
  const rows = state.summary.water.plot_screening
    .slice()
    .sort((a, b) => String(a.plot_code).localeCompare(String(b.plot_code), undefined, { numeric: true }));
  body.innerHTML = rows
    .map((water) => {
      const vegetation = vegetationRecord(water.plot_code) || {};
      const pass = water.screening_flag === "NO_LARGE_WATER_GAIN_SIGNAL";
      return `
        <tr>
          <td><button class="plot-link" data-plot="${escapeHtml(water.plot_code)}">${escapeHtml(water.plot_code)}</button></td>
          <td>${formatArea(water.comparable_area_m2)}</td>
          <td>${formatArea(water.candidate_water_gain_m2)}</td>
          <td>${formatArea(water.candidate_water_loss_m2)}</td>
          <td class="${Number(water.net_candidate_water_gain_m2) > 0 ? "text-gain" : "text-loss"}">${formatSignedArea(water.net_candidate_water_gain_m2)}</td>
          <td>${escapeHtml(trendLabel(vegetation.ndvi_trend))}</td>
          <td><span class="table-status ${pass ? "table-status-pass" : "table-status-review"}">${pass ? "ไม่พบสัญญาณใหญ่" : "ตรวจเพิ่ม"}</span></td>
        </tr>`;
    })
    .join("");

  body.querySelectorAll(".plot-link").forEach((button) => {
    button.addEventListener("click", () => {
      const code = button.dataset.plot;
      const layer = state.plotFeatureLayers.get(code);
      if (!layer) return;
      state.map.fitBounds(layer.getBounds().pad(0.7), { maxZoom: 16 });
      layer.openPopup();
      renderPlotDetail(layer.feature);
      document.querySelector(".map-panel").scrollIntoView({ behavior: "smooth", block: "start" });
    });
  });
}

function qaCard(title, value, note, kind = "neutral") {
  return `
    <article class="qa-card qa-card-${kind}">
      <span>${escapeHtml(title)}</span>
      <strong>${escapeHtml(value)}</strong>
      <p>${escapeHtml(note)}</p>
    </article>`;
}

function renderQa() {
  const qa = state.summary.qa;
  const scl = qa.scl_cross_check;
  const excluded = state.consensus.excluded_scenes || [];
  const calibrationText = qa.radiometric_calibration;
  const reviewItems = scl.review_items || [];
  const reviewDetail = reviewItems.length
    ? `ตรวจทบทวน: ${reviewItems.map((item) => item.date).join(", ")}`
    : "ไม่มีวันที่ถูก flag จากเกณฑ์ QA";

  byId("qaCards").innerHTML = [
    qaCard("Radiometric calibration", "ผ่าน", calibrationText, "pass"),
    qaCard("ภาพ coverage ต่ำ", `${excluded.length} ภาพ`, excluded.length ? excluded.map((item) => item.date).join(", ") : "ไม่พบ", excluded.length ? "review" : "pass"),
    qaCard("Median MNDWI–SCL IoU", formatNumber(scl.median_water_iou, 3), reviewDetail, "neutral"),
    qaCard("Overall agreement", formatPercent(Number(scl.median_overall_agreement) * 100, 1), `Cohen's κ = ${formatNumber(scl.median_cohen_kappa, 3)}`, "neutral"),
    qaCard("Tide control", "ยังไม่ผ่าน", "ยังไม่ได้ normalize ทุก scene เข้าระดับน้ำอ้างอิงเดียวกัน", "warning"),
    qaCard("Erosion rate", "ไม่คำนวณ", "ต้องมี tide-matched imagery และ field shoreline control ก่อน", "warning"),
  ].join("");
}

function renderActions() {
  byId("fieldActions").innerHTML = state.summary.next_field_actions
    .map((action, index) => `<li><span>${index + 1}</span><p>${escapeHtml(action)}</p></li>`)
    .join("");
}

function previewCaption(item) {
  const role = item.role === "earliest" ? "ต้นช่วง" : "ปลายช่วง";
  const kind = item.kind.toUpperCase();
  return `${role} · ${item.date} · ${kind}`;
}

function renderPreviews() {
  const previews = state.manifest.previews || [];
  const grid = byId("previewGrid");
  if (!previews.length) {
    grid.innerHTML = '<p class="empty-state">ไม่มี preview ใน artifact นี้</p>';
    return;
  }
  grid.innerHTML = previews
    .map(
      (item) => `
        <figure>
          <img loading="lazy" src="${encodeURI(item.path)}" alt="${escapeHtml(previewCaption(item))}">
          <figcaption><strong>${escapeHtml(previewCaption(item))}</strong><span>${escapeHtml(item.scene_id)}</span></figcaption>
        </figure>`,
    )
    .join("");
}

function renderDownloads() {
  const downloads = state.manifest.downloads || [];
  const grid = byId("downloadGrid");
  grid.innerHTML = downloads
    .map(
      (item) => `
        <a class="download-card" href="${encodeURI(item.path)}" download="${escapeHtml(item.filename)}">
          <span>${escapeHtml(item.label)}</span>
          <strong>${escapeHtml(item.filename)}</strong>
        </a>`,
    )
    .join("");
}

function showError(error) {
  console.error(error);
  setStatus("โหลดข้อมูลไม่สำเร็จ", "error");
  const banner = byId("errorBanner");
  banner.hidden = false;
  banner.textContent = `หน้าเว็บโหลดผลวิเคราะห์ไม่ครบ: ${error.message}`;
}

async function main() {
  try {
    state.manifest = await fetchJson("data/site_manifest.json");
    const paths = state.manifest.data;
    [state.summary, state.plots, state.waterChange, state.consensus, state.coverage, state.sclAudit] = await Promise.all([
      fetchJson(paths.pilot_summary),
      fetchJson(paths.plots),
      fetchJson(paths.water_change),
      fetchJson(paths.water_consensus),
      fetchJson(paths.coverage),
      fetchJson(paths.scl_audit),
    ]);

    renderHeader();
    renderKpis();
    renderExecutive();
    initMap();
    renderWaterChart();
    initPlotSelect();
    renderPlotTable();
    renderQa();
    renderActions();
    renderPreviews();
    renderDownloads();
  } catch (error) {
    showError(error);
  }
}

document.addEventListener("DOMContentLoaded", main);
