"""
화성시 감시요원 최적 순찰 노선 최적화 v2
- OSM 실제 도로 기반 경로 계산 (osm_roads.json 없으면 haversine×1.25 폴백)
- 시간대별(AM/PM/NIGHT/ALL) 노선 자동 생성
- 요원별 순찰 시간 균등화 (±30분 목표)
- 출력: public/data/optimal_routes.json
"""

import heapq
import json
import math
import os
from collections import Counter, defaultdict
from datetime import datetime

import numpy as np
from sklearn.cluster import KMeans

# ===== 경로 설정 =====
BASE_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUT_PATH  = os.path.join(BASE_DIR, 'public', 'data', 'predicted_risk.json')
OSM_PATH    = os.path.join(BASE_DIR, 'public', 'data', 'osm_roads.json')
OUTPUT_PATH = os.path.join(BASE_DIR, 'public', 'data', 'optimal_routes.json')

# ===== 파라미터 =====
NUM_GUARDS        = 3
WAYPOINTS_TOTAL   = 24
PATROL_SPEED_KPH  = 30.0
STOP_MIN          = 15
BALANCE_THRESH_H  = 0.5    # 허용 시간 편차 (시간 = 30분)
BALANCE_MAX_ITER  = 25
ROAD_FACTOR       = 1.25   # OSM 없을 때 직선거리 보정 계수
ROUTE_MAX_PTS     = 80     # 노선 좌표 최대 포인트 수 (지도 성능 최적화)

GUARD_COLORS = ['#ff6644', '#44bbff', '#88dd44']
PERIOD_LABELS = {
    'AM':    '오전 (06:00–12:00)',
    'PM':    '오후 (12:00–18:00)',
    'NIGHT': '야간 (18:00–06:00)',
    'ALL':   '전체 일별',
}
# 시간대별 위험도 배율 (predicted_risk.json에 prob_am/pm/night 없을 때 폴백)
PERIOD_MULT = {'AM': 0.80, 'PM': 1.40, 'NIGHT': 0.50, 'ALL': 1.00}


# ===== 거리 유틸 =====

def haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlng / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(max(0.0, a)))


# ===== OSM 도로망 =====

