// ===== CONFIG =====
const FIRMS_KEY = '48d1abd5e81dda4c332b926e56353f67';
const FIRMS_URL = `https://firms.modaps.eosdis.nasa.gov/api/area/csv/${FIRMS_KEY}/VIIRS_SNPP_NRT/126.55,36.95,127.15,37.45/1`;

const FORESTRY_KEY = 'ee17a36e905254adb206454f36c179c3449720f4970173782f75869f788af660';
const FORESTRY_BASE = 'https://apis.data.go.kr/1400000/forestStusService/getfirestatsservice';
const FORESTRY_URL = `${FORESTRY_BASE}?serviceKey=${FORESTRY_KEY}&numOfRows=100&pageNo=1&type=json&FRFR_OCCRN_SID_NM=%EA%B2%BD%EA%B8%B0%EB%8F%84&FRFR_OCCRN_SGG_NM=%ED%99%94%EC%84%B1%EC%8B%9C`;

const WEATHER_KEY  = 'ee17a36e905254adb206454f36c179c3449720f4970173782f75869f788af660';
const WEATHER_BASE = 'https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getUltraSrtNcst';
const WEATHER_NX   = 57;
const WEATHER_NY   = 74;

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
let aiPredictions     = null; // predicted_risk.json 전체
let aiRoutePriority   = {};   // routeId → { aiScore, rank }

let currentFilter       = 'ALL';
let markerLayers        = {};
let historyMarkers      = [];
let aiRiskMarkers       = [];
let gridData            = null;
let gridLayers          = [];
let showGrid            = true;
let optimalRoutes       = null;
let optimalRouteLayers  = [];
let showOptimalRoutes   = true;
let routeLayers         = [];
let activeRouteId       = null;

// ===== TIMELINE STATE =====
let selectedYear  = 0;       // 0 = 전체
let timePeriod    = 'ALL';   // 'ALL' | 'AM' | 'PM' | 'NIGHT'
let playInterval  = null;
let playYear      = 2018;

// ===== MAP =====
const map = L.map('map', { zoomControl: true }).setView([37.1996, 126.8312], 11);

// 격자 레이어를 마커 아래에 표시하기 위한 전용 pane
map.createPane('gridPane');
map.getPane('gridPane').style.zIndex = 300;
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
  updateSummaryCards();
}

