// ===== MOCK DATA =====

const riskAreas = [
  // 강원도 - 동해안 산악
  { id: 1, name: "고성군 토성면 일대", region: "강원도", lat: 38.38, lng: 128.47, risk: "HIGH",
    forestArea: "2,840ha", dryDays: 28, windSpeed: "9.2m/s" },
  { id: 2, name: "속초시 설악동 일대", region: "강원도", lat: 38.21, lng: 128.59, risk: "HIGH",
    forestArea: "1,920ha", dryDays: 25, windSpeed: "8.7m/s" },
  { id: 3, name: "양양군 현북면 일대", region: "강원도", lat: 38.07, lng: 128.62, risk: "HIGH",
    forestArea: "3,110ha", dryDays: 23, windSpeed: "8.1m/s" },
  { id: 4, name: "강릉시 옥계면 일대", region: "강원도", lat: 37.75, lng: 128.88, risk: "HIGH",
    forestArea: "2,560ha", dryDays: 22, windSpeed: "7.9m/s" },
  { id: 5, name: "삼척시 도계읍 일대", region: "강원도", lat: 37.45, lng: 129.05, risk: "MEDIUM",
    forestArea: "1,740ha", dryDays: 18, windSpeed: "6.4m/s" },

  // 경상북도 - 동부 산악
  { id: 6, name: "울진군 북면 일대", region: "경상북도", lat: 36.99, lng: 129.37, risk: "HIGH",
    forestArea: "3,280ha", dryDays: 26, windSpeed: "8.5m/s" },
  { id: 7, name: "영덕군 영해면 일대", region: "경상북도", lat: 36.53, lng: 129.31, risk: "HIGH",
    forestArea: "2,050ha", dryDays: 21, windSpeed: "7.6m/s" },
  { id: 8, name: "청송군 주왕산 일대", region: "경상북도", lat: 36.44, lng: 129.03, risk: "MEDIUM",
    forestArea: "1,890ha", dryDays: 17, windSpeed: "6.1m/s" },
  { id: 9, name: "안동시 길안면 일대", region: "경상북도", lat: 36.57, lng: 128.73, risk: "MEDIUM",
    forestArea: "1,450ha", dryDays: 15, windSpeed: "5.8m/s" },

  // 경기도·충청북도
  { id: 10, name: "포천시 이동면 일대", region: "경기도", lat: 37.90, lng: 127.20, risk: "MEDIUM",
    forestArea: "1,320ha", dryDays: 16, windSpeed: "6.0m/s" },
  { id: 11, name: "가평군 북면 일대", region: "경기도", lat: 37.83, lng: 127.51, risk: "MEDIUM",
    forestArea: "1,180ha", dryDays: 14, windSpeed: "5.5m/s" },
  { id: 12, name: "제천시 수산면 일대", region: "충청북도", lat: 37.13, lng: 128.19, risk: "LOW",
    forestArea: "980ha", dryDays: 11, windSpeed: "4.9m/s" },
  { id: 13, name: "단양군 영춘면 일대", region: "충청북도", lat: 36.98, lng: 128.37, risk: "LOW",
    forestArea: "860ha", dryDays: 10, windSpeed: "4.6m/s" },

  // 경상남도·전라남도
  { id: 14, name: "밀양시 산내면 일대", region: "경상남도", lat: 35.50, lng: 128.78, risk: "MEDIUM",
    forestArea: "1,140ha", dryDays: 15, windSpeed: "5.3m/s" },
  { id: 15, name: "담양군 용면 일대", region: "전라남도", lat: 35.32, lng: 126.99, risk: "LOW",
    forestArea: "750ha", dryDays: 9, windSpeed: "4.2m/s" },
  { id: 16, name: "고흥군 도양읍 일대", region: "전라남도", lat: 34.61, lng: 127.28, risk: "LOW",
    forestArea: "620ha", dryDays: 8, windSpeed: "3.9m/s" },
];

