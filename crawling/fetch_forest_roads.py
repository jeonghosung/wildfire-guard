#!/usr/bin/env python3
"""
화성시 임도 SHP 데이터 → WGS84 GeoJSON 변환
입력: crawling/TB_FGDI_FS_ID300_41590.shp (EPSG:5179)
출력: public/data/forest_roads.json
외부 라이브러리 불필요 (순수 Python)
"""

import json
import math
import os
import struct
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE_DIR   = Path(__file__).parent.parent
SHP_PATH   = Path(__file__).parent / 'TB_FGDI_FS_ID300_41590.shp'
DBF_PATH   = Path(__file__).parent / 'TB_FGDI_FS_ID300_41590.dbf'
OUT_PATH   = BASE_DIR / 'public' / 'data' / 'forest_roads.json'

KST = timezone(timedelta(hours=9))

# ===== EPSG:5179 → WGS84 (역 횡메르카토르) =====
# GRS 1980 (Korea 2000 datum ≈ WGS84, 오차 < 1m)
_A  = 6_378_137.0
_F  = 1 / 298.257222101
_B  = _A * (1 - _F)
_E2 = 2 * _F - _F ** 2          # e²
_E4 = _E2 ** 2
_E6 = _E2 ** 3
_K0 = 0.9996
_LAT0 = math.radians(38.0)
_LON0 = math.radians(127.5)
_FE   = 1_000_000.0
_FN   = 2_000_000.0


def _meridional_arc(lat: float) -> float:
    """위도에 대한 자오선 호장(M)."""
    return _A * (
        (1 - _E2/4 - 3*_E4/64 - 5*_E6/256) * lat
        - (3*_E2/8 + 3*_E4/32 + 45*_E6/1024) * math.sin(2*lat)
        + (15*_E4/256 + 45*_E6/1024) * math.sin(4*lat)
        - (35*_E6/3072) * math.sin(6*lat)
    )


_M0 = _meridional_arc(_LAT0)


def tm5179_to_wgs84(easting: float, northing: float) -> tuple:
    """EPSG:5179 좌표 → (위도, 경도) WGS84 변환."""
    x = easting  - _FE
    y = northing - _FN
    M = _M0 + y / _K0

    mu = M / (_A * (1 - _E2/4 - 3*_E4/64 - 5*_E6/256))

    e1  = (1 - math.sqrt(1 - _E2)) / (1 + math.sqrt(1 - _E2))
    lat1 = (mu
             + (3*e1/2 - 27*e1**3/32)           * math.sin(2*mu)
             + (21*e1**2/16 - 55*e1**4/32)      * math.sin(4*mu)
             + (151*e1**3/96)                    * math.sin(6*mu)
             + (1097*e1**4/512)                  * math.sin(8*mu))

    sin1 = math.sin(lat1)
    cos1 = math.cos(lat1)
    tan1 = math.tan(lat1)

    N1  = _A / math.sqrt(1 - _E2 * sin1**2)
    T1  = tan1**2
    C1  = _E2 / (1 - _E2) * cos1**2
    R1  = _A * (1 - _E2) / (1 - _E2 * sin1**2) ** 1.5
    D   = x / (N1 * _K0)

    lat = lat1 - (N1 * tan1 / R1) * (
        D**2/2
        - (5 + 3*T1 + 10*C1 - 4*C1**2 - 9*_E2)          * D**4/24
        + (61 + 90*T1 + 298*C1 + 45*T1**2 - 252*_E2 - 3*C1**2) * D**6/720
    )
    lon = _LON0 + (
        D
        - (1 + 2*T1 + C1)                                 * D**3/6
        + (5 - 2*C1 + 28*T1 - 3*C1**2 + 8*_E2 + 24*T1**2) * D**5/120
    ) / cos1

    return round(math.degrees(lat), 7), round(math.degrees(lon), 7)


# ===== SHP 파서 (PolyLine = shape type 3) =====

def read_shp(path: Path) -> list:
    """SHP 파일에서 PolyLine 레코드 목록 반환."""
    records = []
    with open(path, 'rb') as f:
        f.read(100)                          # file header skip
        while True:
            hdr = f.read(8)
            if len(hdr) < 8:
                break
            rec_num = struct.unpack('>i', hdr[0:4])[0]
            content_len = struct.unpack('>i', hdr[4:8])[0] * 2
            data = f.read(content_len)
            shape_type = struct.unpack('<i', data[0:4])[0]
            if shape_type != 3:              # PolyLine만 처리
                records.append({'num': rec_num, 'parts': [], 'points': []})
                continue
            num_parts  = struct.unpack('<i', data[36:40])[0]
            num_points = struct.unpack('<i', data[40:44])[0]
            parts      = list(struct.unpack(f'<{num_parts}i', data[44:44+num_parts*4]))
            pts_off    = 44 + num_parts * 4
            raw        = struct.unpack(f'<{num_points*2}d', data[pts_off:pts_off+num_points*16])
            points     = [(raw[i*2], raw[i*2+1]) for i in range(num_points)]
            parts.append(num_points)         # sentinel
            record_parts = []
            for pi in range(num_parts):
                record_parts.append(points[parts[pi]:parts[pi+1]])
            records.append({'num': rec_num, 'parts': record_parts})
    return records


