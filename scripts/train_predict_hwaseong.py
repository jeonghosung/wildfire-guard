"""
화성시 읍면동별 산불 위험도 AI 예측 모델 v4
- 시간대별(AM/PM/NIGHT) 독립 모델 학습
  · AM:    봄/가을(3-5,10-11월) + 소각류(쓰레기소각·논밭태우기·농산부산물소각) 가중치
  · PM:    봄/여름 건조기 + 입산자류(입산자실화·담뱃불실화) 가중치
  · NIGHT: 반복 화재 이력(hist_count) 높은 지역 가중치
- 각 모델: RandomForest + XGBoost 앙상블, 5-fold CV
- prob_am / prob_pm / prob_night 각각 독립 모델 예측
- probability (전체): PM×0.50 + AM×0.30 + NIGHT×0.20
- 과적합 방지: forest_grade 학습 제외, max_depth=6, min_samples_leaf=8
"""

import json
import os
import numpy as np
import pandas as pd
from datetime import datetime
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import roc_auc_score, classification_report
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.preprocessing import LabelEncoder

try:
    from xgboost import XGBClassifier
    HAS_XGB = True
except ImportError:
    print("⚠  XGBoost 미설치 — RandomForest 단독 사용")
    HAS_XGB = False

# ===== 경로 설정 =====
BASE_DIR              = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIRE_HISTORY_PATH     = os.path.join(BASE_DIR, 'public', 'data', 'fire_history.json')
GYEONGGI_HISTORY_PATH = os.path.join(BASE_DIR, 'public', 'data', 'fire_history_gyeonggi.json')
WEATHER_PATH          = os.path.join(BASE_DIR, 'public', 'data', 'weather.json')
HIST_WEATHER_PATH     = os.path.join(BASE_DIR, 'public', 'data', 'historical_weather.json')
FOREST_RISK_PATH      = os.path.join(BASE_DIR, 'public', 'data', 'forest_risk.json')
OUTPUT_PATH           = os.path.join(BASE_DIR, 'public', 'data', 'predicted_risk.json')

# ===== 상수 =====
THRESH_HIGH   = 0.30
THRESH_MEDIUM = 0.12
GYEONGGI_MIN_RECORDS = 10

# 시간대별 원인 분류
AM_CAUSES    = {'쓰레기소각', '논밭태우기', '농산부산물소각'}
PM_CAUSES    = {'입산자실화', '담뱃불실화'}
NIGHT_CAUSES = {'담뱃불실화', '건축물화재비화', '담배꽁초'}

# 시간대별 계절
AM_MONTHS    = {3, 4, 5, 10, 11}   # 봄/가을 (이른 소각 활동)
PM_DRY       = {3, 4, 5}           # 봄 건조기 (오후 입산객)
PM_HOT       = {6, 7, 8}           # 여름 (오후 더위)

# 전체 probability 가중 합산 비율
PERIOD_WEIGHT = {'AM': 0.30, 'PM': 0.50, 'NIGHT': 0.20}

# ===== 데이터 로드 =====
print("=" * 62)
print("화성시 산불 위험도 AI 예측 모델 v4 (시간대별 독립 모델)")
print("=" * 62)

with open(FIRE_HISTORY_PATH, 'r', encoding='utf-8') as f:
    fire_data = json.load(f)

with open(WEATHER_PATH, 'r', encoding='utf-8') as f:
    weather_data = json.load(f)

# --- 과거기상 (선택) ---
hist_monthly: dict = {}
if os.path.exists(HIST_WEATHER_PATH):
    with open(HIST_WEATHER_PATH, 'r', encoding='utf-8') as f:
        hw = json.load(f)
    for m_str, stats in hw.get('monthly_stats', {}).items():
        hist_monthly[int(m_str)] = stats
    print(f"  과거기상 로드: {len(hist_monthly)}개월 · {hw.get('total_records',0)}일치")
else:
    print("  historical_weather.json 없음 — 계절 추정값 사용")

