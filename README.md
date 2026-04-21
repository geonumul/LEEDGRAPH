# LEEDGRAPH

> 한국 LEED 인증 건물 460개를 v5 기준으로 표준화하고, SHAP으로 등급 결정 요인 분석.

**핵심 결과**: 에너지(EA) 카테고리가 등급을 가장 크게 결정 (CV Acc 0.8174)

---

## 폴더 구조

```
LEEDGRAPH/
├── README.md
├── requirements.txt
│
├── data/                # 원본 + 가공 데이터
│   ├── scorecards/        (460 PDF)
│   ├── rubrics/           (LEED 루브릭 + mapping_rules.yaml)
│   ├── project_directory.csv
│   ├── project_features.parquet        ← ML 학습 입력
│   ├── project_features_option_a.parquet  (LLM 리뷰 포함)
│   └── standardized_credits.parquet
│
├── notebooks/           # ⭐ 분석 실행
│   ├── 01_전처리.ipynb
│   ├── 02_데이터분석.ipynb
│   └── src/              (내부 파이프라인 라이브러리 — 노트북이 import)
│
├── results/
│   ├── tables/           (6 CSV)
│   └── figures/          (10 PNG)
│
└── docs/
    ├── 01_전처리_과정.md
    └── 02_파이프라인_및_분석.md
```

---

## 빠른 시작

```bash
pip install -r requirements.txt

# 1. 전처리 (PDF → parquet, API 키 불필요)
jupyter notebook notebooks/01_전처리.ipynb

# 2. 분석 (XGBoost + SHAP)
jupyter notebook notebooks/02_데이터분석.ipynb
```

LLM 전문가 리뷰를 원하면 `.env` 에 `OPENAI_API_KEY` 설정.

---

## 주요 결과

| 지표 | 값 |
|------|-----|
| 데이터 | 460건 (한국 LEED 전수) |
| CV 정확도 | **0.8152 ± 0.0471** |
| CV Weighted F1 | **0.8133 ± 0.0464** |
| Top SHAP | **Energy (EA), 0.8618** |

Robustness: 어느 subset이든 EA가 Top feature.

자세한 내용은 `docs/` 참고.

---

## 라이선스

- 데이터: USGBC Public LEED Project Directory (public domain)
- 코드: MIT License
