"""
화성시 감시요원 최적 순찰 노선 최적화 v3
- 시간대별 완전히 다른 스코어링으로 순찰 지점 선정
  · AM  (06–12시): 쓰레기소각/논밭태우기/농산부산물소각 지역 우선
  · PM  (12–18시): 입산자실화/담뱃불실화 지역 + 현재 기상 위험도
  · NIGHT(18–06시): NASA FIRMS 실시간 탐지 인근 + 반복화재(hist_count) 우선
  · ALL: AI 예측 기본 확률
- OSM 실제 도로 기반 경로 (osm_roads.json 없으면 haversine×1.25 폴백)
- 요원별 순찰 시간 균등화 (±30분 목표)
- 출력: public/data/optimal_routes.json
"""

import csv
import heapq
import io
import json
import math
import os
import random
from collections import Counter, defaultdict
from datetime import datetime

try:
    import requests as _requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

# ===== 경로 설정 =====
BASE_DIR       = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUT_PATH     = os.path.join(BASE_DIR, 'public', 'data', 'predicted_risk.json')
OSM_PATH       = os.path.join(BASE_DIR, 'public', 'data', 'osm_roads.json')
WEATHER_PATH   = os.path.join(BASE_DIR, 'public', 'data', 'weather.json')
OUTPUT_PATH    = os.path.join(BASE_DIR, 'public', 'data', 'optimal_routes.json')

# ===== 상수 =====
NUM_GUARDS        = 3   # ← 이 값만 바꾸면 구역 분할·균등화·사이드바 전체 반영
WAYPOINTS_TOTAL   = 24
PATROL_SPEED_KPH  = 30.0
STOP_MIN          = 15
BALANCE_THRESH_H  = 0.5
BALANCE_MAX_ITER  = 25
ROAD_FACTOR       = 1.25
ROUTE_MAX_PTS     = 80

