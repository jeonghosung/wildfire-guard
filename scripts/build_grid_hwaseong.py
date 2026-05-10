"""
화성시 격자 위험도 매핑 v3
- STEP 4: 격자 크기 최적화 (1/2/3/5/10km 시뮬레이션 → 자동 선택)
- 시간대별(AM/PM/NIGHT) 격자 위험도 분리 집계
- 산불위험예보지수 복합 위험도 반영
입력:
  · public/data/predicted_risk.json  (AI 예측 — 시간대별 포함)
  · public/data/forest_risk.json     (산불위험예보, 선택)
출력: public/data/grid_risk.json
"""

import json
import math
import os
from collections import Counter
from datetime import datetime

# 시간대 가중치 (train_predict_hwaseong.py와 동일)
PERIOD_WEIGHT = {'AM': 0.30, 'PM': 0.50, 'NIGHT': 0.20}


def _percentile75(lst):
    """numpy 없이 75퍼센타일 계산."""
    if not lst:
        return 0.25
    s = sorted(lst)
    idx = min(int(len(s) * 0.75), len(s) - 1)
    return s[idx]

# ===== 경로 =====
BASE_DIR         = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRED_PATH        = os.path.join(BASE_DIR, 'public', 'data', 'predicted_risk.json')
FOREST_RISK_PATH = os.path.join(BASE_DIR, 'public', 'data', 'forest_risk.json')
OUTPUT_PATH      = os.path.join(BASE_DIR, 'public', 'data', 'grid_risk.json')

# 화성시 bounding box
LAT_MIN, LAT_MAX = 36.95, 37.45
LNG_MIN, LNG_MAX = 126.55, 127.15
DEFAULT_LAT, DEFAULT_LNG = 37.1996, 126.8312  # 읍면동 좌표 불명 시 폴백

# 시뮬레이션 대상 격자 크기 (km)
GRID_SIZES_KM = [1, 2, 3, 5, 10]

# 위험도 임계값
THRESH_HIGH   = 0.20
THRESH_MEDIUM = 0.10
TIME_PERIODS  = ['AM', 'PM', 'NIGHT']

# 산불위험예보 등급 → 보정 계수
FOREST_GRADE_MULT = {0: 1.0, 1: 1.0, 2: 1.08, 3: 1.18, 4: 1.30, 5: 1.45}


# ===== 데이터 로드 =====
with open(PRED_PATH, 'r', encoding='utf-8') as f:
    pred_data = json.load(f)
predictions = pred_data['predictions']

# ── 시간대별 Youden 임계값 로드 ────────────────────────────────────
period_thresholds: dict = {}
threshold_reason_loaded: dict = {}
_period_key_map = {'AM': 'am', 'PM': 'pm', 'NIGHT': 'night'}

print("[ 임계값 로드 ]")
for _p, _pk in _period_key_map.items():
    _t_high = pred_data.get(f'threshold_high_{_pk}')
    _t_med  = pred_data.get(f'threshold_medium_{_pk}')
    if _t_high is not None and _t_med is not None:
        period_thresholds[_p] = {'high': _t_high, 'medium': _t_med}
        _reason = (pred_data.get('threshold_reason') or {}).get(_p, '저장된 임계값')
        threshold_reason_loaded[_p] = _reason
        print(f"  {_p}: HIGH≥{_t_high:.4f}  MEDIUM≥{_t_med:.4f}  ({_reason[:50]})")
    else:
        # 폴백: 예측 확률 분포 75퍼센타일 기반 (절대값 사용 금지)
        _probs = [r.get(f'prob_{_pk}', r.get('probability', 0)) for r in predictions]
        _t_high = round(min(0.75, max(0.08, _percentile75(_probs))), 4)
        _t_med  = round(_t_high * 0.60, 4)
        period_thresholds[_p] = {'high': _t_high, 'medium': _t_med}
        threshold_reason_loaded[_p] = f"폴백: 예측확률 75퍼센타일({_t_high:.4f}) 기반 임계값"
        print(f"  ⚠ {_p} 임계값 미발견 → 폴백 HIGH≥{_t_high:.4f}  MEDIUM≥{_t_med:.4f}")

# 전체 가중 평균 임계값
_overall_high = round(sum(PERIOD_WEIGHT[p] * period_thresholds[p]['high']   for p in ('AM','PM','NIGHT')), 4)
_overall_med  = round(_overall_high * 0.60, 4)
print(f"  전체(가중): HIGH≥{_overall_high:.4f}  MEDIUM≥{_overall_med:.4f}")

