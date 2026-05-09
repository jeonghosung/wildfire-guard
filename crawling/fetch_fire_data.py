#!/usr/bin/env python3
"""
화성시 산림청 산불발생통계 수집 스크립트
출처: 산림청 forestStusService / getfirestatsservice
실행: python crawling/fetch_fire_data.py
출력: public/data/fire_history.json

※ API는 XML만 반환하며 서버 측 지역 필터가 미지원되므로
  전체 데이터를 순회하여 화성(locgungu='화성') 데이터만 추출합니다.
"""

import json
import sys
import time
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path
from xml.etree import ElementTree as ET

# ===== CONFIG =====
SERVICE_KEY = 'ee17a36e905254adb206454f36c179c3449720f4970173782f75869f788af660'
BASE_URL    = 'https://apis.data.go.kr/1400000/forestStusService/getfirestatsservice'
FILTER_LOCSI   = '경기'    # locsi 필드값 (약칭)
FILTER_LOCGUNGU = '화성'   # locgungu 필드값 (약칭)
NUM_OF_ROWS = 100

BASE_DIR    = Path(__file__).parent.parent
OUTPUT_DIR  = BASE_DIR / 'public' / 'data'
OUTPUT_FILE = OUTPUT_DIR / 'fire_history.json'

KST = timezone(timedelta(hours=9))


# ===== UTILS =====

def safe_float(v):
    try:
        return float(v) if v else None
    except (TypeError, ValueError):
        return None


def safe_int(v):
    try:
        return int(v) if v else None
    except (TypeError, ValueError):
        return None


def parse_item(item: ET.Element) -> dict:
    """XML <item> 요소를 딕셔너리로 변환."""
    def txt(tag):
        el = item.find(tag)
        return el.text.strip() if el is not None and el.text else ''

    return {
        'year':             safe_int(txt('startyear')),
        'month':            safe_int(txt('startmonth')),
        'day':              safe_int(txt('startday')),
        'start_time':       txt('starttime'),
        'end_year':         safe_int(txt('endyear')),
        'end_month':        safe_int(txt('endmonth')),
        'end_day':          safe_int(txt('endday')),
        'end_time':         txt('endtime'),
        'sido':             txt('locsi'),
        'sigungu':          txt('locgungu'),
        'emd':              txt('locdong'),
        'myeon':            txt('locmenu'),
        'bunji':            txt('locbunji'),
        'cause':            txt('firecause') or '미상',
        'damage_area_ha':   safe_float(txt('damagearea')),
    }


# ===== FETCH =====

def get_total_count() -> int:
    resp = requests.get(BASE_URL, params={
        'serviceKey': SERVICE_KEY, 'numOfRows': 1, 'pageNo': 1,
    }, timeout=30)
    resp.raise_for_status()
    root = ET.fromstring(resp.text)
    return int(root.findtext('.//totalCount') or 0)


def fetch_page_xml(page_no: int) -> list[ET.Element]:
    resp = requests.get(BASE_URL, params={
        'serviceKey': SERVICE_KEY,
        'numOfRows':  NUM_OF_ROWS,
        'pageNo':     page_no,
    }, timeout=30)
    resp.raise_for_status()
    root = ET.fromstring(resp.text)

    code = root.findtext('.//resultCode', '')
    if code != '00':
        msg = root.findtext('.//resultMsg', 'UNKNOWN')
        raise ValueError(f"API 오류 [{code}]: {msg}")

    return root.findall('.//item')


def fetch_hwaseong_records() -> list[dict]:
    """전체 데이터를 순회하며 화성시 데이터만 추출."""
    total = get_total_count()
    total_pages = (total + NUM_OF_ROWS - 1) // NUM_OF_ROWS
    print(f"  전체 {total}건 / {total_pages}페이지 순회 시작")

    records = []
    fetched = 0

    for page in range(1, total_pages + 1):
        items = fetch_page_xml(page)
        fetched += len(items)

        for item in items:
            locgungu = (item.findtext('locgungu') or '').strip()
            if locgungu == FILTER_LOCGUNGU:
                records.append(parse_item(item))

        # 진행 상황 10페이지마다 출력
        if page % 10 == 0 or page == total_pages:
            print(f"  [{page}/{total_pages}] 처리 {fetched}건 — 화성 {len(records)}건 발견")

        if not items:
            break

        time.sleep(0.2)

    return records


# ===== ANALYSIS =====

def build_dong_stats(records: list[dict]) -> dict:
    """읍면동별 발생 건수·피해면적 집계 및 취약도 점수 산출."""
    dong_map: dict[str, dict] = {}

    for r in records:
        dong = r.get('emd') or r.get('myeon') or r.get('sigungu') or '미상'
        if dong not in dong_map:
            dong_map[dong] = {'count': 0, 'total_area': 0.0, 'causes': {}}
        dong_map[dong]['count'] += 1
        dong_map[dong]['total_area'] += r.get('damage_area_ha') or 0.0
        cause = r.get('cause') or '미상'
        dong_map[dong]['causes'][cause] = dong_map[dong]['causes'].get(cause, 0) + 1

    if not dong_map:
        return {}

    max_count = max(d['count']      for d in dong_map.values())
    max_area  = max(d['total_area'] for d in dong_map.values()) or 1.0

    result = {}
    for dong, d in dong_map.items():
        score = (d['count'] / max_count) * 0.6 + (d['total_area'] / max_area) * 0.4
        result[dong] = {
            'count':      d['count'],
            'total_area': round(d['total_area'], 2),
            'score':      round(score, 3),
            'level':      'HIGH' if score >= 0.6 else 'MEDIUM' if score >= 0.3 else 'LOW',
            'top_cause':  max(d['causes'], key=d['causes'].get),
        }

    return dict(sorted(result.items(), key=lambda x: -x[1]['score']))


# ===== MAIN =====

def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"[산림청] 화성시 산불 이력 수집 시작 (locgungu='{FILTER_LOCGUNGU}')")

    records = fetch_hwaseong_records()

    records.sort(key=lambda r: (r.get('year') or 0, r.get('month') or 0, r.get('day') or 0))

    dong_stats = build_dong_stats(records)

    year_counts: dict = {}
    for r in records:
        yr = r.get('year')
        if yr:
            year_counts[yr] = year_counts.get(yr, 0) + 1

    result = {
        'timestamp':    datetime.now(KST).isoformat(),
        'location':     '경기도 화성시',
        'total_count':  len(records),
        'year_counts':  dict(sorted(year_counts.items())),
        'dong_stats':   dong_stats,
        'records':      records,
    }

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 저장 완료: {OUTPUT_FILE} ({len(records)}건)")
    print(f"   연도별: {dict(sorted(year_counts.items()))}")

    if dong_stats:
        print(f"   읍면동별 집계: {len(dong_stats)}개 지역")
        print("   ─── 취약지역 TOP 5 ───")
        for dong, stat in list(dong_stats.items())[:5]:
            bar = '█' * max(1, int(stat['score'] * 10))
            print(f"   {dong:<10} {bar:<12} {stat['count']}건 / "
                  f"{stat['total_area']}ha [{stat['level']}] 주원인: {stat['top_cause']}")


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f"❌ 수집 실패: {e}", file=sys.stderr)
        if OUTPUT_FILE.exists():
            print("⚠️  기존 fire_history.json 유지 — 파이프라인 계속 진행", file=sys.stderr)
            sys.exit(0)
        sys.exit(1)
