#!/usr/bin/env python3
"""
화성시 산불위험예보정보 수집 스크립트
출처: 산림청 forestPointV2 / forestPointListSigunguSearchV2
실행: python crawling/fetch_forest_risk.py
출력: public/data/forest_risk.json

응답 필드:
  analdate   : 분석 일시 (YYYY-MM-DD HH)
  d1~d4      : 위험등급별 면적 비율(%) — d1 낮음 / d2 보통 / d3 높음 / d4 매우높음
  meanavg    : 위험지수 평균 (0~100)
  maxi / mini: 위험지수 최대/최소
"""

import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ===== CONFIG =====
SERVICE_KEY  = 'ee17a36e905254adb206454f36c179c3449720f4970173782f75869f788af660'
BASE_URL     = ('https://apis.data.go.kr/1400377/forestPointV2'
                '/forestPointListSigunguSearchV2')
LOCAL_AREAS  = '41590'   # 화성시 시군구 코드
UPPLOCALCD   = '41'      # 경기도 광역코드
LOCATION     = '경기도 화성시'

BASE_DIR     = Path(__file__).parent.parent
OUTPUT_DIR   = BASE_DIR / 'public' / 'data'
OUTPUT_FILE  = OUTPUT_DIR / 'forest_risk.json'

KST = timezone(timedelta(hours=9))

# 위험지수(meanavg 0~100) → 등급 레이블
def _index_to_grade(idx: int) -> dict:
    if idx >= 76:
        return {'grade': 4, 'level': 'HIGH',   'label': '매우높음', 'color': '#ff3333'}
    if idx >= 51:
        return {'grade': 3, 'level': 'MEDIUM', 'label': '높음',     'color': '#ffcc00'}
    if idx >= 26:
        return {'grade': 2, 'level': 'LOW',    'label': '보통',     'color': '#99cc33'}
    return      {'grade': 1, 'level': 'LOW',    'label': '낮음',     'color': '#33cc77'}

# d1~d4 면적비율 중 가장 많은 등급 반환
def _dominant_grade(item: dict) -> dict:
    grades = {
        1: float(item.get('d1', 0) or 0),
        2: float(item.get('d2', 0) or 0),
        3: float(item.get('d3', 0) or 0),
        4: float(item.get('d4', 0) or 0),
    }
    dom = max(grades, key=lambda k: grades[k])
    labels = {
        1: ('LOW',   '낮음',   '#33cc77'),
        2: ('LOW',   '보통',   '#99cc33'),
        3: ('MEDIUM','높음',   '#ffcc00'),
        4: ('HIGH',  '매우높음','#ff3333'),
    }
    lv, lb, co = labels[dom]
    return {'grade': dom, 'level': lv, 'label': lb, 'color': co}


# ===== FETCH =====

def fetch_all(num_rows: int = 50) -> list:
    """전체 예보 시계열 조회 (totalCount 기준 페이지 자동 처리)."""
    params = {
        'ServiceKey':      SERVICE_KEY,
        'pageNo':          1,
        'numOfRows':       num_rows,
        '_type':           'json',
        'localAreas':      LOCAL_AREAS,
        'upplocalcd':      UPPLOCALCD,
        'excludeForecast': 0,
    }
    url = BASE_URL + '?' + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={'User-Agent': 'wildfire-guard/1.0'})

    with urllib.request.urlopen(req, timeout=20) as resp:
        body = json.loads(resp.read().decode('utf-8'))

    header = body.get('response', {}).get('header', {})
    code   = header.get('resultCode', '')
    if code not in ('00', '0000'):
        raise RuntimeError(f"API 오류 [{code}]: {header.get('resultMsg', '')}")

    bd    = body['response']['body']
    total = int(bd.get('totalCount', 0))
    items = bd.get('items', {}).get('item', [])
    if not isinstance(items, list):
        items = [items] if items else []

    # 첫 페이지로 전체 건수 커버되지 않으면 추가 조회
    if total > num_rows:
        params['numOfRows'] = total
        url2 = BASE_URL + '?' + urllib.parse.urlencode(params)
        req2 = urllib.request.Request(url2, headers={'User-Agent': 'wildfire-guard/1.0'})
        with urllib.request.urlopen(req2, timeout=30) as resp2:
            body2 = json.loads(resp2.read().decode('utf-8'))
        items = body2['response']['body'].get('items', {}).get('item', [])
        if not isinstance(items, list):
            items = [items] if items else []

    print(f"  총 {total}건 예보 수신 ({len(items)}건 파싱)")
    return items