const patrolRoutes = [
  {
    id: 1,
    name: "강원 동해안 순찰 노선",
    risk: "HIGH",
    color: "#ff3333",
    distance: "142km",
    guardCount: 4,
    checkpoints: 5,
    coordinates: [
      [38.38, 128.47],
      [38.21, 128.59],
      [38.07, 128.62],
      [37.75, 128.88],
      [37.45, 129.05],
    ],
  },
  {
    id: 2,
    name: "경북 동부 산악 순찰 노선",
    risk: "HIGH",
    color: "#ff6600",
    distance: "98km",
    guardCount: 3,
    checkpoints: 4,
    coordinates: [
      [36.99, 129.37],
      [36.53, 129.31],
      [36.44, 129.03],
      [36.57, 128.73],
    ],
  },
  {
    id: 3,
    name: "경기·충북 내륙 순찰 노선",
    risk: "MEDIUM",
    color: "#ff9900",
    distance: "115km",
    guardCount: 2,
    checkpoints: 4,
    coordinates: [
      [37.90, 127.20],
      [37.83, 127.51],
      [37.13, 128.19],
      [36.98, 128.37],
    ],
  },
  {
    id: 4,
    name: "경남·전남 남부 순찰 노선",
    risk: "LOW",
    color: "#ffc300",
    distance: "187km",
    guardCount: 2,
    checkpoints: 3,
    coordinates: [
      [35.50, 128.78],
      [35.32, 126.99],
      [34.61, 127.28],
    ],
  },
];

// ===== COLORS =====
const riskColors = { HIGH: "#ff3333", MEDIUM: "#ff8c00", LOW: "#ffc300" };
const riskLabels = { HIGH: "위험", MEDIUM: "주의", LOW: "관심" };

// ===== STATE =====
let currentFilter = "ALL";
let markerLayers = {};
let routeLayers = [];
let activeRouteId = null;

// ===== MAP INIT =====
const map = L.map("map", { zoomControl: true }).setView([36.8, 128.3], 7);

L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {
  attribution: '© OpenStreetMap contributors © CARTO',
  subdomains: "abcd",
  maxZoom: 19,
}).addTo(map);

// ===== MARKERS =====
function createMarker(area) {
  const color = riskColors[area.risk];
  const size = area.risk === "HIGH" ? 14 : area.risk === "MEDIUM" ? 11 : 9;

  const marker = L.circleMarker([area.lat, area.lng], {
    radius: size,
    fillColor: color,
    color: "#fff",
    weight: 1.5,
    opacity: 0.9,
    fillOpacity: 0.85,
  });

  const popupContent = `
    <div class="popup-title">${area.name}</div>
    <div class="popup-region">${area.region}</div>
    <span class="popup-risk ${area.risk}">${riskLabels[area.risk]}</span>
    <div class="popup-stats">
      <span>🌲 산림 면적: ${area.forestArea}</span>
      <span>☀️ 연속 건조일: ${area.dryDays}일</span>
      <span>💨 평균 풍속: ${area.windSpeed}</span>
    </div>
  `;

  marker.bindPopup(popupContent, { maxWidth: 220 });
  marker.on("mouseover", () => marker.openPopup());
  return marker;
}

function renderMarkers() {
  Object.values(markerLayers).forEach(m => map.removeLayer(m));
  markerLayers = {};

  riskAreas.forEach(area => {
    if (currentFilter === "ALL" || currentFilter === area.risk) {
      const marker = createMarker(area);
      marker.addTo(map);
      markerLayers[area.id] = marker;
    }
  });
}

// ===== ROUTES =====
function renderRoutes() {
  routeLayers.forEach(l => map.removeLayer(l));
  routeLayers = [];

  patrolRoutes.forEach(route => {
    const visible = currentFilter === "ALL" || currentFilter === route.risk;
    if (!visible) return;

    const line = L.polyline(route.coordinates, {
      color: route.color,
      weight: activeRouteId === route.id ? 4 : 2.5,
      opacity: activeRouteId === route.id ? 1 : 0.7,
      dashArray: "8, 5",
      lineJoin: "round",
    }).addTo(map);

    // Arrow-like start/end markers
    const start = route.coordinates[0];
    const end = route.coordinates[route.coordinates.length - 1];

    [start, end].forEach((point, i) => {
      const dot = L.circleMarker(point, {
        radius: 5,
        fillColor: route.color,
        color: "#fff",
        weight: 1.5,
        fillOpacity: 1,
        opacity: 1,
      }).addTo(map);
      routeLayers.push(dot);
    });

    line.bindTooltip(
      `<strong>${route.name}</strong><br>거리: ${route.distance} · 요원: ${route.guardCount}명`,
      { sticky: true, className: "route-tooltip" }
    );

    line.on("click", () => focusRoute(route.id));
    routeLayers.push(line);
  });
}

