#!/usr/bin/env python3
"""
수원 관측소 기상청 과거관측 일별 기상 데이터 수집 스크립트
출처: 기상청 AsosDalyInfoService / getWthrDataList
실행: python crawling/fetch_historical_weather.py
출력: public/data/historical_weather.json

수원 관측소(119)는 화성시 인근에서 장기 연속 관측 이력이 있는 가장 가까운 ASOS 지점.
최근 5년치 일별 기상을 수집하여 AI 모델 훈련 데이터 및 계절별 분석에 활용.
"""

import json
import sys
import time
import requests
from datetime import datetime, timezone, timedelta, date
from pathlib import Path

# ===== CONFIG =====
SERVICE_KEY = 'ee17a36e905254adb206454f36c179c3449720f4970173782f75869f788af660'
BASE_URL    = 'https://apis.data.go.kr/1360000/AsosDalyInfoService/getWthrDataList'
STN_IDS     = '119'        # 수원 관측소
LOCATION    = '수원 관측소 (화성시 근접 ASOS 지점)'
YEARS_BACK  = 5
NUM_OF_ROWS = 365          # 연간 단위 요청

BASE_DIR    = Path(__file__).parent.parent
OUTPUT_DIR  = BASE_DIR / 'public' / 'data'
OUTPUT_FILE = OUTPUT_DIR / 'historical_weather.json'

KST = timezone(timedelta(hours=9))


# ===== UTILS =====

def safe_float(v) -> float | None:
    try:
        return float(v) if v not in (None, '', '-') else None
    except (TypeError, ValueError):
        return None


def safe_int(v) -> int | None:
    try:
        return int(float(v)) if v not in (None, '', '-') else None
    except (TypeError, ValueError):
        return None


# ===== FETCH =====

def fetch_year(start_dt: str, end_dt: str) -> list[dict]:
    """단일 기간의 일별 기상 조회."""
    all_items = []
    page = 1
    while True:
        params = {
            'serviceKey': SERVICE_KEY,
            'pageNo':     page,
            'numOfRows':  NUM_OF_ROWS,
            'dataType':   'JSON',
            'dataCd':     'ASOS',
            'dateCd':     'DAY',
            'startDt':    start_dt,
            'endDt':      end_dt,
            'stnIds':     STN_IDS,
        }
        resp = requests.get(BASE_URL, params=params, timeout=20)
        resp.raise_for_status()
        body = resp.json()

        header = body.get('response', {}).get('header', {})
        code   = header.get('resultCode', '')
        if code not in ('00', '0000'):
            raise ValueError(f"API 오류 [{code}]: {header.get('resultMsg', 'UNKNOWN')}")

        body_data   = body['response']['body']
        total_count = int(body_data.get('totalCount', 0))
        items       = body_data.get('items', {}).get('item', [])
        if not isinstance(items, list):
            items = [items] if items else []

        all_items.extend(items)
        if len(all_items) >= total_count or not items:
            break
        page += 1
        time.sleep(0.3)

    return all_items


def parse_item(item: dict) -> dict:
    """API 응답 항목을 정규화된 딕셔너리로 변환."""
    tm     = item.get('tm', '')          # 'YYYY-MM-DD'
    parts  = tm.split('-') if '-' in tm else [tm[:4], tm[4:6], tm[6:8]]
    year   = safe_int(parts[0]) if len(parts) > 0 else None
    month  = safe_int(parts[1]) if len(parts) > 1 else None

    temp_avg = safe_float(item.get('avgTa'))
    temp_max = safe_float(item.get('maxTa'))
    temp_min = safe_float(item.get('minTa'))
    hum_avg  = safe_float(item.get('avgRhm'))
    wind_avg = safe_float(item.get('avgWs'))
    wind_max = safe_float(item.get('maxWs'))
    precip   = safe_float(item.get('sumRn', item.get('totRn')))
    sunshine = safe_float(item.get('sumSsHr'))   # 일조시간(h)

    # 화재 기상 위험도 간이 산출 (일별)
    fire_score = _daily_fire_score(temp_max, hum_avg, wind_max, precip)

    return {
        'date':            tm,
        'year':            year,
        'month':           month,
        'stn_id':          safe_int(item.get('stnId')),
        'stn_name':        item.get('stnNm', ''),
        'temp_avg_c':      temp_avg,
        'temp_max_c':      temp_max,
        'temp_min_c':      temp_min,
        'humidity_avg_pct': hum_avg,
        'wind_avg_ms':     wind_avg,
        'wind_max_ms':     wind_max,
        'precip_mm':       precip,
        'sunshine_hr':     sunshine,
        'fire_score':      fire_score['score'],
        'fire_level':      fire_score['level'],
    }


def _daily_fire_score(temp_max, humidity, wind_max, precip) -> dict:
    """일별 화재 위험 지수 간이 산출."""
    if precip is not None and precip > 1.0:
        return {'score': 0.0, 'level': 'LOW'}

    score = 0.0
    if humidity is not None:
        score += (1 - min(humidity, 100) / 100) * 0.45
    if temp_max is not None:
        score += min(max(temp_max, 0), 40) / 40 * 0.30
    if wind_max is not None:
        score += min(wind_max, 20) / 20 * 0.25

    score = round(score, 3)
    if   score >= 0.65: level = 'HIGH'
    elif score >= 0.40: level = 'MEDIUM'
    else:               level = 'LOW'
    return {'score': score, 'level': level}


