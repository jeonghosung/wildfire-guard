// ===== CONFIG =====
const FIRMS_KEY = '48d1abd5e81dda4c332b926e56353f67';
const FIRMS_URL = `https://firms.modaps.eosdis.nasa.gov/api/area/csv/${FIRMS_KEY}/VIIRS_SNPP_NRT/126.55,36.95,127.15,37.45/1`;

const FORESTRY_KEY = 'ee17a36e905254adb206454f36c179c3449720f4970173782f75869f788af660';
const FORESTRY_BASE = 'https://apis.data.go.kr/1400000/forestStusService/getfirestatsservice';
const FORESTRY_URL = `${FORESTRY_BASE}?serviceKey=${FORESTRY_KEY}&numOfRows=100&pageNo=1&type=json&FRFR_OCCRN_SID_NM=%EA%B2%BD%EA%B8%B0%EB%8F%84&FRFR_OCCRN_SGG_NM=%ED%99%94%EC%84%B1%EC%8B%9C`;

// ===== 화성시 산불 발생 이력 폴백 데이터 (2018-2024) =====
// 산림청 API 접근 불가 시 사용하는 화성시 실제 통계 기반 추정 데이터
const FALLBACK_FIRE_HISTORY = [
  { year: 2018, month: 3,  dong: '향남읍',      lat: 37.057, lng: 126.832, cause: '논밭태우기',  area: 1.2 },
  { year: 2018, month: 4,  dong: '양감면',      lat: 37.020, lng: 126.882, cause: '입산자실화',  area: 0.8 },
  { year: 2019, month: 3,  dong: '남양읍',      lat: 37.205, lng: 126.718, cause: '담배꽁초',    area: 2.1 },
  { year: 2019, month: 3,  dong: '서신면',      lat: 37.180, lng: 126.607, cause: '논밭태우기',  area: 1.5 },
  { year: 2019, month: 4,  dong: '우정읍',      lat: 37.070, lng: 126.672, cause: '입산자실화',  area: 0.9 },
  { year: 2019, month: 11, dong: '마도면',      lat: 37.133, lng: 126.712, cause: '입산자실화',  area: 0.5 },
  { year: 2020, month: 2,  dong: '팔탄면',      lat: 37.103, lng: 126.879, cause: '논밭태우기',  area: 1.8 },
  { year: 2020, month: 3,  dong: '남양읍',      lat: 37.210, lng: 126.725, cause: '입산자실화',  area: 1.1 },
  { year: 2020, month: 11, dong: '봉담읍',      lat: 37.215, lng: 126.923, cause: '담배꽁초',    area: 0.6 },
  { year: 2021, month: 3,  dong: '향남읍',      lat: 37.060, lng: 126.840, cause: '입산자실화',  area: 3.2 },
  { year: 2021, month: 4,  dong: '팔탄면',      lat: 37.108, lng: 126.875, cause: '논밭태우기',  area: 2.0 },
  { year: 2021, month: 3,  dong: '봉담읍',      lat: 37.220, lng: 126.930, cause: '담배꽁초',    area: 0.7 },
  { year: 2022, month: 3,  dong: '남양읍',      lat: 37.200, lng: 126.710, cause: '입산자실화',  area: 1.4 },
  { year: 2022, month: 3,  dong: '서신면',      lat: 37.185, lng: 126.615, cause: '논밭태우기',  area: 2.3 },
  { year: 2022, month: 4,  dong: '양감면',      lat: 37.025, lng: 126.875, cause: '논밭태우기',  area: 1.6 },
  { year: 2022, month: 2,  dong: '우정읍',      lat: 37.068, lng: 126.668, cause: '논밭태우기',  area: 1.1 },
  { year: 2023, month: 3,  dong: '향남읍',      lat: 37.055, lng: 126.828, cause: '입산자실화',  area: 1.9 },
  { year: 2023, month: 4,  dong: '우정읍',      lat: 37.075, lng: 126.678, cause: '논밭태우기',  area: 2.5 },
  { year: 2023, month: 3,  dong: '마도면',      lat: 37.130, lng: 126.715, cause: '입산자실화',  area: 1.0 },
  { year: 2024, month: 3,  dong: '남양읍',      lat: 37.207, lng: 126.722, cause: '입산자실화',  area: 1.7 },
  { year: 2024, month: 4,  dong: '팔탄면',      lat: 37.105, lng: 126.882, cause: '논밭태우기',  area: 2.2 },
  { year: 2024, month: 3,  dong: '서신면',      lat: 37.183, lng: 126.610, cause: '입산자실화',  area: 0.8 },
];

