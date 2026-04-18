# LEEDGRAPH

> 한국에서 인증받은 LEED 건물 460개를 분석하는 프로젝트.
> 서로 다른 LEED 버전 점수를 한 버전(v5)으로 맞추고, 어떤 카테고리가 등급을 결정하는지 SHAP으로 분석함.

---

## 1. 이 프로젝트는 뭘 하는가?

LEED는 건물 친환경 인증 제도야. 문제는 시간이 지나면서 인증 버전이 v2.0 → v2.2 → v2009 → v4 → v4.1 이렇게 계속 바뀌었다는 것. 버전마다 점수 배분 방식이 다르니까 직접 비교가 안 돼.

이 프로젝트는:
1. **버전 통일**: 모든 건물 점수를 최신 v5 기준으로 환산 (107개 규칙 사용)
2. **등급 결정 요인 분석**: XGBoost로 등급(Certified/Silver/Gold/Platinum)을 예측하는 모델 학습 → SHAP으로 어느 카테고리가 가장 중요한지 파악

**핵심 결과**: **Energy & Atmosphere (EA, 에너지)** 카테고리가 등급을 가장 크게 좌우함.

---

## 2. 기존 연구와 뭐가 다른가?

| 항목 | 기존 연구들 | 이 프로젝트 |
|------|------------|------------|
| 버전 | 보통 한 버전만 | v2.0~v4.1 전부 |
| 표준화 | 수동 또는 없음 | 규칙 기반 자동 환산 |
| 샘플 수 | 보통 100개 미만 | **460개 (한국 전수)** |
| 해석 방법 | 기본 feature importance | SHAP (크레딧 단위까지) |
| 지역 | 해외 벤치마크 | 한국 건물 stock |

---

## 3. 전체 파이프라인

```
460개 PDF → PDF 파싱 + CSV 매칭 → Rule Mapper (107개 규칙 적용)
                                          ↓
                                  v5 표준화 점수
                                          ↓
                                  XGBoost + SHAP → 등급 결정 요인
```

중간에 LangGraph로 "LLM 전문가 리뷰어"를 붙일 수 있어 (Option A). 점수는 안 바꾸고 검증 signal만 제공.

자세한 그림: `outputs/final/Figure1_pipeline.png`

---

## 4. 데이터

| 항목 | 내용 |
|------|------|
| PDF 스코어카드 | 460개 (한국 LEED 인증 건물 전부) |
| 프로젝트 목록 | PublicLEEDProjectDirectory.csv (456개) |
| LEED 버전 | v2.0 / v2.2 / v2009 / v4 / v4.1 |
| 표준화 후 | v5 기준, 9,747개 크레딧, 7개 카테고리 |
| 등급 분포 | Gold 235 (51%) / Silver 118 (26%) / Platinum 56 (12%) / Certified 51 (11%) |

---

## 5. 주요 결과

### 예측 모델 (XGBoost, 5-Fold CV)

| 지표 | 값 |
|------|-----|
| CV 정확도 | **0.8174 ± 0.0502** |
| CV Weighted F1 | **0.8157 ± 0.0504** |
| 사용한 feature | 9개 (카테고리 달성률 7개 + 면적 + 버전) |

### SHAP Top-5 등급 결정 요인

| 순위 | 카테고리 | 평균 \|SHAP\| |
|------|---------|------------|
| 1 | Energy & Atmosphere (EA) | 0.8840 |
| 2 | Indoor Env. Quality (EQ) | 0.6533 |
| 3 | Water Efficiency (WE) | 0.5895 |
| 4 | Location & Transportation (LT) | 0.4377 |
| 5 | LEED Version | 0.2880 |

→ **에너지(EA)가 압도적**. 실내환경(EQ)과 물(WE)이 그 다음.

---

## 6. 빠른 시작

```bash
pip install -r requirements_frozen.txt

# 1단계: 파이프라인 실행 (PDF → 표준화된 parquet)
python scripts/run_pipeline.py

# 2단계: XGBoost + SHAP 분석
python scripts/run_analysis.py
```

---

## 7. 폴더 구조

```
LEEDGRAPH/
├── data/
│   ├── raw/               # 원본 PDF, 루브릭, CSV
│   └── processed/         # 표준화된 parquet (ML 학습용)
├── src/
│   ├── data/              # 파서 (PDF, CSV, 루브릭)
│   ├── langgraph_workflow/  # LangGraph 파이프라인 (state / nodes / graph)
│   └── analysis/          # ML & SHAP 유틸
├── scripts/               # 실행 스크립트들
├── outputs/               # phase별 리포트 + final figures/tables
└── docs/                  # 문서
```

---

## 8. 한계와 향후 과제

- **10.2% 건물은 drift가 큼**: v5 native PDF 또는 버전 식별 애매. 표준화 불확실성 ↑.
- **12% unmatched 크레딧**: 매핑 규칙에 없는 크레딧 이름 (주로 v5 포맷).
- **train 정확도 100%는 overfitting 지표**: 논문에는 CV 값(0.8174) 사용할 것.
- **v2009 크레딧 상세 파싱 불가**: 카테고리 합계만 씀. 114건은 크레딧 레벨 SHAP 제외.

---

## 9. 라이선스 / 연락처

- 데이터: USGBC Public LEED Project Directory (public domain)
- 코드: MIT License
- Contact: geonumul (GitHub)
