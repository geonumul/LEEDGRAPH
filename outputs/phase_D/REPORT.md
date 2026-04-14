# Phase D – 예측 모델 + SHAP 리포트

## 완료 기준 체크

- [x] 모델 성능 리포트 (CV Accuracy=0.8144)
- [x] SHAP summary plot 생성 → `outputs/phase_D/figs/shap_summary.png`
- [x] 등급별 비교 시각화 → `outputs/phase_D/figs/grade_comparison.png`
- [x] 논문용 figure 4개 (`shap_bar`, `shap_summary`, `waterfall_*`, `grade_comparison`)

---

## 1. 모델 성능

| 항목 | 값 |
|------|-----|
| 모델 | XGBoost (n_est=200, depth=6, lr=0.05) |
| 샘플 수 | 431 |
| Feature 수 | 9 |
| 5-Fold CV Accuracy | **0.8144 ± 0.0317** |
| 5-Fold CV Weighted F1 | **0.8139 ± 0.0315** |
| Train Accuracy (참고, 과적합) | 1.0000 |
| Train Weighted F1 (참고, 과적합) | 1.0000 |

CV Accuracy Folds: [0.7931, 0.8605, 0.8256, 0.7674, 0.8256]
CV F1 Folds: [0.7943, 0.862, 0.8256, 0.7682, 0.8197]

---

## 2. 데이터 구성

| 등급 | 건수 |
|------|------|
| Gold | 210 |
| Silver | 117 |
| Platinum | 53 |
| Certified | 51 |

**Feature 목록** (v5 카테고리별 달성률 + 면적 + 버전):
- ratio_EA, ratio_LT, ratio_MR, ratio_EQ, ratio_WE, ratio_SS, ratio_IP
- log_area (연면적 log), version_ord (버전 순서 인코딩)

---

## 3. SHAP 상위 10개 영향 요인

| 순위 | Feature | Mean |SHAP| |
|------|---------|------------|
| 3 | Energy & Atmosphere (EA) | 0.8272 |
| 5 | Indoor Env. Quality (EQ) | 0.7096 |
| 2 | Water Efficiency (WE) | 0.6139 |
| 1 | Location & Transportation (LT) | 0.4203 |
| 9 | LEED Version | 0.2498 |
| 7 | Sustainable Sites (SS) | 0.2474 |
| 4 | Materials & Resources (MR) | 0.2254 |
| 8 | Floor Area (log sqm) | 0.1594 |
| 6 | Integrative Process (IP) | 0.0000 |

---

## 4. 생성 파일

| 파일 | 설명 |
|------|------|
| `figs/shap_bar.png` | Global feature importance (bar) |
| `figs/shap_summary.png` | Beeswarm summary (Gold class) |
| `figs/waterfall_certified.png` | Waterfall – Certified representative |
| `figs/waterfall_silver.png` | Waterfall – Silver representative |
| `figs/waterfall_gold.png` | Waterfall – Gold representative |
| `figs/waterfall_platinum.png` | Waterfall – Platinum representative |
| `figs/grade_comparison.png` | Grade-wise SHAP boxplot (top feature) |
| `model_metrics.json` | 모델 성능 지표 |
| `shap_values.parquet` | 전체 SHAP 값 |

---

## 5. 해석

- **Energy & Atmosphere (EA)** 이 등급 결정에 가장 큰 영향 (SHAP=0.8272)
- **Indoor Env. Quality (EQ)** 이 두 번째 영향 요인 (SHAP=0.7096)
- waterfall plot: 각 등급 대표 건물에서 어떤 카테고리가 등급 결정에 기여했는지 확인 가능
- grade_comparison: EA(에너지) SHAP 값이 Platinum에서 특히 높음 → 에너지 성능이 고등급 결정 핵심 요인

---

## 6. 한계

- CV Accuracy는 4-class 분류 기준 (Certified/Silver/Gold/Platinum)
- drift > 20% 47건 포함 (v5 신규 포맷 건물) → 이 건들의 매핑 불확실도 존재
- 버전(version_ord) feature는 순서형 인코딩 사용 (nominal 특성 있음)