class RoadNetwork:
    """OSM 도로 데이터로 구축한 최단 경로 그래프."""

    SNAP_RADIUS_KM = 2.5

    def __init__(self, roads: list):
        self.graph: dict = defaultdict(list)   # node_key → [(neighbor_key, dist)]
        self.coords: dict = {}                  # node_key → (lat, lng)
        self._grid: dict = defaultdict(list)   # grid_cell → [node_key, ...]
        self._res = 0.008                       # ≈ 0.9km 격자 해상도

        self._build(roads)

    # ---------- 내부 유틸 ----------

    def _key(self, lat: float, lng: float) -> str:
        return f"{lat:.5f},{lng:.5f}"

    def _cell(self, lat: float, lng: float) -> tuple:
        return (int(lat / self._res), int(lng / self._res))

    def _add_node(self, lat: float, lng: float) -> str:
        k = self._key(lat, lng)
        if k not in self.coords:
            self.coords[k] = (lat, lng)
            self._grid[self._cell(lat, lng)].append(k)
        return k

    def _build(self, roads: list):
        for road in roads:
            pts = road.get('coords', [])
            if len(pts) < 2:
                continue
            prev_k = None
            for lat, lng in pts:
                cur_k = self._add_node(lat, lng)
                if prev_k is not None and prev_k != cur_k:
                    plat, plng = self.coords[prev_k]
                    d = haversine(plat, plng, lat, lng)
                    self.graph[prev_k].append((cur_k, d))
                    self.graph[cur_k].append((prev_k, d))
                prev_k = cur_k

        n_edges = sum(len(v) for v in self.graph.values()) // 2
        print(f"  도로망 구축: {len(self.coords):,} 노드 / {n_edges:,} 에지")

    # ---------- 스냅 ----------

    def snap(self, lat: float, lng: float) -> tuple:
        """(node_key, dist_km) — 가장 가까운 도로 노드."""
        best_k, best_d = None, float('inf')
        r = max(1, math.ceil(self.SNAP_RADIUS_KM / (111 * self._res)))
        cx, cy = int(lat / self._res), int(lng / self._res)
        for dx in range(-r, r + 1):
            for dy in range(-r, r + 1):
                for k in self._grid.get((cx + dx, cy + dy), []):
                    nlat, nlng = self.coords[k]
                    d = haversine(lat, lng, nlat, nlng)
                    if d < best_d:
                        best_d, best_k = d, k
        return best_k, best_d

    # ---------- Dijkstra ----------

    def shortest_path(self, src: str, dst: str,
                      max_km: float = 80.0) -> tuple:
        """(path_coords [[lat,lng],...], dist_km) 반환. 실패 시 ([], inf)."""
        if src == dst:
            lat, lng = self.coords[src]
            return [[lat, lng]], 0.0

        dist_map = {src: 0.0}
        prev_map: dict = {src: None}
        pq = [(0.0, src)]

        while pq:
            d, u = heapq.heappop(pq)
            if u == dst:
                break
            if d > dist_map.get(u, float('inf')) + 1e-9:
                continue
            if d > max_km:
                break
            for v, w in self.graph.get(u, []):
                nd = d + w
                if nd < dist_map.get(v, float('inf')):
                    dist_map[v] = nd
                    prev_map[v] = u
                    heapq.heappush(pq, (nd, v))

        if dst not in dist_map:
            return [], float('inf')

        path: list = []
        cur = dst
        while cur is not None:
            lat, lng = self.coords[cur]
            path.append([lat, lng])
            cur = prev_map.get(cur)
        path.reverse()
        return path, dist_map[dst]

    # ---------- 두 지점 간 도로 경로 ----------

    def route_between(self, p1: dict, p2: dict) -> tuple:
        """(route_coords [[lat,lng]], road_dist_km). 실패 시 직선 폴백."""
        straight = haversine(p1['lat'], p1['lng'], p2['lat'], p2['lng'])

        k1, d1 = self.snap(p1['lat'], p1['lng'])
        k2, d2 = self.snap(p2['lat'], p2['lng'])

        if (k1 is None or k2 is None
                or d1 > self.SNAP_RADIUS_KM
                or d2 > self.SNAP_RADIUS_KM):
            return [[p1['lat'], p1['lng']], [p2['lat'], p2['lng']]], straight * ROAD_FACTOR

        path, road_dist = self.shortest_path(k1, k2, max_km=straight * 3 + 5)

        if not path or road_dist == float('inf'):
            return [[p1['lat'], p1['lng']], [p2['lat'], p2['lng']]], straight * ROAD_FACTOR

        # 경로 포인트 수 제한 (지도 성능)
        if len(path) > ROUTE_MAX_PTS:
            step = len(path) // ROUTE_MAX_PTS
            path = path[::step]
            if path[-1] != [p2['lat'], p2['lng']]:
                path.append([p2['lat'], p2['lng']])

        return path, road_dist


# ===== 예측 데이터 유틸 =====

def get_prob(pred: dict, period: str) -> float:
    """시간대별 확률. 해당 필드 없으면 배율 추정."""
    base = float(pred.get('probability', 0.0))
    if period == 'AM':    return float(pred.get('prob_am',    min(1.0, base * 0.80)))
    if period == 'PM':    return float(pred.get('prob_pm',    min(1.0, base * 1.40)))
    if period == 'NIGHT': return float(pred.get('prob_night', min(1.0, base * 0.50)))
    return base


def get_level(prob: float) -> str:
    if prob >= 0.30: return 'HIGH'
    if prob >= 0.12: return 'MEDIUM'
    return 'LOW'


def zone_name(locs: list) -> str:
    myeons = [loc.get('myeon', '') for loc in locs if loc.get('myeon')]
    if not myeons:
        return '화성시 구역'
    top = Counter(myeons).most_common(2)
    return (f"{top[0][0]}·{top[1][0]} 구역"
            if len(top) >= 2 and top[1][1] > 1
            else f"{top[0][0]} 구역")


