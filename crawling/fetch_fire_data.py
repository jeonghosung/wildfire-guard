#!/usr/bin/env python3
"""
화성시 산림청 산불발생통계 수집 스크립트
출처: 산림청 forestStusService / getfirestatsservice
실행: python crawling/fetch_fire_data.py
출력: public/data/fire_history.json
"""

import json
import sys
import time
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ===== CONFIG =====
SERVICE_KEY = 'ee17a36e905254adb206454f36c179c3449720f4970173782f75869f788af660'
BASE_URL    = 'https://apis.data.go.kr/1400000/forestStusService/getfirestatsservice'
SIDO        = '경기도'
SGG         = '화성시'
NUM_OF_ROWS = 100   # 페이지당 행 수

BASE_DIR    = Path(__file__).parent.parent
OUTPUT_DIR  = BASE_DIR / 'public' / 'data'
OUTPUT_FILE = OUTPUT_DIR / 'fire_history.json'

KST = timezone(timedelta(hours=9))

# API 필드명 후보 (camelCase / SNAKE_CASE 모두 지원)
FIELD_MAP = {
    'year':         ['frfrOccrnYr',    'FRFR_OCCRN_YR'],
    'month':        ['frfrOccrnMo',    'FRFR_OCCRN_MO'],
    'day':          ['frfrOccrnDy',    'FRFR_OCCRN_DY'],
    'sido':         ['frfrOccrnSidNm', 'FRFR_OCCRN_SID_NM'],
    'sigungu':      ['frfrOccrnSggNm', 'FRFR_OCCRN_SGG_NM'],
    'emd':          ['frfrOccrnEmdNm', 'FRFR_OCCRN_EMD_NM'],
    'cause':        ['frfrOccrnResn',  'FRFR_OCCRN_RESN'],
    'damage_area':  ['frfrDmgeArea',   'FRFR_DMGE_AREA'],
    'damage_amount':['frfrDmgeAmt',    'FRFR_DMGE_AMT'],
    'forest_area':  ['frfrFrstArea',   'FRFR_FRST_AREA'],
    'lat':          ['frfrOccrnYcrd',  'FRFR_OCCRN_YCRD'],
    'lng':          ['frfrOccrnXcrd',  'FRFR_OCCRN_XCRD'],
    'address':      ['frfrSttmnAddr',  'FRFR_STTMN_ADDR'],
}


# ===== UTILS =====

def get_field(item: dict, key: str):
    for field in FIELD_MAP.get(key, []):
        if field in item:
            val = item[field]
            return val if val not in ('', None) else None
    return None


def safe_float(v) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def safe_int(v) -> int | None:
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def parse_record(item: dict) -> dict:
    return {
        'year':             safe_int(get_field(item, 'year')),
        'month':            safe_int(get_field(item, 'month')),
        'day':              safe_int(get_field(item, 'day')),
        'sido':             get_field(item, 'sido')    or SIDO,
        'sigungu':          get_field(item, 'sigungu') or SGG,
        'emd':              get_field(item, 'emd')     or '',
        'address':          get_field(item, 'address') or '',
        'cause':            get_field(item, 'cause')   or '미상',
        'damage_area_ha':   safe_float(get_field(item, 'damage_area')),
        'forest_area_ha':   safe_float(get_field(item, 'forest_area')),
        'damage_amount_krw':safe_float(get_field(item, 'damage_amount')),
        'lat':              safe_float(get_field(item, 'lat')),
        'lng':              safe_float(get_field(item, 'lng')),
    }


# ===== FETCH =====

