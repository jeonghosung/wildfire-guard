"""
화성시 읍면동별 산불 위험도 AI 예측 모델 v2
- 학습 데이터:
  · public/data/fire_history.json        (산림청 산불 이력)
  · public/data/weather.json             (기상청 초단기실황)
  · public/data/historical_weather.json  (기상청 5년 과거관측, 선택)
  · public/data/forest_risk.json         (산림청 산불위험예보, 선택)
- 모델: RandomForest + XGBoost 앙상블 (XGBoost 미설치 시 RF 단독)
- 출력: public/data/predicted_risk.json (시간대별 위험도 포함)
"""

import json
import os
import sys
import numpy as np
import pandas as pd
from datetime import datetime
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import roc_auc_score, classification_report
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder

try:
    from xgboost import XGBClassifier
    HAS_XGB = True
except ImportError:
    print("⚠  XGBoost 미설치 — RandomForest 단독 사용 (pip install xgboost)")
    HAS_XGB = False

# ===== 경로 설정 =====
BASE_DIR              = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIRE_HISTORY_PATH     = os.path.join(BASE_DIR, 'public', 'data', 'fire_history.json')
GYEONGGI_HISTORY_PATH = os.path.join(BASE_DIR, 'public', 'data', 'fire_history_gyeonggi.json')
WEATHER_PATH          = os.path.join(BASE_DIR, 'public', 'data', 'weather.json')
HIST_WEATHER_PATH     = os.path.join(BASE_DIR, 'public', 'data', 'historical_weather.json')
FOREST_RISK_PATH      = os.path.join(BASE_DIR, 'public', 'data', 'forest_risk.json')
OUTPUT_PATH           = os.path.join(BASE_DIR, 'public', 'data', 'predicted_risk.json')

# ===== 위험도 임계값 =====
THRESH_HIGH   = 0.30    # ≥ 30% → 위험
THRESH_MEDIUM = 0.12    # ≥ 12% → 주의

# 시간대별 배율 (오전/오후/야간)
TIME_MULT = {'AM': 0.80, 'PM': 1.40, 'NIGHT': 0.50}

# ===== 데이터 로드 =====
print("=" * 60)
print("화성시 산불 위험도 AI 예측 모델 v2")
print("=" * 60)

with open(FIRE_HISTORY_PATH, 'r', encoding='utf-8') as f:
    fire_data = json.load(f)

with open(WEATHER_PATH, 'r', encoding='utf-8') as f:
    weather_data = json.load(f)

# --- 과거기상 (선택) ---
hist_monthly: dict[int, dict] = {}   # month(int) → monthly stats
if os.path.exists(HIST_WEATHER_PATH):
    with open(HIST_WEATHER_PATH, 'r', encoding='utf-8') as f:
        hw = json.load(f)
    for m_str, stats in hw.get('monthly_stats', {}).items():
        hist_monthly[int(m_str)] = stats
    total_rec = hw.get('total_records', 0)
    print(f"  과거기상 로드: {len(hist_monthly)}개월 · {total_rec}일치 실측값")
else:
    print("  historical_weather.json 없음 — 계절 추정값 사용")

# --- 경기도 전체 산불 이력 (선택, 추가 학습용) ---
gyeonggi_records: list = []
gyeonggi_sigungu_stats: dict = {}
if os.path.exists(GYEONGGI_HISTORY_PATH):
    with open(GYEONGGI_HISTORY_PATH, 'r', encoding='utf-8') as f:
        gg = json.load(f)
    gyeonggi_records      = gg.get('records', [])
    gyeonggi_sigungu_stats = gg.get('sigungu_stats', {})
    print(f"  경기도 산불 이력 로드: {len(gyeonggi_records)}건 / {len(gyeonggi_sigungu_stats)}개 시군구")
else:
    print("  fire_history_gyeonggi.json 없음 — 화성시 단독 학습")