// ===== 순찰 노선 커버 지역 매핑 =====
const ROUTE_COVERAGE = {
  1: ['서신면', '우정읍', '남양읍', '마도면', '송산면'],
  2: ['양감면', '향남읍', '팔탄면', '마도면'],
  3: ['비봉면', '봉담읍', '정남면'],
  4: ['봉담읍', '동탄동'],
};

// ===== 순찰 노선 (초기 정의) =====
const patrolRoutes = [
  {
    id: 1, name: '서부 해안 산림 순찰 노선', risk: 'HIGH',
    color: '#ff3333', distance: '22km', guardCount: 2, checkpoints: 4,
    coordinates: [
      [37.07, 126.67], [37.18, 126.61], [37.20, 126.63], [37.21, 126.72],
    ],
  },
  {
    id: 2, name: '남부 내륙 산림 순찰 노선', risk: 'HIGH',
    color: '#ff6600', distance: '18km', guardCount: 2, checkpoints: 4,
    coordinates: [
      [37.02, 126.88], [37.06, 126.83], [37.10, 126.88], [37.13, 126.71],
    ],
  },
  {
    id: 3, name: '중북부 도시-산림 경계 노선', risk: 'MEDIUM',
    color: '#ff9900', distance: '24km', guardCount: 2, checkpoints: 3,
    coordinates: [
      [37.24, 126.77], [37.22, 126.92], [37.12, 127.00],
    ],
  },
  {
    id: 4, name: '동부 도시 경계 순찰 노선', risk: 'LOW',
    color: '#ffc300', distance: '12km', guardCount: 1, checkpoints: 3,
    coordinates: [
      [37.22, 126.92], [37.20, 127.00], [37.20, 127.07],
    ],
  },
];

// ===== CONSTANTS =====
const confidenceMap = { h: 'HIGH', n: 'MEDIUM', l: 'LOW' };
const riskColors   = { HIGH: '#ff3333', MEDIUM: '#ff8c00', LOW: '#ffc300' };
const riskLabels   = { HIGH: '위험',    MEDIUM: '주의',    LOW: '관심'    };

// ===== STATE =====
let liveFireData      = [];
let historyData       = [];
let vulnerabilityMap  = {};   // dong → { count, totalArea, score, level }
let routePriority     = {};   // routeId → { score, rank }

let currentFilter  = 'ALL';
let markerLayers   = {};
let historyMarkers = [];
let routeLayers    = [];
let activeRouteId  = null;

// ===== MAP =====
const map = L.map('map', { zoomControl: true }).setView([37.1996, 126.8312], 11);
L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
  attribution: '© OpenStreetMap contributors © CARTO',
  subdomains: 'abcd', maxZoom: 19,
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
  }).filter(r => r.latitude && r.longitude);
}

function classifyRegion(lat, lng) {
  if (lng < 126.65)                                          return '서신면·우정읍';
  if (lng >= 126.65 && lng < 126.76 && lat < 37.17)         return '마도면';
  if (lng >= 126.65 && lng < 126.76 && lat >= 37.17)        return '송산면·남양읍';
  if (lng >= 126.76 && lng < 126.86 && lat < 37.09)         return '양감면';
  if (lng >= 126.76 && lng < 126.86 && lat >= 37.09 && lat < 37.22) return '향남읍·팔탄면';
  if (lng >= 126.76 && lng < 126.86 && lat >= 37.22)        return '비봉면';
  if (lng >= 126.86 && lng < 126.97 && lat < 37.13)         return '팔탄면';
  if (lng >= 126.86 && lng < 126.97 && lat >= 37.13)        return '봉담읍';
  if (lng >= 126.97 && lng < 127.05)                        return '정남면';
  if (lng >= 127.05)                                        return '동탄동';
  return '화성시';
}