function setStatus(id, type, msg) {
  const el = document.getElementById(id);
  if (!el) return;
  el.className = `data-status ${type}`;
  el.style.whiteSpace = 'pre-line';
  if (type === 'loading') {
    el.innerHTML = `<span class="spinner"></span>${msg}`;
  } else {
    el.textContent = msg;
  }
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

  const data = selectedYear > 0
    ? historyData.filter(f => f.year === selectedYear)
    : historyData;

  data.forEach(fire => {
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

// ===== AI 예측 위험도 =====
async function fetchAIPrediction() {
  setStatus('ai-status', 'loading', 'AI 모델 로딩 중...');
  try {
    const res = await fetch('public/data/predicted_risk.json');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    aiPredictions = await res.json();

    aiRoutePriority = calcAIRoutePriority(aiPredictions.predictions);
    applyAIToRoutes();

    const ts = new Date(aiPredictions.timestamp).toLocaleString('ko-KR', {
      month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit',
    });
    setStatus('ai-status', 'success', `${aiPredictions.summary.total_dongs}개 읍면동 · ${ts}`);
  } catch (err) {
    console.warn('AI 예측 로드 실패:', err.message);
    setStatus('ai-status', 'error', `로드 실패 (${err.message})`);
    return;
  }

  renderAIPredictionMarkers();
  renderAIRiskSidebar();
  renderRouteList();
  renderRoutes();
}

function calcAIRoutePriority(predictions) {
  const scores = {};
  patrolRoutes.forEach(r => { scores[r.id] = { total: 0, count: 0 }; });

  predictions.forEach(pred => {
    const myeon = pred.myeon || '';
    for (const [routeId, coverage] of Object.entries(ROUTE_COVERAGE)) {
      const rid = Number(routeId);
      const hit = coverage.some(c => {
        const base = c.replace(/[면읍동]$/, '');
        return myeon === base || myeon.includes(base);
      });
      if (hit) {
        scores[rid].total += pred.probability;
        scores[rid].count++;
        break;
      }
    }
  });

  const sorted = Object.entries(scores)
    .map(([id, s]) => [Number(id), s.count > 0 ? s.total / s.count : 0])
    .sort((a, b) => b[1] - a[1]);

  const result = {};
  sorted.forEach(([id, score], idx) => {
    result[id] = { aiScore: parseFloat(score.toFixed(3)), rank: idx + 1 };
  });
  return result;
}

function applyAIToRoutes() {
  const scores = Object.values(aiRoutePriority).map(p => p.aiScore);
  const maxScore = Math.max(...scores, 0.001);
  const q66 = maxScore * 0.66;
  const q33 = maxScore * 0.33;

  patrolRoutes.forEach(route => {
    const ap = aiRoutePriority[route.id];
    if (!ap) return;
    if (ap.aiScore >= q66)      { route.risk = 'HIGH';   route.color = '#ff3333'; }
    else if (ap.aiScore >= q33) { route.risk = 'MEDIUM'; route.color = '#ff6600'; }
    else                        { route.risk = 'LOW';    route.color = '#ffc300'; }
  });
}

// AI 위험도 마커 (상위 20개 표시)
const AI_COLORS = { HIGH: '#aa44ff', MEDIUM: '#7733dd', LOW: '#5522aa' };

function renderAIPredictionMarkers() {
  aiRiskMarkers.forEach(m => map.removeLayer(m));
  aiRiskMarkers = [];
  if (!aiPredictions) return;

  const top = aiPredictions.predictions
    .filter(p => p.lat && p.lng)
    .slice(0, 20);

  top.forEach(pred => {
    const color = AI_COLORS[pred.level] || AI_COLORS.LOW;
    const radius = 5 + pred.probability * 18;
    const marker = L.circleMarker([pred.lat, pred.lng], {
      radius,
      fillColor: color,
      color: '#cc88ff',
      weight: 1.5,
      opacity: 0.8,
      fillOpacity: 0.35 + pred.probability * 0.4,
    });
    marker.bindPopup(`
      <div class="popup-title">🤖 AI 예측 위험도</div>
      <div class="popup-region">${pred.dong} (${pred.myeon}면)</div>
      <span class="popup-risk ai-risk-badge">AI ${(pred.probability * 100).toFixed(1)}%</span>
      <div class="popup-stats">
        <span>📊 위험 등급: ${pred.level === 'HIGH' ? '높음' : pred.level === 'MEDIUM' ? '중간' : '낮음'}</span>
        <span>🔥 누적 화재: ${pred.hist_count}건</span>
        <span>⚡ 주요 원인: ${pred.top_cause}</span>
        <span style="color:#8877aa;font-size:10px">※ 좌표는 읍면 중심 기준 추정값</span>
      </div>
    `, { maxWidth: 220 });
    marker.on('mouseover', () => marker.openPopup());
    marker.addTo(map);
    aiRiskMarkers.push(marker);
  });
}

function renderAIRiskSidebar() {
  const container = document.getElementById('ai-top5-list');
  if (!aiPredictions || !aiPredictions.predictions.length) {
    container.innerHTML = '';
    return;
  }

  const top5 = aiPredictions.predictions.slice(0, 5);
  const maxProb = top5[0]?.probability || 1;
  const rankIcons = ['🥇', '🥈', '🥉', '4️⃣', '5️⃣'];

  container.innerHTML = top5.map((pred, i) => {
    const barPct = Math.round((pred.probability / maxProb) * 100);
    const barColor = pred.level === 'HIGH' ? '#aa44ff' : pred.level === 'MEDIUM' ? '#8833dd' : '#6622bb';
    return `
      <div class="ai-risk-row">
        <span class="ai-rank-icon">${rankIcons[i]}</span>
        <div class="ai-dong-info">
          <div class="ai-dong-name">${pred.dong}
            <span class="ai-level-badge ai-level-${pred.level.toLowerCase()}">${pred.level}</span>
          </div>
          <div class="ai-dong-meta">${pred.myeon ? pred.myeon + '면 · ' : ''}${pred.top_cause}</div>
        </div>
        <div class="ai-prob-col">
          <div class="ai-prob-bar-wrap">
            <div class="ai-prob-bar" style="width:${barPct}%;background:${barColor}"></div>
          </div>
          <span class="ai-prob-value">${(pred.probability * 100).toFixed(1)}%</span>
        </div>
      </div>
    `;
  }).join('') + `<div class="ai-source-note">RandomForest · 기상+이력 ${aiPredictions.features_used?.length || 0}개 특성</div>`;
}

// ===== 5km 격자 위험도 =====
async function fetchGridData() {
  setStatus('grid-status', 'loading', '격자 데이터 로딩 중...');
  try {
    const res = await fetch('public/data/grid_risk.json');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    gridData = await res.json();

    const lc = gridData.level_counts;
    const ts = new Date(gridData.timestamp).toLocaleString('ko-KR', {
      month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit',
    });
    setStatus('grid-status', 'success',
      `${gridData.grid_size_km}km 격자 · HIGH ${lc.HIGH} / MEDIUM ${lc.MEDIUM} / LOW ${lc.LOW} · ${ts}`);
  } catch (err) {
    console.warn('격자 데이터 로드 실패:', err.message);
    setStatus('grid-status', 'error', `로드 실패: 스크립트 실행 필요`);
    return;
  }
  renderGridLayers();
  renderGridSidebar();
  updateSummaryCards();
}

const GRID_FILL_OPACITY  = { HIGH: 0.40, MEDIUM: 0.25, LOW: 0.12 };
const TIME_OPACITY_MULT  = { ALL: 1.0, AM: 0.80, PM: 1.35, NIGHT: 0.50 };

function renderGridLayers() {
  gridLayers.forEach(l => map.removeLayer(l));
  gridLayers = [];
  if (!gridData || !showGrid) return;

  const mult = TIME_OPACITY_MULT[timePeriod] || 1.0;

  gridData.cells.forEach(cell => {
    if (cell.level === 'NONE') return;

    const color       = riskColors[cell.level];
    const fillOpacity = Math.min(0.75, GRID_FILL_OPACITY[cell.level] * mult);
    const wps         = cell.waypoints.length ? cell.waypoints.join(', ') : '—';

    const rect = L.rectangle(
      [[cell.lat_min, cell.lng_min], [cell.lat_max, cell.lng_max]],
      {
        pane:        'gridPane',
        color,
        weight:      0.8,
        opacity:     0.5,
        fillColor:   color,
        fillOpacity,
        interactive: true,
      }
    );

    rect.bindPopup(`
      <div class="popup-title">📐 5km 격자 위험도</div>
      <div class="popup-region">${cell.grid_id} · ${cell.waypoint_count}개 읍면동 포함</div>
      <span class="popup-risk ${cell.level}">${riskLabels[cell.level]}</span>
      <div class="popup-stats">
        <span>📊 복합 위험도: ${(cell.combined_risk * 100).toFixed(1)}%</span>
        <span>🤖 AI 예측: ${(cell.ai_risk * 100).toFixed(1)}%</span>
        <span>📜 이력 기반: ${(cell.hist_risk * 100).toFixed(1)}%</span>
        <span>📍 포함 지역: ${wps}</span>
        ${cell.top_cause ? `<span>⚡ 주요 원인: ${cell.top_cause}</span>` : ''}
      </div>
    `, { maxWidth: 240 });

    rect.on('mouseover', () => rect.openPopup());
    rect.addTo(map);
    gridLayers.push(rect);
  });
}

function renderGridSidebar() {
  const container = document.getElementById('grid-stats');
  if (!gridData) { container.innerHTML = ''; return; }

  const lc = gridData.level_counts;
  const active = lc.HIGH + lc.MEDIUM + lc.LOW;
  container.innerHTML = `
    <div class="grid-summary">
      <span class="grid-badge grid-badge-high">위험 ${lc.HIGH}</span>
      <span class="grid-badge grid-badge-medium">주의 ${lc.MEDIUM}</span>
      <span class="grid-badge grid-badge-low">관심 ${lc.LOW}</span>
    </div>
    <div class="ai-source-note">${gridData.grid_size_km}km×${gridData.grid_size_km}km 격자 · ${active}/${gridData.grid_count}개 활성</div>
  `;
}

function toggleGrid() {
  showGrid = !showGrid;
  const btn = document.getElementById('toggle-grid-btn');
  if (btn) {
    btn.textContent = showGrid ? '지도 숨기기' : '지도 표시';
    btn.classList.toggle('active', showGrid);
  }
  renderGridLayers();
}

// ===== 최적 순찰 노선 =====
const PERIOD_LABEL_KO = { ALL: '전체', AM: '오전', PM: '오후', NIGHT: '야간' };
const RISK_LABEL_KO   = { HIGH: '높음', MEDIUM: '중간', LOW: '낮음' };

function _getPeriodGuards() {
  if (!optimalRoutes) return [];
  // v2: time_periods[period].guards 우선, 없으면 guards (v1 호환)
  const tp = optimalRoutes.time_periods;
  if (tp && timePeriod !== 'ALL' && tp[timePeriod]?.guards?.length) {
    return tp[timePeriod].guards;
  }
  if (tp?.ALL?.guards?.length) return tp.ALL.guards;
  return optimalRoutes.guards || [];
}

function _getPeriodMeta() {
  if (!optimalRoutes?.time_periods) return null;
  return optimalRoutes.time_periods[timePeriod] || optimalRoutes.time_periods.ALL || null;
}

async function fetchOptimalRoutes() {
  setStatus('optimal-status', 'loading', '노선 데이터 로딩 중...');
  try {
    const res = await fetch('public/data/optimal_routes.json');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    optimalRoutes = await res.json();

    const ts = new Date(optimalRoutes.timestamp).toLocaleString('ko-KR', {
      month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit',
    });
    const guards     = _getPeriodGuards();
    const totalStops = guards.reduce((s, g) => s + g.stop_count, 0);
    const roadTag    = optimalRoutes.road_based ? ' · OSM 도로 기반' : '';
    setStatus('optimal-status', 'success',
      `${optimalRoutes.num_guards}명 · ${totalStops}개소 · ${ts}${roadTag}`);
  } catch (err) {
    console.warn('최적 노선 로드 실패:', err.message);
    setStatus('optimal-status', 'error', 'optimal_routes.json 없음 — 스크립트 실행 필요');
    return;
  }
  renderOptimalRouteLayers();
  renderOptimalRoutesSidebar();
  updateSummaryCards();
}

function renderOptimalRouteLayers() {
  optimalRouteLayers.forEach(l => map.removeLayer(l));
  optimalRouteLayers = [];
  if (!optimalRoutes || !showOptimalRoutes) return;

  const guards = _getPeriodGuards();

  guards.forEach(guard => {
    // 시간대에 따라 선 스타일 조정
    const isNight  = timePeriod === 'NIGHT';
    const lineOpts = {
      color:     guard.color,
      weight:    timePeriod === 'PM' ? 4.0 : 3.2,
      opacity:   isNight ? 0.70 : 0.92,
      lineJoin:  'round',
      lineCap:   'round',
    };
    if (isNight) lineOpts.dashArray = '6, 4';

    const line = L.polyline(guard.route_coords, lineOpts).addTo(map);
    const ph = int2time(guard.estimated_hours);
    line.bindTooltip(
      `<strong>요원 ${guard.id} · ${guard.zone_name}</strong><br>` +
      `${guard.total_distance_km}km · ${guard.stop_count}개소 · ${ph}`,
      { sticky: true }
    );
    optimalRouteLayers.push(line);

    guard.waypoints.forEach(wp => {
      const icon = L.divIcon({
        className: '',
        html: `<div class="optimal-stop-marker" style="background:${guard.color}">${wp.order}</div>`,
        iconSize: [22, 22], iconAnchor: [11, 11],
      });
      const m = L.marker([wp.lat, wp.lng], { icon });

      // 시간대별 확률 표시
      const probAM    = wp.prob_am    ?? wp.probability;
      const probPM    = wp.prob_pm    ?? wp.probability;
      const probNight = wp.prob_night ?? wp.probability;
      const curProb   = { AM: probAM, PM: probPM, NIGHT: probNight, ALL: wp.prob_base ?? wp.probability }[timePeriod] ?? wp.probability;
      const levelKo   = RISK_LABEL_KO[wp.level] || wp.level;

      m.bindPopup(`
        <div class="popup-title">🚶 요원 ${guard.id} · ${wp.order}번째 순찰</div>
        <div class="popup-region">${wp.dong}${wp.myeon ? ' (' + wp.myeon + '면)' : ''}</div>
        <span class="popup-risk ${wp.level}">${levelKo}</span>
        <div class="popup-stats">
          <span>📊 현재 시간대 위험도: ${(curProb * 100).toFixed(1)}%</span>
          <span>🌅 오전 ${(probAM * 100).toFixed(1)}% / 🌇 오후 ${(probPM * 100).toFixed(1)}% / 🌙 야간 ${(probNight * 100).toFixed(1)}%</span>
          <span>⚡ 주요 원인: ${wp.top_cause}</span>
          <span>📏 직전 지점까지: ${wp.dist_from_prev_km}km</span>
          ${guard.road_based ? '<span>🛣️ OSM 실제 도로 경로</span>' : ''}
        </div>
      `, { maxWidth: 240 });
      m.on('mouseover', () => m.openPopup());
      m.addTo(map);
      optimalRouteLayers.push(m);
    });
  });
}

function int2time(h) {
  const hrs  = Math.floor(h);
  const mins = Math.round((h - hrs) * 60);
  return hrs > 0 ? `${hrs}시간 ${mins}분` : `${mins}분`;
}

function renderOptimalRoutesSidebar() {
  const container = document.getElementById('optimal-routes-list');
  if (!optimalRoutes) { container.innerHTML = ''; return; }

  const guards = _getPeriodGuards();
  const meta   = _getPeriodMeta();
  const periodKo = PERIOD_LABEL_KO[timePeriod] || '전체';

  // 균등화 점수 뱃지
  const balanceBadge = meta?.balance_score != null
    ? `<span class="balance-badge" title="요원별 시간 균등화 점수">⚖ ${(meta.balance_score * 100).toFixed(0)}%</span>`
    : '';

  // 시간대 뱃지
  const periodBadge = `<span class="period-badge period-${timePeriod.toLowerCase()}">${periodKo} 노선</span>`;

  // 도로 뱃지
  const roadBadge = optimalRoutes.road_based
    ? '<span class="road-badge">🛣️ OSM 도로</span>'
    : '<span class="road-badge road-badge-fallback">📐 직선 추정</span>';

  const avgTimes = guards.map(g => g.estimated_hours);
  const avgH     = avgTimes.length ? avgTimes.reduce((s, v) => s + v, 0) / avgTimes.length : 0;

  container.innerHTML = `
    <div class="optimal-meta-bar">
      ${periodBadge}${balanceBadge}${roadBadge}
    </div>
  ` + guards.map(guard => {
    const devPct = avgH > 0 ? Math.abs(guard.estimated_hours - avgH) / avgH * 100 : 0;
    const balanceColor = devPct < 10 ? '#33cc77' : devPct < 25 ? '#ffcc33' : '#ff6644';

    const probFn = timePeriod === 'AM'    ? (wp => wp.prob_am    ?? wp.probability)
                 : timePeriod === 'PM'    ? (wp => wp.prob_pm    ?? wp.probability)
                 : timePeriod === 'NIGHT' ? (wp => wp.prob_night ?? wp.probability)
                 :                          (wp => wp.prob_base  ?? wp.probability);

    return `
    <div class="optimal-guard-card">
      <div class="optimal-guard-bar" style="background:${guard.color}"></div>
      <div class="optimal-guard-body">
        <div class="optimal-guard-name">요원 ${guard.id} · ${guard.zone_name}</div>
        <div class="optimal-guard-stats">
          <span>📏 ${guard.total_distance_km}km</span>
          <span>⏱ <strong>${int2time(guard.estimated_hours)}</strong></span>
          <span>📍 ${guard.stop_count}개소</span>
          <span style="color:${balanceColor}">⚖ ±${devPct.toFixed(0)}%</span>
        </div>
        <div class="optimal-wp-list">
          ${guard.waypoints.map(wp => {
            const prob  = probFn(wp);
            const level = prob >= 0.30 ? 'HIGH' : prob >= 0.12 ? 'MEDIUM' : 'LOW';
            const probColor = level === 'HIGH' ? '#ff6666' : level === 'MEDIUM' ? '#ffaa33' : '#6677aa';
            return `
            <div class="optimal-wp-row" data-lat="${wp.lat}" data-lng="${wp.lng}">
              <span class="optimal-wp-num" style="background:${guard.color}">${wp.order}</span>
              <span class="optimal-wp-dong">${wp.dong}</span>
              <span class="optimal-wp-prob" style="color:${probColor}">${(prob * 100).toFixed(1)}%</span>
            </div>`;
          }).join('')}
        </div>
      </div>
    </div>`;
  }).join('') + `<div class="ai-source-note">${optimalRoutes.algorithm}</div>`;

  container.querySelectorAll('[data-lat]').forEach(el => {
    el.addEventListener('click', () => {
      map.setView([parseFloat(el.dataset.lat), parseFloat(el.dataset.lng)], 14);
    });
  });
}

function toggleOptimalRoutes() {
  showOptimalRoutes = !showOptimalRoutes;
  const btn = document.getElementById('toggle-optimal-btn');
  if (btn) {
    btn.textContent = showOptimalRoutes ? '지도 숨기기' : '지도 표시';
    btn.classList.toggle('active', showOptimalRoutes);
  }
  renderOptimalRouteLayers();
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
    <div class="legend-item"><div class="legend-dot" style="background:#aa44ff;opacity:.6;border:1.5px solid #cc88ff"></div>AI 예측 위험도</div>
    <hr class="legend-separator">
    <div class="legend-item"><div class="legend-rect" style="background:rgba(255,51,51,.35);border:1px solid #ff3333"></div>격자 위험</div>
    <div class="legend-item"><div class="legend-rect" style="background:rgba(255,140,0,.25);border:1px solid #ff8c00"></div>격자 주의</div>
    <div class="legend-item"><div class="legend-rect" style="background:rgba(255,195,0,.15);border:1px solid #ffc300"></div>격자 관심</div>
    <hr class="legend-separator">
    <div class="legend-item"><div class="legend-line" style="background:#ff6644"></div>요원 1 최적 노선</div>
    <div class="legend-item"><div class="legend-line" style="background:#44bbff"></div>요원 2 최적 노선</div>
    <div class="legend-item"><div class="legend-line" style="background:#88dd44"></div>요원 3 최적 노선</div>
    <hr class="legend-separator">
    <div style="font-size:10px;color:#6677aa;">NASA FIRMS · 산림청 · AI 예측</div>
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
      const ap = aiRoutePriority[route.id];
      const aiLabel = ap
        ? `<span class="ai-route-badge">🤖 ${(ap.aiScore * 100).toFixed(1)}%</span>`
        : '';
      return `
        <div class="route-item ${activeRouteId === route.id ? 'active' : ''}" data-route-id="${route.id}">
          <div class="route-color-bar" style="background:${route.color}"></div>
          <div class="route-info">
            <div class="route-name">${route.name}${rankLabel}${aiLabel}</div>
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

// ===== 기상청 초단기실황 API =====

// 기상청 API base_date/base_time 계산 (KST 기준, 현재 시각 - 1시간 보장)
function getKSTBaseTime() {
  const now = new Date();
  const kst = new Date(now.getTime() + 9 * 60 * 60 * 1000);
  // 10분 미만이면 이전 시각 데이터가 아직 미생성일 수 있으므로 1시간 전 사용
  if (kst.getUTCMinutes() < 10) kst.setUTCHours(kst.getUTCHours() - 1);
  const date = kst.toISOString().slice(0, 10).replace(/-/g, '');
  const time = String(kst.getUTCHours()).padStart(2, '0') + '00';
  return { date, time };
}

const WEATHER_FALLBACK = {
  T1H: '17.0', WSD: '3.5', VEC: '270', REH: '48', RN1: '0', PTY: '0',
};

async function fetchWeatherData() {
  setStatus('weather-status', 'loading', '기상 데이터 로딩 중...');
  let weatherData = null;
  let usedFallback = false;

  try {
    const { date, time } = getKSTBaseTime();
    const url = `${WEATHER_BASE}?serviceKey=${WEATHER_KEY}&numOfRows=10&pageNo=1&dataType=JSON` +
                `&base_date=${date}&base_time=${time}&nx=${WEATHER_NX}&ny=${WEATHER_NY}`;
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const json = await res.json();

    const items = json?.response?.body?.items?.item;
    if (!items) throw new Error('항목 없음');

    const parsed = {};
    (Array.isArray(items) ? items : [items]).forEach(item => {
      parsed[item.category] = item.obsrValue;
    });

    if (!parsed.T1H) throw new Error('온도 데이터 없음');
    weatherData = parsed;
  } catch (err) {
    console.warn('기상청 API 실패:', err.message);
    weatherData = WEATHER_FALLBACK;
    usedFallback = true;
  }

  const { date, time } = getKSTBaseTime();
  document.getElementById('weather-time').textContent =
    `화성시 · ${time.slice(0, 2)}:${time.slice(2)} KST`;

  const statusMsg = usedFallback ? '기상청 API 연결 실패 (기본값 표시)' : '';
  setStatus('weather-status', usedFallback ? 'empty' : 'success', statusMsg);

  renderWeather(weatherData);
}

function getWindDir(deg) {
  const dirs = ['북', '북북동', '북동', '동북동', '동', '동남동', '남동', '남남동',
                '남', '남남서', '남서', '서남서', '서', '서북서', '북서', '북북서'];
  return dirs[Math.round(((parseFloat(deg) % 360) / 360) * 16) % 16];
}

function calcFireWeatherIndex(data) {
  const temp  = parseFloat(data.T1H || 0);
  const hum   = parseFloat(data.REH || 100);
  const wind  = parseFloat(data.WSD || 0);
  const pty   = parseInt(data.PTY  || 0);

  if (pty > 0) return { label: '낮음',      level: 'low',       desc: '강수 중 — 정상 순찰 유지' };

  // 건조도(50%), 온도(30%), 풍속(20%) 가중 합산
  const score = ((100 - hum) / 100) * 0.5 + (temp / 40) * 0.3 + (wind / 15) * 0.2;

  if (score >= 0.65) return { label: '매우 위험', level: 'very-high', desc: '즉시 경계 태세 필요' };
  if (score >= 0.45) return { label: '위험',      level: 'high',      desc: '순찰 빈도 강화 권고' };
  if (score >= 0.25) return { label: '주의',      level: 'medium',    desc: '예방 점검 필요' };
  return               { label: '낮음',           level: 'low',       desc: '정상 순찰 유지' };
}

function renderWeather(data) {
  const ptyLabel = { '0':'없음','1':'비','2':'비/눈','3':'눈','5':'빗방울','6':'빗방울눈','7':'눈날림' };
  const ptyIcon  = { '0':'☀️','1':'🌧️','2':'🌨️','3':'❄️','5':'🌦️','6':'🌨️','7':'🌨️' };

  const temp = parseFloat(data.T1H || 0).toFixed(1);
  const hum  = data.REH || '--';
  const wind = parseFloat(data.WSD || 0).toFixed(1);
  const wdir = getWindDir(data.VEC || 0);
  const rain = data.RN1 || '0';
  const pty  = data.PTY || '0';

  document.getElementById('weather-grid').innerHTML = `
    <div class="weather-item">
      <span class="weather-label">🌡️ 기온</span>
      <span class="weather-value">${temp}°C</span>
    </div>
    <div class="weather-item">
      <span class="weather-label">💧 습도</span>
      <span class="weather-value">${hum}%</span>
    </div>
    <div class="weather-item">
      <span class="weather-label">💨 풍속</span>
      <span class="weather-value">${wind} m/s</span>
    </div>
    <div class="weather-item">
      <span class="weather-label">🧭 풍향</span>
      <span class="weather-value">${wdir}풍</span>
    </div>
    <div class="weather-item">
      <span class="weather-label">${ptyIcon[pty] || '☀️'} 강수형태</span>
      <span class="weather-value">${ptyLabel[pty] || '없음'}</span>
    </div>
    <div class="weather-item">
      <span class="weather-label">🌧️ 강수량</span>
      <span class="weather-value">${rain} mm</span>
    </div>
  `;

  const fwi = calcFireWeatherIndex(data);
  const fwiStyle = {
    'very-high': { bg: 'rgba(255,51,51,0.15)',  border: '#ff3333', color: '#ff6666' },
    'high':      { bg: 'rgba(255,140,0,0.15)',  border: '#ff8c00', color: '#ffaa33' },
    'medium':    { bg: 'rgba(255,195,0,0.15)',  border: '#ffc300', color: '#ffd633' },
    'low':       { bg: 'rgba(0,180,80,0.10)',   border: '#00b450', color: '#33cc77' },
  };
  const s = fwiStyle[fwi.level];

  document.getElementById('fire-weather-index').innerHTML = `
    <div class="fwi-box" style="background:${s.bg};border-color:${s.border}">
      <span class="fwi-label">🔥 화재 위험 기상 지수</span>
      <span class="fwi-value" style="color:${s.color}">${fwi.label}</span>
      <span class="fwi-desc">${fwi.desc}</span>
    </div>
  `;
  updateSummaryCards();
}

// ===== TIMELINE & UI =====
function updateTimePeriod(period) {
  timePeriod = period;
  document.querySelectorAll('.time-tab').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.period === period);
  });
  renderGridLayers();
  renderOptimalRouteLayers();
  renderOptimalRoutesSidebar();
  updateSummaryCards();
}

function onYearSlide(val) {
  selectedYear = val;
  const disp = document.getElementById('year-display');
  if (disp) disp.textContent = val;
  renderHistoricalMarkers();
  updateSummaryCards();
}

function resetTimeline() {
  selectedYear = 0;
  const slider = document.getElementById('year-slider');
  if (slider) slider.value = slider.max;
  const disp = document.getElementById('year-display');
  if (disp) disp.textContent = '전체';
  renderHistoricalMarkers();
  updateSummaryCards();
}

function toggleAnimation() {
  if (playInterval !== null) {
    stopAnimation();
  } else {
    startAnimation();
  }
}

function startAnimation() {
  const btn = document.getElementById('play-btn');
  if (btn) btn.textContent = '⏸ 정지';
  playYear = 2018;
  (function step() {
    const slider = document.getElementById('year-slider');
    if (slider) slider.value = playYear;
    const disp = document.getElementById('year-display');
    if (disp) disp.textContent = playYear;
    selectedYear = playYear;
    renderHistoricalMarkers();
    updateSummaryCards();
    if (playYear < 2024) {
      playYear++;
      playInterval = setTimeout(step, 1500);
    } else {
      playInterval = null;
      const b = document.getElementById('play-btn');
      if (b) b.textContent = '▶ 재생';
    }
  })();
}

function stopAnimation() {
  if (playInterval !== null) { clearTimeout(playInterval); playInterval = null; }
  const btn = document.getElementById('play-btn');
  if (btn) btn.textContent = '▶ 재생';
}

function updateSummaryCards() {
  const fireCount = selectedYear > 0
    ? historyData.filter(f => f.year === selectedYear).length
    : historyData.length;
  const statFire = document.getElementById('stat-fire-history');
  if (statFire) statFire.textContent = fireCount ? `${fireCount}건` : '-';

  const statGrid = document.getElementById('stat-high-grid');
  if (statGrid) statGrid.textContent = gridData ? `${gridData.level_counts.HIGH}개` : '-';

  const statWeather = document.getElementById('stat-weather-risk');
  if (statWeather) {
    const fwiEl = document.querySelector('#fire-weather-index .fwi-value');
    statWeather.textContent = fwiEl ? fwiEl.textContent : '-';
  }

  const statPatrol = document.getElementById('stat-patrol-coverage');
  if (statPatrol) {
    if (optimalRoutes) {
      const totalKm = optimalRoutes.guards.reduce((s, g) => s + g.total_distance_km, 0);
      statPatrol.textContent = `${totalKm.toFixed(0)}km`;
    } else {
      statPatrol.textContent = '-';
    }
  }
}

function toggleSidebar() {
  const sidebar = document.getElementById('sidebar');
  if (sidebar) sidebar.classList.toggle('open');
}

// ===== INIT =====
fetchGridData();       // 격자는 가장 먼저 — 다른 마커 아래에 표시
renderRouteList();
renderRoutes();
fetchFireData();
fetchHistoricalData();
fetchWeatherData();
fetchAIPrediction();
fetchOptimalRoutes();
updateSummaryCards();