def fetch_page(page_no: int) -> dict:
    params = {
        'serviceKey':        SERVICE_KEY,
        'numOfRows':         NUM_OF_ROWS,
        'pageNo':            page_no,
        'type':              'json',
        'FRFR_OCCRN_SID_NM': SIDO,
        'FRFR_OCCRN_SGG_NM': SGG,
    }
    resp = requests.get(BASE_URL, params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


def fetch_all_records() -> list[dict]:
    records = []
    page    = 1
    total   = None

    while True:
        print(f"  [페이지 {page}] 요청 중...", end=' ', flush=True)
        body = fetch_page(page)

        header = body.get('response', {}).get('header', {})
        code   = header.get('resultCode', '')
        if code != '00':
            raise ValueError(f"API 오류 [{code}]: {header.get('resultMsg', 'UNKNOWN')}")

        resp_body = body['response']['body']

        if total is None:
            total = int(resp_body.get('totalCount', 0))
            print(f"총 {total}건 확인")

        items = resp_body.get('items', {}) or {}
        items = items.get('item', []) if isinstance(items, dict) else []
        if not items:
            print("  항목 없음 — 수집 종료")
            break
        if not isinstance(items, list):
            items = [items]

        batch = [parse_record(item) for item in items]
        records.extend(batch)
        print(f"  [페이지 {page}] {len(batch)}건 수집 (누계 {len(records)}건)")

        if len(records) >= total:
            break

        page += 1
        time.sleep(0.3)  # API 부하 방지

    return records


# ===== ANALYSIS =====

def build_dong_stats(records: list[dict]) -> dict:
    """읍면동별 발생 건수 및 피해면적 집계 + 취약도 점수 산출."""
    dong_map: dict[str, dict] = {}

    for r in records:
        dong = r.get('emd') or r.get('sigungu') or '미상'
        if dong not in dong_map:
            dong_map[dong] = {'count': 0, 'total_area': 0.0, 'causes': {}}
        dong_map[dong]['count'] += 1
        dong_map[dong]['total_area'] += r.get('damage_area_ha') or 0.0

        cause = r.get('cause') or '미상'
        dong_map[dong]['causes'][cause] = dong_map[dong]['causes'].get(cause, 0) + 1

    if not dong_map:
        return {}

    max_count = max(d['count']      for d in dong_map.values())
    max_area  = max(d['total_area'] for d in dong_map.values()) or 1

    result = {}
    for dong, d in dong_map.items():
        score = (d['count'] / max_count) * 0.6 + (d['total_area'] / max_area) * 0.4
        level = 'HIGH' if score >= 0.6 else 'MEDIUM' if score >= 0.3 else 'LOW'
        top_cause = max(d['causes'], key=d['causes'].get) if d['causes'] else '미상'
        result[dong] = {
            'count':       d['count'],
            'total_area':  round(d['total_area'], 2),
            'score':       round(score, 3),
            'level':       level,
            'top_cause':   top_cause,
        }

    return dict(sorted(result.items(), key=lambda x: -x[1]['score']))


# ===== MAIN =====

def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"[산림청] 산불발생통계 수집 시작: {SIDO} {SGG}")

    records = fetch_all_records()

    # 연도·월·일 오름차순 정렬
    records.sort(key=lambda r: (
        r.get('year')  or 0,
        r.get('month') or 0,
        r.get('day')   or 0,
    ))

    dong_stats = build_dong_stats(records)

    # 연도별 발생 건수
    year_counts: dict[int, int] = {}
    for r in records:
        yr = r.get('year')
        if yr:
            year_counts[yr] = year_counts.get(yr, 0) + 1

    result = {
        'timestamp':    datetime.now(KST).isoformat(),
        'location':     f'{SIDO} {SGG}',
        'total_count':  len(records),
        'year_counts':  dict(sorted(year_counts.items())),
        'dong_stats':   dong_stats,
        'records':      records,
    }

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 저장 완료: {OUTPUT_FILE} ({len(records)}건)")

    if dong_stats:
        print(f"   읍면동별 집계: {len(dong_stats)}개 지역")
        print("   ─── 취약지역 TOP 5 ───")
        for dong, stat in list(dong_stats.items())[:5]:
            bar = '█' * int(stat['score'] * 10)
            print(f"   {dong:<10} {bar:<10} {stat['count']}건 / "
                  f"{stat['total_area']}ha [{stat['level']}]")


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f"❌ 수집 실패: {e}", file=sys.stderr)
        sys.exit(1)