forest_danger_grade  = 0
forest_overall_label = '없음'
if os.path.exists(FOREST_RISK_PATH):
    with open(FOREST_RISK_PATH, 'r', encoding='utf-8') as f:
        fr = json.load(f)
    if fr.get('data_available', False) and fr.get('forecasts'):
        # 새 API 형식: meanavg(0~100) 기준
        max_avg = max((fc.get('meanavg', 0) for fc in fr['forecasts']), default=0)
        if   max_avg >= 76: forest_danger_grade = 4
        elif max_avg >= 51: forest_danger_grade = 3
        elif max_avg >= 26: forest_danger_grade = 2
        else:               forest_danger_grade = 1
    else:
        # 구 형식 폴백
        grades = [item.get('danger_grade', 0) for item in fr.get('forecasts', [])]
        forest_danger_grade = max(grades) if grades else 0
    forest_overall_label = fr.get('overall_label', '없음')
    print(f"산불위험예보 로드: grade={forest_danger_grade} · {forest_overall_label}")
else:
    print("forest_risk.json 없음 — 보정 계수 1.0 적용")

forest_mult = FOREST_GRADE_MULT.get(forest_danger_grade, 1.0)
print(f"격자 보정 계수: ×{forest_mult}")


# ===== 유틸 =====
def _km_to_steps(km: float) -> tuple:
    """km → (lat_step°, lng_step°)"""
    return round(km / 111.0, 6), round(km / 88.7, 6)

def _avg(lst: list) -> float:
    return sum(lst) / len(lst) if lst else 0.0

def _level(v: float, t_high: float = None, t_med: float = None) -> str:
    th = t_high if t_high is not None else _overall_high
    tm = t_med  if t_med  is not None else _overall_med
    if   v >= th: return 'HIGH'
    elif v >= tm: return 'MEDIUM'
    elif v > 0:   return 'LOW'
    return 'NONE'

def _is_default(pred: dict) -> bool:
    return (abs(pred['lat'] - DEFAULT_LAT) < 0.0001
            and abs(pred['lng'] - DEFAULT_LNG) < 0.0001)


# ===== STEP 4: 격자 크기 시뮬레이션 =====

def simulate_size(km: float) -> dict:
    """km 크기 격자를 시뮬레이션하고 평가 지표 + 점수를 반환한다."""
    lat_step, lng_step = _km_to_steps(km)
    n_lat = math.ceil((LAT_MAX - LAT_MIN) / lat_step)
    n_lng = math.ceil((LNG_MAX - LNG_MIN) / lng_step)
    total_cells = n_lat * n_lng

    cell_dongs: dict = {}
    for pred in predictions:
        if _is_default(pred):
            continue
        lat, lng = pred['lat'], pred['lng']
        if not (LAT_MIN <= lat < LAT_MAX and LNG_MIN <= lng < LNG_MAX):
            continue
        i = min(int((lat - LAT_MIN) / lat_step), n_lat - 1)
        j = min(int((lng - LNG_MIN) / lng_step), n_lng - 1)
        cell_dongs.setdefault(f"{i}_{j}", set()).add(pred['dong'])

    active_cells = len(cell_dongs)
    all_dongs    = {p['dong'] for p in predictions if not _is_default(p)}
    covered_dongs = set()
    for dset in cell_dongs.values():
        covered_dongs |= dset

    coverage_rate = len(covered_dongs) / len(all_dongs) if all_dongs else 0.0
    empty_ratio   = 1.0 - (active_cells / total_cells) if total_cells > 0 else 1.0
    avg_dongs     = (sum(len(d) for d in cell_dongs.values()) / active_cells
                     if active_cells > 0 else 0.0)

    # ── 점수 계산 ──
    # 커버율 (40%): 높을수록 좋음
    cov_s = coverage_rate

    # 읍면동 밀도 (30%): 1~3개/셀 적정
    if 1.0 <= avg_dongs <= 3.0:
        dens_s = 1.0
    elif avg_dongs < 1.0:
        dens_s = avg_dongs
    else:
        dens_s = max(0.0, 1.0 - (avg_dongs - 3.0) / 6.0)  # avg=9 → 0

    # 빈 격자 비율 (15%): 낮을수록 좋음
    empty_s = 1.0 - empty_ratio

    # 시각적 복잡도 (15%): 활성 격자 10~25개 이상적
    if 10 <= active_cells <= 25:
        comp_s = 1.0
    elif active_cells < 10:
        comp_s = active_cells / 10.0
    else:
        comp_s = max(0.0, 1.0 - (active_cells - 25) / 75.0)

    score = 0.40 * cov_s + 0.30 * dens_s + 0.15 * empty_s + 0.15 * comp_s

    return {
        'size_km':                    km,
        'total_cells':                total_cells,
        'active_cells':               active_cells,
        'covered_dongs':              len(covered_dongs),
        'total_dongs':                len(all_dongs),
        'coverage_rate':              round(coverage_rate, 3),
        'empty_ratio':                round(empty_ratio, 3),
        'avg_dongs_per_active_cell':  round(avg_dongs, 2),
        'score':                      round(score, 3),
    }