# 요원별 색상 — NUM_GUARDS 변경 시 팔레트를 자동으로 잘라 사용
_COLOR_PALETTE = [
    '#ff6644', '#44bbff', '#88dd44', '#cc44ff',
    '#ffcc00', '#00cccc', '#ff44aa', '#44ffcc',
]
GUARD_COLORS = (_COLOR_PALETTE * ((NUM_GUARDS // len(_COLOR_PALETTE)) + 1))[:NUM_GUARDS]

PERIOD_LABELS = {
    'AM':    '오전 (06:00–12:00)',
    'PM':    '오후 (12:00–18:00)',
    'NIGHT': '야간 (18:00–06:00)',
    'ALL':   '전체 일별',
}

# ===== 시간대별 원인 분류 =====
# 오전: 농경·소각 활동 (이른 아침 논밭·쓰레기 태우기)
MORNING_BURN = {'쓰레기소각', '논밭태우기', '농산부산물소각'}
# 오후: 등산객·흡연자 (오후 야외 활동)
HIKER_CAUSES = {'입산자실화', '담뱃불실화'}
# 야간: 담배꽁초·건축물 비화 (야간 취약 원인)
NIGHT_CAUSES = {'담뱃불실화', '건축물화재비화', '담배꽁초'}

# NASA FIRMS
FIRMS_KEY = '48d1abd5e81dda4c332b926e56353f67'
FIRMS_URL = (
    f'https://firms.modaps.eosdis.nasa.gov/api/area/csv/{FIRMS_KEY}'
    '/VIIRS_SNPP_NRT/126.55,36.95,127.15,37.45/1'
)


# ===== 거리 =====

def haversine(lat1, lng1, lat2, lng2) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlng / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(max(0.0, a)))


# ===== FIRMS 실시간 데이터 =====

def fetch_firms() -> list:
    """NASA FIRMS VIIRS 실시간 화점 좌표 목록 반환. 실패 시 빈 리스트."""
    if not HAS_REQUESTS:
        return []
    try:
        resp = _requests.get(FIRMS_URL, timeout=12)
        resp.raise_for_status()
        reader = csv.DictReader(io.StringIO(resp.text))
        locs = []
        for row in reader:
            try:
                locs.append({'lat': float(row['latitude']),
                              'lng': float(row['longitude'])})
            except (KeyError, ValueError):
                pass
        print(f"  FIRMS 화점: {len(locs)}건")
        return locs
    except Exception as e:
        print(f"  FIRMS 로드 실패: {e}")
        return []


# ===== 컨텍스트 구성 =====

def build_context(predictions: list) -> dict:
    """시간대 스코어링에 공유할 컨텍스트 구성."""
    max_count = max((int(p.get('hist_count', 0)) for p in predictions), default=1)

    # 현재 기상 FWI 점수
    fwi_score = 0.30
    try:
        with open(WEATHER_PATH, 'r', encoding='utf-8') as f:
            wd = json.load(f)
        fwi_score = wd.get('fire_weather_index', {}).get('score') or fwi_score
        print(f"  기상 FWI 점수: {fwi_score}")
    except Exception:
        pass

    firms = fetch_firms()

    return {
        'max_hist_count':  max_count,
        'fwi_score':       float(fwi_score),
        'firms_locations': firms,
    }


# ===== 시간대별 스코어링 =====

def score_period(pred: dict, period: str, ctx: dict) -> float:
    """
    시간대별로 완전히 다른 기준으로 순찰 우선순위 점수 산출.

    AM:    소각 원인 지역 최우선 (0.50 보너스)
    PM:    입산자·흡연자 원인 + 현재 기상 위험 최우선 (0.40 보너스)
    NIGHT: NASA FIRMS 근접 + 반복화재 hist_count 최우선
    ALL:   AI 기본 예측 확률
    """
    prob       = float(pred.get('probability', 0.0))
    hist_score = float(pred.get('hist_score',  0.0))
    hist_count = float(pred.get('hist_count',  0))
    top_cause  = pred.get('top_cause', '기타')
    max_cnt    = max(ctx.get('max_hist_count', 1), 1)
    count_norm = hist_count / max_cnt

    if period == 'AM':
        # 오전: 소각 활동 지역 강력 우선 (+0.50)
        cause_w = 0.50 if top_cause in MORNING_BURN else 0.01
        score   = prob * 0.30 + cause_w + hist_score * 0.15

    elif period == 'PM':
        # 오후: 등산객·흡연 원인 지역 강력 우선 (+0.40) + 기상 위험도
        cause_w = 0.40 if top_cause in HIKER_CAUSES else 0.03
        fwi     = float(ctx.get('fwi_score', 0.30))
        score   = prob * 0.25 + cause_w + hist_score * 0.20 + fwi * 0.10

    elif period == 'NIGHT':
        # 야간: FIRMS 실시간 화점 근접 최우선, 없으면 반복화재 hist_count
        cause_w  = 0.30 if top_cause in NIGHT_CAUSES else 0.01
        firms    = ctx.get('firms_locations', [])
        if firms:
            min_d        = min(haversine(pred['lat'], pred['lng'],
                                         f['lat'], f['lng']) for f in firms)
            firms_score  = max(0.0, 1.0 - min_d / 15.0)  # 15km 이내 1→0
            score = prob * 0.20 + firms_score * 0.50 + count_norm * 0.20 + cause_w * 0.10
        else:
            score = prob * 0.20 + cause_w + count_norm * 0.45

    else:  # ALL
        score = prob

    return round(min(1.0, max(0.0, score)), 4)


def get_priority_reason(pred: dict, period: str, ctx: dict) -> str:
    """순찰 우선 선정 이유 (팝업 표시용)."""
    cause = pred.get('top_cause', '기타')
    if period == 'AM' and cause in MORNING_BURN:
        return f'{cause} 활동 오전 집중'
    if period == 'PM' and cause in HIKER_CAUSES:
        return f'{cause} · 오후 야외활동'
    if period == 'NIGHT':
        firms = ctx.get('firms_locations', [])
        if firms:
            min_d = min(haversine(pred['lat'], pred['lng'],
                                   f['lat'], f['lng']) for f in firms)
            if min_d < 15:
                return f'FIRMS 화점 {min_d:.1f}km 근접'
        if pred.get('hist_count', 0) >= 3:
            return f'반복화재 {pred["hist_count"]}회 (야간 감시)'
        if pred.get('top_cause', '') in NIGHT_CAUSES:
            return f'{cause} · 야간 취약'
    return f'AI 위험도 {pred.get("probability", 0)*100:.0f}%'


# ===== OSM 도로망 =====

def _interpolate_coords(p1: dict, p2: dict, n: int = 5) -> list:
    """두 지점 사이 n개 보간점을 포함한 좌표 목록 반환 (완전 직선 회피용)."""
    coords = [[p1['lat'], p1['lng']]]
    for i in range(1, n + 1):
        t = i / (n + 1)
        coords.append([
            p1['lat'] + t * (p2['lat'] - p1['lat']),
            p1['lng'] + t * (p2['lng'] - p1['lng']),
        ])
    coords.append([p2['lat'], p2['lng']])
    return coords


class RoadNetwork:
    SNAP_RADIUS_KM = 2.5

    def __init__(self, roads: list):
        self.graph: dict = defaultdict(list)
        self.coords: dict = {}
        self._grid: dict  = defaultdict(list)
        self._res = 0.008
        self._build(roads)

    def _key(self, lat, lng) -> str:
        return f"{lat:.5f},{lng:.5f}"

    def _cell(self, lat, lng) -> tuple:
        return (int(lat / self._res), int(lng / self._res))

    def _add_node(self, lat, lng) -> str:
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
                if prev_k and prev_k != cur_k:
                    plat, plng = self.coords[prev_k]
                    d = haversine(plat, plng, lat, lng)
                    self.graph[prev_k].append((cur_k, d))
                    self.graph[cur_k].append((prev_k, d))
                prev_k = cur_k
        n_edges = sum(len(v) for v in self.graph.values()) // 2
        print(f"  도로망: {len(self.coords):,} 노드 / {n_edges:,} 에지")

    def snap(self, lat, lng) -> tuple:
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

    def snap_wide(self, lat, lng, factor: float = 2.0) -> tuple:
        """SNAP_RADIUS_KM × factor 반경으로 스냅 (폴백용 확장 탐색)."""
        wide_r = self.SNAP_RADIUS_KM * factor
        best_k, best_d = None, float('inf')
        r = max(1, math.ceil(wide_r / (111 * self._res)))
        cx, cy = int(lat / self._res), int(lng / self._res)
        for dx in range(-r, r + 1):
            for dy in range(-r, r + 1):
                for k in self._grid.get((cx + dx, cy + dy), []):
                    nlat, nlng = self.coords[k]
                    d = haversine(lat, lng, nlat, nlng)
                    if d < best_d:
                        best_d, best_k = d, k
        return best_k, best_d

    def shortest_path(self, src, dst, max_km=80.0) -> tuple:
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
        path, cur = [], dst
        while cur is not None:
            lat, lng = self.coords[cur]
            path.append([lat, lng])
            cur = prev_map.get(cur)
        path.reverse()
        return path, dist_map[dst]

    def route_between(self, p1, p2) -> tuple:
        """
        두 지점 사이 도로 경로 반환. (path, dist_km, road_based) 3-튜플.

        1단계: 기본 스냅 + Dijkstra
        2단계: 2배 스냅 반경 + 중간 경유지 우회 → 직접 Dijkstra
        3단계: haversine × 1.4 + 보간점 5개 폴백
        """
        straight = haversine(p1['lat'], p1['lng'], p2['lat'], p2['lng'])

        def _trim(path):
            if len(path) > ROUTE_MAX_PTS:
                step = len(path) // ROUTE_MAX_PTS
                path = path[::step]
            return path

        # ── 1단계: 기본 스냅 + Dijkstra ──────────────────────────
        k1, d1 = self.snap(p1['lat'], p1['lng'])
        k2, d2 = self.snap(p2['lat'], p2['lng'])
        if k1 and k2 and d1 <= self.SNAP_RADIUS_KM and d2 <= self.SNAP_RADIUS_KM:
            path, dist = self.shortest_path(k1, k2, max_km=straight * 3 + 5)
            if path and dist != float('inf'):
                return _trim(path), dist, True

        # ── 2단계: 2배 스냅 반경 ──────────────────────────────────
        k1w, _ = self.snap_wide(p1['lat'], p1['lng'])
        k2w, _ = self.snap_wide(p2['lat'], p2['lng'])
        if k1w and k2w:
            # 중간 경유지 우회 시도
            mid_lat = (p1['lat'] + p2['lat']) / 2
            mid_lng = (p1['lng'] + p2['lng']) / 2
            km_node, _ = self.snap_wide(mid_lat, mid_lng)
            if km_node and km_node not in (k1w, k2w):
                pa, da = self.shortest_path(k1w, km_node, max_km=straight * 2 + 5)
                pb, db = self.shortest_path(km_node, k2w,  max_km=straight * 2 + 5)
                if pa and pb and da != float('inf') and db != float('inf'):
                    combined = pa + pb[1:]
                    return _trim(combined), da + db, True

            # 경유지 없이 2배 스냅 직접 Dijkstra
            path, dist = self.shortest_path(k1w, k2w, max_km=straight * 4 + 10)
            if path and dist != float('inf'):
                return _trim(path), dist, True

        # ── 3단계: 보간점 포함 폴백 ───────────────────────────────
        est_dist = straight * 1.4
        coords   = _interpolate_coords(p1, p2, n=5)
        return coords, est_dist, False


# ===== 유틸 =====

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


def greedy_tsp(locs: list, scores: list) -> list:
    """
    위험도·거리 혼합 TSP.
    출발: 위험도(score) 최고 지점
    이동 기준: score×0.6 - dist_normalized×0.4  (거리만 보던 방식 개선)
    """
    n = len(locs)
    if n == 0:
        return []
    start = max(range(n), key=lambda i: scores[i])
    visited = [False] * n
    order = [start]
    visited[start] = True
    for _ in range(n - 1):
        cur   = order[-1]
        cands = [j for j in range(n) if not visited[j]]
        dists = [haversine(locs[cur]['lat'], locs[cur]['lng'],
                           locs[j]['lat'],   locs[j]['lng']) for j in cands]
        max_d = max(dists) or 1.0
        bj = cands[max(
            range(len(cands)),
            key=lambda k: scores[cands[k]] * 0.6 - (dists[k] / max_d) * 0.4,
        )]
        order.append(bj)
        visited[bj] = True
    return order


# ===== 시간 추정 & 균등화 =====

def estimate_time(locs: list, road_net) -> float:
    km = 0.0
    for i in range(1, len(locs)):
        if road_net:
            _, d, _ = road_net.route_between(locs[i - 1], locs[i])
        else:
            d = haversine(locs[i-1]['lat'], locs[i-1]['lng'],
                          locs[i]['lat'],   locs[i]['lng']) * ROAD_FACTOR
        km += d
    return km / PATROL_SPEED_KPH + len(locs) * (STOP_MIN / 60)


def _kmeans(points: list, k: int, weights: list = None,
            seed: int = 42, max_iter: int = 100) -> list:
    """가중치 지원 K-Means 군집화 (순수 Python). 레이블 리스트 반환."""
    n = len(points)
    if n <= k:
        return list(range(n))
    rng = random.Random(seed)
    # k-means++ 초기화
    centers = [list(points[rng.randrange(n)])]
    for _ in range(k - 1):
        dists = []
        for p in points:
            d = min(
                (p[0] - c[0]) ** 2 + (p[1] - c[1]) ** 2
                for c in centers
            )
            dists.append(d)
        total = sum(dists)
        r = rng.random() * total
        cum = 0.0
        chosen = 0
        for i, d in enumerate(dists):
            cum += d
            if cum >= r:
                chosen = i
                break
        centers.append(list(points[chosen]))

    labels = [0] * n
    for _ in range(max_iter):
        # 할당
        new_labels = []
        for p in points:
            best_c = min(range(k),
                         key=lambda c: (p[0]-centers[c][0])**2 + (p[1]-centers[c][1])**2)
            new_labels.append(best_c)
        if new_labels == labels:
            break
        labels = new_labels
        # 중심 갱신 (가중치 적용)
        for c in range(k):
            idxs = [i for i, l in enumerate(labels) if l == c]
            if not idxs:
                continue
            if weights:
                wsum = sum(weights[i] for i in idxs)
                if wsum > 0:
                    centers[c][0] = sum(points[i][0] * weights[i] for i in idxs) / wsum
                    centers[c][1] = sum(points[i][1] * weights[i] for i in idxs) / wsum
                    continue
            centers[c][0] = sum(points[i][0] for i in idxs) / len(idxs)
            centers[c][1] = sum(points[i][1] for i in idxs) / len(idxs)
    return labels


def _mean(vals: list) -> float:
    return sum(vals) / len(vals) if vals else 0.0


def _argmin(vals: list) -> int:
    return min(range(len(vals)), key=lambda i: vals[i])


def balance_clusters(clusters: list, scores_per_cluster: list,
                     road_net, period: str, ctx: dict) -> tuple:
    """
    요원별 순찰 시간 균등화.
    반환: (clusters, scores_per_cluster)
    """
    for iteration in range(BALANCE_MAX_ITER):
        times = [estimate_time(c, road_net) for c in clusters]
        mx, mn = max(times), min(times)
        if mx - mn <= BALANCE_THRESH_H:
            print(f"  균등화 완료: {iteration}회 이동, 편차 {(mx-mn)*60:.0f}분")
            break
        busy_i = times.index(mx)
        idle_i = times.index(mn)
        if len(clusters[busy_i]) <= 1:
            break
        # 바쁜 구역: 스코어 낮고 한가한 구역에 가까운 지점 이동
        idle_lat = _mean([loc['lat'] for loc in clusters[idle_i]])
        idle_lng = _mean([loc['lng'] for loc in clusters[idle_i]])
        cand_scores = [
            haversine(loc['lat'], loc['lng'], idle_lat, idle_lng)
            - scores_per_cluster[busy_i][idx] * 8
            for idx, loc in enumerate(clusters[busy_i])
        ]
        mv = _argmin(cand_scores)
        moved = clusters[busy_i].pop(mv)
        scores_per_cluster[busy_i].pop(mv)
        # 이동한 지점의 스코어를 새 구역에서 재계산
        clusters[idle_i].append(moved)
        scores_per_cluster[idle_i].append(score_period(moved, period, ctx))
    else:
        times = [estimate_time(c, road_net) for c in clusters]
        print(f"  균등화 종료: 편차 {(max(times)-min(times))*60:.0f}분")
    return clusters, scores_per_cluster


# ===== 요원 노선 구성 =====

def build_guard(gid: int, cluster: list, cluster_scores: list,
                period: str, road_net, color: str, ctx: dict) -> dict:
    tsp_order = greedy_tsp(cluster, cluster_scores)
    ordered   = [cluster[i] for i in tsp_order]
    ord_scores = [cluster_scores[i] for i in tsp_order]

    route_coords: list = []
    wps: list = []
    total_km = 0.0

    for seq, loc in enumerate(ordered):
        if seq == 0:
            if road_net:
                k, _ = road_net.snap(loc['lat'], loc['lng'])
                pt = list(road_net.coords[k]) if k else [loc['lat'], loc['lng']]
            else:
                pt = [loc['lat'], loc['lng']]
            route_coords.append(pt)
            leg_km = 0.0
        else:
            prev = ordered[seq - 1]
            if road_net:
                seg, leg_km, seg_road = road_net.route_between(prev, loc)
                route_coords.extend(seg[1:] if len(seg) > 1 else seg)
                if not seg_road:
                    print(f"    [보간폴백] 요원{gid+1} {prev['dong']}→{loc['dong']} "
                          f"({leg_km:.1f}km)")
            else:
                route_coords.append([loc['lat'], loc['lng']])
                leg_km = haversine(prev['lat'], prev['lng'],
                                   loc['lat'],  loc['lng']) * ROAD_FACTOR
        total_km += leg_km

        period_score = ord_scores[seq]
        base_prob    = float(loc.get('probability', 0.0))
        # 모든 시간대 스코어 계산
        sc_am    = score_period(loc, 'AM',    ctx)
        sc_pm    = score_period(loc, 'PM',    ctx)
        sc_night = score_period(loc, 'NIGHT', ctx)

        wps.append({
            'order':             seq + 1,
            'dong':              loc['dong'],
            'myeon':             loc.get('myeon', ''),
            'lat':               loc['lat'],
            'lng':               loc['lng'],
            'probability':       period_score,        # 현재 시간대 스코어
            'level':             get_level(period_score),
            'prob_base':         round(base_prob, 3),  # AI 기본 확률
            'prob_am':           sc_am,
            'prob_pm':           sc_pm,
            'prob_night':        sc_night,
            'level_am':          get_level(sc_am),
            'level_pm':          get_level(sc_pm),
            'level_night':       get_level(sc_night),
            'top_cause':         loc.get('top_cause', '기타'),
            'priority_reason':   get_priority_reason(loc, period, ctx),
            'dist_from_prev_km': round(leg_km, 2),
            'road_based':        road_net is not None,
        })

    probs     = [wp['probability'] for wp in wps]
    est_hours = total_km / PATROL_SPEED_KPH + len(ordered) * (STOP_MIN / 60)
    avg_risk  = round(_mean(probs), 3)

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


def build_period(predictions: list, period: str, road_net, ctx: dict) -> dict:
    """시간대 하나에 대한 전체 노선 딕셔너리 생성."""
    # 시간대별 스코어 계산 후 중복 제거 + 정렬
    scored = []
    seen: set = set()
    for p in predictions:
        key = (round(p['lat'], 3), round(p['lng'], 3))
        if (key in seen
                or (abs(p['lat'] - DEFAULT_LAT) < 0.0001
                    and abs(p['lng'] - DEFAULT_LNG) < 0.0001)):
            continue
        seen.add(key)
        sc = score_period(p, period, ctx)
        scored.append((sc, p))

    scored.sort(key=lambda x: -x[0])
    unique = [p for _, p in scored[:WAYPOINTS_TOTAL]]
    unique_scores = [sc for sc, _ in scored[:WAYPOINTS_TOTAL]]

    if len(unique) < NUM_GUARDS:
        print(f"  [{period}] 순찰 지점 부족: {len(unique)}개")
        return {'period_label': PERIOD_LABELS[period], 'guards': [],
                'waypoints_total': 0, 'balance_score': 0.0, 'top_dongs': []}

    # 선택된 상위 지역 출력
    print(f"  [{period}] 상위 8개 순찰지: "
          + ", ".join(f"{p['dong']}({sc:.3f})" for sc, p in scored[:8]))

    # K-Means 군집화 (시간대 스코어 가중치 — 순수 Python)
    labels = _kmeans(
        [[p['lat'], p['lng']] for p in unique],
        NUM_GUARDS,
        weights=unique_scores,
        seed=42,
    )

    cluster_avg = {
        c: _mean([unique_scores[i] for i in range(len(unique)) if labels[i] == c])
        for c in range(NUM_GUARDS)
    }
    rank_map = {c: r for r, (c, _) in
                enumerate(sorted(cluster_avg.items(), key=lambda x: -x[1]))}

    clusters: list = []
    cluster_scores_list: list = []
    for gid in range(NUM_GUARDS):
        orig_c = next(c for c, r in rank_map.items() if r == gid)
        idxs   = [i for i in range(len(unique)) if labels[i] == orig_c]
        clusters.append([unique[i] for i in idxs])
        cluster_scores_list.append([unique_scores[i] for i in idxs])

    # 시간 균등화
    clusters, cluster_scores_list = balance_clusters(
        clusters, cluster_scores_list, road_net, period, ctx)

    # 요원별 노선 구성
    guards = [
        build_guard(gid, clusters[gid], cluster_scores_list[gid],
                    period, road_net, GUARD_COLORS[gid], ctx)
        for gid in range(NUM_GUARDS)
    ]

    times = [g['estimated_hours'] for g in guards]
    avg_t = _mean(times)
    spread = max(times) - min(times)
    balance_score = round(max(0.0, 1.0 - spread / (avg_t + 0.001)), 3)

    print(f"          요원 " + " / ".join(
        f"{g['stop_count']}개소 {g['total_distance_km']}km {g['estimated_hours']:.1f}h"
        for g in guards))
    print(f"          균등화: {balance_score:.2f}  편차: {spread*60:.0f}분")

    return {
        'period_label':    PERIOD_LABELS[period],
        'guards':          guards,
        'waypoints_total': len(unique),
        'balance_score':   balance_score,
        'top_dongs':       [p['dong'] for _, p in scored[:8]],
    }


# ===== MAIN =====

def main():
    global NUM_GUARDS, GUARD_COLORS

    print("=" * 62)
    print("화성시 감시요원 최적 순찰 노선 v3")
    print("=" * 62)

    with open(INPUT_PATH, 'r', encoding='utf-8') as f:
        risk_data = json.load(f)
    predictions = risk_data['predictions']
    actual_high = risk_data.get('summary', {}).get('high_risk', 0)
    print(f"AI 예측 읍면동: {len(predictions)}개  (HIGH: {actual_high}개)")

    # optimal_guard_count.json 룩업테이블로 NUM_GUARDS 자동 결정
    guard_selection_reason = None
    guard_count_path = os.path.join(BASE_DIR, 'public', 'data', 'optimal_guard_count.json')
    if os.path.exists(guard_count_path):
        try:
            with open(guard_count_path, 'r', encoding='utf-8') as f:
                gc_data = json.load(f)

            lookup_key = f"high_{min(actual_high, 15)}"
            table      = gc_data.get('high_count_table', {})

            if lookup_key in table:
                rec    = table[lookup_key]
                source = f"HIGH {actual_high}개 → 룩업테이블"
            else:
                rec    = gc_data.get('recommended_guards', NUM_GUARDS)
                source = "전역 추천"

            if isinstance(rec, int) and 1 <= rec <= 10:
                NUM_GUARDS   = max(3, rec)
                GUARD_COLORS = (_COLOR_PALETTE * ((NUM_GUARDS // len(_COLOR_PALETTE)) + 1))[:NUM_GUARDS]
                min_note = " (최소 3명 적용)" if rec < 3 else ""
                guard_selection_reason = (
                    f"HIGH {actual_high}개 → 요원 {NUM_GUARDS}명 (엘보우 기반{min_note})"
                )
                print(f"  📊 {guard_selection_reason}  [{source}]")
        except Exception as e:
            print(f"  ⚠️  optimal_guard_count.json 읽기 실패 ({e}) — 기본값 {NUM_GUARDS}명 사용")

    # 컨텍스트 (FIRMS, 기상 FWI)
    print("\n[ 컨텍스트 수집 ]")
    ctx = build_context(predictions)
    print(f"  max_hist_count={ctx['max_hist_count']}  "
          f"FWI={ctx['fwi_score']}  "
          f"FIRMS={len(ctx['firms_locations'])}건")

    # OSM 도로망
    road_net = None
    if os.path.exists(OSM_PATH):
        with open(OSM_PATH, 'r', encoding='utf-8') as f:
            osm = json.load(f)
        roads = osm.get('roads', [])
        if roads:
            print(f"\nOSM 도로 로드: {len(roads)}개 구간")
            road_net = RoadNetwork(roads)
    if road_net is None:
        print("\nosm_roads.json 없음 — 직선거리×1.25 폴백")

    # 시간대별 노선
    print("\n[ 시간대별 최적 노선 계산 ]")
    time_periods: dict = {}
    for period in ('ALL', 'AM', 'PM', 'NIGHT'):
        print(f"\n── {PERIOD_LABELS[period]} ──")
        time_periods[period] = build_period(predictions, period, road_net, ctx)

    # 시간대별 순찰 지점 비교
    print("\n[ 시간대별 선택 지점 비교 ]")
    period_dongs = {
        p: set(wp['dong'] for g in data['guards'] for wp in g['waypoints'])
        for p, data in time_periods.items() if data.get('guards')
    }
    for pa, pb in [('AM', 'PM'), ('PM', 'NIGHT'), ('AM', 'NIGHT')]:
        if pa in period_dongs and pb in period_dongs:
            inter = period_dongs[pa] & period_dongs[pb]
            union = period_dongs[pa] | period_dongs[pb]
            diff  = len(union) - len(inter)
            print(f"  {pa}∩{pb} 교집합 {len(inter)}개, 차이 {diff}개")

    # 저장
    output = {
        'timestamp':               datetime.now().isoformat(),
        'algorithm':               'K-Means 군집화 + Greedy TSP + 시간대별 스코어링 + 시간 균등화',
        'road_based':              road_net is not None,
        'osm_source':              'OpenStreetMap' if road_net else '없음 (직선거리 폴백)',
        'num_guards':              NUM_GUARDS,
        'guard_selection_reason':  guard_selection_reason or f"기본값 {NUM_GUARDS}명",
        'min_guards_note':         '최소 3명 (화성시 3개 권역: 서부/중부/동부)',
        'patrol_speed_kph':        PATROL_SPEED_KPH,
        'stop_minutes':            STOP_MIN,
        'waypoints_total':         time_periods['ALL']['waypoints_total'],
        'firms_count':             len(ctx['firms_locations']),
        'fwi_score':               ctx['fwi_score'],
        'time_periods':            time_periods,
        'guards':                  time_periods['ALL']['guards'],   # v1 하위 호환
    }

    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*62}")
    print(f"✅ 저장 완료 → {OUTPUT_PATH}")
    print(f"   도로 기반: {'OSM' if road_net else '직선 폴백'}")
    for period, data in time_periods.items():
        if not data.get('guards'):
            continue
        top4 = data.get('top_dongs', [])[:4]
        print(f"   [{period}] 상위 4: {', '.join(top4)}")


if __name__ == '__main__':
    main()
