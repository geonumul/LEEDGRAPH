# LEEDGRAPH – 1일 작업 루브릭

> 기존 스캐닝(loader, rubric_loader, graph) 검증 → 실행 → XAI → 문서화  
> 각 Phase 독립 실행 / 완료 기준 체크 / 다음 Phase 이동

---

## 공통 프리앰블 (Claude Code 세션마다 맨 처음 한 번)

```
프로젝트: LEEDGRAPH – 한국 LEED 인증 460개의 v2.2/v2009/v4/v4.1을
          v5 체계로 표준화하고 SHAP으로 등급 결정 요인 분석.

현재 상태:
  - data/raw/scorecards/*.pdf : 460개 PDF, 22 조합 파싱 가능
  - data/raw/buildings_list/PublicLEEDProjectDirectory.csv : 456 rows
  - data/raw/rubrics/v5/LEED_v5_Scorecard_BDC_New_Construction.xlsx : v5 기준
  - data/raw/rubrics/ : v4/v4.1 xlsx 11개 + txt 11개(스코어카드로 대체)
  - src/data/loader.py : PDF+CSV 매칭 완성
  - src/data/rubric_loader.py : 작성됨 (미검증)
  - src/langgraph_workflow/{state,nodes,graph}.py : 조립됨 (미실행)
  - data/processed/ : 비어있음

하루 안에 파이프라인 end-to-end 돌리고 XAI 결과 + README.md 작성이 목표.

원칙:
  1. 현재 Phase만 작업, 완성될때까지 마.
  2. 기존 코드 대규모 재작성 금지. 버그만 수정.
  3. 각 Phase 끝에 outputs/phase_<X>/REPORT.md 남겨.
  4. 실패 빠르게 로깅, 완벽주의 금지 (오늘 끝내야 함).
```

---

## Phase A – 스모크 테스트 (목표 30분)

**목표**: 기존 코드가 샘플 5건에서 돌아가는지 확인하고, 루브릭 XLSX 포맷 파악.

**작업**:
```
1. src/data/loader.py 가 scorecard 5개 + CSV 매칭 → DataFrame 반환까지
   잘 되는지 확인 (pytest 말고 notebooks/smoke.ipynb 에서 임포트 실행).
2. src/data/rubric_loader.py 열어보고, v5 BD+C NC xlsx 하나 로드해서
   (category, credit_id, credit_name, points) 형태로 나오는지 확인.
3. v4 루브릭 xlsx 1개도 같은 로더로 시도. 포맷이 달라서 깨지면
   rubric_loader.py 에 케이스 분기 추가.
4. txt로 표시된 11개(스코어카드로 대체)도 별도 처리 경로 명시:
   → 해당 rating system의 scorecard 여러 개에서 크레딧 집합을 합쳐 루브릭 역산성
5. src/langgraph_workflow/graph.py import만 시도 (실행 X).
   circular import, 타입 에러 등 컴파일 타임 문제 없는지 확인.

출력물:
  - outputs/phase_A/smoke_report.md (뭐가 되고 뭐가 안되는지)
  - rubric_loader.py 수정본 (필요 시)
```

**완료 기준**:
- [ ] loader.py로 5개 PDF → merged DataFrame 출력 확인
- [ ] rubric_loader.py로 v5 + v4 xlsx 각 1개 로드 성공
- [ ] 11개 txt rubric 처리 전략 확정 (코드는 Phase B에서)
- [ ] graph.py 임포트 OK

---

## Phase B – v5 통합 스키마 구축 (목표 1.5시간)

**목표**: 모든 버전의 크레딧을 v5의 카테고리·임팩트 영역에 매핑하는 **마스터 매핑 테이블** 작성.

**배경 (Claude에게 전달)**:
```
v5 BD+C NC xlsx 구조:
  - 카테고리 코드: IP, LT, SS, WE, EA, MR, EQ (+ IN, RP)
  - 크레딧 코드: IPp1, LTc1, SSp1, SSc1 ...
  - 임팩트 영역 3개: Decarbonization / Quality of Life / Ecological C&R

매핑 전략 (우선순위):
  1. Rule-based 우선 (80%): USGBC의 버전 간 공식 유사성 활용.
     - "Optimize energy performance" (v4) → EAc3 Enhanced Energy Efficiency (v5)
     - "Minimum energy performance" (v4 prereq) → EAp2 (v5)
     등 명확한 대응을 규칙 테이블로.
  2. LLM 폴백 (20%): 규칙에 없는 것만 GPT 호출.
     state.py에 이미 구조 있음, 그대로 씀.
  3. 매핑 실패 → "Unknown" 카테고리에 모아두고 리포트.
```

