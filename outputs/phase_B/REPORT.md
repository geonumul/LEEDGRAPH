# Phase B 리포트 (쉬운 버전)

## Phase B가 뭐였나

버전 간 매핑 규칙(`mapping_rules.yaml`) 구축 + 샘플 10건으로 작동 확인.

---

## 결과 요약

| 항목 | 값 |
|------|-----|
| 매핑 규칙 | **107개** (목표 80 이상 ✅) |
| 샘플 hit rate | **96%** (110/115 크레딧, 목표 70% 이상 ✅) |
| LLM 폴백 경로 작동 | 확인됨 ✅ |

---

## 카테고리별 규칙 수

| 카테고리 | 규칙 수 |
|---------|--------|
| EA (에너지) | 20 |
| MR (재료) | 14 |
| SS (부지) | 13 |
| O+M 전용 | 13 |
| LT (입지/교통) | 12 |
| IEQ/EQ (실내환경) | 18 |
| WE (물) | 9 |
| 폐지 카테고리 (IN/RP) | 4 |
| 약어형 보완 | 3 |
| IP (혁신) | 1 |
| **합계** | **107** |

---

## 샘플 10건 hit rate

| 파일 | 버전 | 크레딧 | 히트 | 히트율 |
|------|------|-------|-----|-------|
| AIA Tower | v4.1 | 15 | 15 | 100% |
| AK Plaza | v4.1 | 15 | 15 | 100% |
| ARC Place | v4.1 | 15 | 15 | 100% |
| ARMY v2009 × 5 | v2009 | 0 | - | N/A (크레딧 상세 없음) |
| ARMY Family Towers | v4 | 35 | 33 | 94% |
| ASMK New MFG | v4 | 35 | 32 | 91% |

**총계**: 110/115 = **96%**

> v2009 PDF는 카테고리 합계만 파싱됨 (크레딧 상세 없음). 파이프라인에 영향 없음.

---

## LLM 폴백 라우팅 확인

드리프트 91%의 합성 케이스를 주입해서 테스트:
```
Rule 매핑 완료: 100.0점
수학 검증: FAILED (drift 91.0%)
라우팅: llm_mapper ✅
```

→ `hallucination_checker → llm_mapper` 분기 정상 작동.

---

## 미매핑 (UNKNOWN) 항목

### 크레딧 레벨 UNKNOWN (2건)
- "Prereq Integrative Project Planning and Design" (v4.1 prereq)
- "Credit: Places of Respite" (희귀 크레딧)

### v2009 카테고리 레벨 (5건)
ARMY v2009 BD+C: 카테고리 합계만 존재, 크레딧 레벨 매핑 불가. 카테고리 비율 환산은 정상.

---

## 수정된 파일

### `data/raw/rubrics/mapping_rules.yaml`
- 초기 91개 → 107개로 확장
- O+M 전용 크레딧 13개 추가 (energy performance 등)
- 약어형 3개 추가 (rainwater mgmt 등)

### `src/langgraph_workflow/nodes.py`
- yaml 로더 추가
- `_lookup_credit_rule()` 헬퍼 함수 추가
- `rule_mapper_node`에 크레딧별 rule 조회 로직 추가
- credit_mappings 리스트 + hit_rate 통계 기록

---

## 다음 단계

이제 Phase C에서 460건 전체 돌려서 parquet 생성.