# --- 경기도 전체 산불 이력 (선택, 10건 이상 시 추가 학습) ---
gyeonggi_records: list = []
gyeonggi_sigungu_stats: dict = {}
if os.path.exists(GYEONGGI_HISTORY_PATH):
    with open(GYEONGGI_HISTORY_PATH, 'r', encoding='utf-8') as f:
        gg = json.load(f)
    non_hw = [r for r in gg.get('records', []) if r.get('sigungu', '') != '화성']
    if len(non_hw) >= GYEONGGI_MIN_RECORDS:
        gyeonggi_records       = non_hw
        gyeonggi_sigungu_stats = gg.get('sigungu_stats', {})
        print(f"  경기도 산불 이력: {len(gyeonggi_records)}건 / {len(gyeonggi_sigungu_stats)}개 시군구")
    else:
        print(f"  경기도 데이터 {len(non_hw)}건 (임계값 {GYEONGGI_MIN_RECORDS}건 미만) — 추가 학습 스킵")
else:
    print("  fire_history_gyeonggi.json 없음 — 화성시 단독 학습")

# --- 산불위험예보 (출력 메타용만) ---
forest_danger_grade  = 0
forest_overall_label = '없음'
if os.path.exists(FOREST_RISK_PATH):
    with open(FOREST_RISK_PATH, 'r', encoding='utf-8') as f:
        fr = json.load(f)
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
    print(f"  산불위험예보: 최대 {forest_danger_grade}등급 · {forest_overall_label}")
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

# ===== 월별 기상 특성 =====
def _seasonal_fallback(month: int) -> tuple:
    temp = -2 + month * 3.5 if month <= 7 else 28 - (month - 7) * 3.0
    hum  = max(25, 75 - abs(month - 7) * 5)
    wind = 3.0 + (1.5 if month in [3, 4, 11, 12] else 0)
    return round(temp, 1), round(hum, 1), round(wind, 1)

def get_monthly_features(month: int) -> tuple:
    if month in hist_monthly:
        s = hist_monthly[month]
        tf, hf, wf = _seasonal_fallback(month)
        temp    = s.get('temp_max_avg_c')   or tf
        hum     = s.get('humidity_avg_pct') or hf
        wind    = s.get('wind_max_avg_ms')  or wf
        f_score = s.get('fire_score_avg')   or 0.3
        h_days  = s.get('high_risk_days')   or 0
        t_days  = s.get('total_days')       or 1
        h_ratio = h_days / max(t_days, 1)
    else:
        temp, hum, wind = _seasonal_fallback(month)
        f_score = 0.55 if month in [3, 4, 5, 10, 11] else 0.2
        h_ratio = 0.25 if month in [3, 4, 5, 10, 11] else 0.05
    return temp, hum, wind, round(f_score, 3), round(h_ratio, 3)

# ===== 학습 데이터 구성 =====
# cause / raw_hist_count 는 sample_weight 계산용 메타 컬럼 (FEATURES 외)
fire_set = set()
pos_rows = []

for r in records:
    emd = r.get('emd', '')
    if emd not in all_emds:
        continue
    year  = r.get('year',  2020)
    month = r.get('month', 3)
    cause = r.get('cause', '기타') or '기타'
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
        'fire_occurred':    1,
        # 메타 (가중치 계산용)
        'cause':            cause,
        'raw_hist_count':   int(ds.get('count', 1)),
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
                'fire_occurred':    0,
                'cause':            '없음',
                'raw_hist_count':   int(ds.get('count', 0)),
            })

