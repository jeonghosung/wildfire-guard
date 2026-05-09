#!/usr/bin/env python3
"""
화성시 산불위험예보정보 수집 스크립트
출처: 산림청 국립산림과학원 forestPointV2 / getFireDangerInfo
실행: python crawling/fetch_forest_risk.py
출력: public/data/forest_risk.json
"""

import json
import sys
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ===== CONFIG =====
SERVICE_KEY = 'ee17a36e905254adb206454f36c179c3449720f4970173782f75869f788af660'
BASE_URL    = 'https://apis.data.go.kr/1400377/forestPointV2/getFireDangerInfo'
LOCATION    = '경기도 화성시'

BASE_DIR    = Path(__file__).parent.parent
OUTPUT_DIR  = BASE_DIR / 'public' / 'data'
OUTPUT_FILE = OUTPUT_DIR / 'forest_risk.json'

KST = timezone(timedelta(hours=9))

# 산불위험지수 등급 → 레벨 매핑
DANGER_GRADE = {
    1: {'level': 'LOW',    'label': '낮음',     'color': '#33cc77'},
    2: {'level': 'LOW',    'label': '보통',     'color': '#99cc33'},
    3: {'level': 'MEDIUM', 'label': '높음',     'color': '#ffcc00'},
    4: {'level': 'HIGH',   'label': '매우 높음', 'color': '#ff8c00'},
    5: {'level': 'HIGH',   'label': '위험',     'color': '#ff3333'},
}

# 화성시 주요 읍면동 대표 지점 (위도/경도 기반 요청용)
HWASEONG_POINTS = [
    {'name': '남양읍',  'lat': 37.205, 'lng': 126.718},
    {'name': '향남읍',  'lat': 37.057, 'lng': 126.832},
    {'name': '우정읍',  'lat': 37.070, 'lng': 126.672},
    {'name': '서신면',  'lat': 37.180, 'lng': 126.607},
    {'name': '팔탄면',  'lat': 37.103, 'lng': 126.879},
    {'name': '봉담읍',  'lat': 37.215, 'lng': 126.923},
    {'name': '송산면',  'lat': 37.142, 'lng': 126.695},
    {'name': '마도면',  'lat': 37.133, 'lng': 126.712},
    {'name': '양감면',  'lat': 37.020, 'lng': 126.882},
    {'name': '정남면',  'lat': 37.178, 'lng': 126.992},
]


# ===== FETCH =====

def fetch_risk_by_point(lat: float, lng: float, date_str: str) -> dict | None:
    """단일 지점의 산불위험예보 조회."""
    params = {
        'serviceKey': SERVICE_KEY,
        'numOfRows':  10,
        'pageNo':     1,
        'dataType':   'JSON',
        'searchDate': date_str,
        'lat':        lat,
        'lon':        lng,
    }
    try:
        resp = requests.get(BASE_URL, params=params, timeout=15)
        resp.raise_for_status()
        body = resp.json()

        header = body.get('response', {}).get('header', {})
        code   = header.get('resultCode', '')
        if code not in ('00', '0000'):
            print(f"    API 경고 [{code}]: {header.get('resultMsg', '')} "
                  f"→ lat={lat} lng={lng}")
            return None

        items = body.get('response', {}).get('body', {}).get('items', {}).get('item', [])
        if not isinstance(items, list):
            items = [items] if items else []
        return items[0] if items else None

    except Exception as e:
        print(f"    지점 요청 실패 (lat={lat}): {e}")
        return None


