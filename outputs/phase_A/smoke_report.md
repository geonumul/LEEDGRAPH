# Phase A – 스모크 테스트 리포트

## 완료 기준 체크

- [x] loader.py로 5개 PDF → merged DataFrame 출력 확인
- [x] rubric_loader.py로 v5 + v4 xlsx 각 1개 로드 성공
- [x] 11개 txt rubric 처리 전략 확정
- [x] graph.py 임포트 OK

## 결과 요약

### loader.py
- 5개 PDF 파싱 성공 (version, cert_level, categories, credits 정상 추출)
- CSV 매칭: 5/5 성공 (ID 또는 건물명 기반)

### rubric_loader.py
- 총 15개 파일 로딩 (v4: 9개, v4.1: 2개, v5: 4개)
- v5 별도 파서(`_parse_v5_rubric_xlsx`) 추가로 4개 파일 정상 파싱
  - BDC_NC: IP=1, LT=15, SS=11, WE=9, EA=33, MR=18, EQ=13 → 100pt
  - BDC_CS: IP=7(파싱 아티팩트), LT=15, SS=11, WE=8, EA=27, MR=21, EQ=11 → 100pt
  - IDC: IP=1, LT=14, WE=10, EA=31, MR=26, EQ=18 → 100pt
  - OM: IP=2, LT=8, SS=2, WE=15, EA=34, MR=13, EQ=26 → 100pt

### 11개 txt rubric 처리 전략 (확정)
- 해당 (version, rating_system) 조합의 스코어카드 PDF에서 파싱된 값을 그대로 사용
- `categories_possible` 필드로 만점 보존, rule_mapper의 `get_old_max()` 우선 참조

### graph.py
- import OK, circular import 없음

## 수정된 파일

### nodes.py – V5_MAX 전면 교체
- 기존: 단일 `V5_MAX` 딕셔너리 (IEQ 포함, IN/RP 포함, 총점 110)
- 변경: rating system별 3개 딕셔너리 + `_get_v5_max()` 헬퍼
  - `V5_MAX_BDC`: 총점 100, EQ 코드 사용
  - `V5_MAX_IDC`: 총점 100, SS 없음
  - `V5_MAX_OM`: 총점 100
- IN/RP: v5 폐지 → `dropped_categories`에 기록, mapped에 미포함
- IEQ → EQ 코드 변경
- hallucination_checker: 110 고정값 → `sum(v5_max.values())` 동적 계산

### rubric_loader.py
- `_parse_v5_rubric_xlsx()` 추가 (v5 xlsx의 credit category view 시트 파싱)
- 폴더명 기반 rating system 키 적용 (파일명 중복 문제 해소)

## 파이프라인 테스트 결과 (샘플 5개)

| 파일 | 버전 | 경로 | v5 총점 | drift |
|------|------|------|---------|-------|
| adidasBrandFlagshipSeoul | v4 ID+C | RULE PASS | 48.34/100 | 13.8% |
| AdidasHongdaeBrandCenter | v4 ID+C | RULE PASS | 51.02/100 | 18.4% |
| AdidasWarehouse | v4 BD+C | RULE PASS | 51.10/100 | 8.4% |
| AIATower | v4.1 BD+C | RULE PASS | 71.45/100 | 7.2% |
| AKPlazaGwang-Myeong | v4.1 BD+C | RULE PASS | 65.29/100 | 5.5% |

모두 rule 경로 통과, drift 20% 이내.

## 잔여 이슈 (Phase B로 이월)

1. **BDC_CS v5 IP=7 파싱 오류**: Core and Shell xlsx의 헤더 구조가 달라 IP 점수가 7로 잘못 파싱됨.
   → `_get_v5_max()`는 hardcoded 값을 사용하므로 파이프라인에 영향 없음. rubric_loader 보정은 후순위.
2. **v4 BD+C 루브릭 MR 누락**: xlsx에서 MR이 파싱 안 됨 → `categories_possible` PDF 파싱값으로 대체됨.
3. **O+M v4.1 이상값** (EA=100, LT=22): O+M 체계 특성으로 실제 만점이 BD+C와 다름.
   → `categories_possible` 우선 참조로 자동 보정.
