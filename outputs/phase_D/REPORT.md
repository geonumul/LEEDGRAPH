# Phase D 리포트 (쉬운 버전)

## Phase D가 뭐였나

Phase C에서 만든 460건 parquet을 가지고 **XGBoost로 등급 예측 모델** 학습 + **SHAP으로 어느 카테고리가 중요한지** 분석.

---

## 모델 성능 (XGBoost, 5-Fold CV)

| 지표 | 값 |
|------|-----|
| 모델 | XGBoost (n_est=200, depth=6, lr=0.05) |
| 샘플 | 460 |
| Feature | 9개 |
| **CV 정확도** | **0.8174 ± 0.0502** |
| **CV Weighted F1** | **0.8157 ± 0.0504** |
| Train 정확도 | 1.0 (참고용 - 과적합) |
| Train F1 | 1.0 (참고용 - 과적합) |

**CV 값을 논문에 쓸 것** (Train은 과적합이라 신뢰 X).

각 Fold CV 값: [0.8043, 0.8913, 0.8587, 0.7717, 0.7609]

---

## 데이터 구성

| 등급 | 건수 |
|------|------|
| Gold | 235 |
| Silver | 118 |
| Platinum | 56 |
| Certified | 51 |

**Feature 9개**:
- v5 카테고리별 달성률 (ratio): EA, LT, MR, EQ, WE, SS, IP
- log_area (연면적 log)
- version_ord (버전 순서 인코딩)

---

## SHAP 결과: 등급 결정 Top 요인

| 순위 | 카테고리 | 평균 \|SHAP\| |
|------|---------|------------|
| 1 | **Energy & Atmosphere (EA)** | **0.8840** |
| 2 | Indoor Env. Quality (EQ) | 0.6533 |
| 3 | Water Efficiency (WE) | 0.5895 |
| 4 | Location & Transportation (LT) | 0.4377 |
| 5 | LEED Version | 0.2880 |
| 6 | Sustainable Sites (SS) | 0.2400 |
| 7 | Materials & Resources (MR) | 0.1796 |
| 8 | Floor Area (log sqm) | 0.1622 |
| 9 | Integrative Process (IP) | 0.0066 |

**핵심**: **에너지(EA)가 압도적**. 그 다음이 실내환경(EQ)과 물(WE).

---

## 출력 파일

### 모델 지표
- `outputs/phase_D/model_metrics.json`

### 시각화 (논문용)
- `outputs/phase_D/figs/shap_bar.png` — Top feature bar chart
- `outputs/phase_D/figs/shap_summary.png` — SHAP beeswarm
- `outputs/phase_D/figs/waterfall_certified.png` — Certified 등급 예제
- `outputs/phase_D/figs/waterfall_silver.png` — Silver 등급 예제
- `outputs/phase_D/figs/waterfall_gold.png` — Gold 등급 예제
- `outputs/phase_D/figs/waterfall_platinum.png` — Platinum 등급 예제
- `outputs/phase_D/figs/grade_comparison.png` — 등급별 카테고리 달성률 비교

### 원시 SHAP 값
- `outputs/phase_D/shap_values.parquet` — 1,700개 SHAP 값 (재분석용)

---

## 해석

**왜 EA가 1등?**
- v5 만점 기준으로 EA가 33점 (가장 큰 비중)
- 한국 LEED 건물들이 에너지 절약 전략에 점수 집중
- 설계 단계에서 EA 확보가 등급 업그레이드 가장 효과적

**IP가 거의 0?**
- Integrative Process는 v5 신규 카테고리
- 구버전 건물은 거의 0점 처리됨
- 의미가 없는 feature가 아니라, 대부분 0이라서 분산이 작음

---

## Robustness (Option A 분석)

`outputs/phase_D_option_a/` 참고. credit_hit > 0.7 건물만 써도, 신버전만 써도 **Top feature는 EA로 동일**.
