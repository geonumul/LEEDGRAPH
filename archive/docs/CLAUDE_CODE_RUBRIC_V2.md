# LEEDGRAPH 리팩토링 루브릭 V2
## Rule 기반 매핑 + LLM 의미 검증 파이프라인으로 전환

---

## 📌 프로젝트 컨텍스트 (모든 Phase 시작 시 Claude에게 전달)

```
나는 한국 LEED 인증 건축물 460개의 등급 결정 요인을 분석하는 연구를 하고 있어.
현재 LEEDGRAPH 프로젝트는 v2.0~v4.1 점수를 v5 스키마로 통일하는 파이프라인인데,
실제로는 rule-based if-else로 거의 모두 처리되고 있어서 LangGraph와 LLM이 제 역할을 못 하고 있어.

연구계획서에서 "LangGraph = 휴리스틱의 통제 도구"로 프레이밍했기 때문에,
LLM이 검증의 역할을 **모든 매핑**에 대해 수행하도록 구조를 바꿔야 해.

## 목표 아키텍처
현재: Rule 매핑 → 수학 검증 → (PASS) finalize / (FAIL) LLM 매핑 → LLM 검증 → finalize
변경: Rule 매핑 → 수학 검증 → LLM 의미 검증 (항상) → (PASS) finalize / (FAIL) LLM 재매핑 → LLM 검증 → finalize

## 핵심 원칙
1. Rule이 **주 계산 주체** (결정론·재현성 확보)
2. LLM은 **검증의 역할** (의미적 타당성, 엣지 케이스 감지)
3. LLM 검증 실패 시 LLM 재매핑 (**Option A: LLM 판단 존중**)
4. 460개 전수 검증이므로 비용 관리 필수 (캐시·체크포인트)

## 📝 문서화 규칙 (모든 Phase에 공통 적용)
**매 Phase에서 코드를 수정한 뒤 반드시** `docs/IMPLEMENTATION_V2.md` 에 아래 형식으로 **append** 할 것 
(파일이 없으면 새로 생성):

```markdown
## Phase N — [간단한 제목] (YYYY-MM-DD)

### 변경 파일
- path/to/file.py (function_name, line X~Y)

### 변경 전 / 변경 후
- **Before**: 짧은 설명 (코드 핵심 부분만 인용 가능)
- **After**: 짧은 설명 + 왜 이렇게 바꿨는지

### 설계 근거
- 연구계획서에서 연결 (예: "휴리스틱 통제" 프레이밍 유지)
- 선택한 방식의 장점과 트레이드오프
- 버려진 대안과 버린 이유

### 검증 방법
- 단위 테스트/샘플 실행으로 어떻게 검증했는지
- 결과 요약 (수치, 로그 발췌)

### 알려진 제한사항
- 이 변경으로 남은 이슈, 후속 Phase에서 다뤄야 할 사항
```

이 문서는 논문 3장(데이터셋 구축) 작성과 심사 대비의 1차 원자료가 되므로 **빠뜨리지 말 것**.
```

---

## 🔹 Phase 1: 현재 파이프라인 분석 및 변경 지점 특정

**목표**: 코드 수정 없이, 현재 구조의 변경 지점만 정확히 파악

**지시 프롬프트**:
```
아래 두 파일을 읽고 현재 LangGraph 파이프라인 흐름을 정리해줘:
- src/langgraph_workflow/graph.py
- src/langgraph_workflow/nodes.py 의 hallucination_checker_node, llm_validator_node, 
  그리고 route_after_hallucination_check / route_after_llm_validation 함수

정리 형식:
1. 현재 노드 연결 다이어그램 (텍스트 그림)
2. 현재 구조에서 LLM이 호출되는 조건 (몇 % 정도 호출되는지 로그 확인 가능하면 확인)
3. "Rule 결과를 LLM이 항상 검증"하도록 바꾸려면 수정해야 할 
   - 함수/노드 목록
   - 엣지 라우팅 변경점
   - 프롬프트 조정 필요 여부
4. 수정 시 영향받는 다른 파일 (scripts/, notebooks/ 등)

코드는 아직 수정하지 말고 분석만 해줘.
```

