#!/usr/bin/env python3
"""
화성시 기상청 중기예보 수집 스크립트
출처: 기상청 MidFcstInfoService / getMidLandFcst + getMidTa
실행: python crawling/fetch_mid_weather.py
출력: public/data/mid_weather.json

중기예보 범위: 오늘 기준 +3일 ~ +10일
예보구역코드: 11H10701 (경기남부 — 화성·수원·오산·용인 등)
기온예보코드: 11H10701
"""

import json
import sys
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ===== CONFIG =====
SERVICE_KEY  = 'ee17a36e905254adb206454f36c179c3449720f4970173782f75869f788af660'
BASE_URL     = 'https://apis.data.go.kr/1360000/MidFcstInfoService'
LAND_OP      = 'getMidLandFcst'   # 중기육상예보 (날씨 · 강수확률)
TEMP_OP      = 'getMidTa'         # 중기기온예보 (최저/최고 기온)
REG_ID       = '11H10701'         # 경기남부 예보구역
LOCATION     = '경기도 화성시 (경기남부 예보구역)'

BASE_DIR    = Path(__file__).parent.parent
OUTPUT_DIR  = BASE_DIR / 'public' / 'data'
OUTPUT_FILE = OUTPUT_DIR / 'mid_weather.json'

KST = timezone(timedelta(hours=9))

# 중기예보 날씨 코드 → 한글 설명
WF_LABELS = {
    '맑음':       {'label': '맑음',        'icon': '☀️'},
    '구름많음':   {'label': '구름 많음',   'icon': '⛅'},
    '구름많고 비': {'label': '구름많고 비', 'icon': '🌦️'},
    '구름많고 눈': {'label': '구름많고 눈', 'icon': '🌨️'},
    '구름많고 비/눈': {'label': '비/눈',   'icon': '🌨️'},
    '흐림':       {'label': '흐림',        'icon': '☁️'},
    '흐리고 비':  {'label': '흐리고 비',   'icon': '🌧️'},
    '흐리고 눈':  {'label': '흐리고 눈',   'icon': '❄️'},
    '흐리고 비/눈': {'label': '비/눈',     'icon': '🌨️'},
}


# ===== UTILS =====

def get_tmfc() -> str:
    """중기예보 발표 시각 반환. 하루 2회 발표: 06:00·18:00 KST."""
    now = datetime.now(KST)
    if now.hour >= 18:
        base = now.replace(hour=18, minute=0, second=0, microsecond=0)
    elif now.hour >= 6:
        base = now.replace(hour=6,  minute=0, second=0, microsecond=0)
    else:
        base = (now - timedelta(days=1)).replace(
            hour=18, minute=0, second=0, microsecond=0)
    return base.strftime('%Y%m%d%H%M')


def safe_int(v) -> int | None:
    try:
        return int(v) if v is not None and str(v).strip() != '' else None
    except (TypeError, ValueError):
        return None


def safe_float(v) -> float | None:
    try:
        return float(v) if v is not None and str(v).strip() != '' else None
    except (TypeError, ValueError):
        return None


# ===== FETCH =====

def _call(operation: str, tmfc: str) -> dict:
    """단일 중기예보 API 호출."""
    params = {
        'serviceKey': SERVICE_KEY,
        'numOfRows':  10,
        'pageNo':     1,
        'dataType':   'JSON',
        'regId':      REG_ID,
        'tmFc':       tmfc,
    }
    resp = requests.get(f'{BASE_URL}/{operation}', params=params, timeout=15)
    resp.raise_for_status()
    body = resp.json()

    header = body.get('response', {}).get('header', {})
    code   = header.get('resultCode', '')
    if code not in ('00', '0000'):
        raise ValueError(f"API 오류 [{code}]: {header.get('resultMsg', 'UNKNOWN')}")

    items = body['response']['body']['items']['item']
    if not isinstance(items, list):
        items = [items]
    return items[0] if items else {}


def fetch_land_fcst(tmfc: str) -> dict:
    print(f"  [중기육상예보] getMidLandFcst regId={REG_ID} tmFc={tmfc}")
    return _call(LAND_OP, tmfc)


def fetch_temp_fcst(tmfc: str) -> dict:
    print(f"  [중기기온예보] getMidTa       regId={REG_ID} tmFc={tmfc}")
    return _call(TEMP_OP, tmfc)


# ===== BUILD FORECAST =====

