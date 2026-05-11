"""
화성시 읍면동별 산불 위험도 AI 예측 모델 v5
- 시간대별(AM/PM/NIGHT) Optuna 하이퍼파라미터 자동 튜닝
  · RF:  n_estimators, max_depth, min_samples_leaf, min_samples_split
  · XGB: n_estimators, max_depth, learning_rate, min_child_weight
  · 앙상블 가중치: rf_weight (0.1~0.9)
  · 탐색 횟수: 30 trial (시간대별 독립)
- 최적 파라미터 public/data/best_params.json 캐시 (24h 재사용)
- 시간대별 샘플 가중치로 특화 학습 (v4 유지)
- 과적합 방지: forest_grade 학습 제외, 5-fold CV
"""

import json
import os
import warnings
import numpy as np
import pandas as pd
from datetime import datetime
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import roc_auc_score, roc_curve
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.preprocessing import LabelEncoder

warnings.filterwarnings('ignore', category=UserWarning)

try:
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    HAS_OPTUNA = True
except ImportError:
    print("⚠  Optuna 미설치 — 기본 파라미터 사용 (pip install optuna)")
    HAS_OPTUNA = False

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
PARAMS_CACHE_PATH     = os.path.join(BASE_DIR, 'public', 'data', 'best_params.json')

# ===== 상수 =====
THRESH_HIGH          = 0.30
THRESH_MEDIUM        = 0.12
GYEONGGI_MIN_RECORDS = 10
OPTUNA_TRIALS        = 30
CACHE_MAX_HOURS      = 24

# 시간대별 원인 분류
AM_CAUSES    = {'쓰레기소각', '논밭태우기', '농산부산물소각'}
PM_CAUSES    = {'입산자실화', '담뱃불실화'}
NIGHT_CAUSES = {'담뱃불실화', '건축물화재비화', '담배꽁초'}

AM_MONTHS = {3, 4, 5, 10, 11}
PM_DRY    = {3, 4, 5}
PM_HOT    = {6, 7, 8}

PERIOD_WEIGHT  = {'AM': 0.30, 'PM': 0.50, 'NIGHT': 0.20}
PERIODS        = ('AM', 'PM', 'NIGHT')
PERIOD_LABELS  = {'AM': '오전(06-12시)', 'PM': '오후(12-18시)', 'NIGHT': '야간(18-06시)'}

# ===== 기본 파라미터 (Optuna 미설치 또는 캐시 없을 때 폴백) =====
DEFAULT_PARAMS = {
    'rf_n_estimators':     300,
    'rf_max_depth':          6,
    'rf_min_samples_leaf':   8,
    'rf_min_samples_split': 16,
    'xgb_n_estimators':    300,
    'xgb_max_depth':         4,
    'xgb_learning_rate':  0.05,
    'xgb_min_child_weight':  8,
    'rf_weight':           0.40,
    'best_auc':            0.0,
    'tuned':               False,
}

# ===== 데이터 로드 =====
print("=" * 62)
print("화성시 산불 위험도 AI 예측 모델 v5 (Optuna 하이퍼파라미터 튜닝)")
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