# 경기도 추가 양성 샘플 (10건 이상일 때만)
gyeonggi_pos_rows = []
emd_mid = len(all_emds) // 2
for r in gyeonggi_records:
    sgg      = r.get('sigungu', '')
    month    = r.get('month', 3)
    cause    = r.get('cause', '기타') or '기타'
    area     = r.get('damage_area_ha') or 0.1
    sgg_stat = gyeonggi_sigungu_stats.get(sgg, {})
    temp, hum, wind, f_score, h_ratio = get_monthly_features(month)
    gyeonggi_pos_rows.append({
        'emd_enc':          emd_mid,
        'month':            month,
        'temp':             temp,
        'humidity':         hum,
        'wind_speed':       wind,
        'hist_count':       sgg_stat.get('count', 1),
        'hist_area':        sgg_stat.get('total_area', area),
        'hist_score':       sgg_stat.get('score', 0.3),
        'month_fire_score': f_score,
        'month_high_ratio': h_ratio,
        'fire_occurred':    1,
        'cause':            cause,
        'raw_hist_count':   int(sgg_stat.get('count', 1)),
    })

df = pd.DataFrame(pos_rows + gyeonggi_pos_rows + neg_rows)
print(f"\n학습 데이터: 화성 양성 {len(pos_rows)}건 / 경기도 추가 {len(gyeonggi_pos_rows)}건 / 음성 {len(neg_rows)}건")

# forest_grade 는 학습 피처에서 제외 (양성=현재등급/음성=0 이분법이 AUC=1.0 유발)
FEATURES = [
    'emd_enc', 'month', 'temp', 'humidity', 'wind_speed',
    'hist_count', 'hist_area', 'hist_score',
    'month_fire_score', 'month_high_ratio',
]

X = df[FEATURES].astype(float)
y = df['fire_occurred']

total_pos       = len(pos_rows) + len(gyeonggi_pos_rows)
imbalance_ratio = len(neg_rows) / max(total_pos, 1)


# ===== 시간대별 샘플 가중치 =====

def compute_weights(df_local: pd.DataFrame, period: str) -> np.ndarray:
    """
    시간대별로 관련성이 높은 샘플의 가중치를 높여 모델이 해당 패턴에 집중하게 함.
    가중치 범위: 1.0 ~ 6.0 (과도한 편향 방지)
    """
    w = np.ones(len(df_local))

    months   = df_local['month'].values
    causes   = df_local['cause'].values
    hcounts  = df_local['raw_hist_count'].values
    is_fire  = df_local['fire_occurred'].values

    for i in range(len(df_local)):
        m, c, hc, fired = months[i], causes[i], hcounts[i], is_fire[i]

        if period == 'AM':
            # 봄/가을 + 소각류 원인 우선
            if m in AM_MONTHS:   w[i] *= 2.0
            if c in AM_CAUSES:   w[i] *= 2.0
            # 음성 샘플도 봄/가을은 약간 상향
            if fired == 0 and m in AM_MONTHS:
                w[i] *= 1.3

        elif period == 'PM':
            # 봄 건조기 + 여름 고온 + 입산자류 원인 우선
            if m in PM_DRY:     w[i] *= 2.0
            if m in PM_HOT:     w[i] *= 1.5
            if c in PM_CAUSES:  w[i] *= 2.5
            if fired == 0 and m in PM_DRY | PM_HOT:
                w[i] *= 1.3

        elif period == 'NIGHT':
            # 반복 화재 이력(hist_count) 높은 지역 + 야간 취약 원인
            count_bonus = min(3.0, 1.0 + hc * 0.4)
            w[i] *= count_bonus
            if c in NIGHT_CAUSES: w[i] *= 2.0

        # 최대 6배 캡
        w[i] = min(w[i], 6.0)

    return w


# ===== 단일 시간대 모델 학습 =====