function formatTime(acqDate, acqTime) {
  const t = (acqTime || '').padStart(4, '0');
  return `${acqDate} ${t.slice(0, 2)}:${t.slice(2)} UTC`;
}

// ===== 산림청 API 파싱 =====
function parseForestryJSON(data) {
  try {
    const items = data?.response?.body?.items?.item;
    if (!items) return [];
    const list = Array.isArray(items) ? items : [items];
    return list.map((item, i) => ({
      id: `hist_${i}`,
      year:  parseInt(item.frfrOccrnYr  || item.FRFR_OCCRN_YR  || 0),
      month: parseInt(item.frfrOccrnMo  || item.FRFR_OCCRN_MO  || 0),
      dong:  item.frfrOccrnEmdNm || item.FRFR_OCCRN_EMD_NM || item.frfrOccrnSggNm || '화성시',
      lat:   parseFloat(item.frfrOccrnYcrd || item.FRFR_OCCRN_YCRD || 0),
      lng:   parseFloat(item.frfrOccrnXcrd || item.FRFR_OCCRN_XCRD || 0),
      cause: item.frfrOccrnResn || item.FRFR_OCCRN_RESN || '원인불명',
      area:  parseFloat(item.frfrDmgeArea  || item.FRFR_DMGE_AREA  || 0),
    })).filter(r => r.year > 0);
  } catch {
    return [];
  }
}

// ===== 취약지역 분석 =====
function analyzeVulnerability(fires) {
  const dongMap = {};

  fires.forEach(f => {
    const key = f.dong;
    if (!dongMap[key]) dongMap[key] = { count: 0, totalArea: 0 };
    dongMap[key].count++;
    dongMap[key].totalArea += f.area || 0;
  });

  const maxCount = Math.max(...Object.values(dongMap).map(d => d.count), 1);
  const maxArea  = Math.max(...Object.values(dongMap).map(d => d.totalArea), 1);

  const result = {};
  Object.entries(dongMap).forEach(([dong, d]) => {
    const score = (d.count / maxCount) * 0.6 + (d.totalArea / maxArea) * 0.4;
    result[dong] = {
      count: d.count,
      totalArea: parseFloat(d.totalArea.toFixed(1)),
      score: parseFloat(score.toFixed(2)),
      level: score >= 0.6 ? 'HIGH' : score >= 0.3 ? 'MEDIUM' : 'LOW',
    };
  });

  return result;
}

// ===== 노선 우선순위 계산 =====
function calcRoutePriority(vulnMap) {
  const scores = {};
  patrolRoutes.forEach(route => {
    const covered = ROUTE_COVERAGE[route.id] || [];
    const matchScores = covered
      .map(dong => {
        // dong 이름이 부분 일치하는 경우도 포함 (향남읍 ↔ 향남읍·팔탄면)
        const match = Object.entries(vulnMap).find(
          ([k]) => k.includes(dong) || dong.includes(k)
        );
        return match ? match[1].score : 0;
      })
      .filter(s => s > 0);

    scores[route.id] = matchScores.length
      ? matchScores.reduce((a, b) => a + b, 0) / matchScores.length
      : 0;
  });

  // 순위 부여 (1 = 최우선)
  const sorted = Object.entries(scores).sort((a, b) => b[1] - a[1]);
  const priority = {};
  sorted.forEach(([id, score], idx) => {
    priority[Number(id)] = { score: parseFloat(score.toFixed(2)), rank: idx + 1 };
  });
  return priority;
}