# ===== TSP =====

def greedy_tsp(locs: list, period: str) -> list:
    """최근접 이웃 TSP. 시간대 위험도 최고 지점에서 출발."""
    n = len(locs)
    if n == 0:
        return []
    start    = max(range(n), key=lambda i: get_prob(locs[i], period))
    visited  = [False] * n
    order    = [start]
    visited[start] = True
    for _ in range(n - 1):
        cur = order[-1]
        bd, bj = float('inf'), -1
        for j in range(n):
            if not visited[j]:
                d = haversine(locs[cur]['lat'], locs[cur]['lng'],
                              locs[j]['lat'],   locs[j]['lng'])
                if d < bd:
                    bd, bj = d, j
        order.append(bj)
        visited[bj] = True
    return order


# ===== 시간 추정 & 균등화 =====

def estimate_time_km(locs: list, road_net) -> tuple:
    """(total_km, total_hours) 계산."""
    km = 0.0
    for i in range(1, len(locs)):
        if road_net:
            _, d = road_net.route_between(locs[i - 1], locs[i])
        else:
            d = haversine(locs[i-1]['lat'], locs[i-1]['lng'],
                          locs[i]['lat'],   locs[i]['lng']) * ROAD_FACTOR
        km += d
    hours = km / PATROL_SPEED_KPH + len(locs) * (STOP_MIN / 60)
    return round(km, 2), round(hours, 2)


def balance_clusters(clusters: list, road_net, period: str) -> list:
    """
    요원별 순찰 시간을 탐욕적으로 균등화.
    바쁜 구역의 (낮은 우선순위 + 한가한 구역에 가까운) 지점을 이동.
    """
    for iteration in range(BALANCE_MAX_ITER):
        times = [estimate_time_km(c, road_net)[1] for c in clusters]
        mx, mn = max(times), min(times)
        if mx - mn <= BALANCE_THRESH_H:
            print(f"  균등화 완료 ({iteration}회 이동 · 편차 {(mx - mn)*60:.0f}분)")
            break
        busy_i = times.index(mx)
        idle_i = times.index(mn)
        if len(clusters[busy_i]) <= 1:
            break

        idle_lat = float(np.mean([loc['lat'] for loc in clusters[idle_i]]))
        idle_lng = float(np.mean([loc['lng'] for loc in clusters[idle_i]]))

        # 이동 후보: 낮은 기여도 + 한가한 구역에 가까울수록 점수 낮음 (이동 우선)
        scores = [
            haversine(loc['lat'], loc['lng'], idle_lat, idle_lng)
            - get_prob(loc, period) * 8
            for loc in clusters[busy_i]
        ]
        move_i = int(np.argmin(scores))
        moved  = clusters[busy_i].pop(move_i)
        clusters[idle_i].append(moved)
    else:
        times = [estimate_time_km(c, road_net)[1] for c in clusters]
        print(f"  균등화 종료 (최대편차 {(max(times) - min(times))*60:.0f}분)")

    return clusters


# ===== 요원 노선 구성 =====

