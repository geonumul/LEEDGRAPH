# LEEDGRAPH: LangGraph 기반 LEED 인증 버전 표준화 및 XAI 영향 요인 분석

> **한국 LEED 인증 건물 451개** | LangGraph + SHAP | v2.2/v3/v4 → v5 통합 표준화

---

## 연구 개요

국내 LEED(Leadership in Energy and Environmental Design) 인증 건물은 v2.2, v3, v4 등 **서로 다른 버전 체계**가 혼재하여 직접적인 비교·분석이 불가능합니다.

본 연구는 **LangGraph 기반 멀티-에이전트 워크플로우**로 이 문제를 해결하고, **SHAP(XAI)** 으로 등급 결정에 영향을 미치는 핵심 요인을 도출합니다.

### 연구 차별성

| 기존 연구 | 본 연구 |
|-----------|---------|
| 단일 버전 데이터 분석 | 다중 버전 통합 표준화 |
| 등급 **예측** 모델 | 등급 결정 **영향 요인 도출** (XAI) |
| 통계 기반 매핑 | LLM 기반 지능형 매핑 + 검증 |

---

## 파이프라인 구조

```
Raw Data (v2.2/v3/v4)
        │
        ▼
[LangGraph 워크플로우]
  ┌─────────────────┐
  │  Mapper Agent   │ ◄─── GPT-4.1 (버전별 카테고리 매핑)
  └────────┬────────┘
           ▼
  ┌─────────────────┐
  │ Validator Agent │ ◄─── GPT-4.1 (건축 환경적 타당성 검증)
  └────────┬────────┘
           │ 검증 실패 → Mapper로 재시도 (최대 3회)
           │ 검증 통과
           ▼
   v5 표준화 데이터
        │
        ▼
[ML 모델 학습]
  Random Forest / XGBoost / LightGBM
  (Stratified K-Fold 교차 검증)
        │
        ▼
[XAI - SHAP 분석]
  - Feature Importance (전체 영향력)
  - Summary Plot (등급별 분포)
  - Dependence Plot (카테고리 의존성)
  - Grade Comparison (등급 간 비교)
  - Force Plot (개별 건물 설명)
```

---

## 프로젝트 구조

```
LEEDGRAPH/
├── README.md
├── requirements.txt
├── pyproject.toml
├── .env.example
├── .gitignore
├── data/
│   ├── raw/                    # 원본 데이터 (gitignore)
│   │   ├── PublicLEEDProjectDirectory.xlsx
│   │   └── scorecards/         # 개별 Scorecard PDF
│   └── processed/              # 전처리 완료 데이터 (gitignore)
├── notebooks/
│   ├── 01-Data-Collection-EDA.ipynb
│   ├── 02-LangGraph-Version-Standardization.ipynb
│   ├── 03-ML-Training.ipynb
│   └── 04-XAI-SHAP-Analysis.ipynb
├── src/
│   ├── data/
│   │   ├── loader.py           # 데이터 로더 (XLSX / PDF)
│   │   └── preprocessor.py     # 버전별 점수 정규화 + 인코딩
│   ├── langgraph_workflow/
│   │   ├── state.py            # TypedDict State 정의
│   │   ├── nodes.py            # Mapper / Validator Agent
│   │   └── graph.py            # LangGraph 그래프 구성
│   └── analysis/
│       ├── ml_models.py        # ML 학습기 (RF / XGB / LGBM)
│       └── xai_shap.py         # SHAP 분석 + 시각화
└── outputs/
    ├── figures/                # SHAP 시각화 결과
    └── reports/                # 분석 리포트 (CSV)
```

---

## 데이터 준비

### 1. USGBC 프로젝트 디렉토리 (필수)

```
USGBC 공식 사이트에서 한국 프로젝트 데이터 다운로드:
https://www.usgbc.org/projects?Country=Republic+of+Korea

다운로드 파일: PublicLEEDProjectDirectory.xlsx
저장 위치: data/raw/PublicLEEDProjectDirectory.xlsx
```

### 2. Scorecard PDF (선택)

```
각 프로젝트 페이지 → Scorecard 탭 → PDF 다운로드
저장 위치: data/raw/scorecards/*.pdf
```

### 3. 샘플 데이터 (테스트용)

실제 데이터 없이 바로 실행 가능:
```python
from src.data.loader import LEEDDataLoader
df = LEEDDataLoader.create_sample_data()  # 451개 샘플 생성
```

---

## 설치 및 실행

### 환경 설정

```bash
# 1. 저장소 클론
git clone https://github.com/your-username/LEEDGRAPH.git
cd LEEDGRAPH

# 2. 가상환경 생성 (Python 3.11 권장)
python -m venv .venv
source .venv/bin/activate      # macOS/Linux
.venv\Scripts\activate         # Windows

# 3. 의존성 설치
pip install -r requirements.txt

# 4. 환경변수 설정
cp .env.example .env
# .env 파일에 OPENAI_API_KEY 입력
```

### 실행 순서

```bash
# Jupyter 실행
jupyter lab

# 노트북 순서대로 실행:
# 01 → 02 → 03 → 04
```

---

## LEED 버전별 배점 구조

| 카테고리 | v2.2 | v3 (2009) | v4 | v5 (기준) |
|---------|------|-----------|-----|-----------|
| LT (입지·교통) | - | - | 16 | 16 |
| SS (지속가능 부지) | 14 | 26 | 10 | 10 |
| WE (물 효율) | 5 | 10 | 11 | 12 |
| EA (에너지·대기) | 17 | 35 | 33 | 33 |
| MR (재료·자원) | 13 | 14 | 13 | 13 |
| IEQ (실내환경) | 15 | 15 | 16 | 16 |
| IN (혁신) | 5 | 6 | 6 | 6 |
| RP (지역 우선) | - | 4 | 4 | 4 |
| IP (통합 프로세스) | - | - | 2 | 2 |
| **합계** | **69** | **110** | **110** | **110** |

---

## 등급 기준 (v4/v5)

| 등급 | 점수 범위 |
|------|----------|
| Certified | 40 ~ 49점 |
| Silver | 50 ~ 59점 |
| Gold | 60 ~ 79점 |
| Platinum | 80점 이상 |

---

## 기술 스택

| 분야 | 라이브러리 |
|------|-----------|
| LLM 오케스트레이션 | LangGraph, LangChain, OpenAI GPT-4.1 |
| 데이터 처리 | pandas, numpy, pdfplumber, openpyxl |
| 머신러닝 | scikit-learn, XGBoost, LightGBM |
| XAI | SHAP |
| 시각화 | matplotlib, seaborn |

---

## 라이선스

MIT License

---

## 인용

```bibtex
@misc{leedgraph2025,
  title={LEEDGRAPH: LangGraph-based LEED Certification Version Standardization and XAI Factor Analysis},
  author={},
  year={2025},
  note={Korean LEED Buildings Analysis}
}
```
