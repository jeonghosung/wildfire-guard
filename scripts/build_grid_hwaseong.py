"""
화성시 5km×5km 격자 위험도 매핑
- 화성시 경계를 0.045° × 0.056° 격자(≈5km×5km)로 분할
- AI 예측 위험도 + 산불 이력 점수를 격자별로 집계
- 출력: public/data/grid_risk.json
참고: 2blackcow/Wildfire build_and_grid_train_data.py (격자 ID 체계)
"""

import json
import math
import os
from collections import Counter
from datetime import datetime

# ===== 경로 설정 =====
BASE_DIR     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRED_PATH    = os.path.join(BASE_DIR, 'public', 'data', 'predicted_risk.json')
OUTPUT_PATH  = os.path.join(BASE_DIR, 'public', 'data', 'grid_risk.json')

# ===== 격자 파라미터 =====
# 화성시 행정구역 경계 (main.js classifyRegion 기준)
LAT_MIN, LAT_MAX = 36.95, 37.45
LNG_MIN, LNG_MAX = 126.55, 127.15

# 1° ≈ 111km(위도), 88.7km(경도@37°) → 5km 셀
LAT_STEP = round(5 / 111.0,    4)   # 0.0450°
LNG_STEP = round(5 / 88.7,     4)   # 0.0564°
GRID_SIZE_KM = 5

# 위험도 임계값 (AI 예측 확률 기준)
THRESH_HIGH   = 0.20
THRESH_MEDIUM = 0.10

# ===== 데이터 로드 =====
with open(PRED_PATH, 'r', encoding='utf-8') as f:
    pred_data = json.load(f)

predictions = pred_data['predictions']

# ===== 격자 생성 (참고: assign_grid_id in build_and_grid_train_data.py) =====
n_lat = math.ceil((LAT_MAX - LAT_MIN) / LAT_STEP)
n_lng = math.ceil((LNG_MAX - LNG_MIN) / LNG_STEP)
print(f"격자 분할: {n_lat}행 × {n_lng}열 = {n_lat * n_lng}개 셀")

# 셀 초기화
cells: dict[str, dict] = {}
for i in range(n_lat):
    for j in range(n_lng):
        cell_lat_min = round(LAT_MIN + i * LAT_STEP, 4)
        cell_lat_max = round(min(cell_lat_min + LAT_STEP, LAT_MAX), 4)
        cell_lng_min = round(LNG_MIN + j * LNG_STEP, 4)
        cell_lng_max = round(min(cell_lng_min + LNG_STEP, LNG_MAX), 4)
        gid = f"g_{i}_{j}"
        cells[gid] = {
            'grid_id':    gid,
            'row':        i,
            'col':        j,
            'lat_min':    cell_lat_min,
            'lat_max':    cell_lat_max,
            'lng_min':    cell_lng_min,
            'lng_max':    cell_lng_max,
            'center_lat': round((cell_lat_min + cell_lat_max) / 2, 4),
            'center_lng': round((cell_lng_min + cell_lng_max) / 2, 4),
            '_ai_probs':    [],
            '_hist_scores': [],
            '_waypoints':   [],
            '_causes':      [],
        }

# ===== 예측 데이터 → 격자 할당 =====
default_lat, default_lng = 37.1996, 126.8312  # 좌표 없는 기본값
assigned = 0

for pred in predictions:
    lat, lng = pred['lat'], pred['lng']
    # 기본 좌표(좌표 미확인 지역) 제외
    if abs(lat - default_lat) < 0.0001 and abs(lng - default_lng) < 0.0001:
        continue
    # 화성시 경계 체크
    if not (LAT_MIN <= lat < LAT_MAX and LNG_MIN <= lng < LNG_MAX):
        continue

    i = int((lat - LAT_MIN) / LAT_STEP)
    j = int((lng - LNG_MIN) / LNG_STEP)
    i = max(0, min(i, n_lat - 1))
    j = max(0, min(j, n_lng - 1))
    gid = f"g_{i}_{j}"

    cells[gid]['_ai_probs'].append(pred['probability'])
    cells[gid]['_hist_scores'].append(pred.get('hist_score', 0))
    cells[gid]['_waypoints'].append(pred['dong'])
    if pred.get('top_cause'):
        cells[gid]['_causes'].append(pred['top_cause'])
    assigned += 1

print(f"읍면동 격자 할당: {assigned}개 → {sum(1 for c in cells.values() if c['_ai_probs'])}개 셀 활성")

# ===== 셀별 위험도 계산 =====
result_cells = []
level_counts = {'HIGH': 0, 'MEDIUM': 0, 'LOW': 0, 'NONE': 0}

for gid, cell in cells.items():
    ai_probs    = cell['_ai_probs']
    hist_scores = cell['_hist_scores']
    waypoints   = cell['_waypoints']
    causes      = cell['_causes']

    ai_risk   = sum(ai_probs)    / len(ai_probs)    if ai_probs    else 0.0
    hist_risk = sum(hist_scores) / len(hist_scores) if hist_scores else 0.0

    # AI 예측(60%) + 이력 기반(40%) 복합 점수
    combined = round(0.6 * ai_risk + 0.4 * hist_risk, 4) if ai_probs else 0.0

    if   combined >= THRESH_HIGH:   level = 'HIGH'
    elif combined >= THRESH_MEDIUM: level = 'MEDIUM'
    elif combined > 0:              level = 'LOW'
    else:                           level = 'NONE'

    level_counts[level] += 1
    top_cause = Counter(causes).most_common(1)[0][0] if causes else None

    result_cells.append({
        'grid_id':      gid,
        'row':          cell['row'],
        'col':          cell['col'],
        'lat_min':      cell['lat_min'],
        'lat_max':      cell['lat_max'],
        'lng_min':      cell['lng_min'],
        'lng_max':      cell['lng_max'],
        'center_lat':   cell['center_lat'],
        'center_lng':   cell['center_lng'],
        'ai_risk':      round(ai_risk,   3),
        'hist_risk':    round(hist_risk, 3),
        'combined_risk':combined,
        'level':        level,
        'waypoint_count': len(waypoints),
        'waypoints':    waypoints[:6],   # 팝업 표시용 최대 6개
        'top_cause':    top_cause,
    })

# row, col 순서로 정렬
result_cells.sort(key=lambda c: (c['row'], c['col']))

output = {
    'timestamp':    datetime.now().isoformat(),
    'grid_size_km': GRID_SIZE_KM,
    'lat_step':     LAT_STEP,
    'lng_step':     LNG_STEP,
    'bounds': {
        'lat_min': LAT_MIN, 'lat_max': LAT_MAX,
        'lng_min': LNG_MIN, 'lng_max': LNG_MAX,
    },
    'grid_shape':   {'n_lat': n_lat, 'n_lng': n_lng},
    'grid_count':   len(result_cells),
    'level_counts': level_counts,
    'cells':        result_cells,
}

with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f"\n격자 저장 완료 → {OUTPUT_PATH}")
print(f"  HIGH: {level_counts['HIGH']}개  MEDIUM: {level_counts['MEDIUM']}개  "
      f"LOW: {level_counts['LOW']}개  NONE: {level_counts['NONE']}개")
