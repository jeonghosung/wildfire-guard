#!/usr/bin/env python3
"""
화성시 최적 감시요원 인원 수 분석 스크립트
- predicted_risk.json 상위 위험 지점을 대상으로 요원 수 1~8명 시뮬레이션
- 각 요원 수별: 총 이동 거리 / 최대 순찰 시간 / 커버리지 균등도 / Inertia 계산
- 엘보우 기법(Kneedle 변형)으로 최적 인원 자동 도출
- 출력: public/data/optimal_guard_count.json
- optimize_routes.py가 이 파일을 읽어 NUM_GUARDS를 자동 설정
"""

import json
import math
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# optimize_routes.py에서 공통 유틸 재사용 (ROAD_FACTOR, greedy_tsp 등)
sys.path.insert(0, str(Path(__file__).parent))
from optimize_routes import (
    haversine, _kmeans, greedy_tsp,
    PATROL_SPEED_KPH, STOP_MIN, ROAD_FACTOR, WAYPOINTS_TOTAL,
)

# ===== CONFIG =====
BASE_DIR    = Path(__file__).parent.parent
RISK_PATH   = BASE_DIR / 'public' / 'data' / 'predicted_risk.json'
OUTPUT_PATH = BASE_DIR / 'public' / 'data' / 'optimal_guard_count.json'

MIN_GUARDS = 1
MAX_GUARDS = 8
TOP_N      = WAYPOINTS_TOTAL   # optimize_routes.py와 동일한 분석 대상 수

KST             = timezone(timedelta(hours=9))
DEFAULT_LAT     = 37.1996
DEFAULT_LNG     = 126.8312


# ===== SIMULATION =====