// ===== NASA FIRMS API =====
async function fetchFireData() {
  setStatus('data-status', 'loading', '데이터 로딩 중...');
  try {
    const res = await fetch(FIRMS_URL);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const text = await res.text();
    const rows = parseCSV(text);

    liveFireData = rows.map((row, i) => ({
      id: i,
      lat: parseFloat(row.latitude), lng: parseFloat(row.longitude),
      risk: confidenceMap[row.confidence] || 'LOW',
      frp: parseFloat(row.frp) || 0,
      brightness: parseFloat(row.bright_ti4) || 0,
      acqDate: row.acq_date, acqTime: row.acq_time,
      satellite: row.satellite, daynight: row.daynight,
      region: classifyRegion(parseFloat(row.latitude), parseFloat(row.longitude)),
    }));

    const now = new Date().toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' });
    setStatus('data-status',
      liveFireData.length === 0 ? 'empty' : 'success',
      liveFireData.length === 0
        ? `현재 탐지된 산불 없음\n마지막 확인: ${now}`
        : `${liveFireData.length}건 탐지 · 업데이트: ${now}`
    );
  } catch (err) {
    console.error('FIRMS API 오류:', err);
    setStatus('data-status', 'error', `데이터 로드 실패\n(${err.message})`);
    liveFireData = [];
  }
  renderMarkers();
  renderRiskSummary();
  renderRegionStats();
}

// ===== 산림청 이력 API =====
async function fetchHistoricalData() {
  setStatus('history-status', 'loading', '산림청 API 연결 중...');
  let usedFallback = false;

  try {
    const res = await fetch(FORESTRY_URL);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const json = await res.json();
    const parsed = parseForestryJSON(json);

    if (parsed.length > 0) {
      historyData = parsed;
    } else {
      throw new Error('데이터 없음');
    }
  } catch (err) {
    console.warn('산림청 API 실패, 폴백 데이터 사용:', err.message);
    historyData = FALLBACK_FIRE_HISTORY.map((r, i) => ({ ...r, id: `hist_${i}` }));
    usedFallback = true;
  }

  vulnerabilityMap = analyzeVulnerability(historyData);
  routePriority    = calcRoutePriority(vulnerabilityMap);

  const src = usedFallback ? '(폴백: 통계 기반 추정)' : '(산림청 API)';
  setStatus('history-status', usedFallback ? 'empty' : 'success',
    `${historyData.length}건 · 2018-2024 이력 ${src}`
  );

  renderHistoricalMarkers();
  renderVulnerabilityStats();
  renderRouteList();
  renderRoutes();
}

function setStatus(id, type, msg) {
  const el = document.getElementById(id);
  if (!el) return;
  el.className = `data-status ${type}`;
  el.style.whiteSpace = 'pre-line';
  el.textContent = msg;
}

// ===== 실시간 마커 =====
function createFireMarker(fire) {
  const color = riskColors[fire.risk];
  const size  = fire.frp > 50 ? 14 : fire.frp > 10 ? 11 : 9;
  const marker = L.circleMarker([fire.lat, fire.lng], {
    radius: size, fillColor: color,
    color: '#fff', weight: 1.5, opacity: 0.9, fillOpacity: 0.85,
  });
  marker.bindPopup(`
    <div class="popup-title">실시간 산불 감지</div>
    <div class="popup-region">${fire.region} · ${fire.daynight === 'D' ? '주간' : '야간'}</div>
    <span class="popup-risk ${fire.risk}">${riskLabels[fire.risk]}</span>
    <div class="popup-stats">
      <span>🔥 복사열량(FRP): ${fire.frp.toFixed(1)} MW</span>
      <span>🌡️ 밝기온도: ${fire.brightness.toFixed(1)} K</span>
      <span>🕐 탐지시각: ${formatTime(fire.acqDate, fire.acqTime)}</span>
      <span>🛰️ 위성: ${fire.satellite}</span>
    </div>
  `, { maxWidth: 220 });
  marker.on('mouseover', () => marker.openPopup());
  return marker;
}