# ===== ANALYSIS =====

def build_monthly_stats(records: list[dict]) -> dict:
    """월별 평균 기상 및 화재 위험 집계."""
    monthly: dict[int, dict] = {}

    for r in records:
        m = r.get('month')
        if not m:
            continue
        if m not in monthly:
            monthly[m] = {
                'temp_max': [], 'temp_min': [], 'humidity': [],
                'wind_max': [], 'precip': [], 'fire_score': [],
                'high_risk_days': 0, 'total_days': 0,
            }
        s = monthly[m]
        s['total_days'] += 1
        for field, key in [('temp_max_c','temp_max'), ('temp_min_c','temp_min'),
                            ('humidity_avg_pct','humidity'), ('wind_max_ms','wind_max'),
                            ('precip_mm','precip'), ('fire_score','fire_score')]:
            if r.get(field) is not None:
                s[key].append(r[field])
        if r.get('fire_level') == 'HIGH':
            s['high_risk_days'] += 1

    result = {}
    for m, s in sorted(monthly.items()):
        def avg(lst): return round(sum(lst) / len(lst), 2) if lst else None
        result[m] = {
            'temp_max_avg_c':  avg(s['temp_max']),
            'temp_min_avg_c':  avg(s['temp_min']),
            'humidity_avg_pct': avg(s['humidity']),
            'wind_max_avg_ms': avg(s['wind_max']),
            'precip_total_mm': round(sum(s['precip']), 1) if s['precip'] else None,
            'fire_score_avg':  avg(s['fire_score']),
            'high_risk_days':  s['high_risk_days'],
            'total_days':      s['total_days'],
        }
    return result


def build_yearly_stats(records: list[dict]) -> dict:
    """연도별 화재 위험일 수 집계."""
    yearly: dict[int, dict] = {}
    for r in records:
        yr = r.get('year')
        if not yr:
            continue
        if yr not in yearly:
            yearly[yr] = {'high': 0, 'medium': 0, 'low': 0, 'total': 0}
        yearly[yr]['total'] += 1
        lv = r.get('fire_level', 'LOW').lower()
        yearly[yr][lv] = yearly[yr].get(lv, 0) + 1
    return dict(sorted(yearly.items()))


# ===== MAIN =====

def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    now      = datetime.now(KST)
    end_date = now.date()
    start_date = end_date.replace(year=end_date.year - YEARS_BACK)

    print(f"[기상청] 과거관측 수집: {LOCATION}")
    print(f"  기간: {start_date} ~ {end_date}  ({YEARS_BACK}년)")

    all_items: list[dict] = []
    # 연도별로 나눠 요청 (1회 요청당 365행 제한 대응)
    for yr in range(start_date.year, end_date.year + 1):
        s = date(yr, 1, 1)
        e = date(yr, 12, 31)
        s = max(s, start_date)
        e = min(e, end_date)
        s_str = s.strftime('%Y%m%d')
        e_str = e.strftime('%Y%m%d')
        print(f"  {yr}년 수집 ({s_str}~{e_str}) ...", end=' ', flush=True)
        try:
            items = fetch_year(s_str, e_str)
            all_items.extend(items)
            print(f"{len(items)}건")
        except Exception as e:
            print(f"실패: {e}")
        time.sleep(0.5)

    records = [parse_item(it) for it in all_items]
    records.sort(key=lambda r: r['date'])

    monthly_stats = build_monthly_stats(records)
    yearly_stats  = build_yearly_stats(records)

    # 전체 기간 요약
    fire_scores   = [r['fire_score'] for r in records if r['fire_score'] is not None]
    high_risk_cnt = sum(1 for r in records if r.get('fire_level') == 'HIGH')

    result = {
        'timestamp':       now.isoformat(),
        'location':        LOCATION,
        'station_id':      STN_IDS,
        'start_date':      str(start_date),
        'end_date':        str(end_date),
        'total_records':   len(records),
        'high_risk_days':  high_risk_cnt,
        'avg_fire_score':  round(sum(fire_scores) / len(fire_scores), 3) if fire_scores else None,
        'monthly_stats':   monthly_stats,
        'yearly_stats':    yearly_stats,
        'records':         records,
    }

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 저장 완료: {OUTPUT_FILE} ({len(records)}일)")
    print(f"   화재위험일(HIGH): {high_risk_cnt}일 / "
          f"평균 위험지수: {result['avg_fire_score']}")
    print("   ─── 월별 화재위험일(HIGH) ───")
    for m, stat in monthly_stats.items():
        bar = '█' * stat['high_risk_days']
        print(f"   {m:>2}월  {bar:<20} {stat['high_risk_days']}일")


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f"❌ 수집 실패: {e}", file=sys.stderr)
        sys.exit(1)