# --- 경기도 전체 산불 이력 (선택) ---
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
        'emd_enc': int(emd_enc.transform([emd])[0]),
        'month': month, 'temp': temp, 'humidity': hum, 'wind_speed': wind,
        'hist_count': ds.get('count', 1), 'hist_area': ds.get('total_area', area),
        'hist_score': ds.get('score', 0.5),
        'month_fire_score': f_score, 'month_high_ratio': h_ratio,
        'fire_occurred': 1, 'cause': cause, 'raw_hist_count': int(ds.get('count', 1)),
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
                'emd_enc': int(emd_enc.transform([emd])[0]),
                'month': month, 'temp': temp, 'humidity': hum, 'wind_speed': wind,
                'hist_count': ds.get('count', 0), 'hist_area': ds.get('total_area', 0.0),
                'hist_score': ds.get('score', 0.1),
                'month_fire_score': f_score, 'month_high_ratio': h_ratio,
                'fire_occurred': 0, 'cause': '없음', 'raw_hist_count': int(ds.get('count', 0)),
            })

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
        'emd_enc': emd_mid,
        'month': month, 'temp': temp, 'humidity': hum, 'wind_speed': wind,
        'hist_count': sgg_stat.get('count', 1), 'hist_area': sgg_stat.get('total_area', area),
        'hist_score': sgg_stat.get('score', 0.3),
        'month_fire_score': f_score, 'month_high_ratio': h_ratio,
        'fire_occurred': 1, 'cause': cause, 'raw_hist_count': int(sgg_stat.get('count', 1)),
    })

df = pd.DataFrame(pos_rows + gyeonggi_pos_rows + neg_rows)
print(f"\n학습 데이터: 화성 양성 {len(pos_rows)}건 / 경기도 추가 {len(gyeonggi_pos_rows)}건 / 음성 {len(neg_rows)}건")

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
    w        = np.ones(len(df_local))
    months   = df_local['month'].values
    causes   = df_local['cause'].values
    hcounts  = df_local['raw_hist_count'].values
    is_fire  = df_local['fire_occurred'].values

    for i in range(len(df_local)):
        m, c, hc, fired = months[i], causes[i], hcounts[i], is_fire[i]
        if period == 'AM':
            if m in AM_MONTHS:  w[i] *= 2.0
            if c in AM_CAUSES:  w[i] *= 2.0
            if fired == 0 and m in AM_MONTHS: w[i] *= 1.3
        elif period == 'PM':
            if m in PM_DRY:    w[i] *= 2.0
            if m in PM_HOT:    w[i] *= 1.5
            if c in PM_CAUSES: w[i] *= 2.5
            if fired == 0 and m in PM_DRY | PM_HOT: w[i] *= 1.3
        elif period == 'NIGHT':
            w[i] *= min(3.0, 1.0 + hc * 0.4)
            if c in NIGHT_CAUSES: w[i] *= 2.0
        w[i] = min(w[i], 6.0)
    return w


# ===== 파라미터 캐시 =====

def _cache_fresh() -> bool:
    if not os.path.exists(PARAMS_CACHE_PATH):
        return False
    try:
        with open(PARAMS_CACHE_PATH, 'r', encoding='utf-8') as f:
            cached = json.load(f)
        if cached.get('version') != 'v5':
            return False
        ts    = datetime.fromisoformat(cached['timestamp'])
        age_h = (datetime.now() - ts).total_seconds() / 3600
        return age_h < CACHE_MAX_HOURS and set(cached.get('periods', {}).keys()) >= set(PERIODS)
    except Exception:
        return False


def load_cached_params() -> dict:
    with open(PARAMS_CACHE_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)['periods']


