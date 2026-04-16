# LEEDGRAPH 리팩토링 V2 — 구현 기록

`docs/CLAUDE_CODE_RUBRIC_V2.md` 루브릭에 따라 Rule 매핑 + LLM 의무 검증 파이프라인으로 전환하는 작업 기록.

---

## Phase 1 — 현재 파이프라인 분석 및 변경 지점 특정 (2026-04-17)

### 변경 파일
- (이 Phase는 분석만, 코드 수정 없음)

### Before (현재 구조 파악)

#### 1. 현재 노드 연결 다이어그램

```
                        [pdf_ingest]
                              │
                              ▼
                        [csv_match]
                              │
                              ▼
                       [rule_mapper]
                              │
                              ▼
                 [hallucination_checker]
                              │
               route_after_hallucination_check
                  ┌───────────┼───────────┐
       passed=True│           │passed=False+API│passed=False
                  │           │            │ +no API
                  ▼           ▼            ▼
              [finalize]  [llm_mapper]  [finalize]
                  │           │             │
                  │           ▼             │
                  │     [llm_validator]    │
                  │           │             │
                  │   route_after_llm_validation
                  │     ┌─────┴─────┐       │
                  │     │PASS│FAIL+ret│     │
                  │     ▼     ▼       │     │
                  │ finalize llm_mapper     │
                  │     │  (loop)           │
                  │     │                   │
                  └─────┴───────────────────┘
                              │
                              ▼
                            [END]
```

#### 2. 현재 LLM이 호출되는 조건

현재 실제 실행 결과 (460개 건물):
- **rule 경로**: 413건 (89.8%) — LLM 완전 미호출
- **llm 경로**: 47건 (10.2%) — hallucination_checker FAIL (drift > 20%) 시에만 진입

**LLM 호출 조건** (`route_after_hallucination_check`, graph.py L46–61):
```python
if math_result.get("passed", False):
    return "finalize"        # ← 90%의 건물이 여기로 빠짐
if not os.environ.get("OPENAI_API_KEY"):
    return "finalize"
return "llm_mapper"          # ← 수학 검증 실패한 10%만 LLM 진입
```

**`hallucination_checker_node` PASS 조건** (nodes.py L711–):
1. 모든 카테고리 0 ≤ score ≤ V5_MAX
2. sum(categories) ≈ total_score_v5
3. `|원본 달성률 − v5 달성률| ≤ 20%` (drift threshold)
4. 음수 없음
5. v5에 없는 카테고리 없음

→ **결론**: Rule 결과가 수학적으로 정합성만 있으면 LLM은 절대 호출되지 않는 구조.  
→ 연구계획서의 "LangGraph = 휴리스틱 통제 도구" 주장이 현재는 10.2%에만 해당.

#### 3. "Rule 결과를 LLM이 항상 검증"하려면 수정할 지점

##### 3-1. 수정 대상 함수/파일

| 대상 | 위치 | 변경 내용 |
|------|------|-----------|
| `route_after_hallucination_check` | graph.py L46 | PASS 브랜치: `return "finalize"` → `return "llm_validator"`. no-API 브랜치만 `"finalize"` 유지 |
| `build_standardization_graph` | graph.py L85 | hallucination_checker 분기 엣지 딕셔너리에 `"llm_validator"` 키 추가 |
| `LEEDStandardizationState` | state.py L48 | `validation_target: str` 필드 추가 (`"rule"` / `"llm"`), 초기값 `"rule"` |
| `run_standardization` initial_state | graph.py L167 | `"validation_target": "rule"` 초기화 추가 |
| `llm_validator_node` | nodes.py L978 | 두 분기 프롬프트: `validation_target`에 따라 rule 검증 vs llm 검증 |
| `route_after_llm_validation` | graph.py L64 | rule 경로 PASS→finalize, FAIL→llm_mapper (target="llm"로 전환); llm 경로는 기존 유지 |
| `llm_mapper_node` | nodes.py L762 | rule fallback 진입 시 `rule_mapping_result` + `validation_result.feedback`을 프롬프트에 포함. 출력에 `validation_target="llm"` 설정 |
| `finalize_node` | nodes.py L1120 | `validation_mode` → `validation_target` 기반 결과 선택. rule 검증 통과 시 `rule_mapping_result` 사용 |