# ===== 기본값 저장 =====

def save_default(reason: str):
    """API 실패 시 최소 기본값으로 저장 후 정상 종료."""
    now = datetime.now(KST)
    result = {
        'timestamp':      now.isoformat(),
        'location':       LOCATION,
        'source':         '산림청 forestPointV2 (기본값)',
        'data_available': False,
        'error_reason':   reason,
        'overall_level':  'LOW',
        'overall_label':  '낮음',
        'overall_color':  '#33cc77',
        'meanavg_now':    0,
        'maxi_now':       0,
        'forecast_count': 0,
        'forecasts':      [],
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f'⚠️  기본값으로 저장: {OUTPUT_FILE}  ({reason})')


# ===== MAIN =====

def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(KST)
    print(f'[산림청] 산불위험예보 수집: {LOCATION}')
    print(f'  EndPoint: {BASE_URL}')

    try:
        items = fetch_all()
    except Exception as e:
        print(f'  API 수신 실패: {e}')
        save_default(str(e))
        return

    if not items:
        save_default('API 응답 아이템 없음')
        return

    now_h = now.strftime('%Y-%m-%d %H')

    forecasts = []
    for it in items:
        analdate = str(it.get('analdate', ''))
        meanavg  = int(it.get('meanavg', 0) or 0)
        maxi     = int(it.get('maxi',    0) or 0)
        mini     = int(it.get('mini',    0) or 0)
        std      = int(it.get('std',     0) or 0)
        d1       = float(it.get('d1', 0) or 0)
        d2       = float(it.get('d2', 0) or 0)
        d3       = float(it.get('d3', 0) or 0)
        d4       = float(it.get('d4', 0) or 0)

        idx_info = _index_to_grade(meanavg)
        dom_info = _dominant_grade(it)

        # 전반적 위험은 meanavg 기준, 최고등급 비율도 참고
        high_ratio = d3 + d4   # 높음 이상 면적 비율(%)

        forecasts.append({
            'analdate':       analdate,
            'meanavg':        meanavg,
            'maxi':           maxi,
            'mini':           mini,
            'std':            std,
            'd1_pct':         d1,
            'd2_pct':         d2,
            'd3_pct':         d3,
            'd4_pct':         d4,
            'high_ratio_pct': round(high_ratio, 1),
            'level':          idx_info['level'],
            'label':          idx_info['label'],
            'color':          idx_info['color'],
            'dom_grade':      dom_info['grade'],
            'dom_label':      dom_info['label'],
            'is_current':     analdate[:13] == now_h[:13],
        })

    # 현재 시각에 가장 가까운 예보를 overall 기준으로 사용
    current = next((f for f in forecasts if f['is_current']), None) or forecasts[0]
    overall = _index_to_grade(current['meanavg'])

    # 전체 예보 중 최고 meanavg
    peak = max(forecasts, key=lambda f: f['meanavg'])

    level_counts = {'HIGH': 0, 'MEDIUM': 0, 'LOW': 0}
    for f in forecasts:
        level_counts[f['level']] = level_counts.get(f['level'], 0) + 1

    result = {
        'timestamp':      now.isoformat(),
        'location':       LOCATION,
        'source':         '산림청 forestPointV2 / forestPointListSigunguSearchV2',
        'data_available': True,
        'region_code':    LOCAL_AREAS,
        'overall_level':  overall['level'],
        'overall_label':  overall['label'],
        'overall_color':  overall['color'],
        'meanavg_now':    current['meanavg'],
        'maxi_now':       current['maxi'],
        'peak_meanavg':   peak['meanavg'],
        'peak_analdate':  peak['analdate'],
        'forecast_count': len(forecasts),
        'level_counts':   level_counts,
        'forecasts':      forecasts,
    }

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f'✅ 저장 완료: {OUTPUT_FILE}')
    print(f'   현재({current["analdate"]}) 위험지수: {current["meanavg"]} [{overall["label"]}]')
    print(f'   높음 이상 면적: {current["high_ratio_pct"]}%  (d3={current["d3_pct"]}% d4={current["d4_pct"]}%)')
    print(f'   예보 피크: {peak["analdate"]} meanavg={peak["meanavg"]}')
    print(f'   HIGH {level_counts["HIGH"]} / MEDIUM {level_counts["MEDIUM"]} / LOW {level_counts["LOW"]}')


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f'❌ 수집 실패: {e}', file=sys.stderr)
        save_default(str(e))