print('\n=== STEP 4: 격자 크기 최적화 시뮬레이션 ===')
size_analysis = []
for km in GRID_SIZES_KM:
    m = simulate_size(km)
    size_analysis.append(m)
    print(f"  {km:>2}km: 총={m['total_cells']:>5}셀  활성={m['active_cells']:>3}  "
          f"커버={m['coverage_rate']*100:.0f}%  빈격자={m['empty_ratio']*100:.0f}%  "
          f"평균밀도={m['avg_dongs_per_active_cell']:.1f}개/셀  점수={m['score']:.3f}")

best_m      = max(size_analysis, key=lambda x: x['score'])
GRID_SIZE_KM = best_m['size_km']
LAT_STEP, LNG_STEP = _km_to_steps(GRID_SIZE_KM)
grid_size_reason = (
    f"{GRID_SIZE_KM}km 선택: 커버율 {best_m['coverage_rate']*100:.0f}%, "
    f"격자당 평균 {best_m['avg_dongs_per_active_cell']:.1f}개 읍면동, "
    f"빈 격자 {best_m['empty_ratio']*100:.0f}%, "
    f"활성 격자 {best_m['active_cells']}개 (종합점수 {best_m['score']:.3f})"
)
print(f'\n→ 최적 격자: {GRID_SIZE_KM}km  [{grid_size_reason}]')


# ===== 격자 생성 =====
n_lat = math.ceil((LAT_MAX - LAT_MIN) / LAT_STEP)
n_lng = math.ceil((LNG_MAX - LNG_MIN) / LNG_STEP)
print(f'격자 분할: {n_lat}행 × {n_lng}열 = {n_lat * n_lng}개 셀')

cells: dict = {}
for i in range(n_lat):
    for j in range(n_lng):
        cll = round(LAT_MIN + i * LAT_STEP, 5)
        clu = round(min(cll + LAT_STEP, LAT_MAX), 5)
        crl = round(LNG_MIN + j * LNG_STEP, 5)
        cru = round(min(crl + LNG_STEP, LNG_MAX), 5)
        gid = f'g_{i}_{j}'
        cells[gid] = {
            'grid_id':    gid, 'row': i, 'col': j,
            'lat_min':    cll, 'lat_max': clu,
            'lng_min':    crl, 'lng_max': cru,
            'center_lat': round((cll + clu) / 2, 5),
            'center_lng': round((crl + cru) / 2, 5),
            '_ai_probs':    [], '_hist_scores': [], '_waypoints': [],
            '_causes':      [], '_prob_am':     [],
            '_prob_pm':     [], '_prob_night':  [],
        }


# ===== 예측 데이터 → 격자 할당 =====
assigned = 0
for pred in predictions:
    if _is_default(pred):
        continue
    lat, lng = pred['lat'], pred['lng']
    if not (LAT_MIN <= lat < LAT_MAX and LNG_MIN <= lng < LNG_MAX):
        continue

    i = max(0, min(int((lat - LAT_MIN) / LAT_STEP), n_lat - 1))
    j = max(0, min(int((lng - LNG_MIN) / LNG_STEP), n_lng - 1))
    gid = f'g_{i}_{j}'

    cells[gid]['_ai_probs'].append(pred['probability'])
    cells[gid]['_hist_scores'].append(pred.get('hist_score', 0))
    cells[gid]['_waypoints'].append(pred['dong'])
    if pred.get('top_cause'):
        cells[gid]['_causes'].append(pred['top_cause'])

    cells[gid]['_prob_am'].append(   pred.get('prob_am',    pred['probability'] * 0.80))
    cells[gid]['_prob_pm'].append(   pred.get('prob_pm',    pred['probability'] * 1.40))
    cells[gid]['_prob_night'].append(pred.get('prob_night', pred['probability'] * 0.50))
    assigned += 1

print(f'읍면동 격자 할당: {assigned}개 → '
      f'{sum(1 for c in cells.values() if c["_ai_probs"])}개 셀 활성')