**작업**:
```
1. data/raw/rubrics/mapping_rules.yaml 작성 (또는 csv):
   여기서 아래 카테고리는 규칙 작성해:
   - Energy & Atmosphere (EA) 전체
   - Water Efficiency (WE) 전체
   - Sustainable Sites (SS) 전체
   - Location & Transportation (LT) 전체
   - Material & Resources (MR) 주요 항목
   - Indoor Environmental Quality (EQ) 주요 항목
   - Innovation (IN), Regional Priority (RP)

   버전은 v2.2, v2009(v3), v4, v4.1 다 커버.
   크레딧명은 loader.py 결과에서 나온 실제 문자열 써야 함.

2. src/langgraph_workflow/nodes.py 의 Mapper/Validator 노드 검토:
   - rule 조회 먼저 → 매칭되면 즉시 통과 (LLM 호출 없음)
   - 매칭 실패 있을때만 LLM 호출
   - LLM 호출 전/후 rule 히트 로깅

3. 샘플 실행: scorecard 10개 돌려서 매핑 결과 확인.
   outputs/phase_B/sample_mapping.json

4. 전체 실행 전에 여기서 멈춰 대화 확인 요청.

출력물:
  - data/raw/rubrics/mapping_rules.yaml (핵심 출력물)
  - src/langgraph_workflow/nodes.py 수정본
  - outputs/phase_B/sample_mapping.json
  - outputs/phase_B/REPORT.md: rule 히트율, LLM 호출 건수, 미매핑 항목
```

**완료 기준**:
- [ ] mapping_rules.yaml에 최소 80개 이상의 규칙
- [ ] 샘플 10개에서 rule hit rate ≥ 70%
- [ ] LLM 폴백 경로 1건 이상 실제로 동작 확인
- [ ] 미매핑(Unknown) 항목 리스트 파악 → 수동 검토

---

## Phase C – 전체 파이프라인 실행 (목표 1시간)

**작업**:
```
1. scripts/run_pipeline.py 작성 (또는 기존 것 활용):
   모든 PDF 로드 → 크레딧 추출 → v5 매핑 → 표준화 테이블 저장.
2. 실행 중 에러는 해당 프로젝트만 skip + 로그, 전체 중단 금지.
3. 출력:
   - data/processed/standardized_credits.parquet
     (project_id, v5_credit_code, v5_category, points_awarded, points_possible,
      source_version, source_credit_name, mapping_method)
   - data/processed/project_features.parquet
     (project_id, cert_level, total_points, floor_area, v5_카테고리별 합계...)
   - outputs/phase_C/pipeline_errors.log
   - outputs/phase_C/REPORT.md

4. 검증 진행:
   - 표준화 후 total points vs CSV PointsAchieved 일치율
   - 카테고리별 점수 합이 v5 max points 이내인지
   - 버전별 처리 성공 건수
```

**완료 기준**:
- [ ] standardized_credits.parquet 생성 (≥ 440개 프로젝트 성공 처리)
- [ ] project_features.parquet 생성 (ML 입력용 wide format)
- [ ] Total points 일치율 ≥ 95%
- [ ] REPORT.md에 버전별 성공률, 주요 실패 원인 요약

---

## Phase D – 예측 모델 + SHAP (목표 1.5시간)

**작업**:
```
1. src/analysis/ml_models.py 검토 및 활용:
   - y_grade = ordinal (Certified=1, Silver=2, Gold=3, Platinum=4)
   - y_score = PointsAchieved (회귀)
   - X = project_features의 v5 카테고리별 합계 + floor_area + 버전
   - XGBoost 한 모델만 학습 (시간 절약).
     5-fold CV, random_state=42 고정.
2. src/analysis/xai_shap.py 활용:
   - TreeExplainer
   - Global: summary plot (beeswarm), bar plot
   - Grade별: 각 등급 대표 샘플 2개씩 waterfall
3. 출력:
   - outputs/phase_D/model_metrics.json (R², Accuracy, F1)
   - outputs/phase_D/figs/ : shap_summary.png, shap_bar.png,
     waterfall_<grade>.png, grade_comparison.png
   - outputs/phase_D/shap_values.parquet
   - outputs/phase_D/REPORT.md: 상위 10개 요인 리스트 + 간단 해석
```

**완료 기준**:
- [ ] 모델 성능 리포트 (R² ≥ 0.7, Accuracy ≥ 0.6 정도 기대)
- [ ] SHAP summary plot 생성
- [ ] 등급별 비교 시각화
- [ ] 논문 4장에 바로 쓸 수 있는 figure 4개

---

## Phase E – 논문용 figure & 최종 정리 (목표 1시간)

