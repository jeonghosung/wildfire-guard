"""
화성시 5km×5km 격자 위험도 매핑 v2
- 입력:
  · public/data/predicted_risk.json  (AI 예측 — 시간대별 포함)
  · public/data/forest_risk.json     (산불위험예보, 선택)
- 격자별 시간대(오전/오후/야간) 위험도 분리 집계
- 산불위험예보지수(forest_danger_grade)를 복합 위험도에 반영
- 출력: public/data/grid_risk.json
"""

import json
import math
import os
from collections import Counter
from datetime import datetime

# ===== 경로 설정 =====
BASE_DIR         = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRED_PATH        = os.path.join(BASE_DIR, 'public', 'data', 'predicted_risk.json')
FOREST_RISK_PATH = os.path.join(BASE_DIR, 'public', 'data', 'forest_risk.json')
OUTPUT_PATH      = os.path.join(BASE_DIR, 'public', 'data', 'grid_risk.json')

# ===== 격자 파라미터 =====
LAT_MIN, LAT_MAX = 36.95, 37.45
LNG_MIN, LNG_MAX = 126.55, 127.15
LAT_STEP  = round(5 / 111.0,  4)   # ≈ 0.0450°
LNG_STEP  = round(5 / 88.7,   4)   # ≈ 0.0564°
GRID_SIZE_KM = 5

# ===== 위험도 임계값 =====
THRESH_HIGH   = 0.20
THRESH_MEDIUM = 0.10

# 시간대 이름
TIME_PERIODS = ['AM', 'PM', 'NIGHT']

# 산불위험예보 등급 → 격자 위험도 보정 계수
# 등급 높을수록 복합 위험도를 높게 보정
FOREST_GRADE_MULT = {0: 1.0, 1: 1.0, 2: 1.08, 3: 1.18, 4: 1.30, 5: 1.45}

# ===== 데이터 로드 =====
with open(PRED_PATH, 'r', encoding='utf-8') as f:
    pred_data = json.load(f)

predictions = pred_data['predictions']

# 산불위험예보 (선택)
forest_danger_grade = 0
forest_overall_label = '없음'
if os.path.exists(FOREST_RISK_PATH):
    with open(FOREST_RISK_PATH, 'r', encoding='utf-8') as f:
        fr = json.load(f)
    grades = [item.get('danger_grade', 0) for item in fr.get('forecasts', [])]
    forest_danger_grade  = max(grades) if grades else 0
    forest_overall_label = fr.get('overall_label', '없음')
    print(f"산불위험예보 로드: {forest_danger_grade}등급 · {forest_overall_label}")
else:
    print("forest_risk.json 없음 — 보정 계수 1.0 적용")

forest_mult = FOREST_GRADE_MULT.get(forest_danger_grade, 1.0)
print(f"격자 보정 계수: ×{forest_mult}")

# ===== 격자 생성 =====
n_lat = math.ceil((LAT_MAX - LAT_MIN) / LAT_STEP)
n_lng = math.ceil((LNG_MAX - LNG_MIN) / LNG_STEP)
print(f"격자 분할: {n_lat}행 × {n_lng}열 = {n_lat * n_lng}개 셀")

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
            # 축적 버퍼
            '_ai_probs':    [],
            '_hist_scores': [],
            '_waypoints':   [],
            '_causes':      [],
            '_prob_am':     [],
            '_prob_pm':     [],
            '_prob_night':  [],
        }

# ===== 예측 데이터 → 격자 할당 =====
DEFAULT_LAT, DEFAULT_LNG = 37.1996, 126.8312
assigned = 0

for pred in predictions:
    lat, lng = pred['lat'], pred['lng']
    if abs(lat - DEFAULT_LAT) < 0.0001 and abs(lng - DEFAULT_LNG) < 0.0001:
        continue
    if not (LAT_MIN <= lat < LAT_MAX and LNG_MIN <= lng < LNG_MAX):
        continue

    i = max(0, min(int((lat - LAT_MIN) / LAT_STEP), n_lat - 1))
    j = max(0, min(int((lng - LNG_MIN) / LNG_STEP), n_lng - 1))
    gid = f"g_{i}_{j}"

    cells[gid]['_ai_probs'].append(pred['probability'])
    cells[gid]['_hist_scores'].append(pred.get('hist_score', 0))
    cells[gid]['_waypoints'].append(pred['dong'])
    if pred.get('top_cause'):
        cells[gid]['_causes'].append(pred['top_cause'])

    # 시간대별 확률 — v2 predicted_risk.json에만 존재
    cells[gid]['_prob_am'].append(pred.get('prob_am',    pred['probability'] * 0.80))
    cells[gid]['_prob_pm'].append(pred.get('prob_pm',    pred['probability'] * 1.40))
    cells[gid]['_prob_night'].append(pred.get('prob_night', pred['probability'] * 0.50))
    assigned += 1