# --- 산불위험예보 (선택) ---
forest_danger_grade = 0
forest_overall_label = '없음'
if os.path.exists(FOREST_RISK_PATH):
    with open(FOREST_RISK_PATH, 'r', encoding='utf-8') as f:
        fr = json.load(f)
    # 신규 API: meanavg(0-100) 기반 — grade로 역매핑
    forecasts_fr = fr.get('forecasts', [])
    if forecasts_fr and 'meanavg' in forecasts_fr[0]:
        peak_avg = max(f.get('meanavg', 0) for f in forecasts_fr)
        forest_danger_grade = (4 if peak_avg >= 76 else
                               3 if peak_avg >= 51 else
                               2 if peak_avg >= 26 else 1)
    else:
        grades = [f.get('danger_grade', 0) for f in forecasts_fr]
        forest_danger_grade = max(grades) if grades else 0
    forest_overall_label = fr.get('overall_label', '없음')
    print(f"  산불위험예보 로드: 최대 {forest_danger_grade}등급 · {forest_overall_label}")
else:
    print("  forest_risk.json 없음 — 위험등급 0 사용")

records    = fire_data.get('records', [])
dong_stats = fire_data.get('dong_stats', {})
parsed     = weather_data.get('parsed', {})

current_temp       = parsed.get('temperature', 15.0)
current_humidity   = parsed.get('humidity', 50.0)
current_wind_speed = parsed.get('wind_speed', 3.0)
current_month      = datetime.now().month

print(f"\n산불 기록: {len(records)}건  읍면동: {len(dong_stats)}개")
print(f"현재 기상: {current_temp}°C  습도 {current_humidity}%  "
      f"풍속 {current_wind_speed}m/s  {current_month}월")

# ===== 인코더 =====
CAUSE_CATEGORIES = [
    '쓰레기소각', '입산자실화', '농산부산물소각', '담뱃불실화',
    '건축물화재비화', '논밭태우기', '담배꽁초', '기타',
]
cause_enc = LabelEncoder().fit(CAUSE_CATEGORIES)
all_emds  = sorted(dong_stats.keys())
emd_enc   = LabelEncoder().fit(all_emds)

def encode_cause(c):
    c = c if c in CAUSE_CATEGORIES else '기타'
    return int(cause_enc.transform([c])[0])

# ===== 월별 기상 특성 =====
def _seasonal_fallback(month):
    """과거기상 없을 때 월별 추정값."""
    temp = -2 + month * 3.5 if month <= 7 else 28 - (month - 7) * 3.0
    hum  = max(25, 75 - abs(month - 7) * 5)
    wind = 3.0 + (1.5 if month in [3, 4, 11, 12] else 0)
    return round(temp, 1), round(hum, 1), round(wind, 1)

def get_monthly_features(month: int) -> tuple:
    """(temp, humidity, wind, fire_score_avg, high_risk_ratio) 반환."""
    if month in hist_monthly:
        s        = hist_monthly[month]
        tf, hf, wf = _seasonal_fallback(month)
        temp     = s.get('temp_max_avg_c')    or tf
        hum      = s.get('humidity_avg_pct')  or hf
        wind     = s.get('wind_max_avg_ms')   or wf
        f_score  = s.get('fire_score_avg')    or 0.3
        h_days   = s.get('high_risk_days')    or 0
        t_days   = s.get('total_days')        or 1
        h_ratio  = h_days / max(t_days, 1)
    else:
        temp, hum, wind = _seasonal_fallback(month)
        # 봄철(3-5월)과 가을(10-11월) 기본 위험도 높게 설정
        f_score = 0.55 if month in [3, 4, 5, 10, 11] else 0.2
        h_ratio = 0.25 if month in [3, 4, 5, 10, 11] else 0.05
    return temp, hum, wind, round(f_score, 3), round(h_ratio, 3)

# ===== 학습 데이터 구성 =====
fire_set = set()
pos_rows = []