function focusRoute(routeId) {
  activeRouteId = activeRouteId === routeId ? null : routeId;
  renderRoutes();
  renderRouteList();

  const route = patrolRoutes.find(r => r.id === routeId);
  if (route && activeRouteId === routeId) {
    const bounds = L.latLngBounds(route.coordinates);
    map.fitBounds(bounds, { padding: [60, 60] });
  }
}

// ===== LEGEND =====
const legend = L.control({ position: "bottomright" });
legend.onAdd = () => {
  const div = L.DomUtil.create("div", "map-legend");
  div.innerHTML = `
    <h4>범례</h4>
    <div class="legend-item"><div class="legend-dot" style="background:#ff3333;box-shadow:0 0 5px rgba(255,51,51,.6)"></div>위험 지역</div>
    <div class="legend-item"><div class="legend-dot" style="background:#ff8c00;box-shadow:0 0 5px rgba(255,140,0,.6)"></div>주의 지역</div>
    <div class="legend-item"><div class="legend-dot" style="background:#ffc300;box-shadow:0 0 5px rgba(255,195,0,.6)"></div>관심 지역</div>
    <hr class="legend-separator">
    <div class="legend-item"><div class="legend-line" style="background:#ff3333"></div>위험 노선</div>
    <div class="legend-item"><div class="legend-line" style="background:#ff9900"></div>주의 노선</div>
    <div class="legend-item"><div class="legend-line" style="background:#ffc300"></div>관심 노선</div>
  `;
  return div;
};
legend.addTo(map);

// ===== SIDEBAR =====
function renderRiskSummary() {
  const counts = { HIGH: 0, MEDIUM: 0, LOW: 0 };
  riskAreas.forEach(a => counts[a.risk]++);
  const total = riskAreas.length;

  document.getElementById("count-high").textContent = counts.HIGH;
  document.getElementById("count-medium").textContent = counts.MEDIUM;
  document.getElementById("count-low").textContent = counts.LOW;

  document.getElementById("bar-high").style.width = (counts.HIGH / total * 100) + "%";
  document.getElementById("bar-medium").style.width = (counts.MEDIUM / total * 100) + "%";
  document.getElementById("bar-low").style.width = (counts.LOW / total * 100) + "%";
}

function renderRegionStats() {
  const regionMap = {};
  riskAreas.forEach(a => {
    if (!regionMap[a.region]) regionMap[a.region] = { HIGH: 0, MEDIUM: 0, LOW: 0 };
    regionMap[a.region][a.risk]++;
  });

  const container = document.getElementById("region-stats");
  container.innerHTML = Object.entries(regionMap).map(([region, counts]) => `
    <div class="region-row">
      <span class="region-name">${region}</span>
      <div class="region-badges">
        ${counts.HIGH > 0 ? `<span class="badge badge-high">위험 ${counts.HIGH}</span>` : ""}
        ${counts.MEDIUM > 0 ? `<span class="badge badge-medium">주의 ${counts.MEDIUM}</span>` : ""}
        ${counts.LOW > 0 ? `<span class="badge badge-low">관심 ${counts.LOW}</span>` : ""}
      </div>
    </div>
  `).join("");
}

function renderRouteList() {
  const container = document.getElementById("route-list");
  container.innerHTML = patrolRoutes.map(route => `
    <div class="route-item ${activeRouteId === route.id ? "active" : ""}" data-route-id="${route.id}">
      <div class="route-color-bar" style="background:${route.color}"></div>
      <div class="route-info">
        <div class="route-name">${route.name}</div>
        <div class="route-meta">
          <span>📏 ${route.distance}</span>
          <span>👤 ${route.guardCount}명</span>
          <span>📍 ${route.checkpoints}개소</span>
        </div>
      </div>
    </div>
  `).join("");

  container.querySelectorAll(".route-item").forEach(el => {
    el.addEventListener("click", () => focusRoute(Number(el.dataset.routeId)));
  });
}

// ===== FILTERS =====
document.querySelectorAll(".filter-btn").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".filter-btn").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    currentFilter = btn.dataset.filter;
    activeRouteId = null;
    renderMarkers();
    renderRoutes();
    renderRouteList();
  });
});

// ===== INIT =====
renderRiskSummary();
renderRegionStats();
renderRouteList();
renderMarkers();
renderRoutes();