def simulate_guards(predictions: list, k: int) -> dict:
    """
    k명 요원으로 시뮬레이션.
    반환: total_distance_km, max_patrol_hours, coverage_balance, inertia
    """
    n      = len(predictions)
    points = [[p['lat'], p['lng']] for p in predictions]
    scores = [p['probability'] for p in predictions]

    # K-Means 군집화 (k=1은 전체 하나의 클러스터)
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

        # Greedy TSP 순서 (위험도·거리 혼합 기준)
        order   = greedy_tsp(cluster, c_scores)
        ordered = [cluster[i] for i in order]

        # 총 이동 거리 (도로망 없으므로 직선 × ROAD_FACTOR)
        dist = 0.0
        for i in range(1, len(ordered)):
            dist += haversine(
                ordered[i-1]['lat'], ordered[i-1]['lng'],
                ordered[i]['lat'],   ordered[i]['lng'],
            ) * ROAD_FACTOR
        total_dist += dist

        # 최대 순찰 시간
        hours     = dist / PATROL_SPEED_KPH + len(ordered) * (STOP_MIN / 60)
        max_hours = max(max_hours, hours)

        # 요원별 담당 위험도 합
        cluster_risks.append(sum(c_scores))

        # Inertia: 클러스터 중심까지 거리 제곱합
        cen_lat = sum(p['lat'] for p in cluster) / len(cluster)
        cen_lng = sum(p['lng'] for p in cluster) / len(cluster)
        for p in cluster:
            d = haversine(p['lat'], p['lng'], cen_lat, cen_lng)
            inertia += d ** 2

    # 커버리지 균등도: 요원별 위험도 담당량의 표준편차가 낮을수록 높음
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
    Kneedle 변형: inertia 곡선에서 기준선(첫점→끝점)까지 수직 거리가 최대인 지점.
    - 첫점 (k=1, inertia=max) → 끝점 (k=MAX, inertia=min)
    - 정규화 후 선 x+y=1로부터 수직 거리 최대 위치가 엘보우
    """
    n = len(results)
    if n < 3:
        return results[-1]['num_guards'] if results else 1

    inertias = [r['inertia'] for r in results]
    ks       = [r['num_guards'] for r in results]

    i_min, i_max = min(inertias), max(inertias)
    k_min, k_max = ks[0], ks[-1]

    if i_max == i_min or k_max == k_min:
        return results[0]['num_guards']

    norm_k = [(k - k_min) / (k_max - k_min) for k in ks]
    norm_i = [(iv - i_min) / (i_max - i_min) for iv in inertias]

    # 직선 x + y = 1에서 점 (nk, ni)까지 수직 거리 = |nk + ni - 1| / √2
    distances = [
        abs(norm_k[i] + norm_i[i] - 1) / math.sqrt(2)
        for i in range(n)
    ]
    return results[distances.index(max(distances))]['num_guards']


# ===== EFFICIENCY SCORING =====

def compute_efficiency(results: list) -> list:
    """
    각 요원 수별 효율 점수 산출.
    효율 = 성과(거리단축·시간단축·균등도) / 비용(요원 수 비율)
    """
    d_max = max(r['total_distance_km'] for r in results) or 1.0
    h_max = max(r['max_patrol_hours']  for r in results) or 1.0
    i_max = max(r['inertia']           for r in results) or 1.0

    enriched = []
    for r in results:
        dist_score    = 1.0 - r['total_distance_km'] / d_max   # 낮을수록 좋음 → 반전
        hours_score   = 1.0 - r['max_patrol_hours']  / h_max
        inertia_norm  = r['inertia'] / i_max
        cluster_score = 1.0 - inertia_norm   # 군집화 품질 (높을수록 좋음)

        # 성과: 거리·시간 단축 + 군집화 품질 (k=1은 셋 다 0 → 자명한 inflation 방지)
        perf = dist_score * 0.35 + hours_score * 0.30 + cluster_score * 0.35
        # 비용 비율 (요원 수 / 최대 요원 수), +0.05로 k=1 분모 방지
        cost = r['num_guards'] / MAX_GUARDS + 0.05
        efficiency = round(perf / cost, 4)

        enriched.append({
            **r,
            'inertia_normalized': round(inertia_norm, 4),
            'efficiency_score':   efficiency,
        })
    return enriched


# ===== MAIN =====

def main():
    print('=' * 62)
    print('최적 감시요원 인원 수 분석 (엘보우 기법)')
    print('=' * 62)

    with open(RISK_PATH, 'r', encoding='utf-8') as f:
        risk_data = json.load(f)

    predictions = risk_data['predictions']
    print(f'AI 예측 읍면동: {len(predictions)}개')

    # 기본 좌표 필터 + 상위 TOP_N 추출
    valid = [
        p for p in predictions
        if not (abs(p['lat'] - DEFAULT_LAT) < 0.0001
                and abs(p['lng'] - DEFAULT_LNG) < 0.0001)
    ]
    valid.sort(key=lambda p: p['probability'], reverse=True)
    top = valid[:TOP_N]
    print(f'분석 대상: 상위 {len(top)}개 위험 지점 (WAYPOINTS_TOTAL={TOP_N})\n')

    # 요원 수 1~8명 시뮬레이션
    results = []
    print(f'{"요원":>4}  {"총거리(km)":>10}  {"최대시간(h)":>11}  {"균등도":>8}  {"Inertia":>10}')
    print('-' * 62)
    for k in range(MIN_GUARDS, MAX_GUARDS + 1):
        r = simulate_guards(top, k)
        results.append(r)
        print(f'  {k:>2}명  {r["total_distance_km"]:>10.1f}  '
              f'{r["max_patrol_hours"]:>11.2f}  '
              f'{r["coverage_balance"]:>8.4f}  '
              f'{r["inertia"]:>10.2f}')

    # 분석 결과
    enriched   = compute_efficiency(results)
    elbow_k    = find_elbow(results)
    best_eff_k = max(enriched, key=lambda r: r['efficiency_score'])['num_guards']
    recommended = elbow_k   # 엘보우 우선 (지리적 합리성)

    print(f'\n{"─"*62}')
    print(f'  엘보우 포인트  : {elbow_k}명  (inertia 곡선 변곡점)')
    print(f'  효율 최고      : {best_eff_k}명  (성과/비용 비율 최대)')
    print(f'  ✅ 최종 추천   : {recommended}명')

    # 효율 점수 바 차트
    print('\n  요원별 효율 점수:')
    max_eff = max(r['efficiency_score'] for r in enriched) or 1.0
    for r in enriched:
        bar  = '█' * max(1, int(r['efficiency_score'] / max_eff * 20))
        mark = ' ← 추천' if r['num_guards'] == recommended else ''
        print(f'    {r["num_guards"]}명  {bar:<22} {r["efficiency_score"]:.4f}{mark}')

    output = {
        'timestamp':          datetime.now(KST).isoformat(),
        'recommended_guards': recommended,
        'elbow_point':        elbow_k,
        'best_efficiency_k':  best_eff_k,
        'top_n_analyzed':     len(top),
        'analysis':           enriched,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f'\n✅ 저장 완료: {OUTPUT_PATH}')
    print(f'   optimize_routes.py 실행 시 NUM_GUARDS={recommended} 자동 적용')


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f'❌ 분석 실패: {e}', file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
