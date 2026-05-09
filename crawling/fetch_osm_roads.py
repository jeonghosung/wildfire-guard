#!/usr/bin/env python3
"""
화성시 OpenStreetMap 도로 데이터 수집 스크립트
출처: OpenStreetMap Overpass API (무료, API 키 불필요)
실행: python crawling/fetch_osm_roads.py
출력: public/data/osm_roads.json

화성시 경계 Bbox: 위도 36.95~37.45, 경도 126.55~127.15
수집 대상 도로: primary / secondary / tertiary / unclassified / residential
"""

import json
import sys
import time
import overpy
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ===== CONFIG =====
LOCATION = '경기도 화성시'

# 화성시 경계 (south, west, north, east)
BBOX = (36.95, 126.55, 37.45, 127.15)

# 수집 대상 도로 유형 (순찰 경로 계획에 유용한 등급)
TARGET_HIGHWAY = [
    'primary',       # 국도
    'secondary',     # 지방도
    'tertiary',      # 3차 도로
    'unclassified',  # 비분류 도로
    'residential',   # 주거지 도로
]

BASE_DIR    = Path(__file__).parent.parent
OUTPUT_DIR  = BASE_DIR / 'public' / 'data'
OUTPUT_FILE = OUTPUT_DIR / 'osm_roads.json'

KST = timezone(timedelta(hours=9))

# 도로 유형별 메타 (순찰 우선순위 색상)
HIGHWAY_META = {
    'primary':       {'priority': 1, 'color': '#ff6644', 'label': '국도'},
    'secondary':     {'priority': 2, 'color': '#ff9933', 'label': '지방도'},
    'tertiary':      {'priority': 3, 'color': '#ffcc33', 'label': '3차 도로'},
    'unclassified':  {'priority': 4, 'color': '#88bbdd', 'label': '비분류 도로'},
    'residential':   {'priority': 5, 'color': '#aabbcc', 'label': '주거지 도로'},
}


# ===== FETCH =====

def build_overpass_query() -> str:
    s, w, n, e = BBOX
    highway_filter = '|'.join(TARGET_HIGHWAY)
    return f"""
[out:json][timeout:60];
(
  way["highway"~"^({highway_filter})$"]({s},{w},{n},{e});
);
out body;
>;
out skel qt;
"""


def fetch_roads() -> tuple[list, dict]:
    """Overpass API로 화성시 도로 데이터 수집. (ways, nodes_map) 반환."""
    api   = overpy.Overpass()
    query = build_overpass_query()

    print(f"  Overpass 쿼리 실행 중... (bbox={BBOX})")
    result = api.query(query)

    # 노드 좌표 맵 구성
    nodes_map = {node.id: (float(node.lat), float(node.lng)) for node in result.nodes}

    roads = []
    for way in result.ways:
        hw_type = way.tags.get('highway', '')
        if hw_type not in TARGET_HIGHWAY:
            continue

        # 경로 좌표 (노드 순서대로)
        coords = []
        for nid in way._node_ids:
            if nid in nodes_map:
                coords.append(nodes_map[nid])

        if len(coords) < 2:
            continue

        meta = HIGHWAY_META.get(hw_type, {'priority': 9, 'color': '#888', 'label': hw_type})
        name = (way.tags.get('name:ko')
                or way.tags.get('name')
                or way.tags.get('ref')
                or '')

        roads.append({
            'id':           way.id,
            'name':         name,
            'highway_type': hw_type,
            'label':        meta['label'],
            'priority':     meta['priority'],
            'color':        meta['color'],
            'oneway':       way.tags.get('oneway', 'no') == 'yes',
            'maxspeed':     way.tags.get('maxspeed'),
            'ref':          way.tags.get('ref', ''),
            'node_count':   len(coords),
            'coords':       coords,          # [[lat, lng], ...]
        })

    roads.sort(key=lambda r: (r['priority'], r['name']))
    return roads, nodes_map


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
        'source':     'OpenStreetMap Overpass API',
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
