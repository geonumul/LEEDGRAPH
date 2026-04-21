# LEEDGRAPH

> 한국 LEED 인증 건물 460개를 v5 기준으로 표준화하고, SHAP으로 등급 결정 요인 분석.

---

## 핵심 요약

- **데이터**: 한국 LEED 인증 건물 **460개 전수** (v2.0~v4.1)
- **방법**: LangGraph로 Rule 표준화 + LLM 전문가 리뷰 (Option A) → XGBoost + SHAP
- **주요 결과**: **에너지(EA) 카테고리가 등급을 가장 크게 결정** (CV Acc 0.8174)

---

## 폴더 구조

```
LEEDGRAPH/
├── README.md
├── LICENSE
├── requirements.txt
├── pyproject.toml
│
├── data/
│   ├── raw/              # 원본 PDF, CSV, 루브릭
│   └── processed/        # 정제된 parquet
│
├── notebooks/            # ⭐ 분석 실행
│   ├── 01_데이터_준비.ipynb
│   ├── 02_LLM_검증.ipynb
│   └── 03_SHAP_분석.ipynb
│
├── src/                  # 모듈 코드 (notebook에서 import)
│   ├── langgraph_workflow/
│   ├── data/
│   └── analysis/
│
├── results/              # ⭐ 표 + 그림
│   ├── tables/           # CSV 4~6개
│   └── figures/          # PNG 10개
│
├── docs/                 # 해설 문서 4개
│   ├── 01_데이터_준비_과정.md
│   ├── 02_파이프라인_설계.md
│   ├── 03_분석_방법론.md
│   └── 04_심사_질문_대응.md
│
├── scripts/              # 재현용 스크립트
│   └── run_pipeline.py
│
└── archive/              # 옛 버전 기록 (phase별 reports, legacy scripts)
```

---

## 빠른 시작

```bash
# 1. 설치
pip install -r requirements.txt

# 2. 데이터 준비 (PDF → parquet, API 키 불필요)
jupyter notebook notebooks/01_데이터_준비.ipynb

# 3. (선택) LLM 전문가 리뷰 (OPENAI_API_KEY 필요, $9 비용)
jupyter notebook notebooks/02_LLM_검증.ipynb

# 4. 분석 실행 (XGBoost + SHAP)
jupyter notebook notebooks/03_SHAP_분석.ipynb
```

---

## 결과 요약

### 모델 성능

| 지표 | 값 |
|------|-----|
| CV 정확도 | **0.8174 ± 0.0502** |
| CV Weighted F1 | **0.8157 ± 0.0504** |
| Feature | 9개 (카테고리 달성률 7 + 면적 + 버전) |

### SHAP Top 5

| 순위 | 카테고리 | 평균 \|SHAP\| |
|------|---------|------------|
| 1 | **Energy & Atmosphere (EA)** | **0.8840** |
| 2 | Indoor Env. Quality (EQ) | 0.6533 |
| 3 | Water Efficiency (WE) | 0.5895 |
| 4 | Location & Transportation (LT) | 0.4377 |
| 5 | LEED Version | 0.2880 |

### Robustness

어느 subset이든 **EA가 Top SHAP feature** (전체 / credit_hit>0.7 / 신버전 / 구버전 / LLM 리뷰 표본).

---

## 데이터셋 구성

| 항목 | 값 |
|------|-----|
| 총 건물 | **460** |
| 버전 | v4(276) / v2009(114) / v4.1(48) / v2.2(18) / v2.0(4) |
| 등급 | Gold 51% / Silver 26% / Platinum 12% / Certified 11% |
| 크레딧 레코드 | 9,747개 |

---

## 한계점

1. **LLM 리뷰 16.3%** (75/460) — 비용 관리로 조기 종료, 표본 리뷰로 포지셔닝
2. **Train 1.0은 과적합** — CV 값(0.8174) 사용, holdout test set 미도입
3. **v2009 크레딧 상세 파싱 불가** — 114건은 카테고리 합계만
4. **Feature 9개만** — 건물 용도/위치/연도 등 반영 안 됨

---

## 라이선스 / 참고

- 데이터: USGBC Public LEED Project Directory (public domain)
- 코드: MIT License
- Contact: [geonumul](https://github.com/geonumul)