##### 3-2. 엣지 라우팅 변경점

```
[변경 전]
  hallucination_checker  ─ PASS ─▶ finalize
                         ─ FAIL ─▶ llm_mapper

[변경 후]
  hallucination_checker  ─ PASS ─▶ llm_validator   (신규: rule 결과 의미 검증)
                         ─ FAIL ─▶ llm_mapper
                         ─ no-API ▶ finalize        (fallback 유지)

  llm_validator  ─ target=rule, PASS ─▶ finalize
                 ─ target=rule, FAIL ─▶ llm_mapper   (신규: LLM 재매핑)
                 ─ target=llm,  PASS ─▶ finalize
                 ─ target=llm,  FAIL ─▶ llm_mapper   (기존 loop)
```

##### 3-3. 프롬프트 조정 필요 여부

**Yes, 필수.** `llm_validator_node` 내부에 두 버전 프롬프트 필요:

- **rule 검증 프롬프트** (`validation_target == "rule"`):
  - 관점: "결정론적 규칙으로 계산된 결과의 **의미적** 타당성"
  - 주요 체크: 버전 특성 반영 여부(v2.2 SS→LT 분리), 누락된 크레딧, v5 신규 카테고리 배분 적절성
  - 기대: rule이 정확히 계산했더라도 의미적으로 틀릴 수 있다는 관점
- **llm 검증 프롬프트** (`validation_target == "llm"`, 기존 유지):
  - 관점: "LLM 출력의 할루시네이션 + 수치 오류"
  - 주요 체크: 카테고리 초과, 음수, 등급 일관성
  - 기대: LLM 재매핑 결과를 이중 체크

##### 3-4. 무한 루프 방지

- `current_iteration`은 `llm_mapper_node` 진입마다 +1
- rule→llm 전환도 `current_iteration`에 포함 (target 전환이 곧 재매핑이므로 중복 카운트 X, 그러나 자연스러운 증가)
- `max_iterations` 도달 시 `llm_validator_node`에서 강제 승인 → finalize
- 최종 단계에서 `validation_target`에 따라:
  - `"rule"`이면 `rule_mapping_result` 사용
  - `"llm"`이면 마지막 `mapping_result` 사용

#### 4. 수정 시 영향받는 다른 파일

| 파일 | 영향 | 설명 |
|------|------|------|
| `scripts/run_pipeline.py` | 🟡 중간 | `final.get("standardization_track")` 읽는데, 현재 `"rule"`/`"llm"` 두 값. 신규 파이프라인에서 의미 변화 확인 필요 (rule+LLM 검증 경로를 어떻게 표기?) |
| `scripts/run_llm_retry.py` | 🟡 중간 | 위와 동일하게 `standardization_track`으로 필터링 |
| `scripts/run_analysis.py` | 🟢 낮음 | feature parquet만 읽으므로 컬럼 값만 유지되면 영향 없음 |
| `make_req.py` | 🟢 낮음 | requirements 생성, 구조 변경과 무관 |
| notebooks (`*.ipynb`) | ⚠️ 미확인 | 노트북이 있다면 별도 체크 필요 |

### After (변경 계획)

#### Phase 2 → Phase 3 순서로 진행 예정

**Phase 2** (graph.py, state.py):
- `validation_target` 필드 추가
- 라우팅 변경 (4개 엣지 딕셔너리 + 2개 route 함수)
- `llm_mapper_node`에 rule feedback 수용 로직 추가
- **테스트**: `build_standardization_graph()` 컴파일 에러 없이 통과

**Phase 3** (nodes.py):
- `llm_validator_node`에 `validation_target` 분기
- rule 검증용 프롬프트 신규 작성
- 로그 메시지 구분

**Phase 4** (단일 PDF 테스트):
- v2009 또는 v2.2 PDF 1개 선택 (매핑 복잡도 높음)
- 노드 방문 순서 확인: `… → rule_mapper → hallucination_checker → llm_validator → finalize`
- LLM feedback이 state에 저장되는지 확인

### 설계 근거

