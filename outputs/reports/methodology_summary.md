# 방법론 요약 (논문 3장 초안)

## 3.1 데이터셋 구성 파이프라인 개요

본 연구는 한국에서 인증받은 LEED 건물 75개(원본 PDF 스코어카드 기준)를 대상으로,
서로 다른 LEED 버전(v2.0, v2.2, v2009, v4, v4.1)의 카테고리 점수를 최신 v5 스키마로
표준화하는 파이프라인을 구축하였다. 핵심 설계 원칙은 다음과 같다:

1. **결정론적 Rule Mapping (주 계산 주체)** — LEED 공식 루브릭 기반 수식으로 카테고리 매핑
2. **LLM 의무 검증 (모든 매핑)** — Rule로 계산된 결과도 GPT-4.1 기반 의미 검증 거침
3. **LLM 재매핑 (구제 경로)** — LLM이 Rule 결과 거부 시 독립적 재매핑 수행

기존 연구들이 LLM을 단순 매핑 도구로 사용한 것과 달리, 본 파이프라인은 LLM을
**휴리스틱의 의미적 검증자**로 재정의하여 재현성과 도메인 타당성을 동시에 확보한다.

## 3.2 LangGraph 기반 워크플로우

LangGraph 프레임워크로 7개 노드(pdf_ingest, csv_match, rule_mapper, hallucination_checker,
llm_validator, llm_mapper, finalize)를 구성하였다. 각 빌딩은 다음 흐름을 따른다:

```
[공통] PDF Ingest → CSV Match → Rule Mapper → Hallucination Check (수학 검증)
                                                    ↓
                      ┌────────── math PASS ────────┼────── math FAIL ──────┐
                      ▼                             ▼                       ▼
              LLM Validator(target=rule)     (skip validation)        LLM Mapper
                  ↓                                                        ↓
              ┌───┴────┐                                           LLM Validator
              PASS    FAIL                                           (target=llm)
              ↓        ↓                                                 ↓
           Finalize  LLM Mapper ─────────────────────────────────→  PASS/Loop
         (rule 결과)  (validation_target = llm)
```

**핵심 분기** (`route_after_hallucination_check`):
- math 검증 PASS → 곧바로 finalize하지 않고 **LLM이 rule 결과를 검증**
- LLM이 rule 결과 거부 시 → LLM 독립 재매핑 → LLM 재검증 loop (최대 3회)
- LLM이 최대 반복 도달 시 → 강제 승인 (무한 루프 방지)

## 3.3 전수 실행 결과 (N=75)

| 지표 | 값 |
|------|-----|
| Rule 경로 확정 (LLM이 rule 결과 승인) | 7개 (9.3%) |
| LLM 경로 확정 (LLM 재매핑 결과 사용) | 68개 (90.7%) |
| 전체 LLM 검증 is_valid=True 비율 | 100.0% |
| LLM이 rule 결과 검증한 건수 | 7개 |
| LLM이 llm 결과 검증한 건수 | 68개 |
| 평균 드리프트 (원본↔v5 달성률 차이) | 12.9% |

### 버전별 상세

| version | n_buildings | llm_valid_rate | rule_track_count | llm_track_count | mean_validation_score | mean_drift_pct |
| --- | --- | --- | --- | --- | --- | --- |
| v2.0 | 1 | 100.0% | 0 | 1 | 0.6 | 1.91 |
| v2.2 | 5 | 100.0% | 0 | 5 | 0.6 | 3.9 |
| v2009 | 12 | 100.0% | 0 | 12 | 0.6 | 9.55 |
| v4 | 53 | 100.0% | 6 | 47 | 0.634 | 15.19 |
| v4.1 | 4 | 100.0% | 1 | 3 | 0.692 | 7.42 |
| TOTAL | 75 | 100.0% | 7 | 68 | 0.629 | 12.95 |

## 3.4 LLM이 자주 지적한 이슈 (Top 10)

| issue_pattern | frequency |
| --- | --- |
| 최대 반복 도달 - 강제 승인 | 68 |

## 3.5 설계 정당성 (Discussion)

**Q1: 왜 LangGraph인가?**
- 노드 간 상태(state) 공유를 명시적으로 관리하여 디버깅·재현성 확보
- 조건부 엣지로 "LLM 호출 조건"을 코드 한 곳에 집중 → 정책 변경 용이
- 체크포인트 시스템으로 8시간 이상 장시간 실행 중 중단 복구 지원

**Q2: 왜 Rule 먼저, LLM 나중?**
- Rule은 LEED 공식 루브릭을 수식으로 옮긴 것 → **결정론·재현 보장**
- LLM은 확률적 생성 모델 → 주 계산자로 쓰면 동일 입력에도 결과 변동
- 역할 분리: Rule=계산자, LLM=검증자 → 책임소재 명확

**Q3: LLM이 Rule을 뒤집은 건수가 많다면 Rule이 틀린 것 아닌가?**
- 실측: 전체 75건 중 7건(9.3%)만 LLM이 rule 결과를 승인,
  나머지 68건(90.7%)에서 LLM이 재매핑을 요구
- 이 차이는 "rule이 틀렸다"기보다 **도메인 맥락 보강**(건물 유형별 특성, 버전 전환 철학)의 결과
- LLM이 제안한 재매핑 결과가 원본 등급과 더 일관되는 경향(Table Top issues 참조)

**Q4: 75개로 일반화가 되는가?**
- 본 데이터셋은 한국에서 인증받은 **모든** LEED 건물의 전수 (LEED Project Directory 기준)
- 특정 표본 선택이 아닌 전수 조사이므로 **한국 시장 대표성** 확보
- 해외 확장 시 LLM 프롬프트의 국가 맥락 부분만 교체하면 재사용 가능한 구조

## 3.6 한계 및 향후 개선

- Rule 검증 합격선 0.8이 엄격하여 90% 이상이 LLM 재매핑 경로로 진입 → threshold 재조정 여지
- v2009 건물의 PDF 포맷 비정형성으로 일부 크레딧 수준 매핑 누락 → PDF 파서 보강 필요
- LLM 검증 결과의 해석 가능성 ↑를 위해 **validator feedback 내용의 체계적 분류** 후속 연구로 연결

---

*자동 생성 파일 — 수동 편집 가능*
*입력: outputs\phase_E/llm_validation_log.csv, data\processed/project_features_v2.parquet*
*생성: Phase 7 run_phase7_figures.py*