def build_daily_forecasts(land: dict, temp: dict, base_date: str) -> list:
    """육상예보 + 기온예보를 일자별 리스트로 합산."""
    forecasts = []
    base = datetime.strptime(base_date, '%Y%m%d')

    for day in range(3, 11):   # D+3 ~ D+10
        target = base + timedelta(days=day)
        ds     = target.strftime('%Y-%m-%d')

        # 강수확률: AM/PM 구분 (D+3~7: am/pm, D+8+: 단일)
        if day <= 7:
            rn_am = safe_int(land.get(f'rnSt{day}Am'))
            rn_pm = safe_int(land.get(f'rnSt{day}Pm'))
            rn    = max(v for v in [rn_am, rn_pm] if v is not None) if (rn_am or rn_pm) else None
            wf_am = land.get(f'wf{day}Am', '')
            wf_pm = land.get(f'wf{day}Pm', '')
            wf    = wf_pm if wf_pm else wf_am
        else:
            rn_am, rn_pm = None, None
            rn    = safe_int(land.get(f'rnSt{day}'))
            wf    = land.get(f'wf{day}', '')

        wf_meta = WF_LABELS.get(wf, {'label': wf, 'icon': '🌥️'})

        ta_min = safe_float(temp.get(f'taMin{day}'))
        ta_max = safe_float(temp.get(f'taMax{day}'))

        # 화재 위험도 간이 추정 (강수확률 낮고 기온 높을수록 위험)
        fire_risk = _estimate_fire_risk(rn, ta_max, wf)

        forecasts.append({
            'date':              ds,
            'day_offset':        day,
            'weather_code':      wf,
            'weather_label':     wf_meta['label'],
            'weather_icon':      wf_meta['icon'],
            'rain_prob_pct':     rn,
            'rain_prob_am_pct':  rn_am,
            'rain_prob_pm_pct':  rn_pm,
            'temp_min_c':        ta_min,
            'temp_max_c':        ta_max,
            'fire_risk_level':   fire_risk['level'],
            'fire_risk_label':   fire_risk['label'],
        })

    return forecasts


def _estimate_fire_risk(rain_prob, temp_max, wf_code) -> dict:
    """강수확률·최고기온·날씨 코드를 기반으로 간이 화재 위험도 추정."""
    if rain_prob is not None and rain_prob >= 60:
        return {'level': 'LOW',    'label': '낮음'}
    if '비' in (wf_code or '') or '눈' in (wf_code or ''):
        return {'level': 'LOW',    'label': '낮음'}

    score = 0.0
    if rain_prob is not None:
        score += (1 - rain_prob / 100) * 0.5
    if temp_max is not None:
        score += min(temp_max / 35, 1.0) * 0.3
    if rain_prob is not None and rain_prob < 20:
        score += 0.2

    if   score >= 0.70: return {'level': 'HIGH',   'label': '위험'}
    elif score >= 0.45: return {'level': 'MEDIUM',  'label': '주의'}
    else:               return {'level': 'LOW',    'label': '낮음'}


# ===== MAIN =====

def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    now    = datetime.now(KST)
    tmfc   = get_tmfc()
    base_d = now.strftime('%Y%m%d')
    print(f"[기상청] 중기예보 수집: {LOCATION}")
    print(f"  발표 기준 시각: {tmfc}")

    try:
        land = fetch_land_fcst(tmfc)
    except Exception as e:
        print(f"  중기육상예보 실패: {e}", file=sys.stderr)
        land = {}

    try:
        temp = fetch_temp_fcst(tmfc)
    except Exception as e:
        print(f"  중기기온예보 실패: {e}", file=sys.stderr)
        temp = {}

    forecasts = build_daily_forecasts(land, temp, base_d)

    # 요약
    high_risk_days = [f for f in forecasts if f['fire_risk_level'] == 'HIGH']
    low_rain_days  = [f for f in forecasts if (f['rain_prob_pct'] or 100) < 30]

    result = {
        'timestamp':        now.isoformat(),
        'location':         LOCATION,
        'region_id':        REG_ID,
        'base_date':        base_d,
        'tmfc':             tmfc,
        'forecast_days':    len(forecasts),
        'high_risk_days':   len(high_risk_days),
        'dry_days':         len(low_rain_days),
        'forecasts':        forecasts,
        'raw_land':         land,
        'raw_temp':         temp,
    }

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"✅ 저장 완료: {OUTPUT_FILE} ({len(forecasts)}일 예보)")
    for fc in forecasts:
        rn = f"{fc['rain_prob_pct']}%" if fc['rain_prob_pct'] is not None else '--'
        ta = (f"{fc['temp_min_c']}~{fc['temp_max_c']}°C"
              if fc['temp_min_c'] is not None else '--')
        print(f"  {fc['date']} {fc['weather_icon']} {fc['weather_label']:<10} "
              f"강수 {rn:<5} 기온 {ta:<14} 화재위험 [{fc['fire_risk_level']}]")


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f"❌ 수집 실패: {e}", file=sys.stderr)
        sys.exit(1)
