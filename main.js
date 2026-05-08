// ===== CONFIG =====
const API_KEY = '48d1abd5e81dda4c332b926e56353f67';
const API_URL = `https://firms.modaps.eosdis.nasa.gov/api/area/csv/${API_KEY}/VIIRS_SNPP_NRT/124.6,33.1,131.9,38.6/1`;

// ===== STATIC: PATROL ROUTES (취약지역 기반 고정 노선) =====
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
      [38.38, 128.47], [38.21, 128.59], [38.07, 128.62],
      [37.75, 128.88], [37.45, 129.05],
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
      [36.99, 129.37], [36.53, 129.31],
      [36.44, 129.03], [36.57, 128.73],
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
      [37.90, 127.20], [37.83, 127.51],
      [37.13, 128.19], [36.98, 128.37],
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
      [35.50, 128.78], [35.32, 126.99], [34.61, 127.28],
    ],
  },
];

// ===== CONSTANTS =====
const confidenceMap = { h: 'HIGH', n: 'MEDIUM', l: 'LOW' };
const riskColors = { HIGH: '#ff3333', MEDIUM: '#ff8c00', LOW: '#ffc300' };
const riskLabels = { HIGH: '위험', MEDIUM: '주의', LOW: '관심' };

// ===== STATE =====
let liveFireData = [];
let currentFilter = 'ALL';
let markerLayers = {};
let routeLayers = [];
let activeRouteId = null;

// ===== MAP INIT =====
const map = L.map('map', { zoomControl: true }).setView([36.8, 128.3], 7);

L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
  attribution: '© OpenStreetMap contributors © CARTO',
  subdomains: 'abcd',
  maxZoom: 19,
}).addTo(map);

// ===== UTILS =====
function parseCSV(text) {
  const lines = text.trim().split('\n');
  if (lines.length < 2) return [];
  const headers = lines[0].split(',').map(h => h.trim());
  return lines.slice(1).map(line => {
    const values = line.split(',');
    const obj = {};
    headers.forEach((h, i) => { obj[h] = (values[i] || '').trim(); });
    return obj;
  }).filter(row => row.latitude && row.longitude);
}

function classifyRegion(lat, lng) {
  if (lat >= 37.3 && lng >= 127.5 && lng <= 129.5) return '강원도';
  if (lat >= 37.2 && lat < 37.3 && lng >= 127.5) return '강원도';
  if (lat >= 37.2 && lng < 127.5) return '경기도';
  if (lat >= 36.0 && lat < 37.2 && lng >= 128.5) return '경상북도';
  if (lat >= 36.0 && lat < 37.2 && lng >= 127.3 && lng < 128.5) return '충청북도';
  if (lat >= 35.0 && lat < 36.0 && lng >= 128.0) return '경상남도';
  if (lat >= 35.0 && lat < 36.5 && lng >= 126.5 && lng < 128.0) return '전라북도';
  if (lat < 35.0 && lng >= 127.3) return '경상남도';
  if (lat < 35.5 && lng < 127.3) return '전라남도';
  return '기타';
}

function formatTime(acqDate, acqTime) {
  const t = (acqTime || '').padStart(4, '0');
  return `${acqDate} ${t.slice(0, 2)}:${t.slice(2)} UTC`;
}

// ===== API FETCH =====
async function fetchFireData() {
  setStatus('loading', '데이터 로딩 중...');
  try {
    const res = await fetch(API_URL);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const text = await res.text();
    const rows = parseCSV(text);

    liveFireData = rows.map((row, i) => ({
      id: i,
      lat: parseFloat(row.latitude),
      lng: parseFloat(row.longitude),
      risk: confidenceMap[row.confidence] || 'LOW',
      frp: parseFloat(row.frp) || 0,
      brightness: parseFloat(row.bright_ti4) || 0,
      acqDate: row.acq_date,
      acqTime: row.acq_time,
      satellite: row.satellite,
      daynight: row.daynight,
      region: classifyRegion(parseFloat(row.latitude), parseFloat(row.longitude)),
    }));

    const now = new Date().toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' });
    if (liveFireData.length === 0) {
      setStatus('empty', `현재 탐지된 산불 없음\n마지막 확인: ${now}`);
    } else {
      setStatus('success', `${liveFireData.length}건 탐지 · 업데이트: ${now}`);
    }
  } catch (err) {
    console.error('FIRMS API 오류:', err);
    setStatus('error', `데이터 로드 실패\n(${err.message})`);
    liveFireData = [];
  }

  renderMarkers();
  renderRiskSummary();
  renderRegionStats();
}

