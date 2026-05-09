"""
화성시 읍면동별 산불 위험도 AI 예측 모델
- 학습 데이터: public/data/fire_history.json (산림청), public/data/weather.json (기상청)
- 모델: RandomForestClassifier
- 출력: public/data/predicted_risk.json
"""

import json
import os
import numpy as np
import pandas as pd
from datetime import datetime
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIRE_HISTORY_PATH = os.path.join(BASE_DIR, 'public', 'data', 'fire_history.json')
WEATHER_PATH = os.path.join(BASE_DIR, 'public', 'data', 'weather.json')
OUTPUT_PATH = os.path.join(BASE_DIR, 'public', 'data', 'predicted_risk.json')

# ===== 데이터 로드 =====
with open(FIRE_HISTORY_PATH, 'r', encoding='utf-8') as f:
    fire_data = json.load(f)

with open(WEATHER_PATH, 'r', encoding='utf-8') as f:
    weather_data = json.load(f)

records = fire_data.get('records', [])
dong_stats = fire_data.get('dong_stats', {})

parsed = weather_data.get('parsed', {})
current_temp = parsed.get('temperature', 15.0)
current_humidity = parsed.get('humidity', 50.0)
current_wind_speed = parsed.get('wind_speed', 3.0)
current_month = datetime.now().month

print(f"산불 기록 수: {len(records)}건")
print(f"읍면동 수: {len(dong_stats)}개")
print(f"현재 기상: 기온 {current_temp}°C, 습도 {current_humidity}%, 풍속 {current_wind_speed}m/s, 월 {current_month}")

# ===== 원인·읍면동 인코더 =====
CAUSE_CATEGORIES = ['쓰레기소각', '입산자실화', '농산부산물소각', '담뱃불실화', '건축물화재비화', '기타']
cause_enc = LabelEncoder().fit(CAUSE_CATEGORIES)

all_emds = sorted(dong_stats.keys())
emd_enc = LabelEncoder().fit(all_emds)

def encode_cause(c):
    return cause_enc.transform([c if c in CAUSE_CATEGORIES else '기타'])[0]

def seasonal_weather(month):
    """학습용: 월별 대표 기상값 추정"""
    temp = -2 + month * 3.5 if month <= 7 else 28 - (month - 7) * 3.0
    humidity = max(25, 75 - abs(month - 7) * 5)
    wind = 3.0 + (1.5 if month in [3, 4, 11, 12] else 0)
    return round(temp, 1), round(humidity, 1), round(wind, 1)

# ===== 학습 데이터 구성 =====
fire_set = set()  # (emd, year, month) 화재 발생 조합
pos_rows = []

for r in records:
    emd = r.get('emd', '')
    if emd not in all_emds:
        continue
    year = r.get('year', 2020)
    month = r.get('month', 3)
    cause = r.get('cause', '기타')
    area = r.get('damage_area_ha', 0.1)

    fire_set.add((emd, year, month))
    ds = dong_stats.get(emd, {})
    temp, hum, wind = seasonal_weather(month)

    pos_rows.append({
        'emd_enc': emd_enc.transform([emd])[0],
        'month': month,
        'temp': temp,
        'humidity': hum,
        'wind_speed': wind,
        'hist_count': ds.get('count', 1),
        'hist_area': ds.get('total_area', area),
        'hist_score': ds.get('score', 0.5),
        'cause_enc': encode_cause(cause),
        'fire_occurred': 1,
    })

# 음성 샘플: 화재 없는 (emd, year, month) 조합
years = list(range(2011, 2026))
neg_rows = []
for emd in all_emds:
    ds = dong_stats.get(emd, {})
    for year in years:
        for month in range(1, 13):
            if (emd, year, month) in fire_set:
                continue
            temp, hum, wind = seasonal_weather(month)
            neg_rows.append({
                'emd_enc': emd_enc.transform([emd])[0],
                'month': month,
                'temp': temp,
                'humidity': hum,
                'wind_speed': wind,
                'hist_count': ds.get('count', 0),
                'hist_area': ds.get('total_area', 0.0),
                'hist_score': ds.get('score', 0.1),
                'cause_enc': encode_cause('기타'),
                'fire_occurred': 0,
            })

df = pd.DataFrame(pos_rows + neg_rows)
print(f"\n학습 데이터: 양성 {len(pos_rows)}건, 음성 {len(neg_rows)}건")

FEATURES = ['emd_enc', 'month', 'temp', 'humidity', 'wind_speed', 'hist_count', 'hist_area', 'hist_score']
X = df[FEATURES]
y = df['fire_occurred']

