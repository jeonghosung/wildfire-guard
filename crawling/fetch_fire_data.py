#!/usr/bin/env python3
"""
산림청 산불발생통계 수집 스크립트
출처: 산림청 forestStusService / getfirestatsservice
실행: python crawling/fetch_fire_data.py
출력:
  public/data/fire_history.json          (화성시)
  public/data/fire_history_gyeonggi.json (경기도 전체)

※ API는 XML만 반환하며 서버 측 지역 필터가 미지원되므로
  전체 데이터를 순회하여 대상 지역 데이터만 추출합니다.
"""

import json
import sys
import time
import urllib.request
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path
from xml.etree import ElementTree as ET

# ===== CONFIG =====
SERVICE_KEY     = 'ee17a36e905254adb206454f36c179c3449720f4970173782f75869f788af660'
BASE_URL        = 'https://apis.data.go.kr/1400000/forestStusService/getfirestatsservice'
FILTER_LOCSI    = '경기'    # 경기도 시·도 약칭
FILTER_LOCGUNGU = '화성'    # 화성시 시·군·구 약칭
NUM_OF_ROWS     = 100

BASE_DIR         = Path(__file__).parent.parent
OUTPUT_DIR       = BASE_DIR / 'public' / 'data'
OUTPUT_FILE      = OUTPUT_DIR / 'fire_history.json'
OUTPUT_GYEONGGI  = OUTPUT_DIR / 'fire_history_gyeonggi.json'

KST = timezone(timedelta(hours=9))

# ===== GIS 좌표 (vuski/admdongkor GeoJSON 기반) =====
_GEOJSON_URL = (
    'https://raw.githubusercontent.com/vuski/admdongkor/master'
    '/ver20231001/HangJeongDong_ver20231001.geojson'
)
_DEFAULT_LAT, _DEFAULT_LNG = 37.1996, 126.8312


def _multipolygon_centroid(geometry: dict) -> tuple:
    polys = (geometry['coordinates'] if geometry['type'] == 'MultiPolygon'
             else [geometry['coordinates']])
    total_area = cx = cy = 0.0
    for poly in polys:
        ring = poly[0]
        a = px = py = 0.0
        for i in range(len(ring) - 1):
            x0, y0 = ring[i]
            x1, y1 = ring[i + 1]
            cross = x0 * y1 - x1 * y0
            a  += cross
            px += (x0 + x1) * cross
            py += (y0 + y1) * cross
        a /= 2.0
        if abs(a) < 1e-12:
            continue
        total_area += abs(a)
        cx += (px / (6.0 * a)) * abs(a)
        cy += (py / (6.0 * a)) * abs(a)
    if total_area < 1e-12:
        return _DEFAULT_LAT, _DEFAULT_LNG
    return round(cy / total_area, 4), round(cx / total_area, 4)


def _load_hwaseong_centroids() -> dict:
    try:
        with urllib.request.urlopen(_GEOJSON_URL, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        result = {}
        for f in data['features']:
            if f['properties'].get('sgg') != '41590':
                continue
            name = f['properties']['adm_nm'].split()[-1]
            key  = name[:-1] if name.endswith('읍') or name.endswith('면') else name
            result[key] = _multipolygon_centroid(f['geometry'])
        print(f"  GeoJSON 좌표 로드: {len(result)}개 읍면동")
        return result
    except Exception as e:
        print(f"  ⚠ GeoJSON 로드 실패 ({e}) — 기본 좌표 사용", file=sys.stderr)
        return {}


_HWASEONG_CENTROID = _load_hwaseong_centroids()


def _get_coords(myeon: str) -> tuple:
    if myeon and myeon in _HWASEONG_CENTROID:
        return _HWASEONG_CENTROID[myeon]
    return _DEFAULT_LAT, _DEFAULT_LNG


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

    myeon = txt('locmenu')
    lat, lng = _get_coords(myeon)
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
        'myeon':            myeon,
        'bunji':            txt('locbunji'),
        'cause':            txt('firecause') or '미상',
        'damage_area_ha':   safe_float(txt('damagearea')),
        'lat':              lat,
        'lng':              lng,
    }


# ===== FETCH =====

def get_total_count() -> int:
    resp = requests.get(BASE_URL, params={
        'serviceKey': SERVICE_KEY, 'numOfRows': 1, 'pageNo': 1,
    }, timeout=30)
    resp.raise_for_status()
    root = ET.fromstring(resp.text)
    return int(root.findtext('.//totalCount') or 0)


def fetch_page_xml(page_no: int, max_retries: int = 3) -> list[ET.Element]:
    for attempt in range(1, max_retries + 1):
        try:
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
        except Exception as e:
            if attempt == max_retries:
                raise
            wait = attempt * 3
            print(f"  ⚠️  페이지 {page_no} 요청 실패 (시도 {attempt}/{max_retries}), {wait}초 후 재시도: {e}")
            time.sleep(wait)


def fetch_records_by_filter(label: str, filter_fn) -> list[dict]:
    """
    전체 데이터를 순회하며 filter_fn(item) == True 인 레코드만 추출.
    이미 캐시(total_count)가 있으면 재사용.
    """
    total = get_total_count()
    total_pages = (total + NUM_OF_ROWS - 1) // NUM_OF_ROWS
    print(f"  전체 {total}건 / {total_pages}페이지 순회 [{label}]")

    records, fetched = [], 0
    for page in range(1, total_pages + 1):
        items = fetch_page_xml(page)
        fetched += len(items)
        for item in items:
            if filter_fn(item):
                records.append(parse_item(item))
        if page % 10 == 0 or page == total_pages:
            print(f"  [{page}/{total_pages}] {fetched}건 처리 — {label} {len(records)}건")
        if not items:
            break
        time.sleep(0.2)
    return records