for r in records:
    emd = r.get('emd', '')
    if emd not in all_emds:
        continue
    year  = r.get('year',  2020)
    month = r.get('month', 3)
    cause = r.get('cause', '기타')
    area  = r.get('damage_area_ha') or 0.1

    fire_set.add((emd, year, month))
    ds = dong_stats.get(emd, {})
    temp, hum, wind, f_score, h_ratio = get_monthly_features(month)

    pos_rows.append({
        'emd_enc':          int(emd_enc.transform([emd])[0]),
        'month':            month,
        'temp':             temp,
        'humidity':         hum,
        'wind_speed':       wind,
        'hist_count':       ds.get('count', 1),
        'hist_area':        ds.get('total_area', area),
        'hist_score':       ds.get('score', 0.5),
        'month_fire_score': f_score,
        'month_high_ratio': h_ratio,
        'forest_grade':     forest_danger_grade,
        'fire_occurred':    1,
    })

years    = list(range(2011, 2026))
neg_rows = []
for emd in all_emds:
    ds = dong_stats.get(emd, {})
    for year in years:
        for month in range(1, 13):
            if (emd, year, month) in fire_set:
                continue
            temp, hum, wind, f_score, h_ratio = get_monthly_features(month)
            neg_rows.append({
                'emd_enc':          int(emd_enc.transform([emd])[0]),
                'month':            month,
                'temp':             temp,
                'humidity':         hum,
                'wind_speed':       wind,
                'hist_count':       ds.get('count', 0),
                'hist_area':        ds.get('total_area', 0.0),
                'hist_score':       ds.get('score', 0.1),
                'month_fire_score': f_score,
                'month_high_ratio': h_ratio,
                'forest_grade':     0,
                'fire_occurred':    0,
            })

# ── 경기도 추가 양성 샘플 ─────────────────────────────────────────────────
# 화성시 외 경기도 레코드를 추가 학습 데이터로 활용.
# emd_enc 는 Hwaseong 인코더에 없으므로 해당 시군구의 취약도 점수 비례
# 평균 인덱스(emd_enc=0)로 고정, hist_count·hist_score는 시군구 통계 사용.
gyeonggi_pos_rows = []
for r in gyeonggi_records:
    sgg   = r.get('sigungu', '')
    if sgg == '화성':          # 화성시는 이미 pos_rows에 포함
        continue
    month = r.get('month', 3)
    area  = r.get('damage_area_ha') or 0.1
    sgg_stat = gyeonggi_sigungu_stats.get(sgg, {})
    temp, hum, wind, f_score, h_ratio = get_monthly_features(month)
    gyeonggi_pos_rows.append({
        'emd_enc':          0,                           # 화성시 외 지역 플레이스홀더
        'month':            month,
        'temp':             temp,
        'humidity':         hum,
        'wind_speed':       wind,
        'hist_count':       sgg_stat.get('count', 1),
        'hist_area':        sgg_stat.get('total_area', area),
        'hist_score':       sgg_stat.get('score', 0.3),
        'month_fire_score': f_score,
        'month_high_ratio': h_ratio,
        'forest_grade':     forest_danger_grade,
        'fire_occurred':    1,
    })

df = pd.DataFrame(pos_rows + gyeonggi_pos_rows + neg_rows)
print(f"\n학습 데이터: 화성 양성 {len(pos_rows)}건 / 경기도 추가 {len(gyeonggi_pos_rows)}건 / 음성 {len(neg_rows)}건")

FEATURES = [
    'emd_enc', 'month', 'temp', 'humidity', 'wind_speed',
    'hist_count', 'hist_area', 'hist_score',
    'month_fire_score', 'month_high_ratio', 'forest_grade',
]
X = df[FEATURES].astype(float)
y = df['fire_occurred']

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y
)

imbalance_ratio = len(neg_rows) / max(len(pos_rows), 1)

# ===== RandomForest =====
print("\n[ RandomForest 학습 중... ]")
rf = RandomForestClassifier(
    n_estimators=300,
    max_depth=12,
    min_samples_leaf=4,
    class_weight='balanced',
    random_state=42,
    n_jobs=-1,
)
rf.fit(X_train, y_train)
rf_prob_test = rf.predict_proba(X_test)[:, 1]
rf_auc       = roc_auc_score(y_test, rf_prob_test)
print(f"  RandomForest ROC-AUC: {rf_auc:.4f}")