**완료 조건**:
- [ ] 현재 흐름 다이어그램 출력됨
- [ ] 수정 대상 함수/파일이 명확히 목록화됨
- [ ] 수정 계획이 내 확인 전에 실행되지 않음
- [ ] `docs/IMPLEMENTATION_V2.md` 에 Phase 1 항목 작성 
  (분석 결과·수정 계획·설계 근거 작성)

---

## 🔹 Phase 2: LLM Validator를 항상 호출되도록 리팩토링

**목표**: `hallucination_checker` PASS 후 **항상** `llm_validator`를 거치게 변경

**지시 프롬프트**:
```
Phase 1에서 파악한 내용을 바탕으로 src/langgraph_workflow/graph.py를 리팩토링해줘.

변경 요구사항:
1. route_after_hallucination_check 함수 수정:
   - 기존: PASS→finalize, FAIL→llm_mapper
   - 변경: PASS→llm_validator (의미 검증), FAIL→llm_mapper (구제 경로)
   - OPENAI_API_KEY 없으면 기존처럼 finalize로 (그래프가 LLM 없이도 돌아가야 함)

2. llm_validator 노드의 진입선이 2개가 됨:
   (a) rule 매핑 결과 검증 (신규) → state["rule_mapping_result"] 사용
   (b) llm 매핑 결과 검증 (기존) → state["mapping_result"] 사용
   → llm_validator_node가 어떤 경로로 들어왔는지 state로 구분할 수 있게
     state에 "validation_target" 필드 추가 ("rule" | "llm")

3. route_after_llm_validation 수정 (**Option A: LLM 판단 존중 방식**):
   - validation_target="rule" 일 때:
     * PASS (is_valid=True) → finalize
     * FAIL (is_valid=False) → llm_mapper 로 진입 (validation_target="llm" 으로 갱신)
       → LLM이 rule 결과를 신뢰하지 않으면, LLM이 처음부터 다시 매핑
   - validation_target="llm" 일 때: 기존 로직 유지 (PASS→finalize, FAIL→llm_mapper 반복)
   - FAIL 시 LLM이 받을 컨텍스트에 rule 결과와 LLM의 feedback을 모두 전달할 것
     (llm_mapper_node의 프롬프트가 "기존 rule 매핑 결과와 그에 대한 검증 피드백을 참고하여 재매핑"
      할 수 있도록 state에서 rule_mapping_result와 validation_result를 읽게 조정)

4. 무한 루프 방지: 
   - validation_target 전환을 current_iteration 카운트에 포함
   - max_iterations 도달 시 최종 단계의 결과를 강제 통과 (rule 경로라면 rule 결과, 
     llm 경로라면 마지막 llm 매핑) 사용하고 logs에 명시

수정 후 반드시:
- graph.py의 build_standardization_graph() 엣지 연결이 올바른지 설명
- state.py의 LEEDStandardizationState TypedDict에 "validation_target" 추가
- 단위 테스트 없이 그래프 compile이 에러 없이 되는지 확인
```

**완료 조건**:
- [ ] graph.py, state.py 수정됨
- [ ] `from src.langgraph_workflow.graph import build_standardization_graph; build_standardization_graph()` 실행 시 에러 없음
- [ ] 새 다이어그램 출력으로 변경된 흐름 확인
- [ ] `docs/IMPLEMENTATION_V2.md` 에 Phase 2 항목 append 
  (Option A 선택 근거, 무한루프 방지 전략, 영향받은 파일 목록 포함)

---

## 🔹 Phase 3: LLM Validator 프롬프트 개선

**목표**: `llm_validator_node`가 "rule 매핑 검증"과 "llm 매핑 검증"을 다르게 다루도록 프롬프트 분기

