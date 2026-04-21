# LEEDGRAPH

> 한국 LEED 인증 건물 460개를 v5 기준으로 표준화하고, SHAP으로 등급 결정 요인 분석.

**핵심 결과**: 에너지(EA) 카테고리가 등급을 가장 크게 결정 (CV Acc 0.8174)

---

## 폴더 구조

```
LEEDGRAPH/
├── data/                # raw PDF + processed parquet
├── notebooks/           # ⭐ 분석 실행
│   ├── 01_전처리.ipynb
│   └── 02_데이터분석.ipynb
├── src/                 # 라이브러리 코드
├── results/
│   ├── tables/          # 6개 CSV
│   └── figures/         # 10개 PNG
├── docs/                # 해설 문서 3개
│   ├── 01_전처리_과정.md
│   ├── 02_파이프라인_설계.md
│   └── 03_분석_방법론.md
└── README.md
```

---

## 빠른 시작

```bash
pip install -r requirements.txt

# 1. 전처리 (PDF → parquet)
jupyter notebook notebooks/01_전처리.ipynb

# 2. 분석 (XGBoost + SHAP)
jupyter notebook notebooks/02_데이터분석.ipynb
```

LLM 전문가 리뷰도 원하면 `.env` 에 `OPENAI_API_KEY` 설정 후 `01_전처리.ipynb` 실행.

---

## 주요 결과

| 지표 | 값 |
|------|-----|
| 데이터 | 460건 (한국 LEED 전수) |
| CV 정확도 | **0.8174 ± 0.0502** |
| CV Weighted F1 | **0.8157 ± 0.0504** |
| Top SHAP | **Energy (EA), 0.8840** |

Robustness: 어느 subset이든 EA가 Top feature.

자세한 내용은 `docs/` 참고.

---

## 라이선스

- 데이터: USGBC Public LEED Project Directory (public domain)
- 코드: MIT License