print("\n  특성 중요도:")
for feat, imp in sorted(zip(FEATURES, rf.feature_importances_), key=lambda x: -x[1]):
    bar = '█' * int(imp * 40)
    print(f"    {feat:<22}: {bar:<20} {imp:.4f}")

# ===== XGBoost (선택적) =====
if HAS_XGB:
    print("\n[ XGBoost 학습 중... ]")
    xgb = XGBClassifier(
        n_estimators=300,
        max_depth=6,
        learning_rate=0.04,
        subsample=0.8,
        colsample_bytree=0.75,
        min_child_weight=5,
        scale_pos_weight=imbalance_ratio,
        random_state=42,
        eval_metric='logloss',
        verbosity=0,
    )
    xgb.fit(X_train, y_train)
    xgb_prob_test  = xgb.predict_proba(X_test)[:, 1]
    xgb_auc        = roc_auc_score(y_test, xgb_prob_test)
    ensemble_test  = 0.40 * rf_prob_test + 0.60 * xgb_prob_test
    ens_auc        = roc_auc_score(y_test, ensemble_test)
    print(f"  XGBoost      ROC-AUC: {xgb_auc:.4f}")
    print(f"  앙상블(RF40+XGB60) AUC: {ens_auc:.4f}")
else:
    ensemble_test  = rf_prob_test
    ens_auc        = rf_auc

y_pred_ens = (ensemble_test >= 0.5).astype(int)
print("\n[ 앙상블 분류 리포트 ]")
print(classification_report(y_test, y_pred_ens, target_names=['화재없음', '화재발생']))

# ===== 읍면동 → 면 · 좌표 매핑 =====
emd_to_myeon: dict[str, str] = {}
for r in records:
    emd, myeon = r.get('emd', ''), r.get('myeon', '')
    if emd and myeon and emd not in emd_to_myeon:
        emd_to_myeon[emd] = myeon

MYEON_COORDS = {
    '향남': (37.057, 126.832), '팔탄': (37.103, 126.879),
    '남양': (37.207, 126.722), '서신': (37.180, 126.607),
    '우정': (37.070, 126.672), '마도': (37.133, 126.712),
    '양감': (37.020, 126.882), '비봉': (37.243, 126.798),
    '봉담': (37.215, 126.923), '정남': (37.150, 127.010),
    '동탄': (37.200, 127.080), '송산': (37.195, 126.689),
    '장안': (37.051, 126.776),
}

def get_approx_coords(emd: str) -> tuple[float, float]:
    myeon = emd_to_myeon.get(emd, '')
    for key, (lat, lng) in MYEON_COORDS.items():
        if key in myeon:
            rng = np.random.default_rng(abs(hash(emd)) % (2**32))
            return (round(lat + rng.uniform(-0.018, 0.018), 4),
                    round(lng + rng.uniform(-0.018, 0.018), 4))
    return 37.1996, 126.8312

def get_level(prob: float) -> str:
    if prob >= THRESH_HIGH:   return 'HIGH'
    if prob >= THRESH_MEDIUM: return 'MEDIUM'
    return 'LOW'

# ===== 현재 기상 기준 읍면동별 예측 =====
curr_temp, curr_hum, curr_wind, curr_f_score, curr_h_ratio = \
    get_monthly_features(current_month)

pred_rows = []
for emd in all_emds:
    ds = dong_stats.get(emd, {})
    pred_rows.append({
        'emd':              emd,
        'emd_enc':          int(emd_enc.transform([emd])[0]),
        'month':            current_month,
        'temp':             current_temp,
        'humidity':         current_humidity,
        'wind_speed':       current_wind_speed,
        'hist_count':       ds.get('count', 0),
        'hist_area':        ds.get('total_area', 0.0),
        'hist_score':       ds.get('score', 0.1),
        'month_fire_score': curr_f_score,
        'month_high_ratio': curr_h_ratio,
        'forest_grade':     forest_danger_grade,
    })