function setStatus(type, msg) {
  const el = document.getElementById('data-status');
  el.className = `data-status ${type}`;
  el.style.whiteSpace = 'pre-line';
  el.textContent = msg;
}

// ===== MARKERS =====
function createFireMarker(fire) {
  const color = riskColors[fire.risk];
  const size = fire.frp > 50 ? 14 : fire.frp > 10 ? 11 : 9;

  const marker = L.circleMarker([fire.lat, fire.lng], {
    radius: size,
    fillColor: color,
    color: '#fff',
    weight: 1.5,
    opacity: 0.9,
    fillOpacity: 0.85,
  });

  const popup = `
    <div class="popup-title">실시간 산불 감지</div>
    <div class="popup-region">${fire.region} · ${fire.daynight === 'D' ? '주간' : '야간'}</div>
    <span class="popup-risk ${fire.risk}">${riskLabels[fire.risk]}</span>
    <div class="popup-stats">
      <span>🔥 복사열량(FRP): ${fire.frp.toFixed(1)} MW</span>
      <span>🌡️ 밝기온도: ${fire.brightness.toFixed(1)} K</span>
      <span>🕐 탐지시각: ${formatTime(fire.acqDate, fire.acqTime)}</span>
      <span>🛰️ 위성: ${fire.satellite}</span>
    </div>
  `;

  marker.bindPopup(popup, { maxWidth: 220 });
  marker.on('mouseover', () => marker.openPopup());
  return marker;
}

function renderMarkers() {
  Object.values(markerLayers).forEach(m => map.removeLayer(m));
  markerLayers = {};

  const filtered = liveFireData.filter(
    f => currentFilter === 'ALL' || currentFilter === f.risk
  );

  if (filtered.length === 0) return;

  filtered.forEach(fire => {
    const marker = createFireMarker(fire);
    marker.addTo(map);
    markerLayers[fire.id] = marker;
  });
}

// ===== ROUTES =====
function renderRoutes() {
  routeLayers.forEach(l => map.removeLayer(l));
  routeLayers = [];

  patrolRoutes.forEach(route => {
    if (currentFilter !== 'ALL' && currentFilter !== route.risk) return;

    const line = L.polyline(route.coordinates, {
      color: route.color,
      weight: activeRouteId === route.id ? 4 : 2.5,
      opacity: activeRouteId === route.id ? 1 : 0.7,
      dashArray: '8, 5',
      lineJoin: 'round',
    }).addTo(map);

    route.coordinates.forEach((point, i) => {
      if (i === 0 || i === route.coordinates.length - 1) {
        const dot = L.circleMarker(point, {
          radius: 5,
          fillColor: route.color,
          color: '#fff',
          weight: 1.5,
          fillOpacity: 1,
          opacity: 1,
        }).addTo(map);
        routeLayers.push(dot);
      }
    });

    line.bindTooltip(
      `<strong>${route.name}</strong><br>거리: ${route.distance} · 요원: ${route.guardCount}명`,
      { sticky: true }
    );
    line.on('click', () => focusRoute(route.id));
    routeLayers.push(line);
  });
}

function focusRoute(routeId) {
  activeRouteId = activeRouteId === routeId ? null : routeId;
  renderRoutes();
  renderRouteList();
  const route = patrolRoutes.find(r => r.id === routeId);
  if (route && activeRouteId === routeId) {
    map.fitBounds(L.latLngBounds(route.coordinates), { padding: [60, 60] });
  }
}

