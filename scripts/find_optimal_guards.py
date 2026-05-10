#!/usr/bin/env python3
"""
화성시 최적 감시요원 인원 수 분석 스크립트
- 전체 시뮬레이션: predicted_risk.json 상위 24개 지점, 요원 수 1~8명 (전역 추천)
- HIGH 지역 수별 시뮬레이션: HIGH 0~15개 각각에 대해 K-Means + 엘보우 → 룩업테이블 구축
- 출력: public/data/optimal_guard_count.json
  {
    recommended_guards: 3,          ← 전역 추천
    high_count_table: {
      high_0: 1, high_1: 1, ..., high_15: 6
    },
    ...
  }
- optimize_routes.py가 실제 HIGH 개수로 룩업테이블을 조회해 NUM_GUARDS 결정
"""

import json
import math
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from optimize_routes import (
    haversine, _kmeans, greedy_tsp,
    PATROL_SPEED_KPH, STOP_MIN, ROAD_FACTOR, WAYPOINTS_TOTAL,
)

# ===== CONFIG =====
BASE_DIR    = Path(__file__).parent.parent
RISK_PATH   = BASE_DIR / 'public' / 'data' / 'predicted_risk.json'
OUTPUT_PATH = BASE_DIR / 'public' / 'data' / 'optimal_guard_count.json'

MIN_GUARDS   = 1
MAX_GUARDS   = 8
TOP_N        = WAYPOINTS_TOTAL   # 전역 시뮬레이션용 (optimize_routes.py와 동일)
MAX_HIGH_SIM = 15                # HIGH 지역 수 시뮬레이션 상한

KST         = timezone(timedelta(hours=9))
DEFAULT_LAT = 37.1996
DEFAULT_LNG = 126.8312


# ===== SIMULATION =====

def simulate_guards(predictions: list, k: int) -> dict:
    """k명 요원 시뮬레이션 → 거리·시간·균등도·inertia 반환."""
    n      = len(predictions)
    points = [[p['lat'], p['lng']] for p in predictions]
    scores = [p['probability'] for p in predictions]

    labels = _kmeans(points, k, weights=scores, seed=42) if k > 1 else [0] * n

    clusters = [[] for _ in range(k)]
    for i, lbl in enumerate(labels):
        clusters[lbl].append(predictions[i])

    total_dist    = 0.0
    max_hours     = 0.0
    cluster_risks = []
    inertia       = 0.0

    for cluster in clusters:
        if not cluster:
            cluster_risks.append(0.0)
            continue

        c_scores = [p['probability'] for p in cluster]
        order    = greedy_tsp(cluster, c_scores)
        ordered  = [cluster[i] for i in order]

        dist = sum(
            haversine(ordered[i-1]['lat'], ordered[i-1]['lng'],
                      ordered[i]['lat'],   ordered[i]['lng']) * ROAD_FACTOR
            for i in range(1, len(ordered))
        )
        total_dist += dist
        hours = dist / PATROL_SPEED_KPH + len(ordered) * (STOP_MIN / 60)
        max_hours = max(max_hours, hours)
        cluster_risks.append(sum(c_scores))

        cen_lat = sum(p['lat'] for p in cluster) / len(cluster)
        cen_lng = sum(p['lng'] for p in cluster) / len(cluster)
        inertia += sum(haversine(p['lat'], p['lng'], cen_lat, cen_lng) ** 2
                       for p in cluster)

    active = [r for r in cluster_risks if r > 0]
    if len(active) >= 2:
        mean_r = sum(active) / len(active)
        std_r  = math.sqrt(sum((r - mean_r) ** 2 for r in active) / len(active))
        coverage_balance = round(max(0.0, 1.0 - std_r / (mean_r + 1e-9)), 4)
    else:
        coverage_balance = 1.0

    return {
        'num_guards':        k,
        'total_distance_km': round(total_dist, 2),
        'max_patrol_hours':  round(max_hours, 2),
        'coverage_balance':  coverage_balance,
        'inertia':           round(inertia, 4),
    }


# ===== ELBOW DETECTION =====

