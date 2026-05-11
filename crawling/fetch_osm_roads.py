#!/usr/bin/env python3
"""
화성시 OpenStreetMap 도로 데이터 수집 스크립트
출처: osmnx (1순위) → Overpass API 직접 호출 (폴백)
실행: python crawling/fetch_osm_roads.py
출력: public/data/osm_roads.json

화성시 경계 Bbox: 위도 36.99~37.31, 경도 126.56~127.11 (행정 경계 기준 정밀화)
수집 대상 도로: primary(국도) / secondary(지방도) / tertiary(시도)
  - unclassified/residential 제외 (파일 크기 25MB 이하 유지)
"""

import json
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ===== CONFIG =====
LOCATION = '경기도 화성시'

# 화성시 행정 경계 (south, west, north, east) — 실제 읍면동 좌표 기반 정밀화
# 구 bbox (36.95~37.45, 126.55~127.15) 대비 면적 약 59% 축소
BBOX = (36.99, 126.56, 37.31, 127.11)

# 수집 대상 도로 유형 — residential 추가 (주거지 연결도로)
TARGET_HIGHWAY = [
    'primary',       # 국도
    'secondary',     # 지방도
    'tertiary',      # 시도
    'unclassified',  # 비분류도로 (마을 진입로·연결도로)
    'residential',   # 주거지도로 (주택가·단지 내 도로)
]

BASE_DIR    = Path(__file__).parent.parent
OUTPUT_DIR  = BASE_DIR / 'public' / 'data'
OUTPUT_FILE = OUTPUT_DIR / 'osm_roads.json'

KST = timezone(timedelta(hours=9))

# 도로 유형별 메타 (순찰 우선순위 색상)
HIGHWAY_META = {
    'primary':      {'priority': 1, 'color': '#ff6644', 'label': '국도'},
    'secondary':    {'priority': 2, 'color': '#ff9933', 'label': '지방도'},
    'tertiary':     {'priority': 3, 'color': '#ffcc44', 'label': '시도'},
    'unclassified': {'priority': 4, 'color': '#aabbcc', 'label': '비분류도로'},
    'residential':  {'priority': 5, 'color': '#99aabb', 'label': '주거지도로'},
}


# ===== FETCH =====

OVERPASS_MIRRORS = [
    'https://overpass-api.de/api/interpreter',
    'https://overpass.kumi.systems/api/interpreter',
    'https://maps.mail.ru/osm/tools/overpass/api/interpreter',
]
MAX_RETRIES = 3
RETRY_DELAY = 30  # seconds


def build_overpass_query() -> str:
    s, w, n, e = BBOX
    highway_filter = '|'.join(TARGET_HIGHWAY)
    return (
        f'[out:json][timeout:120];'
        f'(way["highway"~"^({highway_filter})$"]({s},{w},{n},{e}););'
        f'out body;>;out skel qt;'
    )


# ── 공통: osmnx 그래프 → roads 리스트 변환 ──────────────────────────────
def _scalar(v):
    """list 값이면 첫 번째 원소, None이면 빈 문자열 반환."""
    if isinstance(v, list):
        return v[0] if v else ''
    return v if v is not None else ''


def _graph_to_roads(G) -> list:
    """osmnx MultiDiGraph를 roads 리스트로 변환 (기존 JSON 포맷 유지)."""
    import osmnx as ox
    edges = ox.graph_to_gdfs(G, nodes=False)
    roads = []
    for _, row in edges.iterrows():
        hw_type = str(_scalar(row.get('highway', '')))
        if hw_type not in TARGET_HIGHWAY:
            continue
        try:
            coords = [(float(lat), float(lng)) for lng, lat in row.geometry.coords]
        except Exception:
            continue
        if len(coords) < 2:
            continue
        meta  = HIGHWAY_META.get(hw_type, {'priority': 9, 'color': '#888', 'label': hw_type})
        osmid = _scalar(row.get('osmid', 0))
        roads.append({
            'id':           int(osmid) if osmid else 0,
            'name':         str(_scalar(row.get('name', ''))),
            'highway_type': hw_type,
            'label':        meta['label'],
            'priority':     meta['priority'],
            'color':        meta['color'],
            'oneway':       bool(row.get('oneway', False)),
            'maxspeed':     str(_scalar(row.get('maxspeed', ''))) or None,
            'ref':          str(_scalar(row.get('ref', ''))),
            'node_count':   len(coords),
            'coords':       coords,
        })
    roads.sort(key=lambda r: (r['priority'], r['name']))
    return roads


# ── 1순위: osmnx ─────────────────────────────────────────────────────────
def fetch_roads_osmnx() -> list:
    """osmnx로 화성시 도로 수집. Overpass 미러 서버 순차 시도."""
    import osmnx as ox
    cf = '["highway"~"^(' + '|'.join(TARGET_HIGHWAY) + ')$"]'

    last_error = None
    for mirror in OVERPASS_MIRRORS:
        try:
            ox.settings.overpass_url        = mirror
            ox.settings.timeout             = 120
            ox.settings.overpass_rate_limit = False
            print(f"  [osmnx] 서버: {mirror}")
            G = ox.graph_from_bbox(
                north=BBOX[2], south=BBOX[0],
                east=BBOX[3],  west=BBOX[1],
                custom_filter=cf,
                retain_all=True,
            )
            roads = _graph_to_roads(G)
            print(f"  ✅ osmnx 수집 완료: {len(roads)}개 도로")
            return roads
        except Exception as e:
            last_error = e
            print(f"  ⚠ osmnx [{mirror}] 실패: {type(e).__name__}: {e}", file=sys.stderr)

    raise RuntimeError(f"osmnx 모든 서버 실패: {last_error}")