#### 왜 Option A (LLM 판단 존중) 채택?
- rule이 결정론적으로 **정확**하더라도 **의미**가 틀릴 수 있음 (예: v2.2 SS→LT 비율 추정은 수학적으로는 맞지만 해당 건물 맥락에 안 맞을 수 있음).
- LLM이 rule 결과를 `is_valid=False`로 판정하면 "LLM 재매핑"이 자연스러운 후속 조치.
- 연구계획서의 "휴리스틱 통제" 프레이밍과 일치 (휴리스틱 = rule, 통제자 = LLM).

#### 왜 rule_mapper는 그대로 두고 validator만 리라우팅?
- rule_mapper는 버전 특성 (SS→LT 분리 등)을 이미 잘 처리하고 있음 → 계산 주체로 유지.
- LLM을 rule_mapper로 직접 끌어들이면 재현성·비용 모두 악화.
- **계산 = rule / 검증 = LLM** 이라는 역할 분리 유지.

#### 버려진 대안: "LLM이 rule 결과를 편집"
- LLM에게 부분 편집을 허용하면 어떤 필드를 바꿨는지 추적 어려움 → 재현성 악화.
- 현재 설계(PASS 또는 완전 재매핑)가 감사·재현성 측면에서 우월.

### 검증 방법 (분석 단계라 실행 없음)

이 Phase에서는 코드 수정을 하지 않았으므로 실행 검증 없음.  
Phase 2 이후 컴파일 테스트, Phase 4 단일 샘플 실행으로 단계적 검증 예정.

### 알려진 제한사항

1. **`validation_mode` vs `validation_target` 공존**: 현재 state에 `validation_mode`("rule"/"llm")가 있고, 신규로 `validation_target`을 추가하면 두 필드의 의미가 겹칠 수 있음.
   - 해결 방안: `validation_mode`는 **최종 경로**(어느 결과가 채택됐는지), `validation_target`은 **현재 검증 대상**(rule인지 llm인지)으로 역할 분리.
   - Phase 2에서 state.py에 주석으로 명시 필요.
2. **비용 증가**: 현재 10.2%(47건)만 LLM 호출 → 변경 후 100%(460건 × 최소 1회 validator) → **약 10배 증가**. gpt-4.1 기준 $15~25 추정 (Phase 5에서 10건 실측 후 확정).
3. **Rate limit**: 이미 Phase 0에서 tenacity retry + 2초 sleep 적용됨 → 460건 연속 호출 시 약 15~25분 소요 예상.
4. **기존 결과와의 호환**: `outputs/phase_C/REPORT.md`와 `llm_vs_rule_comparison.md`의 기준은 rule 경로 413건 / LLM 경로 47건. Phase 6 이후 "rule 검증 경로"라는 개념이 새로 생기므로 REPORT 재서술 필요.

---

## Phase 1 Appendix — 현재 Baseline 성능 (LLM 검증 10.2%만 적용된 상태)

Phase 6 이후 "LLM 100% 검증" 결과와 비교하기 위한 기준선.

### A. 파이프라인 경로별 품질 지표

| 지표 | Rule 경로 (413건) | LLM 경로 (47건) | 해석 |
|------|------------------|-----------------|------|
| drift 평균 | **10.7%** | 22.6% | Rule 경로는 hallucination_checker를 통과하도록 20% 이하로 자동 클램핑됨 |
| drift 중앙값 | 10.7% | 21.4% | 동일 |
| drift 최대 | 19.7% | **48.3%** | LLM 경로는 Gucci Yeoju(v2.2) 같은 구조적 엣지 케이스 포함 |
| v5 총점 평균 | 46.0 pt | 37.4 pt | LLM 경로는 고급 retail 건물이 많아 구조적으로 낮음 |
| credit_rule_hit_rate 평균 | **59.1%** | **86.3%** | ⚠️ **역전**: rule 경로의 크레딧 매칭률이 오히려 낮음 |

### B. 크레딧 매핑 방식 분포

| mapping_method | Rule 경로 | LLM 경로 |
|----------------|-----------|----------|
| rule | 77.7% | 87.6% |
| unmatched | 11.4% | 12.4% |
| category_proportional | **10.9%** | 0.0% |