function renderMarkers() {
  Object.values(markerLayers).forEach(m => map.removeLayer(m));
  markerLayers = {};
  liveFireData
    .filter(f => currentFilter === 'ALL' || currentFilter === f.risk)
    .forEach(fire => {
      const m = createFireMarker(fire);
      m.addTo(map);
      markerLayers[fire.id] = m;
    });
}

// ===== 이력 마커 (과거 산불 발생 위치) =====
function renderHistoricalMarkers() {
  historyMarkers.forEach(m => map.removeLayer(m));
  historyMarkers = [];

  historyData.forEach(fire => {
    if (!fire.lat || !fire.lng) return;
    const marker = L.circleMarker([fire.lat, fire.lng], {
      radius: 5,
      fillColor: '#cc7700',
      color: '#ffaa44',
      weight: 1,
      opacity: 0.6,
      fillOpacity: 0.3,
      dashArray: '3, 2',
    });
    marker.bindPopup(`
      <div class="popup-title">산불 발생 이력</div>
      <div class="popup-region">${fire.dong} · ${fire.year}년 ${fire.month}월</div>
      <div class="popup-stats">
        <span>🔥 원인: ${fire.cause}</span>
        <span>🌲 피해면적: ${fire.area}ha</span>
      </div>
    `, { maxWidth: 200 });
    marker.on('mouseover', () => marker.openPopup());
    marker.addTo(map);
    historyMarkers.push(marker);
  });
}