# ===== DBF 파서 =====

def read_dbf(path: Path) -> list:
    """DBF 파일에서 속성 레코드 목록 반환."""
    with open(path, 'rb') as f:
        hdr       = f.read(32)
        num_recs  = struct.unpack('<i', hdr[4:8])[0]
        hdr_size  = struct.unpack('<H', hdr[8:10])[0]
        rec_size  = struct.unpack('<H', hdr[10:12])[0]

        fields = []
        while True:
            fd = f.read(32)
            if not fd or fd[0] == 0x0D:
                break
            name  = fd[0:11].split(b'\x00')[0].decode('cp949', errors='replace').strip()
            ftype = chr(fd[11])
            flen  = fd[16]
            fields.append((name, ftype, flen))

        f.seek(hdr_size)
        records = []
        for _ in range(num_recs):
            del_flag = f.read(1)
            raw = f.read(rec_size - 1)
            row, off = {}, 0
            for name, ftype, flen in fields:
                val = raw[off:off+flen].decode('cp949', errors='replace').strip()
                row[name] = val
                off += flen
            records.append(row)
    return records


# ===== 메인 =====

def main():
    print('=' * 60)
    print('화성시 임도 SHP → WGS84 변환')
    print('=' * 60)

    shp_records = read_shp(SHP_PATH)
    dbf_records = read_dbf(DBF_PATH)
    print(f'레코드 수: {len(shp_records)}개 (SHP), {len(dbf_records)}개 (DBF)')

    roads = []
    for i, (shp, dbf) in enumerate(zip(shp_records, dbf_records)):
        parts_wgs = []
        for part in shp.get('parts', []):
            wgs_part = [tm5179_to_wgs84(x, y) for x, y in part]
            parts_wgs.append(wgs_part)

        all_lats = [lat for part in parts_wgs for lat, lng in part]
        all_lngs = [lng for part in parts_wgs for lat, lng in part]

        road_id = dbf.get('HSTR_MNNMB', str(i + 1))
        road_nm = dbf.get('FRRD_NM', '') or f'임도_{road_id}'
        fclt    = dbf.get('FRRD_FCLT', '')
        fcltd_str = dbf.get('FRRD_FCLTD', '0') or '0'
        try:
            fcltd = round(float(fcltd_str), 5)
        except ValueError:
            fcltd = 0.0

        # 각 파트를 하나의 도로 세그먼트로 저장 (coords: [[lat, lng], ...])
        # optimize_routes.py의 RoadNetwork._build()와 동일한 형식
        for pi, part_wgs in enumerate(parts_wgs):
            if len(part_wgs) < 2:
                continue
            coords = [[lat, lng] for lat, lng in part_wgs]
            roads.append({
                'id':           f'fr_{road_id}_{pi}',
                'name':         road_nm,
                'highway_type': 'forest_road',
                'label':        '임도',
                'priority':     0,               # 임도는 최우선
                'color':        '#228B22',
                'oneway':       False,
                'maxspeed':     None,
                'ref':          road_id,
                'fclt':         fclt,
                'fclt_km':      fcltd,
                'node_count':   len(coords),
                'coords':       coords,
            })
            lat0, lng0 = coords[0]
            latN, lngN = coords[-1]
            print(f'  [{road_id} part{pi}] {len(coords)} pts  '
                  f'start=({lat0:.5f},{lng0:.5f})  end=({latN:.5f},{lngN:.5f})')

    bbox_lats = [c[0] for r in roads for c in r['coords']]
    bbox_lngs = [c[1] for r in roads for c in r['coords']]
    summary = {
        'total_roads':  len(roads),
        'total_nodes':  sum(r['node_count'] for r in roads),
        'bbox': {
            'south': round(min(bbox_lats), 6),
            'west':  round(min(bbox_lngs), 6),
            'north': round(max(bbox_lats), 6),
            'east':  round(max(bbox_lngs), 6),
        },
        'by_type': {
            'forest_road': {
                'count': len(roads),
                'label': '임도',
                'color': '#228B22',
            }
        },
    }

    result = {
        'timestamp': datetime.now(KST).isoformat(),
        'source':    '산림청 산림공간정보 TB_FGDI_FS_ID300 (화성시)',
        'crs_orig':  'EPSG:5179 (Korea_2000_KUC)',
        'crs_out':   'WGS84 (EPSG:4326)',
        'summary':   summary,
        'roads':     roads,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f'\n✅ 저장 완료: {OUT_PATH}')
    print(f'   임도 구간: {len(roads)}개 / 노드: {summary["total_nodes"]}개')
    print(f'   BBox: {summary["bbox"]}')


if __name__ == '__main__':
    main()