**지시 프롬프트**:
```
src/langgraph_workflow/nodes.py 의 llm_validator_node 함수를 수정해줘.

변경점:
1. state["validation_target"] 값에 따라 시스템 프롬프트/유저 프롬프트 분기
   - "rule": "아래 매핑은 결정론적 규칙으로 계산된 결과다. 의미적 오류, 맥락 누락, 
             버전별 특성 반영 부족 등을 점검하라" 관점
   - "llm":  기존 프롬프트 유지 (LLM 출력의 할루시네이션·수치 오류 점검)

2. 공통 검증 항목은 유지하되, rule 경로에서 특히 확인할 항목 추가:
   - SS→LT 교통 분리가 버전 특성에 맞게 이뤄졌는지 (v2.2/v2009)
   - PDF에 존재한 credit 중 매핑 규칙에서 누락된 것 없는지
   - v5 신규 카테고리(IP, RP)에 과도한/부족한 점수가 배정되지 않았는지

3. 응답 JSON 스키마는 기존 그대로 유지:
   {"is_valid": bool, "validation_score": 0~1, "issues": [...], "feedback": "..."}

4. 로깅: 로그 메시지에 [LLM Validator - rule 경로] 또는 [LLM Validator - llm 경로] 구분

기존 함수 시그니처나 반환값 형식은 바꾸지 말 것. 호출 측 코드 영향 최소화.
```

