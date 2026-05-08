#!/usr/bin/env python3
"""
화성시 기상청 초단기실황 수집 스크립트
출처: 기상청 VilageFcstInfoService_2.0 / getUltraSrtNcst
실행: python crawling/fetch_weather.py
출력: public/data/weather.json
"""

import json
import sys
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ===== CONFIG =====
SERVICE_KEY = 'ee17a36e905254adb206454f36c179c3449720f4970173782f75869f788af660'
BASE_URL    = 'https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getUltraSrtNcst'
NX          = 57    # 화성시 격자 X
NY          = 74    # 화성시 격자 Y
LOCATION    = '경기도 화성시'

BASE_DIR   = Path(__file__).parent.parent
OUTPUT_DIR = BASE_DIR / 'public' / 'data'
OUTPUT_FILE = OUTPUT_DIR / 'weather.json'

KST = timezone(timedelta(hours=9))

# 카테고리 코드 → (한글명, 단위)
CATEGORY_META = {
    'T1H': ('기온',           '°C'),
    'RN1': ('1시간 강수량',   'mm'),
    'UUU': ('동서 바람성분',  'm/s'),
    'VVV': ('남북 바람성분',  'm/s'),
    'REH': ('습도',           '%'),
    'PTY': ('강수형태',       ''),
    'VEC': ('풍향',           '°'),
    'WSD': ('풍속',           'm/s'),
}

PTY_LABELS = {
    '0': '없음', '1': '비', '2': '비/눈', '3': '눈',
    '5': '빗방울', '6': '빗방울눈날림', '7': '눈날림',
}

WIND_DIRS = [
    '북', '북북동', '북동', '동북동', '동', '동남동', '남동', '남남동',
    '남', '남남서', '남서', '서남서', '서', '서북서', '북서', '북북서',
]


# ===== UTILS =====

def get_kst_basetime():
    """KST 현재 시각 기준 base_date / base_time 반환.
    10분 미만이면 이전 시각 사용(데이터 생성 지연 대응)."""
    now = datetime.now(KST)
    if now.minute < 10:
        now = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
    return now.strftime('%Y%m%d'), now.strftime('%H00')


def wind_dir_text(deg: float) -> str:
    idx = round((deg % 360) / 360 * 16) % 16
    return WIND_DIRS[idx] + '풍'


def calc_fire_weather_index(raw: dict) -> dict:
    """건조도(50%) + 기온(30%) + 풍속(20%) 가중 합산으로 화재 위험 기상 지수 산출."""
    try:
        temp = float(raw.get('T1H', 0))
        hum  = float(raw.get('REH', 100))
        wind = float(raw.get('WSD', 0))
        pty  = int(raw.get('PTY', 0))
    except (TypeError, ValueError):
        return {'level': 'unknown', 'label': '알 수 없음', 'desc': '--', 'score': None}

    if pty > 0:
        return {'level': 'low', 'label': '낮음', 'desc': '강수 중 — 정상 순찰 유지', 'score': 0.0}

    score = ((100 - hum) / 100) * 0.5 + (temp / 40) * 0.3 + (wind / 15) * 0.2

    if score >= 0.65:
        level, label, desc = 'very_high', '매우 위험', '즉시 경계 태세 필요'
    elif score >= 0.45:
        level, label, desc = 'high',      '위험',      '순찰 빈도 강화 권고'
    elif score >= 0.25:
        level, label, desc = 'medium',    '주의',      '예방 점검 필요'
    else:
        level, label, desc = 'low',       '낮음',      '정상 순찰 유지'

    return {'level': level, 'label': label, 'desc': desc, 'score': round(score, 3)}


# ===== FETCH =====

def fetch_weather(base_date: str, base_time: str) -> dict:
    params = {
        'serviceKey': SERVICE_KEY,
        'numOfRows':  10,
        'pageNo':     1,
        'dataType':   'JSON',
        'base_date':  base_date,
        'base_time':  base_time,
        'nx':         NX,
        'ny':         NY,
    }

    resp = requests.get(BASE_URL, params=params, timeout=15)
    resp.raise_for_status()
    body = resp.json()

    header = body.get('response', {}).get('header', {})
    result_code = header.get('resultCode', '')
    if result_code != '00':
        raise ValueError(f"API 오류 [{result_code}]: {header.get('resultMsg', 'UNKNOWN')}")

    items = body['response']['body']['items']['item']
    if not isinstance(items, list):
        items = [items]

    return {item['category']: item['obsrValue'] for item in items}


# ===== MAIN =====

def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    base_date, base_time = get_kst_basetime()
    print(f"[기상청] 초단기실황 수집: {LOCATION} ({base_date} {base_time} KST)")

    raw = fetch_weather(base_date, base_time)

    fwi = calc_fire_weather_index(raw)

    result = {
        'timestamp':  datetime.now(KST).isoformat(),
        'location':   LOCATION,
        'nx':         NX,
        'ny':         NY,
        'base_date':  base_date,
        'base_time':  base_time,
        'raw':        raw,
        'parsed': {
            'temperature':        float(raw.get('T1H', 0)),
            'humidity':           int(float(raw.get('REH', 0))),
            'wind_speed':         float(raw.get('WSD', 0)),
            'wind_direction_deg': float(raw.get('VEC', 0)),
            'wind_direction':     wind_dir_text(float(raw.get('VEC', 0))),
            'precipitation':      float(raw.get('RN1', 0)),
            'precipitation_type': PTY_LABELS.get(raw.get('PTY', '0'), '없음'),
        },
        'fire_weather_index': fwi,
    }

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    p = result['parsed']
    print(f"✅ 저장 완료: {OUTPUT_FILE}")
    print(f"   기온 {p['temperature']}°C  습도 {p['humidity']}%  "
          f"풍속 {p['wind_speed']}m/s {p['wind_direction']}")
    print(f"   강수: {p['precipitation_type']}  "
          f"화재 위험 기상 지수: [{fwi['level'].upper()}] {fwi['label']}")


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f"❌ 수집 실패: {e}", file=sys.stderr)
        sys.exit(1)