def fetch_hwaseong_records() -> list[dict]:
    """전체 데이터를 순회하며 화성시 데이터만 추출."""
    return fetch_records_by_filter(
        '화성시',
        lambda item: (item.findtext('locgungu') or '').strip() == FILTER_LOCGUNGU,
    )


def fetch_gyeonggi_records() -> list[dict]:
    """전체 데이터를 순회하며 경기도 전체 데이터 추출."""
    return fetch_records_by_filter(
        '경기도',
        lambda item: (item.findtext('locsi') or '').strip() == FILTER_LOCSI,
    )


# ===== ANALYSIS =====

def build_sigungu_stats(records: list[dict]) -> dict:
    """시군구별 발생 건수·피해면적 집계 (경기도 전체용)."""
    sgg_map: dict[str, dict] = {}
    for r in records:
        sgg = r.get('sigungu') or '미상'
        if sgg not in sgg_map:
            sgg_map[sgg] = {'count': 0, 'total_area': 0.0, 'causes': {}}
        sgg_map[sgg]['count'] += 1
        sgg_map[sgg]['total_area'] += r.get('damage_area_ha') or 0.0
        cause = r.get('cause') or '미상'
        sgg_map[sgg]['causes'][cause] = sgg_map[sgg]['causes'].get(cause, 0) + 1

    if not sgg_map:
        return {}
    max_count = max(d['count']      for d in sgg_map.values())
    max_area  = max(d['total_area'] for d in sgg_map.values()) or 1.0
    result = {}
    for sgg, d in sgg_map.items():
        score = (d['count'] / max_count) * 0.6 + (d['total_area'] / max_area) * 0.4
        result[sgg] = {
            'count':      d['count'],
            'total_area': round(d['total_area'], 2),
            'score':      round(score, 3),
            'level':      'HIGH' if score >= 0.6 else 'MEDIUM' if score >= 0.3 else 'LOW',
            'top_cause':  max(d['causes'], key=d['causes'].get),
        }
    return dict(sorted(result.items(), key=lambda x: -x[1]['score']))


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

def _save_records(output_file: Path, location: str,
                  records: list[dict], stats: dict, stats_key: str):
    """레코드 + 통계를 JSON으로 저장하고 요약 출력."""
    records.sort(key=lambda r: (r.get('year') or 0, r.get('month') or 0, r.get('day') or 0))
    year_counts: dict = {}
    for r in records:
        yr = r.get('year')
        if yr:
            year_counts[yr] = year_counts.get(yr, 0) + 1

    result = {
        'timestamp':   datetime.now(KST).isoformat(),
        'location':    location,
        'total_count': len(records),
        'year_counts': dict(sorted(year_counts.items())),
        stats_key:     stats,
        'records':     records,
    }
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 저장 완료: {output_file} ({len(records)}건)")
    print(f"   연도별: {dict(sorted(year_counts.items()))}")
    if stats:
        label = '읍면동' if stats_key == 'dong_stats' else '시군구'
        print(f"   {label}별 집계: {len(stats)}개 지역")
        print(f"   ─── 취약지역 TOP 5 ───")
        for name, stat in list(stats.items())[:5]:
            bar = '█' * max(1, int(stat['score'] * 10))
            print(f"   {name:<10} {bar:<12} {stat['count']}건 / "
                  f"{stat['total_area']}ha [{stat['level']}] 주원인: {stat['top_cause']}")


def _is_fresh(path: Path, hours: int = 24) -> bool:
    if not path.exists():
        return False
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=KST)
    age_h = (datetime.now(KST) - mtime).total_seconds() / 3600
    return age_h < hours


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # ── 화성시 ────────────────────────────────────────────
    if _is_fresh(OUTPUT_FILE):
        mtime = datetime.fromtimestamp(OUTPUT_FILE.stat().st_mtime, tz=KST)
        age_h = (datetime.now(KST) - mtime).total_seconds() / 3600
        print(f"⏭️  fire_history.json이 {age_h:.1f}시간 전 갱신됨 — 화성시 스킵")
    else:
        print(f"[산림청] 화성시 산불 이력 수집 (locgungu='{FILTER_LOCGUNGU}')")
        hw_records = fetch_hwaseong_records()
        _save_records(OUTPUT_FILE, '경기도 화성시',
                      hw_records, build_dong_stats(hw_records), 'dong_stats')

    # ── 경기도 전체 ────────────────────────────────────────
    if _is_fresh(OUTPUT_GYEONGGI):
        mtime = datetime.fromtimestamp(OUTPUT_GYEONGGI.stat().st_mtime, tz=KST)
        age_h = (datetime.now(KST) - mtime).total_seconds() / 3600
        print(f"⏭️  fire_history_gyeonggi.json이 {age_h:.1f}시간 전 갱신됨 — 경기도 스킵")
    else:
        print(f"\n[산림청] 경기도 전체 산불 이력 수집 (locsi='{FILTER_LOCSI}')")
        gg_records = fetch_gyeonggi_records()
        _save_records(OUTPUT_GYEONGGI, '경기도 전체',
                      gg_records, build_sigungu_stats(gg_records), 'sigungu_stats')


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f"❌ 수집 실패: {e}", file=sys.stderr)
        if OUTPUT_FILE.exists():
            print("⚠️  기존 fire_history.json 유지 — 파이프라인 계속 진행", file=sys.stderr)
            sys.exit(0)
        sys.exit(1)