def build_guard(gid: int, cluster: list, period: str,
                road_net, color: str) -> dict:
    """단일 요원 노선 딕셔너리 생성."""
    tsp_ord = greedy_tsp(cluster, period)
    ordered = [cluster[i] for i in tsp_ord]

    route_coords: list = []
    wps: list = []
    total_km = 0.0

    for seq, loc in enumerate(ordered):
        if seq == 0:
            if road_net:
                k, _ = road_net.snap(loc['lat'], loc['lng'])
                route_coords.append(list(road_net.coords[k]) if k else [loc['lat'], loc['lng']])
            else:
                route_coords.append([loc['lat'], loc['lng']])
            leg_km = 0.0
        else:
            prev = ordered[seq - 1]
            if road_net:
                seg, leg_km = road_net.route_between(prev, loc)
                route_coords.extend(seg[1:] if len(seg) > 1 else seg)
            else:
                route_coords.append([loc['lat'], loc['lng']])
                leg_km = haversine(prev['lat'], prev['lng'],
                                   loc['lat'],  loc['lng']) * ROAD_FACTOR
        total_km += leg_km

        prob = get_prob(loc, period)
        wps.append({
            'order':             seq + 1,
            'dong':              loc['dong'],
            'myeon':             loc.get('myeon', ''),
            'lat':               loc['lat'],
            'lng':               loc['lng'],
            'probability':       round(prob, 3),
            'level':             get_level(prob),
            'prob_base':         round(float(loc.get('probability', prob)), 3),
            'prob_am':           round(float(loc.get('prob_am',    min(1.0, float(loc.get('probability', 0)) * 0.80))), 3),
            'prob_pm':           round(float(loc.get('prob_pm',    min(1.0, float(loc.get('probability', 0)) * 1.40))), 3),
            'prob_night':        round(float(loc.get('prob_night', min(1.0, float(loc.get('probability', 0)) * 0.50))), 3),
            'top_cause':         loc.get('top_cause', '기타'),
            'dist_from_prev_km': round(leg_km, 2),
        })

    est_hours = total_km / PATROL_SPEED_KPH + len(ordered) * (STOP_MIN / 60)
    probs     = [wp['probability'] for wp in wps]
    avg_risk  = float(np.mean(probs)) if probs else 0.0

    return {
        'id':                  gid + 1,
        'color':               color,
        'zone_name':           zone_name(ordered),
        'waypoints':           wps,
        'route_coords':        route_coords,
        'total_distance_km':   round(total_km, 2),
        'estimated_hours':     round(est_hours, 2),
        'avg_risk':            round(avg_risk, 3),
        'stop_count':          len(ordered),
        'high_risk_count':     sum(1 for p in probs if get_level(p) == 'HIGH'),
        'medium_risk_count':   sum(1 for p in probs if get_level(p) == 'MEDIUM'),
        'low_risk_count':      sum(1 for p in probs if get_level(p) == 'LOW'),
        'road_based':          road_net is not None,
    }


# ===== 시간대별 전체 노선 생성 =====

DEFAULT_LAT, DEFAULT_LNG = 37.1996, 126.8312


def build_period(predictions: list, period: str, road_net) -> dict:
    """시간대 하나에 대한 전체 노선 딕셔너리 생성."""
    # 좌표 중복 제거 + 시간대별 위험도 기준 정렬
    seen: dict = {}
    for p in sorted(predictions, key=lambda x: get_prob(x, period), reverse=True):
        key = (round(p['lat'], 3), round(p['lng'], 3))
        if (key not in seen
                and not (abs(p['lat'] - DEFAULT_LAT) < 0.0001
                         and abs(p['lng'] - DEFAULT_LNG) < 0.0001)):
            seen[key] = p
    unique = list(seen.values())[:WAYPOINTS_TOTAL]

    if len(unique) < NUM_GUARDS:
        return {'period_label': PERIOD_LABELS[period], 'guards': [],
                'waypoints_total': 0, 'balance_score': 0.0}

    # K-Means 군집화 (확률 가중치)
    coords  = np.array([[w['lat'], w['lng']] for w in unique], dtype=float)
    weights = np.array([get_prob(w, period)  for w in unique], dtype=float)
    km      = KMeans(n_clusters=NUM_GUARDS, random_state=42, n_init=10)
    km.fit(coords, sample_weight=weights)
    labels  = km.labels_

    # 위험도 높은 군집 → 요원 1번
    cluster_avg = {
        c: float(np.mean([get_prob(unique[i], period)
                           for i in range(len(unique)) if labels[i] == c]))
        for c in range(NUM_GUARDS)
    }
    rank_map = {c: r for r, (c, _) in
                enumerate(sorted(cluster_avg.items(), key=lambda x: -x[1]))}
    clusters = [
        [unique[i] for i in range(len(unique)) if labels[i] == orig_c]
        for gid in range(NUM_GUARDS)
        for orig_c in [next(c for c, r in rank_map.items() if r == gid)]
    ]

    # 시간 균등화
    clusters = balance_clusters(clusters, road_net, period)

    # 요원별 노선 구성
    guards = [
        build_guard(gid, clusters[gid], period, road_net, GUARD_COLORS[gid])
        for gid in range(NUM_GUARDS)
    ]

    # 균등화 점수
    times = [g['estimated_hours'] for g in guards]
    avg_t = float(np.mean(times))
    spread = max(times) - min(times)
    balance_score = round(max(0.0, 1.0 - spread / (avg_t + 0.001)), 3)

    total_stops = sum(g['stop_count'] for g in guards)
    total_km    = sum(g['total_distance_km'] for g in guards)
    print(f"  [{period}] {total_stops}개소 · {total_km:.1f}km · "
          f"균등화 {balance_score:.2f} (편차 {spread*60:.0f}분)")

    return {
        'period_label':   PERIOD_LABELS[period],
        'guards':         guards,
        'waypoints_total': len(unique),
        'balance_score':  balance_score,
    }


