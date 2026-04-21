# Phase C 리포트 (쉬운 버전)

## Phase C가 뭐였나

460개 PDF 스코어카드를 전부 처리해서 v5 기준으로 표준화하는 단계. **V1 파이프라인** (Rule 위주, LLM은 10%만 사용).

---

## 결과 요약

| 항목 | 값 |
|------|-----|
| 총 PDF | 460 |
| 성공 처리 | **460 (100%)** |
| Rule 경로 | 413 (89.8%) |
| LLM 경로 (drift>20% 건물) | 47 (10.2%) |

> 초기 실행에서 429 Rate Limit 때문에 LLM 18건만 성공했는데, run_llm_retry.py 돌려서 47건 전부 완료.

---

## 버전별 결과

| 버전 | 건수 | 성공률 |
|------|------|-------|
| v4 | 276 | 100% |
| v2009 | 114 | 100% |
| v4.1 | 48 | 100% |
| v2.2 | 18 | 100% |
| v2.0 | 4 | 100% |
| 합계 | **460** | **100%** |

---

## 출력 파일

- `data/processed/project_features.parquet` — 460행, 28컬럼 (ML 입력용)
- `data/processed/standardized_credits.parquet` — 9,747행 (크레딧 단위)

### 크레딧 매핑 방식 분포
- rule: 7,697 (79%)
- unmatched (매핑 규칙 없음): 1,127 (12%)
- category_proportional (v2009 상세 없어 카테고리 합계 사용): 923 (9%)

---

## LLM 경로 47건 특징

- 모두 drift > 20% (원본 달성률 vs v5 달성률 차이 20% 초과)
- 평균 drift: 22.6%
- 최대 drift: 48.3% (Gucci Yeoju Premium Outlet, v2.2)

Rate Limit 대응:
- tenacity exponential backoff (최대 5회, 2→4→8→16→32초)
- 호출 간 2초 sleep (TPM 30k 기준)

---

## 통계 검증

### v5 환산 점수 (460건)
- 평균: 45.1 / 100
- 중앙값: 42.3
- ratio > 1.01 위반: **0건** (클램핑 정상)

### 등급 분포
| 등급 | 건수 | 비율 |
|------|------|------|
| Gold | 235 | 51.1% |
| Silver | 118 | 25.7% |
| Platinum | 56 | 12.2% |
| Certified | 51 | 11.1% |

### 드리프트
| 트랙 | 건수 | 평균 drift |
|------|------|-----------|
| Rule | 413 | 10.7% |
| LLM | 47 | 22.6% |

---

## 다음 단계 (Phase D)

이 parquet를 사용해 XGBoost + SHAP 분석 진행. 결과는 `outputs/phase_D/REPORT.md` 참고.