def save_params_cache(periods_params: dict):
    cache = {
        'timestamp': datetime.now().isoformat(),
        'version':   'v5',
        'periods':   periods_params,
    }
    os.makedirs(os.path.dirname(PARAMS_CACHE_PATH), exist_ok=True)
    with open(PARAMS_CACHE_PATH, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
    print(f"  파라미터 캐시 저장 → {PARAMS_CACHE_PATH}")


# ===== Optuna 탐색 =====

def _make_objective(period: str, sample_w: np.ndarray):
    """Optuna objective: hold-out ROC-AUC 최대화."""
    X_tr, X_te, y_tr, y_te, w_tr, _ = train_test_split(
        X, y, sample_w, test_size=0.2, random_state=42, stratify=y,
    )

    def objective(trial: 'optuna.Trial') -> float:
        rf_n     = trial.suggest_int('rf_n_estimators',     100, 500, step=50)
        rf_depth = trial.suggest_int('rf_max_depth',          4,  10)
        rf_leaf  = trial.suggest_int('rf_min_samples_leaf',   4,  20)
        rf_split = trial.suggest_int('rf_min_samples_split',  8,  32)
        rf_w     = trial.suggest_float('rf_weight',         0.1, 0.9)

        rf_m = RandomForestClassifier(
            n_estimators=rf_n, max_depth=rf_depth,
            max_features='sqrt', min_samples_leaf=rf_leaf,
            min_samples_split=rf_split, class_weight='balanced',
            random_state=42, n_jobs=-1,
        )
        rf_m.fit(X_tr, y_tr, sample_weight=w_tr)
        rf_prob = rf_m.predict_proba(X_te)[:, 1]

        if HAS_XGB:
            xgb_n     = trial.suggest_int('xgb_n_estimators',   100, 500, step=50)
            xgb_depth = trial.suggest_int('xgb_max_depth',         3,   8)
            xgb_lr    = trial.suggest_float('xgb_learning_rate', 0.01, 0.3, log=True)
            xgb_child = trial.suggest_int('xgb_min_child_weight',  4,  20)

            xgb_m = XGBClassifier(
                n_estimators=xgb_n, max_depth=xgb_depth,
                learning_rate=xgb_lr, min_child_weight=xgb_child,
                subsample=0.8, colsample_bytree=0.7,
                scale_pos_weight=imbalance_ratio,
                random_state=42, eval_metric='logloss', verbosity=0,
            )
            xgb_m.fit(X_tr, y_tr, sample_weight=w_tr)
            xgb_prob = xgb_m.predict_proba(X_te)[:, 1]
            ens_prob  = rf_w * rf_prob + (1 - rf_w) * xgb_prob
        else:
            ens_prob = rf_prob

        return roc_auc_score(y_te, ens_prob)

    return objective


def optuna_tune(period: str) -> dict:
    """시간대별 Optuna 탐색 → 최적 파라미터 dict 반환."""
    sample_w = compute_weights(df, period)
    study    = optuna.create_study(direction='maximize',
                                   sampler=optuna.samplers.TPESampler(seed=42))
    study.optimize(_make_objective(period, sample_w),
                   n_trials=OPTUNA_TRIALS, show_progress_bar=False)

    bp = study.best_params
    params = {
        'rf_n_estimators':     bp['rf_n_estimators'],
        'rf_max_depth':        bp['rf_max_depth'],
        'rf_min_samples_leaf': bp['rf_min_samples_leaf'],
        'rf_min_samples_split':bp['rf_min_samples_split'],
        'xgb_n_estimators':    bp.get('xgb_n_estimators',    DEFAULT_PARAMS['xgb_n_estimators']),
        'xgb_max_depth':       bp.get('xgb_max_depth',       DEFAULT_PARAMS['xgb_max_depth']),
        'xgb_learning_rate':   bp.get('xgb_learning_rate',   DEFAULT_PARAMS['xgb_learning_rate']),
        'xgb_min_child_weight':bp.get('xgb_min_child_weight',DEFAULT_PARAMS['xgb_min_child_weight']),
        'rf_weight':           bp['rf_weight'],
        'best_auc':            round(study.best_value, 4),
        'tuned':               True,
    }
    return params


# ===== 파라미터 결정 (캐시 → Optuna → 기본값) =====
print(f"\n[ 하이퍼파라미터 결정 ]")
best_params_by_period: dict = {}

if _cache_fresh():
    best_params_by_period = load_cached_params()
    ts_str = json.load(open(PARAMS_CACHE_PATH))['timestamp'][:16]
    print(f"  캐시 재사용: {PARAMS_CACHE_PATH} (생성: {ts_str})")
    for p in PERIODS:
        bp = best_params_by_period[p]
        print(f"  {PERIOD_LABELS[p]}: 캐시 AUC={bp.get('best_auc', '?')}, "
              f"rf_w={bp.get('rf_weight', '?'):.2f}")

elif HAS_OPTUNA:
    print(f"  Optuna 탐색 시작: {OPTUNA_TRIALS} trials × 3 시간대")
    for period in PERIODS:
        print(f"  [{PERIOD_LABELS[period]}] 탐색 중...", end=' ', flush=True)
        params = optuna_tune(period)
        best_params_by_period[period] = params
        print(f"AUC={params['best_auc']:.4f}  "
              f"RF n={params['rf_n_estimators']} d={params['rf_max_depth']} "
              f"leaf={params['rf_min_samples_leaf']}  "
              f"rf_w={params['rf_weight']:.2f}")
        if HAS_XGB:
            print(f"           XGB n={params['xgb_n_estimators']} d={params['xgb_max_depth']} "
                  f"lr={params['xgb_learning_rate']:.4f} child={params['xgb_min_child_weight']}")
    save_params_cache(best_params_by_period)

else:
    print("  Optuna 미설치 — 기본 파라미터 사용")
    for period in PERIODS:
        best_params_by_period[period] = dict(DEFAULT_PARAMS)


# ===== 최적 파라미터로 시간대별 모델 학습 =====

def train_period(period: str, params: dict, seed: int = 42) -> dict:
    """최적 파라미터로 RF+XGB 앙상블 학습 및 5-fold CV 평가."""
    sample_w = compute_weights(df, period)
    X_tr, X_te, y_tr, y_te, w_tr, _ = train_test_split(
        X, y, sample_w, test_size=0.2, random_state=seed, stratify=y,
    )

    rf_m = RandomForestClassifier(
        n_estimators=    params['rf_n_estimators'],
        max_depth=       params['rf_max_depth'],
        max_features=    'sqrt',
        min_samples_leaf=params['rf_min_samples_leaf'],
        min_samples_split=params['rf_min_samples_split'],
        class_weight=    'balanced',
        random_state=    seed,
        n_jobs=          -1,
    )
    rf_m.fit(X_tr, y_tr, sample_weight=w_tr)
    rf_prob = rf_m.predict_proba(X_te)[:, 1]
    rf_auc  = roc_auc_score(y_te, rf_prob)
    rf_w    = params.get('rf_weight', 0.40)

    cv_sc = cross_val_score(rf_m, X, y, cv=5, scoring='roc_auc', n_jobs=-1)

    xgb_m = None
    if HAS_XGB:
        xgb_m = XGBClassifier(
            n_estimators=    params['xgb_n_estimators'],
            max_depth=       params['xgb_max_depth'],
            learning_rate=   params['xgb_learning_rate'],
            min_child_weight=params['xgb_min_child_weight'],
            subsample=       0.8,
            colsample_bytree=0.7,
            scale_pos_weight=imbalance_ratio,
            random_state=    seed,
            eval_metric=     'logloss',
            verbosity=       0,
        )
        xgb_m.fit(X_tr, y_tr, sample_weight=w_tr)
        xgb_prob = xgb_m.predict_proba(X_te)[:, 1]
        ens_prob = rf_w * rf_prob + (1 - rf_w) * xgb_prob
        xgb_auc  = roc_auc_score(y_te, xgb_prob)
        ens_auc  = roc_auc_score(y_te, ens_prob)
    else:
        xgb_auc  = None
        ens_auc  = rf_auc
        rf_w     = 1.0
        ens_prob = rf_prob

    return {
        'rf':          rf_m,
        'xgb':         xgb_m,
        'rf_weight':   rf_w,
        'rf_auc':      round(rf_auc, 4),
        'xgb_auc':     round(xgb_auc, 4) if xgb_auc is not None else None,
        'ens_auc':     round(ens_auc, 4),
        'cv_mean':     round(float(cv_sc.mean()), 4),
        'cv_std':      round(float(cv_sc.std()),  4),
        'cv_scores':   [round(float(s), 4) for s in cv_sc],
        'params':      params,
        'y_te':        np.array(y_te),
        'ens_prob_te': ens_prob,
    }


def predict_period(model_info: dict, X_p: pd.DataFrame) -> np.ndarray:
    rf_p  = model_info['rf'].predict_proba(X_p)[:, 1]
    rf_w  = model_info['rf_weight']
    if model_info['xgb'] is not None:
        xgb_p = model_info['xgb'].predict_proba(X_p)[:, 1]
        return rf_w * rf_p + (1 - rf_w) * xgb_p
    return rf_p


# ===== Youden Index 임계값 도출 =====

def compute_youden_threshold(y_te_arr: np.ndarray,
                              prob_te_arr: np.ndarray,
                              period: str) -> tuple:
    """
    ROC 커브 Youden Index (TPR-FPR 최대화) 기반 최적 임계값 도출.
    실패 시 폴백 순서:
      1) 양성 비율 × 5 기반  (절대값 사용 금지 — 항상 데이터 기반)
      2) 예측 확률 분포 75퍼센타일 기반
    반환: (threshold_high, threshold_medium, reason_str)
    """
    try:
        pos = int(np.sum(y_te_arr))
        neg = int(len(y_te_arr) - pos)
        if pos < 2 or neg < 2:
            raise ValueError(f"클래스 부족 (pos={pos}, neg={neg})")
        fpr, tpr, thresholds = roc_curve(y_te_arr, prob_te_arr)
        youden   = tpr - fpr
        best_idx = int(np.argmax(youden))
        j_val    = float(youden[best_idx])
        if j_val < 0.05:
            raise ValueError(f"Youden J={j_val:.3f} — 판별력 부족")
        t_high = round(float(np.clip(thresholds[best_idx], 0.05, 0.90)), 4)
        t_med  = round(t_high * 0.60, 4)
        reason = (f"Youden Index (TPR-FPR 최대화) 기반 자동 도출 "
                  f"(J={j_val:.3f}, {period})")
        return t_high, t_med, reason
    except Exception as e:
        print(f"    ⚠  {period} Youden 실패 ({e}) → 폴백")

    # 폴백 1: 양성 비율 × 5 기반
    pos_ratio = float(np.mean(y_te_arr))
    if pos_ratio > 0.005:
        t_high = round(float(np.clip(pos_ratio * 5.0, 0.08, 0.75)), 4)
        t_med  = round(t_high * 0.60, 4)
        reason = f"폴백1: 양성 비율({pos_ratio:.4f})×5 기반 임계값 ({period})"
        return t_high, t_med, reason

    # 폴백 2: 예측 확률 분포 75퍼센타일 기반
    q75   = round(float(np.clip(np.percentile(prob_te_arr, 75), 0.08, 0.75)), 4)
    t_med = round(q75 * 0.60, 4)
    reason = f"폴백2: 예측 확률 75퍼센타일({q75:.4f}) 기반 임계값 ({period})"
    return q75, t_med, reason


print(f"\n[ 시간대별 최종 모델 학습 ]")
period_models: dict = {}
for period in PERIODS:
    params = best_params_by_period[period]
    info   = train_period(period, params)
    period_models[period] = info

    print(f"\n  {PERIOD_LABELS[period]}")
    print(f"    RF  AUC: {info['rf_auc']}  |  rf_weight={info['rf_weight']:.2f}")
    if info['xgb_auc'] is not None:
        print(f"    XGB AUC: {info['xgb_auc']}  |  앙상블 AUC: {info['ens_auc']}")
    print(f"    5-fold CV: {info['cv_mean']:.4f} ± {info['cv_std']:.4f}  "
          f"[{', '.join(str(s) for s in info['cv_scores'])}]")
    print(f"    특성 중요도 TOP-3: " + " / ".join(
        f"{f}({imp:.3f})"
        for f, imp in sorted(zip(FEATURES, info['rf'].feature_importances_),
                              key=lambda x: -x[1])[:3]))


# ===== 시간대별 Youden Index 임계값 도출 =====
print(f"\n[ Youden Index 임계값 도출 ]")
period_thresholds: dict = {}
threshold_reasons: dict = {}

for period in PERIODS:
    mi = period_models[period]
    t_high, t_med, reason = compute_youden_threshold(
        mi['y_te'], mi['ens_prob_te'], period
    )
    period_thresholds[period] = {'high': t_high, 'medium': t_med}
    threshold_reasons[period] = reason
    print(f"  {PERIOD_LABELS[period]}: HIGH≥{t_high:.4f}  MEDIUM≥{t_med:.4f}")
    print(f"    근거: {reason}")

# 전체(가중 평균) 임계값
thresh_overall_high = round(
    sum(PERIOD_WEIGHT[p] * period_thresholds[p]['high']   for p in PERIODS), 4)
thresh_overall_med  = round(thresh_overall_high * 0.60, 4)
print(f"  전체(가중): HIGH≥{thresh_overall_high:.4f}  MEDIUM≥{thresh_overall_med:.4f}")


# ===== 읍면동 → 면·좌표 매핑 =====
emd_to_myeon: dict = {}
for r in records:
    emd, myeon = r.get('emd', ''), r.get('myeon', '')
    if emd and myeon and emd not in emd_to_myeon:
        emd_to_myeon[emd] = myeon

# ===== GeoJSON 기반 화성시 읍면동 중심 좌표 =====
_GEOJSON_URL = (
    'https://raw.githubusercontent.com/vuski/admdongkor/master'
    '/ver20231001/HangJeongDong_ver20231001.geojson'
)
_DEFAULT_LAT, _DEFAULT_LNG = 37.1996, 126.8312

def _multipolygon_centroid(geometry: dict) -> tuple:
    """Polygon 또는 MultiPolygon의 면적 가중 중심 좌표 (lat, lng) 반환."""
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
    """GeoJSON에서 화성시(sgg=41590) 읍면동 중심 좌표 딕셔너리 반환."""
    import urllib.request
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
        print(f"  GeoJSON 중심 좌표 로드: {len(result)}개 읍면동")
        return result
    except Exception as e:
        print(f"  ⚠ GeoJSON 로드 실패 ({e}) — 기존 좌표 사용")
        return {}

_HWASEONG_CENTROID = _load_hwaseong_centroids()

# GeoJSON 로드 실패 또는 미포함 면 대비 폴백 (성산 등)
_MYEON_COORDS_FALLBACK = {
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
    if myeon and myeon in _HWASEONG_CENTROID:
        return _HWASEONG_CENTROID[myeon]
    for key, coords in _MYEON_COORDS_FALLBACK.items():
        if key in myeon:
            return coords
    return _DEFAULT_LAT, _DEFAULT_LNG

def get_level(prob: float, t_high: float, t_med: float) -> str:
    if prob >= t_high: return 'HIGH'
    if prob >= t_med:  return 'MEDIUM'
    return 'LOW'


# ===== 읍면동별 예측 =====
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

probs_by_period = {p: predict_period(period_models[p], X_pred) for p in PERIODS}

results = []
for i, row in df_pred.iterrows():
    emd = row['emd']
    ds  = dong_stats.get(emd, {})
    lat, lng = get_approx_coords(emd)

    p_am    = float(probs_by_period['AM'][i])
    p_pm    = float(probs_by_period['PM'][i])
    p_night = float(probs_by_period['NIGHT'][i])
    prob    = (PERIOD_WEIGHT['AM'] * p_am
               + PERIOD_WEIGHT['PM'] * p_pm
               + PERIOD_WEIGHT['NIGHT'] * p_night)

    results.append({
        'dong':        emd,
        'myeon':       emd_to_myeon.get(emd, ''),
        'lat':         lat,
        'lng':         lng,
        'probability': round(prob,    3),
        'level':       get_level(prob,    thresh_overall_high, thresh_overall_med),
        'prob_am':     round(p_am,    3),
        'prob_pm':     round(p_pm,    3),
        'prob_night':  round(p_night, 3),
        'level_am':    get_level(p_am,    period_thresholds['AM']['high'],    period_thresholds['AM']['medium']),
        'level_pm':    get_level(p_pm,    period_thresholds['PM']['high'],    period_thresholds['PM']['medium']),
        'level_night': get_level(p_night, period_thresholds['NIGHT']['high'], period_thresholds['NIGHT']['medium']),
        'hist_count':  int(ds.get('count',  0)),
        'hist_score':  round(float(ds.get('score', 0.0)), 3),
        'top_cause':   ds.get('top_cause', '기타'),
        'forest_danger_grade': forest_danger_grade,
    })

results.sort(key=lambda x: x['probability'], reverse=True)


# ===== 출력 =====
model_label = ('RF+XGB 앙상블 Optuna튜닝 (시간대별 독립)' if HAS_XGB
               else 'RandomForest Optuna튜닝 (시간대별 독립)')

output = {
    'timestamp':      datetime.now().isoformat(),
    'model':          model_label,
    'model_version':  'v5',
    'optuna_trials':  OPTUNA_TRIALS if HAS_OPTUNA else 0,
    'params_cached':  _cache_fresh(),
    'features_used':  FEATURES,
    'thresholds': {
        'overall_high':   thresh_overall_high,
        'overall_medium': thresh_overall_med,
        'AM':    period_thresholds['AM'],
        'PM':    period_thresholds['PM'],
        'NIGHT': period_thresholds['NIGHT'],
    },
    'threshold_high_am':      period_thresholds['AM']['high'],
    'threshold_high_pm':      period_thresholds['PM']['high'],
    'threshold_high_night':   period_thresholds['NIGHT']['high'],
    'threshold_medium_am':    period_thresholds['AM']['medium'],
    'threshold_medium_pm':    period_thresholds['PM']['medium'],
    'threshold_medium_night': period_thresholds['NIGHT']['medium'],
    'threshold_reason':       threshold_reasons,
    'period_weights': PERIOD_WEIGHT,
    'period_models': {
        p: {
            'rf_auc':   period_models[p]['rf_auc'],
            'xgb_auc':  period_models[p]['xgb_auc'],
            'ens_auc':  period_models[p]['ens_auc'],
            'cv_mean':  period_models[p]['cv_mean'],
            'cv_std':   period_models[p]['cv_std'],
            'rf_weight':period_models[p]['rf_weight'],
            'best_params': {
                k: v for k, v in best_params_by_period[p].items()
                if k not in ('best_auc', 'tuned')
            },
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
print(f"   시간대별 AUC:")
for p in PERIODS:
    mi = period_models[p]
    bp = best_params_by_period[p]
    print(f"     {PERIOD_LABELS[p]:<18}: ens={mi['ens_auc']:.4f}  "
          f"CV {mi['cv_mean']:.4f}±{mi['cv_std']:.4f}  "
          f"(Optuna AUC={bp.get('best_auc','?')})")
print(f"   전체: HIGH {s['high_risk']} / MEDIUM {s['medium_risk']} / LOW {s['low_risk']}")
print(f"   시간대 HIGH — 오전 {s['high_risk_am']} / 오후 {s['high_risk_pm']} / 야간 {s['high_risk_night']}")
print("\n위험도 상위 5개 읍면동:")
for r in results[:5]:
    print(f"  {r['dong']:<12} {r['probability']:.3f} ({r['level']:6}) "
          f"│ 오전 {r['prob_am']:.3f} 오후 {r['prob_pm']:.3f} 야간 {r['prob_night']:.3f}")