# ===== MAIN =====

def main():
    print("=" * 60)
    print("화성시 감시요원 최적 순찰 노선 v2")
    print("=" * 60)

    # 데이터 로드
    with open(INPUT_PATH, 'r', encoding='utf-8') as f:
        risk_data = json.load(f)
    predictions = risk_data['predictions']
    print(f"AI 예측 읍면동: {len(predictions)}개")

    # OSM 도로망 구축 (선택)
    road_net = None
    if os.path.exists(OSM_PATH):
        with open(OSM_PATH, 'r', encoding='utf-8') as f:
            osm = json.load(f)
        roads = osm.get('roads', [])
        print(f"OSM 도로 로드: {len(roads)}개 구간")
        if roads:
            road_net = RoadNetwork(roads)
    else:
        print("osm_roads.json 없음 — 직선거리×1.25 폴백 사용")

    # 시간대별 노선 생성
    print("\n[ 시간대별 최적 노선 계산 ]")
    time_periods: dict = {}
    for period in ('ALL', 'AM', 'PM', 'NIGHT'):
        print(f"\n-- {PERIOD_LABELS[period]} --")
        time_periods[period] = build_period(predictions, period, road_net)

    # 저장
    all_guards = time_periods['ALL']['guards']
    output = {
        'timestamp':        datetime.now().isoformat(),
        'algorithm':        'K-Means 군집화 + Greedy TSP + 시간 균등화',
        'road_based':       road_net is not None,
        'osm_source':       'OpenStreetMap Overpass API' if road_net else '없음 (직선거리 폴백)',
        'num_guards':       NUM_GUARDS,
        'patrol_speed_kph': PATROL_SPEED_KPH,
        'stop_minutes':     STOP_MIN,
        'waypoints_total':  time_periods['ALL']['waypoints_total'],
        'time_periods':     time_periods,
        'guards':           all_guards,   # 하위 호환
    }

    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*60}")
    print(f"✅ 저장 완료 → {OUTPUT_PATH}")
    print(f"   도로 기반: {'예 (OSM)' if road_net else '아니오 (직선 폴백)'}")
    for period, data in time_periods.items():
        guards = data.get('guards', [])
        if not guards:
            continue
        times = [g['estimated_hours'] for g in guards]
        label = PERIOD_LABELS[period]
        print(f"\n  [{label}]")
        for g in guards:
            h = int(g['estimated_hours'])
            m = round((g['estimated_hours'] - h) * 60)
            print(f"    요원 {g['id']} ({g['zone_name']}): "
                  f"{g['stop_count']}개소 · {g['total_distance_km']}km · "
                  f"{h}시간{m}분 · 평균위험 {g['avg_risk']:.3f}")
        print(f"    균등화 점수: {data['balance_score']:.2f}  "
              f"편차: {(max(times)-min(times))*60:.0f}분")


if __name__ == '__main__':
    main()