print(f"읍면동 격자 할당: {assigned}개 → "
      f"{sum(1 for c in cells.values() if c['_ai_probs'])}개 셀 활성")


# ===== 셀별 위험도 계산 =====
def _avg(lst: list) -> float:
    return sum(lst) / len(lst) if lst else 0.0

def _level(combined: float) -> str:
    if   combined >= THRESH_HIGH:   return 'HIGH'
    elif combined >= THRESH_MEDIUM: return 'MEDIUM'
    elif combined > 0:              return 'LOW'
    return 'NONE'

result_cells = []
level_counts = {'HIGH': 0, 'MEDIUM': 0, 'LOW': 0, 'NONE': 0}

for gid, cell in cells.items():
    ai_probs    = cell['_ai_probs']
    hist_scores = cell['_hist_scores']

    ai_risk   = _avg(ai_probs)
    hist_risk = _avg(hist_scores)

    # 기본 복합 점수 (AI 60% + 이력 40%)
    raw_combined = (0.6 * ai_risk + 0.4 * hist_risk) if ai_probs else 0.0

    # 산불위험예보 보정 — 등급 높을수록 위험도 상향
    combined = round(min(1.0, raw_combined * forest_mult), 4)

    # 시간대별 위험도
    am_risk    = _avg(cell['_prob_am'])    if ai_probs else 0.0
    pm_risk    = _avg(cell['_prob_pm'])    if ai_probs else 0.0
    night_risk = _avg(cell['_prob_night']) if ai_probs else 0.0

    # 시간대에도 같은 보정 계수 적용
    am_combined    = round(min(1.0, am_risk    * forest_mult), 4)
    pm_combined    = round(min(1.0, pm_risk    * forest_mult), 4)
    night_combined = round(min(1.0, night_risk * forest_mult), 4)

    level = _level(combined)
    level_counts[level] += 1

    waypoints = cell['_waypoints']
    causes    = cell['_causes']
    top_cause = Counter(causes).most_common(1)[0][0] if causes else None

    result_cells.append({
        'grid_id':       gid,
        'row':           cell['row'],
        'col':           cell['col'],
        'lat_min':       cell['lat_min'],
        'lat_max':       cell['lat_max'],
        'lng_min':       cell['lng_min'],
        'lng_max':       cell['lng_max'],
        'center_lat':    cell['center_lat'],
        'center_lng':    cell['center_lng'],
        # 전체
        'ai_risk':       round(ai_risk,   3),
        'hist_risk':     round(hist_risk, 3),
        'combined_risk': combined,
        'level':         level,
        # 시간대별
        'risk_am':       am_combined,
        'risk_pm':       pm_combined,
        'risk_night':    night_combined,
        'level_am':      _level(am_combined),
        'level_pm':      _level(pm_combined),
        'level_night':   _level(night_combined),
        # 메타
        'waypoint_count': len(waypoints),
        'waypoints':      waypoints[:6],
        'top_cause':      top_cause,
        'forest_mult':    forest_mult,
    })

result_cells.sort(key=lambda c: (c['row'], c['col']))

# ===== 시간대별 레벨 집계 =====
time_level_counts = {
    period: {'HIGH': 0, 'MEDIUM': 0, 'LOW': 0, 'NONE': 0}
    for period in TIME_PERIODS
}
for c in result_cells:
    for period, key in [('AM', 'level_am'), ('PM', 'level_pm'), ('NIGHT', 'level_night')]:
        lv = c[key]
        time_level_counts[period][lv] += 1

# ===== 저장 =====
output = {
    'timestamp':       datetime.now().isoformat(),
    'grid_size_km':    GRID_SIZE_KM,
    'lat_step':        LAT_STEP,
    'lng_step':        LNG_STEP,
    'bounds': {
        'lat_min': LAT_MIN, 'lat_max': LAT_MAX,
        'lng_min': LNG_MIN, 'lng_max': LNG_MAX,
    },
    'grid_shape':      {'n_lat': n_lat, 'n_lng': n_lng},
    'grid_count':      len(result_cells),
    'level_counts':    level_counts,
    'time_level_counts': time_level_counts,
    'forest_danger_grade':  forest_danger_grade,
    'forest_overall_label': forest_overall_label,
    'forest_mult':     forest_mult,
    'cells':           result_cells,
}

with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f"\n격자 저장 완료 → {OUTPUT_PATH}")
print(f"  전체:   HIGH {level_counts['HIGH']} / MEDIUM {level_counts['MEDIUM']} "
      f"/ LOW {level_counts['LOW']} / NONE {level_counts['NONE']}")
for period in TIME_PERIODS:
    lc = time_level_counts[period]
    label = {'AM': '오전', 'PM': '오후', 'NIGHT': '야간'}[period]
    print(f"  {label}:   HIGH {lc['HIGH']} / MEDIUM {lc['MEDIUM']} / LOW {lc['LOW']}")