df_pred   = pd.DataFrame(pred_rows)
X_pred    = df_pred[FEATURES].astype(float)

rf_prob_pred = rf.predict_proba(X_pred)[:, 1]
if HAS_XGB:
    xgb_prob_pred = xgb.predict_proba(X_pred)[:, 1]
    ensemble_prob = 0.40 * rf_prob_pred + 0.60 * xgb_prob_pred
else:
    ensemble_prob = rf_prob_pred

results = []
for i, row in df_pred.iterrows():
    prob = float(ensemble_prob[i])
    emd  = row['emd']
    ds   = dong_stats.get(emd, {})
    lat, lng = get_approx_coords(emd)

    prob_am    = min(1.0, prob * TIME_MULT['AM'])
    prob_pm    = min(1.0, prob * TIME_MULT['PM'])
    prob_night = min(1.0, prob * TIME_MULT['NIGHT'])

    results.append({
        'dong':         emd,
        'myeon':        emd_to_myeon.get(emd, ''),
        'lat':          lat,
        'lng':          lng,
        'probability':  round(prob,     3),
        'level':        get_level(prob),
        'prob_am':      round(prob_am,  3),
        'prob_pm':      round(prob_pm,  3),
        'prob_night':   round(prob_night, 3),
        'level_am':     get_level(prob_am),
        'level_pm':     get_level(prob_pm),
        'level_night':  get_level(prob_night),
        'hist_count':   int(ds.get('count',      0)),
        'hist_score':   round(float(ds.get('score', 0.0)), 3),
        'top_cause':    ds.get('top_cause', '기타'),
        'forest_danger_grade': forest_danger_grade,
    })

results.sort(key=lambda x: x['probability'], reverse=True)

# ===== 출력 =====
model_label = ('RandomForest+XGBoost Ensemble (RF40+XGB60)'
               if HAS_XGB else 'RandomForestClassifier')

output = {
    'timestamp':     datetime.now().isoformat(),
    'model':         model_label,
    'auc_score':     round(ens_auc, 4),
    'features_used': FEATURES,
    'thresholds':    {'high': THRESH_HIGH, 'medium': THRESH_MEDIUM},
    'time_multipliers': TIME_MULT,
    'weather_condition': {
        'temperature':  current_temp,
        'humidity':     current_humidity,
        'wind_speed':   current_wind_speed,
        'month':        current_month,
    },
    'forest_danger_grade':  forest_danger_grade,
    'forest_overall_label': forest_overall_label,
    'summary': {
        'total_dongs':   len(results),
        'high_risk':     sum(1 for r in results if r['level']       == 'HIGH'),
        'medium_risk':   sum(1 for r in results if r['level']       == 'MEDIUM'),
        'low_risk':      sum(1 for r in results if r['level']       == 'LOW'),
        'high_risk_am':  sum(1 for r in results if r['level_am']    == 'HIGH'),
        'high_risk_pm':  sum(1 for r in results if r['level_pm']    == 'HIGH'),
        'high_risk_night': sum(1 for r in results if r['level_night'] == 'HIGH'),
    },
    'predictions': results,
}

with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

s = output['summary']
print(f"\n{'='*60}")
print(f"✅ 예측 완료 → {OUTPUT_PATH}")
print(f"   모델: {model_label}")
print(f"   AUC:  {ens_auc:.4f}")
print(f"   전체: HIGH {s['high_risk']} / MEDIUM {s['medium_risk']} / LOW {s['low_risk']}")
print(f"   시간대별 HIGH — 오전 {s['high_risk_am']} / 오후 {s['high_risk_pm']} / 야간 {s['high_risk_night']}")
print("\n위험도 상위 5개 읍면동:")
for r in results[:5]:
    print(f"  {r['dong']:<12} {r['probability']:.3f} ({r['level']:6}) "
          f"│ 오전 {r['prob_am']:.3f} 오후 {r['prob_pm']:.3f} 야간 {r['prob_night']:.3f}")