def train_period(period: str, seed: int = 42) -> dict:
    """
    시간대별 RF+XGB 앙상블 학습.
    반환: {rf, xgb(or None), cv_scores, auc}
    """
    sample_w = compute_weights(df, period)

    X_tr, X_te, y_tr, y_te, w_tr, w_te = train_test_split(
        X, y, sample_w,
        test_size=0.2, random_state=seed, stratify=y,
    )

    # RandomForest
    rf_m = RandomForestClassifier(
        n_estimators=300,
        max_depth=6,
        max_features='sqrt',
        min_samples_leaf=8,
        min_samples_split=16,
        class_weight='balanced',
        random_state=seed,
        n_jobs=-1,
    )
    rf_m.fit(X_tr, y_tr, sample_weight=w_tr)
    rf_prob = rf_m.predict_proba(X_te)[:, 1]
    rf_auc  = roc_auc_score(y_te, rf_prob)

    # 5-fold CV (가중치 없이 일반화 성능 측정)
    cv_sc = cross_val_score(rf_m, X, y, cv=5, scoring='roc_auc', n_jobs=-1)

    xgb_m = None
    if HAS_XGB:
        xgb_m = XGBClassifier(
            n_estimators=300,
            max_depth=4,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.7,
            min_child_weight=8,
            scale_pos_weight=imbalance_ratio,
            random_state=seed,
            eval_metric='logloss',
            verbosity=0,
        )
        xgb_m.fit(X_tr, y_tr, sample_weight=w_tr)
        xgb_prob   = xgb_m.predict_proba(X_te)[:, 1]
        ens_prob   = 0.40 * rf_prob + 0.60 * xgb_prob
        ens_auc    = roc_auc_score(y_te, ens_prob)
        xgb_auc    = roc_auc_score(y_te, xgb_prob)
    else:
        ens_auc  = rf_auc
        xgb_auc  = None

    return {
        'rf':        rf_m,
        'xgb':       xgb_m,
        'rf_auc':    round(rf_auc, 4),
        'xgb_auc':   round(xgb_auc, 4) if xgb_auc is not None else None,
        'ens_auc':   round(ens_auc, 4),
        'cv_mean':   round(float(cv_sc.mean()), 4),
        'cv_std':    round(float(cv_sc.std()),  4),
        'cv_scores': [round(float(s), 4) for s in cv_sc],
    }


def predict_period(model_info: dict, X_p: pd.DataFrame) -> np.ndarray:
    rf_p = model_info['rf'].predict_proba(X_p)[:, 1]
    if model_info['xgb'] is not None:
        xgb_p = model_info['xgb'].predict_proba(X_p)[:, 1]
        return 0.40 * rf_p + 0.60 * xgb_p
    return rf_p


# ===== 시간대별 3개 모델 학습 =====
PERIODS = ('AM', 'PM', 'NIGHT')
PERIOD_LABELS = {'AM': '오전(06-12시)', 'PM': '오후(12-18시)', 'NIGHT': '야간(18-06시)'}

period_models: dict = {}
for period in PERIODS:
    print(f"\n[ {PERIOD_LABELS[period]} 모델 학습 중... ]")
    info = train_period(period)
    period_models[period] = info

    print(f"  RF  Hold-out AUC: {info['rf_auc']}")
    if info['xgb_auc'] is not None:
        print(f"  XGB Hold-out AUC: {info['xgb_auc']}")
        print(f"  앙상블 AUC:        {info['ens_auc']}")
    print(f"  5-fold CV AUC:    {info['cv_mean']:.4f} ± {info['cv_std']:.4f}  "
          f"[{', '.join(str(s) for s in info['cv_scores'])}]")

    # 특성 중요도
    rf_m = info['rf']
    print(f"  특성 중요도:")
    for feat, imp in sorted(zip(FEATURES, rf_m.feature_importances_), key=lambda x: -x[1])[:5]:
        bar = '█' * int(imp * 30)
        print(f"    {feat:<22}: {bar:<15} {imp:.4f}")


# ===== 읍면동 → 면·좌표 매핑 =====
emd_to_myeon: dict = {}
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

def get_approx_coords(emd: str) -> tuple:
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


# ===== 읍면동별 예측 (시간대별 독립 모델) =====
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
    })

df_pred = pd.DataFrame(pred_rows)
X_pred  = df_pred[FEATURES].astype(float)

# 시간대별 독립 예측
probs_by_period = {p: predict_period(period_models[p], X_pred) for p in PERIODS}

