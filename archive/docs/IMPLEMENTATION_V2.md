# V2 작업 기록 (정말 쉬운 버전)

## 이 문서가 뭐야?

프로젝트를 처음부터 V2 방식으로 뜯어고치면서 한 작업들을 순서대로 기록한 문서야. 앞으로 논문 쓸 때 "내가 언제 뭘 왜 바꿨나"를 찾아볼 수 있도록 남겨둔 것.

**자주 쓰는 단어 미리 정리**:
- **파이프라인(pipeline)**: 데이터가 여러 단계를 거쳐 처리되는 과정. 공장 컨베이어벨트 같은 것.
- **LangGraph**: 파이프라인을 "그래프 노드 연결"로 짜는 도구. 각 단계가 노드, 흐름이 화살표.
- **Rule(규칙)**: 미리 정해놓은 계산식. 항상 같은 입력에 같은 결과.
- **LLM**: ChatGPT 같은 언어 모델. 유연하지만 매번 답이 조금씩 다를 수 있음.
- **Phase**: 작업을 몇 단계로 나눈 것. Phase 1, Phase 2…
- **리팩토링**: 기존 코드를 기능 유지하면서 구조만 바꾸는 작업.

---

## 한줄 요약

원래 파이프라인은 Rule(규칙)만으로 돌아가서 LLM(ChatGPT)은 거의 안 쓰였어. V2에서는 **LLM이 "검증자" 역할로 들어오도록** 구조를 바꿨음. 단, 최종 점수는 여전히 Rule이 결정 (LLM이 마음대로 바꾸면 결과가 매번 달라지니까).

---

## 왜 V2가 필요했나

기존 파이프라인 흐름:
```
1. Rule이 점수 계산
2. 수학 검증 (드리프트 20% 이하인가?)
3. 수학 통과 → 바로 저장 끝. LLM 안 씀.
```

문제: 460건 중 90%가 수학 검증 통과라 **LLM이 실제로 10%만 쓰임**. 연구계획서에 "LangGraph로 휴리스틱(=Rule)을 통제한다"고 써놓았는데 사실상 통제가 거의 없었어.

V2에서 바꾼 것:
```
1. Rule이 점수 계산
2. 수학 검증
3. **LLM이 "이 매핑 의미 통하나?" 확인**  ← 신규
4. 저장
```

LLM이 검사는 하되 **점수는 안 바꿈** (Option A). 의견(점수, 피드백)만 메타데이터로 기록.

---

## 최종 결과 (75/460건 처리)

중간에 API 비용이 많이 나와서 75건에서 멈춤. 결과:

| 항목 | 값 |
|------|-----|
| 처리 완료 | 75건 (460건 중) |
| **LLM이 Rule 승인** | **7건 (9.3%)** |
| LLM이 Rule 의문 제기 | 68건 (90.7%) |
| 비용 | 약 $9 (596번 API 호출) |

**핵심 발견**: `credit_rule_hit_rate`(크레딧 매핑 성공률)가 높은 건물일수록 LLM도 승인하는 경향. 0.7 이상이면 거의 승인.

---

## Phase별 진행 기록

### Phase 1: 기존 코드 분석만 (2026-04-17)

**뭘 했나**: 코드 수정 없이 **기존 흐름 파악만**. LLM이 언제 호출되는지, 어디를 바꿔야 하는지 리스트업.

**결과**: 바꿔야 할 곳 8군데 확인 (graph.py, state.py, nodes.py).

---

### Phase 2: 흐름 변경 (라우팅)

**뭘 했나**: 수학 검증 통과해도 LLM 검증을 **반드시** 거치게 흐름 수정.

핵심 바꾼 코드:
```python
# Before
if 수학통과: return "finalize"  # 바로 끝

# After
if API키없음: return "finalize"
if 수학통과: return "llm_validator"  # 신규: LLM 검증으로
else: return "llm_mapper"           # 수학 실패 시 LLM이 재매핑
```

**state에 `validation_target` 추가**: LLM이 지금 Rule 결과를 검증 중인지, LLM 재매핑 결과를 검증 중인지 구분.

---

### Phase 3: LLM 검증 프롬프트 작성

**뭘 했나**: `validation_target`에 따라 LLM한테 다른 질문 던지게 프롬프트 2종류 작성.

**Rule 결과 검증 프롬프트**:
> "이 매핑 의미적으로 말 되나? 버전 특성 반영됐나? 크레딧 누락 없나?"