# ===== 셀별 위험도 계산 =====
result_cells = []
level_counts = {'HIGH': 0, 'MEDIUM': 0, 'LOW': 0, 'NONE': 0}

for gid, cell in cells.items():
    ai_probs  = cell['_ai_probs']
    hist_sc   = cell['_hist_scores']

    ai_risk   = _avg(ai_probs)
    hist_risk = _avg(hist_sc)
    raw_comb  = (0.6 * ai_risk + 0.4 * hist_risk) if ai_probs else 0.0
    combined  = round(min(1.0, raw_comb * forest_mult), 4)

    am_r    = round(min(1.0, _avg(cell['_prob_am'])    * forest_mult), 4) if ai_probs else 0.0
    pm_r    = round(min(1.0, _avg(cell['_prob_pm'])    * forest_mult), 4) if ai_probs else 0.0
    night_r = round(min(1.0, _avg(cell['_prob_night']) * forest_mult), 4) if ai_probs else 0.0

    level = _level(combined)
    level_counts[level] += 1

    waypoints = cell['_waypoints']
    causes    = cell['_causes']
    top_cause = Counter(causes).most_common(1)[0][0] if causes else None

    _am_th  = period_thresholds['AM']
    _pm_th  = period_thresholds['PM']
    _ni_th  = period_thresholds['NIGHT']

    result_cells.append({
        'grid_id':    gid,
        'row':        cell['row'],
        'col':        cell['col'],
        'lat_min':    cell['lat_min'],
        'lat_max':    cell['lat_max'],
        'lng_min':    cell['lng_min'],
        'lng_max':    cell['lng_max'],
        'center_lat': cell['center_lat'],
        'center_lng': cell['center_lng'],
        # 전체
        'ai_risk':       round(ai_risk,   3),
        'hist_risk':     round(hist_risk, 3),
        'combined_risk': combined,
        'level':         level,
        # 시간대별 (각 시간대 임계값으로 독립 판정)
        'risk_am':    am_r,    'level_am':    _level(am_r,    _am_th['high'], _am_th['medium']),
        'risk_pm':    pm_r,    'level_pm':    _level(pm_r,    _pm_th['high'], _pm_th['medium']),
        'risk_night': night_r, 'level_night': _level(night_r, _ni_th['high'], _ni_th['medium']),
        # 메타
        'waypoint_count': len(waypoints),
        'waypoints':      waypoints[:6],
        'top_cause':      top_cause,
        'forest_mult':    forest_mult,
    })

result_cells.sort(key=lambda c: (c['row'], c['col']))


# ===== 시간대별 레벨 집계 =====
time_level_counts = {p: {'HIGH': 0, 'MEDIUM': 0, 'LOW': 0, 'NONE': 0}
                     for p in TIME_PERIODS}
for c in result_cells:
    for period, key in [('AM', 'level_am'), ('PM', 'level_pm'), ('NIGHT', 'level_night')]:
        time_level_counts[period][c[key]] += 1


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
    'grid_shape':        {'n_lat': n_lat, 'n_lng': n_lng},
    'grid_count':        len(result_cells),
    'level_counts':      level_counts,
    'time_level_counts': time_level_counts,
    'forest_danger_grade':  forest_danger_grade,
    'forest_overall_label': forest_overall_label,
    'forest_mult':          forest_mult,
    # 시간대별 임계값
    'period_thresholds':    period_thresholds,
    'threshold_reason':     threshold_reason_loaded,
    # STEP 4 추가 필드
    'optimal_grid_size_km': GRID_SIZE_KM,
    'grid_size_reason':     grid_size_reason,
    'grid_size_analysis':   size_analysis,
    'cells':                result_cells,
}

with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f'\n격자 저장 완료 → {OUTPUT_PATH}')
print(f'  선택 격자: {GRID_SIZE_KM}km')
print(f'  전체: HIGH {level_counts["HIGH"]} / MEDIUM {level_counts["MEDIUM"]} '
      f'/ LOW {level_counts["LOW"]} / NONE {level_counts["NONE"]}')
for period in TIME_PERIODS:
    lc = time_level_counts[period]
    label = {'AM': '오전', 'PM': '오후', 'NIGHT': '야간'}[period]
    print(f'  {label}: HIGH {lc["HIGH"]} / MEDIUM {lc["MEDIUM"]} / LOW {lc["LOW"]}')
print(f'\n크기별 분석:')
for m in size_analysis:
    mark = ' ← 선택' if m['size_km'] == GRID_SIZE_KM else ''
    print(f"  {m['size_km']}km: 점수={m['score']:.3f}{mark}")