// ===== LEGEND =====
const legend = L.control({ position: 'bottomright' });
legend.onAdd = () => {
  const div = L.DomUtil.create('div', 'map-legend');
  div.innerHTML = `
    <h4>범례</h4>
    <div class="legend-item"><div class="legend-dot" style="background:#ff3333;box-shadow:0 0 5px rgba(255,51,51,.6)"></div>위험 (신뢰도 높음)</div>
    <div class="legend-item"><div class="legend-dot" style="background:#ff8c00;box-shadow:0 0 5px rgba(255,140,0,.6)"></div>주의 (신뢰도 보통)</div>
    <div class="legend-item"><div class="legend-dot" style="background:#ffc300;box-shadow:0 0 5px rgba(255,195,0,.6)"></div>관심 (신뢰도 낮음)</div>
    <hr class="legend-separator">
    <div class="legend-item"><div class="legend-line" style="background:#ff3333"></div>위험 노선</div>
    <div class="legend-item"><div class="legend-line" style="background:#ff9900"></div>주의 노선</div>
    <div class="legend-item"><div class="legend-line" style="background:#ffc300"></div>관심 노선</div>
    <hr class="legend-separator">
    <div style="font-size:10px;color:#6677aa;">출처: NASA FIRMS VIIRS SNPP</div>
  `;
  return div;
};
legend.addTo(map);

// ===== SIDEBAR =====
function renderRiskSummary() {
  const counts = { HIGH: 0, MEDIUM: 0, LOW: 0 };
  liveFireData.forEach(f => counts[f.risk]++);
  const total = liveFireData.length || 1;

  document.getElementById('count-high').textContent = counts.HIGH;
  document.getElementById('count-medium').textContent = counts.MEDIUM;
  document.getElementById('count-low').textContent = counts.LOW;
  document.getElementById('bar-high').style.width = (counts.HIGH / total * 100) + '%';
  document.getElementById('bar-medium').style.width = (counts.MEDIUM / total * 100) + '%';
  document.getElementById('bar-low').style.width = (counts.LOW / total * 100) + '%';
}

function renderRegionStats() {
  const container = document.getElementById('region-stats');

  if (liveFireData.length === 0) {
    container.innerHTML = `
      <div class="no-fire-msg">
        <span class="no-fire-icon">🌲</span>
        현재 탐지된 산불이 없습니다.<br>순찰 노선은 취약지역 분석 기반으로 유지됩니다.
      </div>
    `;
    return;
  }

  const regionMap = {};
  liveFireData.forEach(f => {
    if (!regionMap[f.region]) regionMap[f.region] = { HIGH: 0, MEDIUM: 0, LOW: 0 };
    regionMap[f.region][f.risk]++;
  });

  container.innerHTML = Object.entries(regionMap)
    .sort((a, b) => (b[1].HIGH - a[1].HIGH) || (b[1].MEDIUM - a[1].MEDIUM))
    .map(([region, counts]) => `
      <div class="region-row">
        <span class="region-name">${region}</span>
        <div class="region-badges">
          ${counts.HIGH > 0 ? `<span class="badge badge-high">위험 ${counts.HIGH}</span>` : ''}
          ${counts.MEDIUM > 0 ? `<span class="badge badge-medium">주의 ${counts.MEDIUM}</span>` : ''}
          ${counts.LOW > 0 ? `<span class="badge badge-low">관심 ${counts.LOW}</span>` : ''}
        </div>
      </div>
    `).join('');
}

function renderRouteList() {
  const container = document.getElementById('route-list');
  container.innerHTML = patrolRoutes.map(route => `
    <div class="route-item ${activeRouteId === route.id ? 'active' : ''}" data-route-id="${route.id}">
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
  `).join('');

  container.querySelectorAll('.route-item').forEach(el => {
    el.addEventListener('click', () => focusRoute(Number(el.dataset.routeId)));
  });
}

// ===== FILTERS =====
document.querySelectorAll('.filter-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    currentFilter = btn.dataset.filter;
    activeRouteId = null;
    renderMarkers();
    renderRoutes();
    renderRouteList();
  });
});

// ===== INIT =====
renderRouteList();
renderRoutes();
fetchFireData();