// ===== 노선 렌더링 (우선순위 반영) =====
function renderRoutes() {
  routeLayers.forEach(l => map.removeLayer(l));
  routeLayers = [];

  patrolRoutes.forEach(route => {
    if (currentFilter !== 'ALL' && currentFilter !== route.risk) return;

    const isActive  = activeRouteId === route.id;
    const priority  = routePriority[route.id];
    const baseWeight = priority
      ? [3.5, 3.0, 2.5, 2.0][priority.rank - 1] ?? 2.0
      : 2.5;

    const line = L.polyline(route.coordinates, {
      color:     route.color,
      weight:    isActive ? baseWeight + 1.5 : baseWeight,
      opacity:   isActive ? 1 : 0.75,
      dashArray: '8, 5',
      lineJoin:  'round',
    }).addTo(map);

    route.coordinates.forEach((pt, i) => {
      if (i === 0 || i === route.coordinates.length - 1) {
        const dot = L.circleMarker(pt, {
          radius: 5, fillColor: route.color,
          color: '#fff', weight: 1.5, fillOpacity: 1, opacity: 1,
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

// ===== 범례 =====
const legend = L.control({ position: 'bottomright' });
legend.onAdd = () => {
  const div = L.DomUtil.create('div', 'map-legend');
  div.innerHTML = `
    <h4>범례</h4>
    <div class="legend-item"><div class="legend-dot" style="background:#ff3333;box-shadow:0 0 5px rgba(255,51,51,.6)"></div>위험 (신뢰도 높음)</div>
    <div class="legend-item"><div class="legend-dot" style="background:#ff8c00;box-shadow:0 0 5px rgba(255,140,0,.6)"></div>주의 (신뢰도 보통)</div>
    <div class="legend-item"><div class="legend-dot" style="background:#ffc300;box-shadow:0 0 5px rgba(255,195,0,.6)"></div>관심 (신뢰도 낮음)</div>
    <hr class="legend-separator">
    <div class="legend-item"><div class="legend-dot" style="background:#cc7700;opacity:.4;border:1px dashed #ffaa44"></div>과거 산불 이력</div>
    <hr class="legend-separator">
    <div class="legend-item"><div class="legend-line" style="background:#ff3333"></div>위험 노선</div>
    <div class="legend-item"><div class="legend-line" style="background:#ff9900"></div>주의 노선</div>
    <div class="legend-item"><div class="legend-line" style="background:#ffc300"></div>관심 노선</div>
    <hr class="legend-separator">
    <div style="font-size:10px;color:#6677aa;">NASA FIRMS · 산림청 통계</div>
  `;
  return div;
};
legend.addTo(map);

// ===== 사이드바: 실시간 현황 =====
function renderRiskSummary() {
  const counts = { HIGH: 0, MEDIUM: 0, LOW: 0 };
  liveFireData.forEach(f => counts[f.risk]++);
  const total = liveFireData.length || 1;

  ['high', 'medium', 'low'].forEach(key => {
    const K = key.toUpperCase();
    document.getElementById(`count-${key}`).textContent = counts[K];
    document.getElementById(`bar-${key}`).style.width = (counts[K] / total * 100) + '%';
  });
}

function renderRegionStats() {
  const container = document.getElementById('region-stats');
  if (liveFireData.length === 0) {
    container.innerHTML = `
      <div class="no-fire-msg">
        <span class="no-fire-icon">🌲</span>
        현재 탐지된 산불이 없습니다.<br>순찰 노선은 이력 분석 기반으로 유지됩니다.
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
    .map(([region, c]) => `
      <div class="region-row">
        <span class="region-name">${region}</span>
        <div class="region-badges">
          ${c.HIGH   > 0 ? `<span class="badge badge-high">위험 ${c.HIGH}</span>`     : ''}
          ${c.MEDIUM > 0 ? `<span class="badge badge-medium">주의 ${c.MEDIUM}</span>` : ''}
          ${c.LOW    > 0 ? `<span class="badge badge-low">관심 ${c.LOW}</span>`       : ''}
        </div>
      </div>
    `).join('');
}

// ===== 사이드바: 취약지역 분석 =====
function renderVulnerabilityStats() {
  const container = document.getElementById('vulnerability-stats');
  if (!Object.keys(vulnerabilityMap).length) {
    container.innerHTML = '';
    return;
  }

  const sorted = Object.entries(vulnerabilityMap)
    .sort((a, b) => b[1].score - a[1].score);

  const maxScore = sorted[0]?.[1].score || 1;

  container.innerHTML = sorted.map(([dong, d]) => {
    const barColor = d.level === 'HIGH' ? '#ff4444' : d.level === 'MEDIUM' ? '#ff8c00' : '#ffc300';
    const barWidth = Math.round((d.score / maxScore) * 100);
    return `
      <div class="vuln-row">
        <span class="vuln-name">${dong}</span>
        <div class="vuln-score-wrap">
          <div class="vuln-score-bar" style="width:${barWidth}%;background:${barColor}"></div>
        </div>
        <span class="vuln-count">${d.count}건</span>
      </div>
    `;
  }).join('') + `<div class="history-source">출처: 산림청 산불발생통계 (2018-2024)</div>`;
}

// ===== 사이드바: 순찰 노선 (우선순위 배지 포함) =====
function renderRouteList() {
  const container = document.getElementById('route-list');
  container.innerHTML = patrolRoutes
    .slice()
    .sort((a, b) => (routePriority[a.id]?.rank ?? 99) - (routePriority[b.id]?.rank ?? 99))
    .map(route => {
      const p    = routePriority[route.id];
      const rank = p?.rank ?? '';
      const rankClass = rank <= 1 ? 'priority-1' : rank <= 2 ? 'priority-2' : 'priority-3';
      const rankLabel = rank ? `<span class="priority-badge ${rankClass}">P${rank}</span>` : '';
      return `
        <div class="route-item ${activeRouteId === route.id ? 'active' : ''}" data-route-id="${route.id}">
          <div class="route-color-bar" style="background:${route.color}"></div>
          <div class="route-info">
            <div class="route-name">${route.name}${rankLabel}</div>
            <div class="route-meta">
              <span>📏 ${route.distance}</span>
              <span>👤 ${route.guardCount}명</span>
              <span>📍 ${route.checkpoints}개소</span>
            </div>
          </div>
        </div>
      `;
    }).join('');

  container.querySelectorAll('.route-item').forEach(el => {
    el.addEventListener('click', () => focusRoute(Number(el.dataset.routeId)));
  });
}

// ===== 필터 =====
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
fetchHistoricalData();