# ===== 모델 학습 =====
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)

model = RandomForestClassifier(
    n_estimators=200,
    max_depth=10,
    min_samples_leaf=5,
    class_weight='balanced',
    random_state=42,
    n_jobs=-1,
)
model.fit(X_train, y_train)

print("\n특성 중요도:")
for feat, imp in sorted(zip(FEATURES, model.feature_importances_), key=lambda x: -x[1]):
    print(f"  {feat}: {imp:.4f}")

y_prob = model.predict_proba(X_test)[:, 1]
y_pred = (y_prob >= 0.5).astype(int)
print(f"\nROC-AUC: {roc_auc_score(y_test, y_prob):.4f}")
print(classification_report(y_test, y_pred, target_names=['화재없음', '화재발생']))

# ===== 읍면동 → 면 매핑 및 좌표 추정 =====
emd_to_myeon = {}
for r in records:
    emd = r.get('emd', '')
    myeon = r.get('myeon', '')
    if emd and myeon and emd not in emd_to_myeon:
        emd_to_myeon[emd] = myeon

MYEON_COORDS = {
    '향남': (37.057, 126.832),
    '팔탄': (37.103, 126.879),
    '남양': (37.207, 126.722),
    '서신': (37.180, 126.607),
    '우정': (37.070, 126.672),
    '마도': (37.133, 126.712),
    '양감': (37.020, 126.882),
    '비봉': (37.243, 126.798),
    '봉담': (37.215, 126.923),
    '정남': (37.150, 127.010),
    '동탄': (37.200, 127.080),
    '송산': (37.195, 126.689),
    '장안': (37.051, 126.776),
}

def get_approx_coords(emd):
    myeon = emd_to_myeon.get(emd, '')
    for key, (lat, lng) in MYEON_COORDS.items():
        if key in myeon:
            rng = np.random.default_rng(abs(hash(emd)) % (2**32))
            return round(lat + rng.uniform(-0.018, 0.018), 4), round(lng + rng.uniform(-0.018, 0.018), 4)
    return 37.1996, 126.8312

# ===== 현재 기상 기준 읍면동별 예측 =====
pred_rows = []
for emd in all_emds:
    ds = dong_stats.get(emd, {})
    pred_rows.append({
        'emd': emd,
        'emd_enc': emd_enc.transform([emd])[0],
        'month': current_month,
        'temp': current_temp,
        'humidity': current_humidity,
        'wind_speed': current_wind_speed,
        'hist_count': ds.get('count', 0),
        'hist_area': ds.get('total_area', 0.0),
        'hist_score': ds.get('score', 0.1),
    })

df_pred = pd.DataFrame(pred_rows)
probabilities = model.predict_proba(df_pred[FEATURES])[:, 1]

results = []
for i, row in df_pred.iterrows():
    prob = float(probabilities[i])
    emd = row['emd']
    ds = dong_stats.get(emd, {})
    myeon = emd_to_myeon.get(emd, '')
    lat, lng = get_approx_coords(emd)
    results.append({
        'dong': emd,
        'myeon': myeon,
        'lat': lat,
        'lng': lng,
        'probability': round(prob, 3),
        'level': 'HIGH' if prob >= 0.6 else 'MEDIUM' if prob >= 0.3 else 'LOW',
        'hist_count': int(ds.get('count', 0)),
        'hist_score': round(float(ds.get('score', 0.0)), 3),
        'top_cause': ds.get('top_cause', '기타'),
    })

results.sort(key=lambda x: x['probability'], reverse=True)

output = {
    'timestamp': datetime.now().isoformat(),
    'model': 'RandomForestClassifier',
    'features_used': FEATURES,
    'weather_condition': {
        'temperature': current_temp,
        'humidity': current_humidity,
        'wind_speed': current_wind_speed,
        'month': current_month,
    },
    'summary': {
        'total_dongs': len(results),
        'high_risk': sum(1 for r in results if r['level'] == 'HIGH'),
        'medium_risk': sum(1 for r in results if r['level'] == 'MEDIUM'),
        'low_risk': sum(1 for r in results if r['level'] == 'LOW'),
    },
    'predictions': results,
}

with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f"\n예측 완료 → {OUTPUT_PATH}")
print(f"HIGH: {output['summary']['high_risk']}개, MEDIUM: {output['summary']['medium_risk']}개, LOW: {output['summary']['low_risk']}개")

top5 = results[:5]
print("\n위험도 상위 5개 읍면동:")
for r in top5:
    print(f"  {r['dong']}: {r['probability']:.3f} ({r['level']}) - 누적화재 {r['hist_count']}건")
