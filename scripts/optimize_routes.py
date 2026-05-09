"""
화성시 감시요원 최적 순찰 노선 최적화
- AI 예측 위험도 기반 우선 순찰 지점 선정
- K-Means 군집화로 요원별 담당 구역 분할
- Greedy TSP (최근접 이웃) 로 각 구역 내 최적 방문 순서 결정
- 출력: public/data/optimal_routes.json
"""

import json
import math
import os
from collections import Counter
from datetime import datetime

import numpy as np
from sklearn.cluster import KMeans

# ===== 경로 설정 =====
BASE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUT_PATH = os.path.join(BASE_DIR, 'public', 'data', 'predicted_risk.json')
OUTPUT_PATH = os.path.join(BASE_DIR, 'public', 'data', 'optimal_routes.json')

# ===== 파라미터 =====
NUM_GUARDS       = 3          # 감시요원 수
WAYPOINTS_TOTAL  = 24         # 총 순찰 지점 수 (요원당 8개)
PATROL_SPEED_KPH = 30.0       # 평균 순찰 속도 (km/h)
STOP_MIN         = 15         # 지점당 점검 시간 (분)
GUARD_COLORS     = ['#ff6644', '#44bbff', '#88dd44']

# ===== 유틸 =====
def haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """두 좌표 간 거리 (km)."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlng / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(max(0, a)))


def greedy_tsp(locations: list[dict]) -> list[int]:
    """최근접 이웃 TSP: 위험도 최고 지점 출발 → 가장 가까운 미방문 지점 순회."""
    n = len(locations)
    if n == 0:
        return []
    # 출발점: 위험도 최고 지점
    start = max(range(n), key=lambda i: locations[i]['probability'])
    visited = [False] * n
    order   = [start]
    visited[start] = True

    for _ in range(n - 1):
        cur = order[-1]
        best_dist, best_j = float('inf'), -1
        for j in range(n):
            if not visited[j]:
                d = haversine(locations[cur]['lat'], locations[cur]['lng'],
                              locations[j]['lat'],   locations[j]['lng'])
                if d < best_dist:
                    best_dist, best_j = d, j
        order.append(best_j)
        visited[best_j] = True

    return order


def zone_name(locations: list[dict]) -> str:
    """군집 내 주요 면 이름으로 구역 명칭 생성."""
    myeons = [loc['myeon'] for loc in locations if loc.get('myeon')]
    if not myeons:
        return '화성시 구역'
    top = Counter(myeons).most_common(2)
    if len(top) >= 2 and top[1][1] > 1:
        return f"{top[0][0]}·{top[1][0]} 구역"
    return f"{top[0][0]} 구역"


# ===== 데이터 로드 =====
with open(INPUT_PATH, 'r', encoding='utf-8') as f:
    risk_data = json.load(f)

predictions = risk_data['predictions']

# ===== 좌표 중복 제거 + 상위 N개 선택 =====
DEFAULT_LAT, DEFAULT_LNG = 37.1996, 126.8312  # 좌표 없는 경우 기본값

seen_coords: dict = {}
for p in sorted(predictions, key=lambda x: x['probability'], reverse=True):
    key = (round(p['lat'], 3), round(p['lng'], 3))
    if key not in seen_coords:
        seen_coords[key] = p

unique_preds = sorted(seen_coords.values(), key=lambda x: x['probability'], reverse=True)
waypoints    = unique_preds[:WAYPOINTS_TOTAL]

print(f"전체 읍면동: {len(predictions)}개")
print(f"유니크 좌표: {len(unique_preds)}개 → 상위 {len(waypoints)}개 선택")

# ===== K-Means 군집화 (확률 가중치 적용) =====
coords  = np.array([[w['lat'], w['lng']] for w in waypoints])
weights = np.array([w['probability']     for w in waypoints])

kmeans = KMeans(n_clusters=NUM_GUARDS, random_state=42, n_init=10)
kmeans.fit(coords, sample_weight=weights)
labels = kmeans.labels_

# 군집 번호 → 위험도 평균 기준 정렬 (높을수록 요원 1번)
cluster_avg = {
    c: np.mean([waypoints[i]['probability'] for i in range(len(waypoints)) if labels[i] == c])
    for c in range(NUM_GUARDS)
}
rank_map = {c: r for r, (c, _) in enumerate(sorted(cluster_avg.items(), key=lambda x: -x[1]))}

# ===== 요원별 TSP + 통계 계산 =====
guards = []
for guard_id in range(NUM_GUARDS):
    orig_cluster = [c for c, r in rank_map.items() if r == guard_id][0]
    cluster_locs = [waypoints[i] for i in range(len(waypoints)) if labels[i] == orig_cluster]

    tsp_order = greedy_tsp(cluster_locs)
    ordered   = [cluster_locs[i] for i in tsp_order]

    # 거리 계산
    route_coords = [[loc['lat'], loc['lng']] for loc in ordered]
    total_dist   = 0.0
    waypoint_list = []
    for seq, loc in enumerate(ordered):
        if seq == 0:
            leg_dist = 0.0
        else:
            prev = ordered[seq - 1]
            leg_dist = haversine(prev['lat'], prev['lng'], loc['lat'], loc['lng'])
        total_dist += leg_dist
        waypoint_list.append({
            'order':             seq + 1,
            'dong':              loc['dong'],
            'myeon':             loc.get('myeon', ''),
            'lat':               loc['lat'],
            'lng':               loc['lng'],
            'probability':       loc['probability'],
            'level':             loc['level'],
            'top_cause':         loc.get('top_cause', '기타'),
            'dist_from_prev_km': round(leg_dist, 2),
        })

    n_stops  = len(ordered)
    est_hours = total_dist / PATROL_SPEED_KPH + n_stops * (STOP_MIN / 60)
    avg_risk  = float(np.mean([loc['probability'] for loc in ordered]))

    guards.append({
        'id':           guard_id + 1,
        'color':        GUARD_COLORS[guard_id],
        'zone_name':    zone_name(ordered),
        'waypoints':    waypoint_list,
        'route_coords': route_coords,
        'total_distance_km':   round(total_dist, 2),
        'estimated_hours':     round(est_hours, 2),
        'avg_risk':            round(avg_risk, 3),
        'stop_count':          n_stops,
        'high_risk_count':     sum(1 for loc in ordered if loc['level'] == 'HIGH'),
        'medium_risk_count':   sum(1 for loc in ordered if loc['level'] == 'MEDIUM'),
        'low_risk_count':      sum(1 for loc in ordered if loc['level'] == 'LOW'),
    })

# ===== 저장 =====
output = {
    'timestamp':        datetime.now().isoformat(),
    'num_guards':       NUM_GUARDS,
    'algorithm':        'K-Means 군집화 + Greedy TSP (최근접 이웃)',
    'waypoints_total':  len(waypoints),
    'patrol_speed_kph': PATROL_SPEED_KPH,
    'stop_minutes':     STOP_MIN,
    'guards':           guards,
}

with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f"\n최적 노선 저장 완료 → {OUTPUT_PATH}")
for g in guards:
    print(f"  요원 {g['id']} ({g['zone_name']}): "
          f"{g['stop_count']}개소 · {g['total_distance_km']}km · "
          f"예상 {g['estimated_hours']:.1f}h · 평균위험 {g['avg_risk']:.3f}")