**LLM 결과 검증 프롬프트**:
> "LLM이 이상한 숫자 뱉은 거 아니냐? 카테고리 최대값 초과, 할루시네이션 점검해라"

**합격선**: score ≥ 0.8

---

### Phase 4: 단일 PDF 테스트

**뭘 했나**: 실제 PDF 1개(adidas Brand Flagship Seoul) 돌려서 흐름 제대로 가는지 확인.

**결과**:
```
PDF → Rule Mapper (Rule이 v5=48.3점 계산, 매칭률 88%)
→ 수학 검증 PASS (drift 13.8%)
→ LLM 검증 [Rule 대상] → FAIL (score=0.70)  ← 원했던 V2 동작
→ LLM이 재매핑
→ 다시 LLM 검증 → 또 FAIL
→ 3번 반복 후 강제 통과
→ 저장 완료
```

흐름은 정상인데 **LLM이 너무 엄격** (threshold 0.8)해서 Rule 결과를 자꾸 거부.

---

### Phase 5: 10건 배치 테스트

**뭘 했나**: 10개 건물 돌려보면서 전체 460건 돌리면 시간/비용 얼마나 나올지 계산.

**결과**:
- 10/10 최종 통과
- 1/10만 Rule PASS (나머지 9개는 LLM이 거부하고 재매핑)
- 건물당 61.7초
- 460건 예상: **8시간, $6~12**

---

### Phase 6: 460건 전수 실행 → 75건에서 중단

**뭘 했나**: 전체 460건 돌리기 시도. 그런데 비용이 예상보다 많이 나와서 75건에서 멈춤.

**결과**:
- 75건 처리 완료, $9 들어감
- 68건(90.7%)가 "LLM이 rule 거부 → 재매핑 → 3번 반복 → 강제 승인"
- **threshold 0.8이 너무 엄격했다는 결론**

**버전별 Rule 승인 패턴**:

| 버전 | 리뷰 | Rule 승인 | 거부 |
|------|-----|-----------|------|
| v2.0 | 1 | 0 | 1 |
| v2.2 | 5 | 0 | 5 |
| v2009 | 12 | 0 | 12 |
| v4 | 53 | 6 | 47 |
| v4.1 | 4 | 1 | 3 |

→ **구버전은 LLM이 전부 거부**. 버전이 오래될수록 LLM이 Rule 매핑을 불신.

---

### Phase 7: 논문용 그림/표 생성

**뭘 했나**: 논문 3장(방법론)에 넣을 자료 만들기.

**만든 것**:
- `Figure_pipeline_v2.png` — V2 구조 다이어그램
- `Table_validation_summary.csv` — 버전별 검증 통계
- `Table_llm_issues_topk.csv` — LLM이 자주 지적한 이슈 패턴
- `methodology_summary.md` — 논문 3장 초안

---

### Phase 8: 문서 정리

지금 보고 있는 이 문서의 원형 작성. Executive Summary + Phase별 기록 + 심사 예상 질문 + 코드 예시.

---

### Phase 9: ⭐ Option A로 피벗 (가장 중요)

**왜 피벗했나**: 원래 설계대로 가면 "LLM이 재매핑한 점수" 정확도를 증명해야 해서 **NLP 논문**이 돼버림. 우리 본론은 "한국 LEED 건물 등급 분석"인데.

**바꾼 것**:

| 항목 | Before | **After (Option A)** |
|------|--------|---------------------|
| 최종 점수 | LLM 재매핑 결과 | **Rule 결과 (항상)** |
| LLM 역할 | 재매핑자 | **리뷰어** |
| FAIL 처리 | 재매핑 loop | **그냥 저장 (리뷰 메타만 기록)** |

**최종 데이터**: `data/processed/project_features_option_a.parquet`
- 460건 모두 Rule 기반 점수 (결정론)
- 75건은 LLM 리뷰 메타 포함
- 385건은 리뷰 없음 (필드 비어있음)

---

### Phase 10: Robustness 검증

**뭘 했나**: "credit_hit 높은 건물만 썼을 때도 SHAP 결과 같나?" 확인.

| Subset | N | CV 정확도 | Top SHAP |
|--------|---|----------|----------|
| 전체 | 460 | 0.8152 | EA |
| credit_hit > 0.7 | 324 | 0.8333 | EA |
| 신버전 (v4, v4.1) | 324 | 0.8333 | - |
| 구버전 (v2.x, v2009) | 136 | 0.7865 | - |