def find_elbow(results: list) -> int:
    """
    Kneedle 변형: inertia 곡선의 기준선(첫점→끝점)에서 수직 거리 최대 지점.
    결과가 2개일 때: inertia 감소율 40% 이상이면 k=2, 미만이면 k=1.
    """
    n = len(results)
    if n == 0:
        return 1
    if n == 1:
        return results[0]['num_guards']
    if n == 2:
        i0, i1 = results[0]['inertia'], results[1]['inertia']
        reduction = (i0 - i1) / (i0 + 1e-9)
        return results[1]['num_guards'] if reduction >= 0.40 else results[0]['num_guards']

    inertias = [r['inertia'] for r in results]
    ks       = [r['num_guards'] for r in results]
    i_min, i_max = min(inertias), max(inertias)
    k_min, k_max = ks[0], ks[-1]

    if i_max == i_min or k_max == k_min:
        return results[0]['num_guards']

    norm_k = [(k - k_min) / (k_max - k_min) for k in ks]
    norm_i = [(iv - i_min) / (i_max - i_min) for iv in inertias]

    distances = [abs(norm_k[i] + norm_i[i] - 1) / math.sqrt(2) for i in range(n)]
    return results[distances.index(max(distances))]['num_guards']


# ===== EFFICIENCY SCORING =====

def compute_efficiency(results: list) -> list:
    """거리·시간 단축 + 군집화 품질 기반 효율 점수 산출."""
    d_max = max(r['total_distance_km'] for r in results) or 1.0
    h_max = max(r['max_patrol_hours']  for r in results) or 1.0
    i_max = max(r['inertia']           for r in results) or 1.0

    enriched = []
    for r in results:
        dist_score    = 1.0 - r['total_distance_km'] / d_max
        hours_score   = 1.0 - r['max_patrol_hours']  / h_max
        inertia_norm  = r['inertia'] / i_max
        cluster_score = 1.0 - inertia_norm

        perf       = dist_score * 0.35 + hours_score * 0.30 + cluster_score * 0.35
        cost       = r['num_guards'] / MAX_GUARDS + 0.05
        efficiency = round(perf / cost, 4)

        enriched.append({
            **r,
            'inertia_normalized': round(inertia_norm, 4),
            'efficiency_score':   efficiency,
        })
    return enriched


# ===== HIGH-COUNT 룩업테이블 =====