# ── 2순위: Overpass API 직접 호출 ────────────────────────────────────────
def fetch_roads_overpass() -> tuple:
    """Overpass API 직접 호출. 실패 시 미러 서버 순환 재시도."""
    query = build_overpass_query()
    data  = urllib.parse.urlencode({'data': query}).encode()

    last_error = None
    for attempt in range(MAX_RETRIES):
        mirror = OVERPASS_MIRRORS[attempt % len(OVERPASS_MIRRORS)]
        if attempt == 0:
            print(f"  [Overpass] 쿼리 실행 중... 서버: {mirror}")
        else:
            print(f"  ⏳ {RETRY_DELAY}초 대기 후 재시도 {attempt}/{MAX_RETRIES - 1}... [{mirror}]")
            time.sleep(RETRY_DELAY)
        try:
            req = urllib.request.Request(
                mirror, data=data,
                headers={'User-Agent': 'wildfire-guard/1.0'},
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                raw = json.loads(resp.read().decode('utf-8'))
            break
        except Exception as e:
            last_error = e
            print(f"  ⚠ 실패 ({type(e).__name__}: {e})", file=sys.stderr)
    else:
        raise RuntimeError(f"Overpass API {MAX_RETRIES}회 재시도 모두 실패: {last_error}")

    elements  = raw.get('elements', [])
    nodes_map = {
        e['id']: (float(e['lat']), float(e['lon']))
        for e in elements if e['type'] == 'node'
    }
    roads = []
    for e in elements:
        if e['type'] != 'way':
            continue
        tags    = e.get('tags', {})
        hw_type = tags.get('highway', '')
        if hw_type not in TARGET_HIGHWAY:
            continue
        coords = [nodes_map[nid] for nid in e.get('nodes', []) if nid in nodes_map]
        if len(coords) < 2:
            continue
        meta = HIGHWAY_META.get(hw_type, {'priority': 9, 'color': '#888', 'label': hw_type})
        name = tags.get('name:ko') or tags.get('name') or tags.get('ref') or ''
        roads.append({
            'id':           e['id'],
            'name':         name,
            'highway_type': hw_type,
            'label':        meta['label'],
            'priority':     meta['priority'],
            'color':        meta['color'],
            'oneway':       tags.get('oneway', 'no') == 'yes',
            'maxspeed':     tags.get('maxspeed'),
            'ref':          tags.get('ref', ''),
            'node_count':   len(coords),
            'coords':       coords,
        })
    roads.sort(key=lambda r: (r['priority'], r['name']))
    return roads, nodes_map


# ── 통합 진입점 ──────────────────────────────────────────────────────────
def fetch_roads() -> tuple:
    """osmnx 우선 시도 → 실패 시 Overpass API 직접 호출."""
    try:
        print("  1순위: osmnx 방식 시도")
        roads = fetch_roads_osmnx()
        return roads, {}
    except Exception as e:
        print(f"  ⚠ osmnx 실패 ({e}), 2순위: Overpass API 직접 호출", file=sys.stderr)

    return fetch_roads_overpass()


# ===== ANALYSIS =====

def build_summary(roads: list) -> dict:
    """도로 유형별 건수 및 순찰 활용도 집계."""
    type_counts: dict[str, int] = {}
    for r in roads:
        hw = r['highway_type']
        type_counts[hw] = type_counts.get(hw, 0) + 1

    total_segments = len(roads)
    total_nodes    = sum(r['node_count'] for r in roads)

    return {
        'total_roads':    total_segments,
        'total_nodes':    total_nodes,
        'by_type':        {
            hw: {
                'count': cnt,
                'label': HIGHWAY_META.get(hw, {}).get('label', hw),
                'color': HIGHWAY_META.get(hw, {}).get('color', '#888'),
            }
            for hw, cnt in sorted(type_counts.items(),
                                  key=lambda x: HIGHWAY_META.get(x[0], {}).get('priority', 9))
        },
    }


# ===== MAIN =====

def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    now = datetime.now(KST)
    print(f"[OSM] 화성시 도로 데이터 수집: {LOCATION}")
    print(f"  대상 유형: {', '.join(TARGET_HIGHWAY)}")

    roads, _ = fetch_roads()
    summary  = build_summary(roads)

    result = {
        'timestamp':  now.isoformat(),
        'location':   LOCATION,
        'bbox': {
            'south': BBOX[0], 'west': BBOX[1],
            'north': BBOX[2], 'east': BBOX[3],
        },
        'source':     'OpenStreetMap (osmnx / Overpass API)',
        'summary':    summary,
        'roads':      roads,
    }

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"✅ 저장 완료: {OUTPUT_FILE}")
    print(f"   총 {summary['total_roads']}개 도로 구간 / {summary['total_nodes']}개 노드")
    for hw_type, info in summary['by_type'].items():
        print(f"   {info['label']:<12}: {info['count']}개")


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f"❌ 수집 실패: {e}", file=sys.stderr)
        sys.exit(1)