> **핵심 관찰**: Rule 경로 건물은 크레딧 이름 매핑이 안 될 때 `category_proportional` (카테고리 합계 기반 비율 환산)로 fallback됨. 이 때문에 credit_rule_hit_rate는 낮지만 drift는 안정적.  
> → **즉 현재 파이프라인은 드리프트를 강제로 낮추고 있을 뿐, 의미적 정확성은 보장하지 못함**. LLM 의무 검증이 필요한 이유의 직접적 근거.

### C. 등급 분포 편향

| 등급 | Rule 경로 (n=413) | LLM 경로 (n=47) | 비율 (LLM/Rule) |
|------|-------------------|-----------------|-----------------|
| Gold | 194 (47.0%) | 41 (87.2%) | **1.86×** |
| Silver | 116 (28.1%) | 2 (4.3%) | 0.15× |
| Platinum | 52 (12.6%) | 4 (8.5%) | 0.68× |
| Certified | 51 (12.3%) | 0 | 0.00× |

> **편향**: LLM 경로는 Gold 건물에 집중(87.2%). Rule은 균등 분포.  
> → Phase 6 이후 모든 등급 건물이 LLM 검증을 거치면 **등급별 is_valid 비율 차이**가 주요 분석 대상이 됨.

### D. 전체 모델 성능 (현재 baseline)

| 지표 | 값 | 출처 |
|------|-----|------|
| 샘플 수 | 460 | project_features.parquet |
| XGBoost 5-Fold CV Accuracy | **0.8174 ± 0.0502** | outputs/phase_D/model_metrics.json |
| XGBoost 5-Fold CV Weighted F1 | **0.8157 ± 0.0504** | 동일 |
| Top SHAP feature | EA (0.8180) | 일관됨 |

### E. Phase 6 이후 비교할 신규 지표

"LLM 100% 검증" 적용 후 새로 얻게 될 지표:

| 지표 | 의미 | 현재 상태 |
|------|------|----------|
| **is_valid 비율 (rule 대상)** | 413건 rule 결과 중 LLM이 OK 판정한 비율 | ⚫ 측정 불가 (검증 안 함) |
| **LLM issue top-k 패턴** | 어떤 유형의 오류를 지적하는지 | ⚫ 측정 불가 |
| **재매핑 발생 비율** | LLM이 rule 결과를 뒤집고 재매핑한 건수 | ⚫ 측정 불가 |
| **category_proportional 대체율** | 크레딧 미매칭 건을 LLM이 의미적으로 보정한 비율 | ⚫ 측정 불가 |
| **drift 분포 변화** | 전체 drift 평균이 어떻게 달라지는지 | 현재 12.0% |
| **XGBoost CV F1 변화** | 매핑 품질 개선이 분류 성능에 주는 영향 | 현재 0.8157 |

### F. 비교 설계 가이드

Phase 6 완료 시 `outputs/phase_E/comparison_v1_vs_v2.md` 자동 생성 권장:

```markdown
| 지표 | V1 (baseline) | V2 (LLM 100% 검증) | Δ |
|------|---------------|---------------------|---|
| drift 평균 | 12.0% | ? | ? |
| credit_rule_hit_rate | 63.9% | ? | ? |
| category_proportional 비율 | 9.5% | ? | ? |
| CV Accuracy | 0.8174 | ? | ? |
| CV Weighted F1 | 0.8157 | ? | ? |
| 전체 LLM 호출 수 | 47 | 460+ | +10× |
| 예상 비용 | ~$2 | $15~25 | +10× |
| 실행 시간 | 10분 | 25~40분 | +3~4× |
```

### G. 리스크 체크 (V1 → V2 전환 시)

1. **성능 하락 가능성**: LLM이 rule 결과를 뒤집었는데 실제로는 rule이 맞았다면 오히려 drift 증가 / CV F1 하락 가능.
   - 대응: Phase 5 (10건 샘플)에서 LLM 재매핑 결과의 drift를 실측하여 Phase 6 Go/No-Go 판단.
2. **비용 초과**: gpt-4.1-mini로 validator 교체 시 1/5 비용 가능.
   - 대응: Phase 5 토큰 실측 후 결정.
3. **등급 편향**: Gold에 집중된 LLM 판단이 다른 등급으로 확장될 때 일관된 품질 유지 여부 미지수.
   - 대응: Phase 6 결과에서 등급별 is_valid 비율 따로 리포트.

---