def find_optimal_for_high_n(valid_preds: list, n_high: int) -> int:
    """
    n_high개 HIGH 지역이 있을 때 최적 요원 수를 K-Means + 엘보우로 도출.
    - 순찰 지점 = 상위 n_high개 지점
    - 요원 수 상한: n_high // 2 (요원 1인당 최소 2개 지점 보장, 과도 세분화 방지)
    """
    if n_high <= 1:
        return 1

    pts   = valid_preds[:n_high]
    max_k = min(MAX_GUARDS, max(1, n_high // 2))

    if max_k < 2:
        return 1

    results = [simulate_guards(pts, k) for k in range(1, max_k + 1)]
    return find_elbow(results)


# ===== MAIN =====

def main():
    print('=' * 62)
    print('최적 감시요원 인원 수 분석 (엘보우 기법)')
    print('=' * 62)

    with open(RISK_PATH, 'r', encoding='utf-8') as f:
        risk_data = json.load(f)

    predictions  = risk_data['predictions']
    actual_high  = risk_data.get('summary', {}).get('high_risk', 0)
    print(f'AI 예측 읍면동: {len(predictions)}개  (현재 HIGH: {actual_high}개)')

    # 기본 좌표 필터 후 확률 내림차순 정렬
    valid = [
        p for p in predictions
        if not (abs(p['lat'] - DEFAULT_LAT) < 0.0001
                and abs(p['lng'] - DEFAULT_LNG) < 0.0001)
    ]
    valid.sort(key=lambda p: p['probability'], reverse=True)

    # ── ① 전역 시뮬레이션 (상위 TOP_N 지점, k=1~8) ──────────────────
    top = valid[:TOP_N]
    print(f'\n[1] 전역 시뮬레이션 — 상위 {len(top)}개 지점, k=1~{MAX_GUARDS}명')
    print(f'{"요원":>4}  {"총거리(km)":>10}  {"최대시간(h)":>11}  {"균등도":>8}  {"Inertia":>10}')
    print('-' * 62)

    global_results = []
    for k in range(MIN_GUARDS, MAX_GUARDS + 1):
        r = simulate_guards(top, k)
        global_results.append(r)
        print(f'  {k:>2}명  {r["total_distance_km"]:>10.1f}  '
              f'{r["max_patrol_hours"]:>11.2f}  '
              f'{r["coverage_balance"]:>8.4f}  '
              f'{r["inertia"]:>10.2f}')

    enriched   = compute_efficiency(global_results)
    elbow_k    = find_elbow(global_results)
    best_eff_k = max(enriched, key=lambda r: r['efficiency_score'])['num_guards']
    recommended = elbow_k

    print(f'\n  엘보우 포인트  : {elbow_k}명')
    print(f'  효율 최고      : {best_eff_k}명')
    print(f'  ✅ 전역 추천   : {recommended}명')

    # ── ② HIGH 개수별 룩업테이블 (n_high=0~MAX_HIGH_SIM) ─────────────
    # 화성시 지리적 3개 권역: 서부 해안권 / 중부 내륙권 / 동부 도시권
    # → 권역별 최소 1명 배치 필요 → 최소 3명 보장
    print(f'\n[2] HIGH 지역 수별 최적 요원 수 시뮬레이션 (0~{MAX_HIGH_SIM}개)')
    print(f'    화성시 서부 해안권 / 중부 내륙권 / 동부 도시권'
          f' → 지리적 3개 권역으로 최소 3명 필요')
    print(f'{"HIGH":>6}  {"최적요원":>8}  {"순찰지점":>8}  {"max_k":>6}')
    print('-' * 40)

    # 1단계: 엘보우 원시 결과 수집
    raw_table: dict[str, int] = {}
    for n_high in range(0, MAX_HIGH_SIM + 1):
        raw_table[f'high_{n_high}'] = find_optimal_for_high_n(valid, n_high)

    # 2단계: 최소 3명 보장 (서부·중부·동부 권역 각 1명)
    high_count_table: dict[str, int] = {
        k: max(3, v) for k, v in raw_table.items()
    }

    # 3단계: 스무딩 — 이전 값보다 2명 이상 점프 시 1명씩 증가로 보정
    smoothed_log: list = []
    prev_val = high_count_table['high_0']
    for n_high in range(1, MAX_HIGH_SIM + 1):
        key = f'high_{n_high}'
        cur = high_count_table[key]
        if cur - prev_val >= 2:
            high_count_table[key] = prev_val + 1
            smoothed_log.append((n_high, cur, prev_val + 1))
        prev_val = high_count_table[key]

    # 출력 (최종 확정값 기준)
    for n_high in range(0, MAX_HIGH_SIM + 1):
        key      = f'high_{n_high}'
        opt_k    = high_count_table[key]
        raw_k    = raw_table[key]
        pts_used = min(n_high, len(valid))
        max_k    = min(MAX_GUARDS, max(1, n_high // 2)) if n_high >= 2 else 1
        mark     = ' ◀ 현재' if n_high == actual_high else ''
        note     = f' (원:{raw_k}→min3)' if raw_k < 3 else ''
        print(f'  {n_high:>3}개  →  {opt_k:>3}명  ({pts_used:>3}개 지점, max_k={max_k}){note}{mark}')

    if smoothed_log:
        print('\n  [스무딩 적용] ' +
              ', '.join(f'high_{n}: {old}→{new}' for n, old, new in smoothed_log))

    # ── ③ 효율 점수 바 차트 ──────────────────────────────────────────
    print(f'\n[3] 전역 효율 점수:')
    max_eff = max(r['efficiency_score'] for r in enriched) or 1.0
    for r in enriched:
        bar  = '█' * max(1, int(r['efficiency_score'] / max_eff * 20))
        mark = ' ← 추천' if r['num_guards'] == recommended else ''
        print(f'    {r["num_guards"]}명  {bar:<22} {r["efficiency_score"]:.4f}{mark}')

    # ── 저장 ─────────────────────────────────────────────────────────
    min_guards_reason = (
        "화성시 지리적 3개 권역 (서부 해안·중부 내륙·동부 도시) 각 1명 배치 필요 "
        "→ 최솟값 3명 보장"
    )
    output = {
        'timestamp':          datetime.now(KST).isoformat(),
        'recommended_guards': recommended,
        'elbow_point':        elbow_k,
        'best_efficiency_k':  best_eff_k,
        'top_n_analyzed':     len(top),
        'min_guards':         3,
        'min_guards_reason':  min_guards_reason,
        'high_count_table':   high_count_table,
        'analysis':           enriched,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f'\n✅ 저장 완료: {OUTPUT_PATH}')
    looked_up = high_count_table.get(f'high_{actual_high}', recommended)
    print(f'   현재 HIGH {actual_high}개 → 룩업 결과 {looked_up}명'
          f'  (전역 추천 {recommended}명)')
    print(f'   optimize_routes.py 실행 시 NUM_GUARDS={looked_up} 자동 적용')


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f'❌ 분석 실패: {e}', file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