**결론**: 어느 subset이든 **EA(에너지)가 가장 중요**. 결과 robust.

---

## 심사 예상 질문 Q&A

### Q1. "왜 LangGraph 써요? 그냥 함수로 해도 되잖아요"

**답**: 단계별로 노드가 분리되고, "어디서 LLM 불러올지"가 조건부 엣지 한 줄에 집중돼서 정책 바꾸기 쉬움. State 객체로 중간 결과 다 추적 가능해서 디버깅 편함. 체크포인트로 8시간 돌리다 끊겨도 재개 가능.

### Q2. "왜 Rule 먼저고 LLM 나중이야? LLM 먼저 쓰면 안 돼?"

**답**:
1. **재현성**: Rule은 LEED 공식 루브릭 수식이라 동일 입력 = 동일 결과. LLM은 매번 조금씩 다를 수 있음.
2. **비용**: LLM을 주 계산자로 쓰면 460건 × 반복 = 수백 달러.
3. **책임소재**: 계산=Rule, 검증=LLM으로 분리하면 어떤 숫자가 어디서 왔는지 명확.

### Q3. "LLM이 Rule을 90% 거부했는데 Rule이 틀린 거 아니냐?"

**답**: 아님. threshold 0.8이 너무 보수적이어서 거부율이 높았음. 실제로 LLM이 **확실하게 승인한 7건**은 구체적 도메인 근거 제시 ("LT/SS 분리 올바름, IN/RP 폐지 정확히 반영"). Rule이 틀렸다기보다 LLM이 보완 지표 역할.

### Q4. "460개로 일반화 되나?"

**답**: 이건 한국에서 인증받은 LEED 건물 **전수** (USGBC 공식 Directory). 표본 추출 아니라 한국 시장 대표. 해외 가면 프롬프트 국가 맥락 부분만 바꾸면 재사용 가능.

---

## 수정한 주요 파일 정리

| 파일 | 뭐 하는지 |
|------|----------|
| `src/langgraph_workflow/state.py` | 파이프라인 중간 데이터 정의 (validation_target 포함) |
| `src/langgraph_workflow/graph.py` | 노드들 연결 + 분기 규칙 |
| `src/langgraph_workflow/nodes.py` | 각 노드 실제 구현 (7개: PDF 파싱, CSV 매칭, Rule, 수학 검증, LLM 검증, LLM 재매핑, 최종) |
| `scripts/run_pipeline.py` | V1 파이프라인 실행 |
| `scripts/run_pipeline_v2.py` | V2 파이프라인 실행 (체크포인트 지원) |
| `scripts/run_validation_batch.py` | 10건 샘플 배치 |
| `scripts/build_option_a_dataset.py` | V1 점수 + LLM 리뷰 합치기 |
| `scripts/run_analysis.py` | XGBoost + SHAP 분석 |
| `scripts/run_analysis_option_a.py` | Option A SHAP robustness 비교 |
| `test_rule_llm_validation.py` | 단일 PDF 디버깅 |

---

## 핵심 코드 스니펫

### 라우팅 (graph.py)

```python
def route_after_hallucination_check(state):
    # 수학 검증 후 어디로 갈지 결정
    if not API키있음:
        return "finalize"           # API 없으면 Rule 결과 바로 저장
    if 수학검증통과:
        return "llm_validator"      # V2: Rule도 LLM이 검증
    return "llm_mapper"             # 수학 실패: LLM이 재매핑

def route_after_llm_validation(state):
    # Option A: 검증 결과 상관없이 항상 저장
    # LLM 의견은 메타데이터로만 기록, 점수는 Rule 유지
    return "finalize"
```

### LLM 리뷰 메타데이터 (nodes.py finalize)

```python
final_data = {
    # ... 기본 점수 필드 ...
    "standardization_track": "rule",
    # Option A: LLM 리뷰 결과 (점수는 안 바꿈)
    "llm_review_target":    "rule",   # 뭘 검증했나
    "llm_review_is_valid":  True,     # LLM 판단: 통과?
    "llm_review_score":     0.92,     # 신뢰도
    "llm_review_issues":    "...",    # 지적 사항
    "llm_review_feedback":  "...",    # 전체 의견
}
```

---

*이 문서는 실제 구현 기록용이야. 논문 쓸 때 표현은 자유롭게 바꿔도 됨.*