**완료 조건**:
- [ ] nodes.py 내 llm_validator_node만 수정됨
- [ ] 두 분기 프롬프트가 시각적으로 구분됨 (주석으로 #── Rule 검증 프롬프트 ──# 이런 식)
- [ ] 기존 llm_mapper 호출 경로에서 동작이 깨지지 않음
- [ ] `docs/IMPLEMENTATION_V2.md` 에 Phase 3 항목 append 
  (두 분기 프롬프트 전문 포함, 각 프롬프트가 어떤 검증 목적인지 해설)

---

## 🔹 Phase 4: 단일 샘플 테스트 및 결과 확인

**목표**: 실제 PDF 1개로 신규 파이프라인이 작동하는지 확인

**지시 프롬프트**:
```
OPENAI_API_KEY가 .env에 설정된다고 가정하고, 아래 테스트 스크립트를 만들어서 실행해줘:

1. test_rule_llm_validation.py (프로젝트 루트)
   - data/raw/scorecards/ 폴더에서 PDF 1개 선택 (가능하면 v2009 또는 v2.2 - 매핑 복잡도 높은 버전)
   - run_standardization()로 실행
   - 최종 state에서 다음을 출력:
     * rule_mapping_result (rule이 계산한 점수)
     * math_validation_result (수학 검증 결과)
     * validation_result (LLM 의미 검증 결과)
     * validation_target가 "rule"인지 확인
     * LLM이 rule 결과에 대해 어떤 피드백을 줬는지 (feedback 필드)
     * 최종 final_v5_data
   - 로그 전체를 출력하여 노드 방문 순서 확인

2. 실행 결과를 요약:
   - Rule 결과와 LLM이 검증한 결과가 일치하는지
   - LLM이 추가로 지적한 issues가 있었는지
   - 토큰 사용량 추정 (가능하면)

3. 성공/실패 여부 명확히 보고. 실패 시 원인 분석만 하고 수정은 내 확인 후 진행.
```

**완료 조건**:
- [ ] PDF 1개 실행 완료
- [ ] 노드 방문 순서가 pdf_ingest → csv_match → rule_mapper → hallucination_checker → llm_validator → finalize 순임 확인
- [ ] LLM의 validation_result가 state에 저장됨
- [ ] `docs/IMPLEMENTATION_V2.md` 에 Phase 4 항목 append 
  (실제 실행 로그 발췌, LLM 피드백 예시, 관찰된 동작 요약)

---

## 🔹 Phase 5: 소배치 (10개) 검증 및 비용 추정

**목표**: 460개 전수 실행 전에 10개로 품질·비용 체감

**지시 프롬프트**:
```
scripts/ 폴더에 run_validation_batch.py 를 만들어줘.

요구사항:
1. data/raw/scorecards/ 에서 버전 골고루 섞이게 10개 샘플링 
   (가능하면 v2.2, v2009, v4, v4.1 각 2~3개씩)
2. 각 PDF 처리하며 다음 기록:
   - project_id, version, 원본 등급
   - Rule 매핑 이슈
   - 수학 검증 PASS/FAIL
   - LLM 검증 validation_score, is_valid, issues 목록
   - 최종 final_v5_data의 총점과 등급
   - 각 건당 소요 시간, 추정 토큰 수
3. 결과를 outputs/phase_E/validation_batch_10.csv 로 저장
4. 요약 리포트 출력:
   - LLM 검증에서 is_valid=False 나온 비율
   - issues 상위 3개 패턴
   - 10개 기준 평균 토큰·시간 → 460개 전수 돌릴 때 예상 비용·시간 역산

비용이 예상보다 크게 나오면 460개 전수 진행 전에 먼저 내게 보고.
```

**완료 조건**:
- [ ] validation_batch_10.csv 생성됨
- [ ] 460개 전수 예상 비용·시간 추정치 제시됨
- [ ] LLM이 rule 결과에 대해 의미 있는 피드백을 주는지 최소 1~2개 사례 확인
- [ ] `docs/IMPLEMENTATION_V2.md` 에 Phase 5 항목 append 
  (비용·시간 추정 근거, is_valid=False 사례 분석, 460 전수 진행 여부 판단)

---

## 🔹 Phase 6: 전수 460개 실행 (승인 후)

**목표**: 파이프라인 전체 건물 재처리 + 검증 결과 누적

**지시 프롬프트** (Phase 5에서 비용·품질 OK 판단 후 실행):
```
scripts/run_pipeline.py 를 신규 파이프라인(rule + 의무 LLM 검증)으로 전면 실행.

추가 요구사항:
1. 중간 저장: 매 50건마다 outputs/phase_E/standardized_credits_checkpoint.parquet 
   업데이트 → 중단 시 재개 가능하게
2. 이미 처리된 project_id 는 건너뛰기 (비용 절약)
3. 최종 outputs/phase_E/standardized_credits_v2.parquet 생성
4. 검증 결과 누적: outputs/phase_E/llm_validation_log.csv 에 
   (project_id, is_valid, validation_score, issues, feedback) 기록
5. 완료 후 리포트:
   - 460건 중 is_valid=True 비율
   - LLM이 issue 제기한 건물 프로파일 (버전별 분포)
   - 기존 standardized_credits.parquet vs v2의 점수 차이 통계 (평균/최대 드리프트)

중단 후 재개 명령: python scripts/run_pipeline.py --resume
```

**완료 조건**:
- [ ] standardized_credits_v2.parquet 생성
- [ ] llm_validation_log.csv 생성
- [ ] 기존 결과와의 차이 리포트 출력
- [ ] `docs/IMPLEMENTATION_V2.md` 에 Phase 6 항목 append 
  (전수 실행 통계, rule vs rule+LLM 결과 비교, 이상치 건물 ID 목록, 실제 비용)

---

## 🔹 Phase 7: 논문 3장용 방법론 다이어그램·표 작성

**목표**: Phase 6 결과를 논문에 넣을 형식으로 정리

**지시 프롬프트**:
```
논문 3장(LangGraph 기반 데이터셋 구축)에 넣을 자료를 작성해줘.

1. outputs/final/Figure_pipeline_v2.png (또는 .svg)
   - 신규 파이프라인 다이어그램 (PDF → Ingest → CSV Match → Rule Mapper 
     → Math Check → LLM Validator → Finalize, 실패 시 LLM Mapper 분기)
   - 깔끔한 흑백, 논문 스타일 (matplotlib 또는 graphviz 중 선택)

2. outputs/final/Table_validation_summary.csv
   - 열: 버전(v2.2/v2009/v4/v4.1) / 건수 / LLM is_valid=True 비율 / 
     평균 validation_score / 평균 드리프트(%)

3. outputs/final/Table_llm_issues_topk.csv
   - LLM이 지적한 issue 상위 10개 패턴, 각 빈도

4. outputs/reports/methodology_summary.md
   - 3장에 들어갈 방법론 서술 초안 (한국어, 약 1~2페이지)
   - "결정론적 규칙 매핑 + LLM 의미 검증의 이중 검증 파이프라인" 관점으로 서술
   - 연구계획서에서 "휴리스틱 통제" 프레이밍 연결
```

**완료 조건**:
- [ ] 3개 파일 + 1개 md 생성됨
- [ ] 서술 초안이 연구계획서 1.2절 톤과 일관됨
- [ ] `docs/IMPLEMENTATION_V2.md` 에 Phase 7 항목 append 
  (그림·표 해석 포인트, 서술 초안의 근거가 된 데이터 출처)

---

## 🔹 Phase 8: 구현 문서 최종 정리 및 논문 연결

**목표**: Phase 1~7 동안 누적된 `docs/IMPLEMENTATION_V2.md`를 논문 제출용으로 다듬기

**지시 프롬프트**:
```
docs/IMPLEMENTATION_V2.md 전체를 읽고 다음 작업을 해줘.

1. 일관성 정리:
   - Phase별 항목이 동일한 형식을 유지하는지 확인 (안 된 칸은 채워넣기)
   - 중복 내용 통합, 모순되는 서술 수정
   - 오타·번역투 정리

2. 앞부분에 "Executive Summary" 섹션 추가 (A4 1페이지 분량):
   - 현재 파이프라인 전체 아키텍처 요약
   - 왜 rule + LLM 검증 이중 구조인지 (연구계획서 논리 연결)
   - Phase 6 전수 실행 결과 핵심 수치 3~5개
   - 한계와 향후 개선 방향

3. 뒷부분에 "심사 예상 질문 대응" 섹션 추가:
   - "왜 LangGraph인가?" → 답변 초안
   - "왜 rule 먼저, LLM 나중?" → 답변 초안 (재현성·비용·책임소재 관점)
   - "LLM이 rule을 뒤집은 건수가 많다면 rule이 틀린 것 아닌가?" → 답변 초안
   - "460개로 일반화가 되는가?" → 답변 초안 (한국 시장 전수 성격 근거)

4. 부록으로 "핵심 코드 스니펫" 섹션 추가:
   - route_after_hallucination_check (변경 후)
   - route_after_llm_validation (Option A 구현)
   - llm_validator_node 의 rule 검증 프롬프트 전문
   - 각 스니펫에 3~5줄 주석으로 설계 의도

5. 최종본은 docs/IMPLEMENTATION_V2.md 에 overwrite 저장.
   원본이 너무 길면 docs/IMPLEMENTATION_V2_raw.md 로 백업.

이 문서는 내가 논문 3장 쓸 때, 심사 대비할 때, 코드 리뷰 받을 때 모두 1차 참고자료로 쓸 거야.
```

**완료 조건**:
- [ ] docs/IMPLEMENTATION_V2.md 가 Executive Summary + 각 Phase 기록 + 심사 대응 + 코드 부록 구조로 재편됨
- [ ] 중복·모순 없음
- [ ] 논문 3장 작성 시 바로 참조할 수 있을 정도의 완성도

---

## 💰 비용 관리 팁

- Phase 2~4는 API 호출 거의 없음 (구조 변경이 주)
- Phase 5에서 10건 × ~3,000 토큰 → $0.3~0.5 수준
- Phase 6 전수 460건 → $15~25 수준 (gpt-4.1 기준)
- gpt-4.1-mini 로 검증만 돌리면 1/5로 절감 가능 → Phase 5 결과 보고 결정

---

## 🚨 각 Phase 실행 전 체크리스트

- [ ] git commit 해두고 시작 (롤백 가능하게)
- [ ] .env 에 OPENAI_API_KEY 설정됨
- [ ] 이전 Phase 완료 조건 모두 충족됨
- [ ] Claude Code에게 **현재 Phase 번호**와 **프로젝트 컨텍스트 블록** 먼저 전달

---

## ▶️ 지금 바로 시작하려면

VSCode에서 Claude Code에게 이렇게 전달:

```
이 루브릭(CLAUDE_CODE_RUBRIC_V2.md)을 참고해서 Phase 1부터 시작해줘.
먼저 맨 위의 "프로젝트 컨텍스트" 블록을 읽고, 그 다음 Phase 1의 
"지시 프롬프트"를 따라가. 완료 조건을 모두 만족하면 멈추고 내 확인을 기다려.
```