def fetch_all_region(date_str: str) -> list:
    """화성시 전체 데이터를 경기도 필터로 일괄 조회."""
    params = {
        'serviceKey': SERVICE_KEY,
        'numOfRows':  500,
        'pageNo':     1,
        'dataType':   'JSON',
        'searchDate': date_str,
    }
    try:
        resp = requests.get(BASE_URL, params=params, timeout=20)
        resp.raise_for_status()
        body = resp.json()

        header = body.get('response', {}).get('header', {})
        code   = header.get('resultCode', '')
        if code not in ('00', '0000'):
            print(f"  API 오류 [{code}]: {header.get('resultMsg', '')}")
            return []

        items = body.get('response', {}).get('body', {}).get('items', {}).get('item', [])
        if not isinstance(items, list):
            items = [items] if items else []

        # 화성시 / 경기도 필터링
        filtered = [
            it for it in items
            if '화성' in str(it.get('RS_NM', ''))
            or '화성' in str(it.get('CTPV_NM', ''))
            or ('경기' in str(it.get('RS_NM', ''))
                and '화성' in str(it.get('RS_NM', '')))
        ]
        print(f"  전체 {len(items)}건 조회 → 화성 관련 {len(filtered)}건 필터")
        return filtered

    except Exception as e:
        print(f"  전체 조회 실패: {e}")
        return []


# ===== MAIN =====

def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    now      = datetime.now(KST)
    date_str = now.strftime('%Y%m%d')
    print(f"[산림청] 산불위험예보 수집: {LOCATION} ({date_str})")

    # 1차: 전체 조회 후 화성 필터
    region_items = fetch_all_region(date_str)

    # 2차: 전체 조회 결과가 없으면 지점별 개별 조회
    forecasts = []
    if region_items:
        for item in region_items:
            grade = int(item.get('FIRE_DANG_GRD', item.get('DANGER_GRD', 0)) or 0)
            info  = DANGER_GRADE.get(grade, {'level': 'NONE', 'label': '없음', 'color': '#888'})
            forecasts.append({
                'region_code':       item.get('RS_CD', item.get('SIDO_CD', '')),
                'region_name':       item.get('RS_NM', item.get('CTPV_NM', '')),
                'forecast_datetime': item.get('FCST_DT', item.get('TM', date_str)),
                'danger_grade':      grade,
                'level':             info['level'],
                'label':             info['label'],
                'color':             info['color'],
            })
    else:
        print("  지점별 개별 조회로 전환...")
        for pt in HWASEONG_POINTS:
            item = fetch_risk_by_point(pt['lat'], pt['lng'], date_str)
            if item is None:
                continue
            grade = int(item.get('FIRE_DANG_GRD', item.get('DANGER_GRD', 0)) or 0)
            info  = DANGER_GRADE.get(grade, {'level': 'NONE', 'label': '없음', 'color': '#888'})
            forecasts.append({
                'region_name':       pt['name'],
                'lat':               pt['lat'],
                'lng':               pt['lng'],
                'forecast_datetime': item.get('FCST_DT', date_str),
                'danger_grade':      grade,
                'level':             info['level'],
                'label':             info['label'],
                'color':             info['color'],
            })

    # 요약 집계
    level_counts = {'HIGH': 0, 'MEDIUM': 0, 'LOW': 0, 'NONE': 0}
    for f in forecasts:
        lv = f.get('level', 'NONE')
        level_counts[lv] = level_counts.get(lv, 0) + 1

    max_grade = max((f['danger_grade'] for f in forecasts), default=0)
    overall   = DANGER_GRADE.get(max_grade, {'level': 'NONE', 'label': '없음', 'color': '#888'})

    result = {
        'timestamp':     now.isoformat(),
        'location':      LOCATION,
        'search_date':   date_str,
        'forecast_count': len(forecasts),
        'level_counts':  level_counts,
        'overall_level': overall['level'],
        'overall_label': overall['label'],
        'forecasts':     forecasts,
    }

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"✅ 저장 완료: {OUTPUT_FILE} ({len(forecasts)}건)")
    print(f"   종합 위험 등급: [{overall['level']}] {overall['label']}")
    print(f"   HIGH {level_counts['HIGH']} / MEDIUM {level_counts['MEDIUM']} "
          f"/ LOW {level_counts['LOW']}")


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f"❌ 수집 실패: {e}", file=sys.stderr)
        sys.exit(1)
