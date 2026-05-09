# 화성시 산불 감시요원 최적 노선도

![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)
![JavaScript](https://img.shields.io/badge/JavaScript-ES2022-F7DF1E?logo=javascript&logoColor=black)
![scikit-learn](https://img.shields.io/badge/scikit--learn-1.3-F7931E?logo=scikitlearn&logoColor=white)
![XGBoost](https://img.shields.io/badge/XGBoost-1.7-189B3B)
![Leaflet](https://img.shields.io/badge/Leaflet-1.9-199900?logo=leaflet&logoColor=white)
![GitHub Actions](https://img.shields.io/badge/GitHub_Actions-자동화-2088FF?logo=githubactions&logoColor=white)
![Cloudflare Pages](https://img.shields.io/badge/Cloudflare_Pages-배포-F38020?logo=cloudflare&logoColor=white)

> **배포 주소:** https://adsp.pages.dev

AI 기반 산불 위험도 예측과 최적화 알고리즘을 결합하여, 화성시 감시요원의 일일 순찰 노선을 자동으로 산출하고 지도 위에 시각화하는 시스템입니다.

---

## 목차

1. [프로젝트 배경 및 목적](#1-프로젝트-배경-및-목적)
2. [시스템 구조도](#2-시스템-구조도)
3. [사용 데이터](#3-사용-데이터)
4. [AI 모델 상세](#4-ai-모델-상세)
5. [노선 최적화 상세](#5-노선-최적화-상세)
6. [자동화 파이프라인](#6-자동화-파이프라인)
7. [결과 분석](#7-결과-분석)
8. [한계점 및 개선 방향](#8-한계점-및-개선-방향)
9. [프로젝트 구조](#9-프로젝트-구조)
10. [참고 자료](#10-참고-자료)

---

## 1. 프로젝트 배경 및 목적

### 화성시 산불 현황

화성시는 2011년부터 2025년까지 **135건**의 산불이 기록된 경기도 내 고위험 지역입니다.

| 주요 원인 | 비중 |
|---|---|
| 쓰레기소각 | 가장 높은 빈도 (서부 해안권 집중) |
| 입산자실화 | 오후 등산객 활동과 연계 |
| 농산부산물소각 | 오전 농경지 작업 시간대 집중 |
| 담뱃불실화 | 야간·도시 경계지역 취약 |

### 기존 문제점

- 감시요원 배치가 경험에 의존하여 데이터 근거가 부족함
- 시간대별 위험 패턴(오전 소각·오후 등산객·야간 화점)을 반영하지 못함
- 요원별 순찰 구역이 수동으로 설정되어 효율 편차가 큼

### 해결 방향

- 산불 이력·기상·산림 위험등급을 결합한 **AI 앙상블 모델**로 읍면동별 위험도를 매일 예측
- **K-Means + Greedy TSP + Dijkstra** 파이프라인으로 요원별 최적 노선을 자동 산출
- 시간대(오전·오후·야간)별 스코어링으로 순찰 우선순위를 동적으로 조정
- GitHub Actions + Cloudflare Pages로 매일 오전 6시 자동 업데이트·배포

---

## 2. 시스템 구조도

```
┌─────────────────────────────────────────────────────────────────┐
│                    데이터 수집 (매일 06:00 KST)                  │
│                                                                 │
│  NASA FIRMS ──┐                                                 │
│  산림청 이력 ──┤                                                 │
│  기상청 실황 ──┼──► public/data/ (JSON 캐시)                    │
│  기상청 중기 ──┤                                                 │
│  OSM 도로망 ──┘                                                 │
└─────────────────┬───────────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                     AI 예측 파이프라인                           │
│                                                                 │
│  train_predict_hwaseong.py                                      │
│  ├── RandomForest (n=300, depth=12, class_weight=balanced)      │
│  ├── XGBoost     (n=300, lr=0.04, scale_pos_weight=imbalance)   │
│  └── 앙상블 (RF×0.40 + XGB×0.60) → predicted_risk.json         │
│                                                                 │
│  build_grid_hwaseong.py                                         │
│  └── 5km 격자 위험도 매핑 → grid_risk.json                      │
└─────────────────┬───────────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                    노선 최적화 파이프라인                         │
│                                                                 │
│  find_optimal_guards.py                                         │
│  └── K-Means + 엘보우 기법 → optimal_guard_count.json           │
│       (HIGH 지역 수 0~15 룩업테이블, 최소 3팀 보장)              │
│                                                                 │
│  optimize_routes.py                                             │
│  ├── 룩업테이블로 NUM_GUARDS 결정 (max(3, 룩업값))              │
│  ├── 시간대별 스코어링 (AM/PM/NIGHT/ALL)                        │
│  ├── K-Means 구역 분할 + 순찰 시간 균등화                       │
│  ├── Greedy TSP 노선 정렬                                       │
│  └── Dijkstra + OSM 실제 도로 → optimal_routes.json             │
└─────────────────┬───────────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                      시각화 (index.html + main.js)               │
│                                                                 │
│  Leaflet 지도                                                   │
│  ├── 읍면동 AI 위험도 마커 (HIGH/MEDIUM/LOW)                    │
│  ├── 5km 격자 위험도 히트맵                                     │
│  ├── 감시요원 순찰 노선 (위험도 기반 실선/점선)                  │
│  ├── NASA FIRMS 실시간 화점                                     │
│  └── 시간대 전환 패널 (AM/PM/NIGHT/ALL)                         │
└─────────────────┬───────────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────────┐
│              자동 배포 (GitHub Actions → Cloudflare Pages)       │
│                                                                 │
│  매일 06:00 KST ──► update_data.yml ──► deploy.yml             │
│  매주 일요일   ──► update_data_weekly.yml (과거기상·OSM)        │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. 사용 데이터

| 데이터 | 출처 | 갱신 주기 | 용도 |
|---|---|---|---|
| **산불 이력** | 산림청 산불통계정보시스템 | 주 1회 | AI 학습 양성 샘플 (2011–2025, 135건) |
| **초단기실황** | 기상청 Open API | 매일 | 현재 온도·습도·풍속 → 예측 입력값 |
| **중기예보** | 기상청 Open API | 매일 | 10일 예보 기상 트렌드 사이드바 표시 |
| **과거관측** | 기상청 Open API (수원관측소) | 주 1회 | 월별 기온·습도·풍속 통계 → 학습 특성 |
| **산불위험예보** | 산림청 Open API | 매일 | 위험등급(`forest_grade`) → 학습 특성 |
| **NASA FIRMS** | VIIRS SNPP NRT | 실시간 | 야간 순찰 스코어링 보정, 화점 지도 표시 |
| **OSM 도로망** | OpenStreetMap Overpass API | 주 1회 | Dijkstra 실제 도로 경로 계산 |

### 기상 화재위험지수 (FWI)

기상청 초단기실황의 온도·습도·풍속을 조합하여 자체 산출하는 복합 지수입니다.

```
FWI = (temp_norm × 0.35) + (wind_norm × 0.30) + ((1 - humidity_norm) × 0.35)
```

FWI는 오후 시간대 스코어링에 추가 가중치(`fwi × 0.10`)로 반영됩니다.

---

## 4. AI 모델 상세

### 알고리즘

**RandomForest + XGBoost 앙상블 (RF 40% + XGB 60%)**

```
최종 확률 = RF.predict_proba() × 0.40 + XGB.predict_proba() × 0.60
```

XGB에 더 높은 가중치를 부여하는 이유: 불균형 데이터(양성 131건 vs 음성 14,451건)에서 `scale_pos_weight` 파라미터를 통해 클래스 불균형을 명시적으로 처리하는 XGBoost가 소수 클래스(화재 발생) 감지에 더 강인한 성능을 보이기 때문입니다.

### 학습 특성 11개

| # | 특성명 | 설명 |
|---|---|---|
| 1 | `emd_enc` | 읍면동 레이블 인코딩 (공간적 위치 정보) |
| 2 | `month` | 예측 월 (계절성 반영) |
| 3 | `temp` | 월별 평균 최고기온 (°C) |
| 4 | `humidity` | 월별 평균 습도 (%) |
| 5 | `wind_speed` | 월별 평균 최대풍속 (m/s) |
| 6 | `hist_count` | 읍면동 과거 산불 발생 횟수 |
| 7 | `hist_area` | 읍면동 과거 산불 피해 면적 합계 (ha) |
| 8 | `hist_score` | 읍면동 종합 위험 점수 (이력 기반) |
| 9 | `month_fire_score` | 해당 월의 평균 화재 위험도 (과거관측 기반) |
| 10 | `month_high_ratio` | 해당 월의 고위험일 비율 |
| 11 | `forest_grade` | 산림청 산불위험예보 등급 (0–4) |

### 성능

| 지표 | 값 |
|---|---|
| ROC-AUC | **0.69** |
| 학습 데이터 | 양성 131건 / 음성 14,451건 |
| 테스트 분할 | 80:20 (stratified) |
| 불균형 처리 | RF: `class_weight='balanced'` / XGB: `scale_pos_weight=imbalance_ratio` |

### 시간대별 위험도 배율

학습으로 산출된 기본 확률에 시간대별 배율을 곱하여 각 시간대 위험도를 도출합니다.

| 시간대 | 배율 | 근거 |
|---|---|---|
| 오전 (06–12시) | × 0.80 | 소각 활동은 많지만 야외 체류 인구 적음 |
| 오후 (12–18시) | × 1.40 | 입산자·흡연자 활동 최다, 기상 위험도 정점 |
| 야간 (18–06시) | × 0.50 | 전반적 위험 낮음, 단 화점 근접 시 급상승 |

### 위험도 임계값

```
probability ≥ 0.30 → HIGH   (위험)
probability ≥ 0.12 → MEDIUM (주의)
probability <  0.12 → LOW   (관심)
```

---

## 5. 노선 최적화 상세

### 요원 수 결정 (엘보우 기법 + 최소 3팀 보장)

`find_optimal_guards.py`는 실제 HIGH 지역 수(0–15개)에 따른 최적 요원 수를 미리 시뮬레이션하여 **룩업테이블**로 저장합니다.

```
optimal_guard_count.json
├── high_count_table: { "high_0": 1, "high_1": 1, ..., "high_15": 6 }
└── min_guards: 3  (화성시 지리적 3개 권역 근거)
```

**최소 3팀 보장 근거 — 화성시 지리적 3개 권역**

화성시는 지리적으로 뚜렷하게 3개 권역으로 구분되며, 각 권역에 최소 1명 배치가 필요합니다.

| 권역 | 해당 읍면동 |
|---|---|
| 서부 해안 권역 | 서신면, 우정읍, 송산면, 마도면 |
| 중부 내륙 권역 | 향남읍, 팔탄면, 남양읍, 양감면 |
| 동부 도시 권역 | 봉담읍, 동탄동, 정남면, 비봉면 |

`optimize_routes.py`는 룩업테이블 조회 후 `NUM_GUARDS = max(3, 룩업값)`을 적용하여 최소 3팀을 항상 보장합니다.

### K-Means 구역 분할

순찰 지점 상위 24개를 요원 수(K)만큼 군집화합니다. 시간대별 스코어를 가중치로 적용한 **가중 K-Means++ 초기화**를 사용하여 고위험 지점이 동일 요원 구역에 집중되는 것을 방지합니다.

### Greedy TSP 노선 정렬

각 구역 내 순찰 순서를 결정합니다.

```
출발점: 위험도(score) 최고 지점
이동 기준: score × 0.6 − dist_normalized × 0.4
```

순수 거리 최소화 대신 위험도에 가중치를 두어, 고위험 지점을 순찰 초반에 집중 방문하도록 설계되었습니다.

### Dijkstra + OSM 실제 도로

OpenStreetMap에서 수집한 화성시 도로망으로 `RoadNetwork` 그래프를 구성하고, 웨이포인트 간 실제 도로 최단 경로를 Dijkstra 알고리즘으로 계산합니다. OSM 데이터가 없을 경우 직선거리 × 1.25 폴백을 적용합니다.

### 시간대별 스코어링 로직

| 시간대 | 스코어링 기준 |
|---|---|
| **오전 (AM)** | 소각 원인(`쓰레기소각`, `논밭태우기`, `농산부산물소각`) 지역에 +0.50 보너스 |
| **오후 (PM)** | 입산자·흡연 원인(`입산자실화`, `담뱃불실화`) 지역에 +0.40 보너스 + FWI × 0.10 |
| **야간 (NIGHT)** | NASA FIRMS 화점 15km 이내 시 최대 +0.50 / 없을 경우 반복화재 `hist_count` 우선 |
| **전체 (ALL)** | AI 기본 예측 확률 그대로 사용 |

### 요원 균등화 알고리즘

K-Means 군집화 후 요원별 예상 순찰 시간 편차가 30분을 초과할 경우, 최대 25회 반복으로 지점을 재배치합니다.

```
이동 대상: 가장 바쁜 구역의 지점 중
           (idle 구역 중심까지의 거리 − score × 8) 이 가장 작은 지점
```

스코어가 낮고 한가한 구역에 가까운 지점을 이동시켜, 위험도 손실을 최소화하면서 시간을 균등화합니다.

### 노선 표시 방식 (위험도 기반)

| avg_risk | 스타일 |
|---|---|
| ≥ 0.30 (HIGH) | 굵은 실선 (weight: 4) |
| ≥ 0.15 (MEDIUM) | 실선 (weight: 2) |
| < 0.15 (LOW) | 점선 (weight: 2, dashArray: 6,4) |

---

## 6. 자동화 파이프라인

### 실행 스케줄

| 워크플로우 | 실행 시각 | 내용 |
|---|---|---|
| `update_data.yml` | **매일 06:00 KST** | 기상·산불예보·AI예측·노선 전체 갱신 |
| `update_data_weekly.yml` | **매주 일요일 05:00 KST** | 과거기상(5년)·OSM 도로망·산불이력 갱신 |
| `deploy.yml` | push 트리거 | Cloudflare Pages 자동 배포 |

### 일별 파이프라인 실행 순서

```
1. fetch_weather.py          기상청 초단기실황 수집
2. fetch_forest_risk.py      산림청 산불위험예보 수집
3. fetch_mid_weather.py      기상청 중기예보 (10일) 수집
4. fetch_fire_data.py        산림청 산불 이력 수집 (24h 캐시)
5. fetch_osm_roads.py        OpenStreetMap 도로망 수집
            ↓
6. train_predict_hwaseong.py RF+XGB 앙상블 위험도 예측
7. build_grid_hwaseong.py    5km 격자 위험도 매핑
8. find_optimal_guards.py    엘보우 기법 요원 수 룩업테이블 생성
9. optimize_routes.py        K-Means + TSP + Dijkstra 노선 산출
            ↓
10. git commit & push        JSON 데이터 자동 커밋
11. Cloudflare Pages 배포    정적 사이트 갱신
```

---

## 7. 결과 분석

> 아래 수치는 2026-05-09 기준 최신 예측 결과입니다.

### AI 예측 요약

| 구분 | 전체 | 오전 | 오후 | 야간 |
|---|---|---|---|---|
| HIGH 지역 수 | 4개 | 4개 | 8개 | 1개 |
| MEDIUM 지역 수 | 16개 | — | — | — |
| LOW 지역 수 | 61개 | — | — | — |
| 총 예측 읍면동 | 81개 | — | — | — |

### 위험 지역 TOP 5

| 순위 | 읍면동 | 면 | 확률 | 등급 | 주요 원인 |
|---|---|---|---|---|---|
| 1 | 전곡 | 서신 | 0.686 | HIGH | 쓰레기소각 |
| 2 | 송림 | 남양 | 0.523 | HIGH | 쓰레기소각 |
| 3 | 백미 | 서신 | 0.521 | HIGH | 쓰레기소각 |
| 4 | 중 | — | 0.387 | HIGH | 담뱃불실화 |
| 5 | 원평 | 매송 | 0.290 | MEDIUM | 입산자실화 |

서부 해안권(서신면, 남양읍)이 쓰레기소각 원인으로 상위권을 차지하고 있습니다.

### 요원별 순찰 효율 (전체 시간대 기준)

| 요원 | 담당 구역 | 총 거리 | 예상 시간 | 평균 위험도 | 노선 유형 |
|---|---|---|---|---|---|
| 요원 1 | 서신·장안 구역 | 55.6 km | 4.1 h | 0.283 | 실선 (MEDIUM) |
| 요원 2 | 남양·송산 구역 | 46.1 km | 3.5 h | 0.178 | 실선 (MEDIUM) |
| 요원 3 | 팔탄·봉담 구역 | 73.3 km | 4.2 h | 0.144 | 점선 (LOW) |

### 시간대별 위험 지역 비교

- **오전**: 서신·남양 소각 지역 집중 → 요원 1·2 서부 배치 강화
- **오후**: HIGH 지역 8개로 급증 → 입산자 활동 지역(팔탄·봉담) 추가 편입
- **야간**: HIGH 1개로 감소 → FIRMS 화점 인근 집중 순찰

---

## 8. 한계점 및 개선 방향

### 데이터 부족

화성시 산불 이력이 135건(2011–2025)에 불과하여 학습 양성 샘플이 제한적입니다. 더 넓은 지역(경기도 전체, 전국)의 이력 데이터를 포함하면 일반화 성능이 향상될 수 있습니다.

### 모델 정확도

현재 ROC-AUC **0.69** (목표: **0.80**). 개선 방안:
- 필지별 임상도(수종·수령·밀도) 특성 추가
- 전날 기상 데이터(lag feature) 포함
- NDVI(식생지수) 위성 이미지 특성 결합
- LightGBM 또는 TabNet 추가 앙상블 실험

### 임도 데이터 미연결

현재 OSM 도로망 기반 경로에 화성시 임도(산림도로)가 포함되어 있지 않습니다. 산림청 임도 GIS 데이터를 연계하면 실제 순찰 가능 경로 정확도가 높아집니다.

### 좌표 정밀도

읍면동 단위 예측이므로 순찰 지점 좌표가 면 중심에서 ±0.018° 범위의 근사값으로 배치됩니다. 필지·구역 단위 GIS 데이터가 확보되면 정밀도가 향상됩니다.

---

## 9. 프로젝트 구조

```
hosung1/
├── index.html                      # 메인 지도 UI
├── main.js                         # Leaflet 지도 렌더링·사이드바·노선 시각화
├── style.css                       # 전체 스타일
├── requirements.txt                # Python 패키지 목록
│
├── crawling/                       # 데이터 수집 스크립트
│   ├── fetch_weather.py            # 기상청 초단기실황
│   ├── fetch_mid_weather.py        # 기상청 중기예보
│   ├── fetch_historical_weather.py # 기상청 과거관측 (수원, 5년)
│   ├── fetch_fire_data.py          # 산림청 산불 이력
│   ├── fetch_forest_risk.py        # 산림청 산불위험예보
│   └── fetch_osm_roads.py          # OpenStreetMap 도로망
│
├── scripts/                        # 분석·최적화 스크립트
│   ├── train_predict_hwaseong.py   # RF+XGBoost 앙상블 위험도 예측
│   ├── build_grid_hwaseong.py      # 5km 격자 위험도 매핑
│   ├── find_optimal_guards.py      # 엘보우 기법 최적 요원 수 산출
│   └── optimize_routes.py          # K-Means + TSP + Dijkstra 노선 최적화
│
├── public/data/                    # 자동 생성 JSON 데이터
│   ├── predicted_risk.json         # 읍면동별 AI 위험도 예측 결과
│   ├── grid_risk.json              # 5km 격자 위험도
│   ├── optimal_guard_count.json    # 요원 수 룩업테이블
│   ├── optimal_routes.json         # 최적 순찰 노선
│   ├── weather.json                # 기상청 실황
│   ├── mid_weather.json            # 기상청 중기예보
│   ├── forest_risk.json            # 산림청 산불위험예보
│   ├── fire_history.json           # 산불 이력
│   └── osm_roads.json              # OSM 도로망
│
└── .github/workflows/
    ├── update_data.yml             # 일별 데이터 갱신 (매일 06:00 KST)
    ├── update_data_weekly.yml      # 주간 데이터 갱신 (매주 일요일 05:00 KST)
    └── deploy.yml                  # Cloudflare Pages 자동 배포
```

---

## 10. 참고 자료

### 오픈소스 참고 프로젝트

- [2blackcow/Wildfire](https://github.com/2blackcow/Wildfire) — 한국 산불 데이터 분석 및 시각화 레퍼런스

### 공공데이터포털 API

| API | 제공 기관 | 활용 데이터 |
|---|---|---|
| [기상청 초단기실황조회](https://www.data.go.kr/data/15084084/openapi.do) | 기상청 | 온도·습도·풍속 실황 |
| [기상청 중기예보조회](https://www.data.go.kr/data/15059468/openapi.do) | 기상청 | 10일 기상 예보 |
| [기상청 지상기상관측자료](https://www.data.go.kr/data/15077855/openapi.do) | 기상청 | 수원관측소 5년 과거관측 |
| [산림청 산불위험예보정보](https://www.data.go.kr/data/15113026/openapi.do) | 산림청 | 산불 위험등급 예보 |
| 산림청 산불통계정보시스템 | 산림청 | 화성시 산불 이력 (2011–2025) |

### 외부 데이터 소스

| 출처 | URL | 용도 |
|---|---|---|
| NASA FIRMS | https://firms.modaps.eosdis.nasa.gov | VIIRS SNPP 실시간 화점 |
| OpenStreetMap | https://www.openstreetmap.org | 도로망 (Overpass API) |

### 주요 라이브러리

| 라이브러리 | 버전 | 용도 |
|---|---|---|
| scikit-learn | ≥ 1.3 | RandomForest, K-Means, 데이터 전처리 |
| XGBoost | ≥ 1.7 | 그래디언트 부스팅 앙상블 |
| pandas / numpy | ≥ 2.0 / 1.24 | 데이터 처리 |
| Leaflet.js | 1.9 | 지도 시각화 |
| overpy | ≥ 0.6 | Overpass API 클라이언트 |