results = []
for i, row in df_pred.iterrows():
    emd = row['emd']
    ds  = dong_stats.get(emd, {})
    lat, lng = get_approx_coords(emd)

    p_am    = float(probs_by_period['AM'][i])
    p_pm    = float(probs_by_period['PM'][i])
    p_night = float(probs_by_period['NIGHT'][i])

    # 전체 probability: 시간대 가중 합산 (PM 최우선)
    prob = (PERIOD_WEIGHT['AM']    * p_am
            + PERIOD_WEIGHT['PM']  * p_pm
            + PERIOD_WEIGHT['NIGHT'] * p_night)

    results.append({
        'dong':        emd,
        'myeon':       emd_to_myeon.get(emd, ''),
        'lat':         lat,
        'lng':         lng,
        'probability': round(prob,    3),
        'level':       get_level(prob),
        'prob_am':     round(p_am,    3),
        'prob_pm':     round(p_pm,    3),
        'prob_night':  round(p_night, 3),
        'level_am':    get_level(p_am),
        'level_pm':    get_level(p_pm),
        'level_night': get_level(p_night),
        'hist_count':  int(ds.get('count',  0)),
        'hist_score':  round(float(ds.get('score', 0.0)), 3),
        'top_cause':   ds.get('top_cause', '기타'),
        'forest_danger_grade': forest_danger_grade,
    })

results.sort(key=lambda x: x['probability'], reverse=True)


# ===== 출력 =====
model_label = ('RF+XGB 앙상블 (시간대별 독립)' if HAS_XGB
               else 'RandomForest (시간대별 독립)')

output = {
    'timestamp':      datetime.now().isoformat(),
    'model':          model_label,
    'model_version':  'v4',
    'features_used':  FEATURES,
    'thresholds':     {'high': THRESH_HIGH, 'medium': THRESH_MEDIUM},
    'period_weights': PERIOD_WEIGHT,
    'period_models': {
        p: {
            'rf_auc':    period_models[p]['rf_auc'],
            'xgb_auc':   period_models[p]['xgb_auc'],
            'ens_auc':   period_models[p]['ens_auc'],
            'cv_mean':   period_models[p]['cv_mean'],
            'cv_std':    period_models[p]['cv_std'],
        }
        for p in PERIODS
    },
    'weather_condition': {
        'temperature':  current_temp,
        'humidity':     current_humidity,
        'wind_speed':   current_wind_speed,
        'month':        current_month,
    },
    'forest_danger_grade':  forest_danger_grade,
    'forest_overall_label': forest_overall_label,
    'summary': {
        'total_dongs':     len(results),
        'high_risk':       sum(1 for r in results if r['level']       == 'HIGH'),
        'medium_risk':     sum(1 for r in results if r['level']       == 'MEDIUM'),
        'low_risk':        sum(1 for r in results if r['level']       == 'LOW'),
        'high_risk_am':    sum(1 for r in results if r['level_am']    == 'HIGH'),
        'high_risk_pm':    sum(1 for r in results if r['level_pm']    == 'HIGH'),
        'high_risk_night': sum(1 for r in results if r['level_night'] == 'HIGH'),
    },
    'predictions': results,
}

with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

s = output['summary']
print(f"\n{'='*62}")
print(f"✅ 예측 완료 → {OUTPUT_PATH}")
print(f"   모델: {model_label}")
print(f"   시간대별 AUC (앙상블 hold-out):")
for p in PERIODS:
    mi = period_models[p]
    print(f"     {PERIOD_LABELS[p]:<18}: {mi['ens_auc']:.4f}  "
          f"CV {mi['cv_mean']:.4f}±{mi['cv_std']:.4f}")
print(f"   전체: HIGH {s['high_risk']} / MEDIUM {s['medium_risk']} / LOW {s['low_risk']}")
print(f"   시간대 HIGH — 오전 {s['high_risk_am']} / 오후 {s['high_risk_pm']} / 야간 {s['high_risk_night']}")
print("\n위험도 상위 5개 읍면동:")
for r in results[:5]:
    print(f"  {r['dong']:<12} {r['probability']:.3f} ({r['level']:6}) "
          f"│ 오전 {r['prob_am']:.3f} 오후 {r['prob_pm']:.3f} 야간 {r['prob_night']:.3f}")