**작업**:
```
1. outputs/final/ 에 논문 제출 수준 figure 모음:
   - Figure 1: 전체 파이프라인 다이어그램 (graphviz or mermaid)
   - Figure 2: 버전별 프로젝트 분포 (bar)
   - Figure 3: SHAP summary (300dpi)
   - Figure 4: 등급별 주요 요인 비교
   - Table 1: 통합 전/후 데이터셋 스펙
   - Table 2: 모델 성능
   - Table 3: SHAP 상위 10개 요인 (카테고리, 평균 |SHAP|, 방향)

2. outputs/final/paper_draft_section4.md:
   LEEDGRAPH.hwpx 4장·5장에 붙일 본문 이어쓰기
   (패러프레이징 주의, 주관적 표현 지양, 강한 비판 지양)

3. requirements.txt freeze → requirements_frozen.txt
```

**완료 기준**:
- [ ] 논문 직접 쓸 수 있는 figure 4개 + table 3개
- [ ] 본문 이어쓰기 문단 (3~5 문단)
- [ ] requirements freeze

---

## Phase F – README.md 작성 (목표 30분)

**작업**:
```
프로젝트 루트의 README.md 작성 (또는 덮어쓰기):

구조:
# LEEDGRAPH
1. 연구 개요 (3문장 요약)
2. 연구 차별성 표 (기존 vs 본 연구)
3. 파이프라인 다이어그램 (Phase E의 Figure 1)
4. 데이터
   - 원본: 460 scorecards, 456 CSV rows, 22 버전조합
   - 표준화 후: v5 체계, N개 크레딧, M개 카테고리
5. 주요 결과
   - 모델 성능 (표)
   - SHAP 상위 10개 요인 (간단 해설)
6. 실행 방법
   ```bash
   pip install -r requirements_frozen.txt
   python scripts/run_pipeline.py
   python scripts/run_analysis.py
   ```
7. 디렉토리 구조 트리 (find . -maxdepth 2 -type d)
8. 한계 및 향후 과제
9. 라이선스 / 인용 / 연락처

README는 코드 repo 방문자가 "뭔지, 어떻게 돌리는지, 결과 뭐 나왔는지"
5분 안에 파악할 수 있어야 함.
```

**완료 기준**:
- [ ] README.md 루트에 존재
- [ ] 파이프라인 다이어그램 포함
- [ ] 실행 명령어 복붙 가능
- [ ] 주요 결과 수치 1개 이상 노출

---

## 타임박스 요약

| Phase | 작업 | 시간 | 누적 |
|---|---|---|---|
| A | 스모크 테스트 | 0.5h | 0.5h |
| B | v5 매핑 구축 | 1.5h | 2.0h |
| C | 파이프라인 실행 | 1.0h | 3.0h |
| D | 모델 + SHAP | 1.5h | 4.5h |
| E | 논문용 figure | 1.0h | 5.5h |
| F | README.md | 0.5h | 6.0h |

**사전 2~3시간**: Phase B(매핑 규칙)가 가장 오래 걸릴 가능성 ↑.  
여기 초과되면 LLM 폴백 비율 높이고 규칙 최소화로 시간 방어.

---

## 리스크 & 대응

| 리스크 | 대응 |
|---|---|
| rubric_loader xlsx 포맷 제각각 | Phase A에서 포맷별 분기, 최소의 경우 v5만 로드하고 나머지는 scorecard에서 역산성 |
| LLM API 비용/속도 | rule hit rate 70% 이상 유지, 샘플 10개 먼저 돌려서 예상 비용 확인 |
| 미매핑 항목 과다 | "Unknown" 카테고리로 일괄 처리, 논문에 "n% 미매핑, 수동 검토 필요" 명시 |
| Total points 불일치 | 불일치 건 별도 분석 칼럼으로 뺌, 논문 한계점에 언급 |
| 모델 성능 낮음 | XGBoost 기본값 + feature 그대로 써서 "베이스라인" 포지션 취함, 튜닝 X |

---

## 실행 가이드

1. 이 파일을 프로젝트 루트의 `docs/RUBRIC_1DAY.md` 로 저장
2. VSCode Claude Code 세션 첫 메시지:
   ```
   docs/RUBRIC_1DAY.md 읽고 Phase A부터 시작해줘.
   공통 프리앰블 숙지하고, Phase A 완료 기준 다 체크될 때까지만 작업.
   ```
3. 각 Phase 끝나면 REPORT.md 내용만 확인 후 "Phase X 개시" 명령
4. 막히면: "Phase X 완료 기준 중 [항목] 미충족. 이것만 처리해줘."
