# Phase A 리포트 (쉬운 버전)

## Phase A가 뭐였나

본격 작업 전 **최소 구성 5개 PDF로 파이프라인 작동 확인** (smoke test).

---

## 체크 결과

| 항목 | 결과 |
|------|------|
| 5개 PDF 파싱 | ✅ (version, cert_level, categories 정상 추출) |
| CSV 매칭 | ✅ 5/5 (건물명 or ID 기반) |
| 루브릭 xlsx 로드 (v5, v4) | ✅ |
| graph.py 임포트 | ✅ (circular import 없음) |

---

## 루브릭 로딩

총 15개 파일 로딩 성공:
- v4: 9개
- v4.1: 2개
- v5: 4개 (BDC_NC / BDC_CS / IDC / OM)

**v5 만점 분포** (모두 100pt):
- **BDC_NC**: IP=1, LT=15, SS=11, WE=9, EA=33, MR=18, EQ=13
- BDC_CS: (IP 파싱 오류, 나머지 정상)
- IDC: IP=1, LT=14, WE=10, EA=31, MR=26, EQ=18 (SS 없음)
- OM: IP=2, LT=8, SS=2, WE=15, EA=34, MR=13, EQ=26

---

## 5개 PDF 테스트 결과

| 건물 | 버전 | 경로 | v5 점수 | drift |
|------|------|------|--------|-------|
| adidas Flagship Seoul | v4 ID+C | Rule | 48.34 | 13.8% |
| adidas Hongdae | v4 ID+C | Rule | 51.02 | 18.4% |
| Adidas Warehouse | v4 BD+C | Rule | 51.10 | 8.4% |
| AIA Tower | v4.1 BD+C | Rule | 71.45 | 7.2% |
| AK Plaza Gwang-Myeong | v4.1 BD+C | Rule | 65.29 | 5.5% |

모두 Rule 경로 정상 통과, drift 20% 이내.

---

## 수정된 파일 (주요 변경)

### `src/langgraph_workflow/nodes.py` — v5 만점 테이블 분리

**기존**: 단일 `V5_MAX` (IEQ 포함, IN/RP 포함, 총점 110)

**변경**:
- `V5_MAX_BDC` (100pt, EQ 코드)
- `V5_MAX_IDC` (100pt, SS 없음)
- `V5_MAX_OM` (100pt)
- `_get_v5_max(leed_system)` 헬퍼 함수
- IN/RP는 v5에서 폐지 → `dropped_categories`에 기록
- IEQ → EQ 코드로 바뀜

### `src/data/rubric_loader.py`
- `_parse_v5_rubric_xlsx()` 추가 (v5 xlsx 별도 파싱)
- 폴더명 기반 rating system 구분

---

## 잔여 이슈 (Phase B로)

1. **BDC_CS v5 IP=7 파싱 오류**: xlsx 헤더 구조 달라서. `_get_v5_max()`는 hardcoded라 파이프라인에 영향 없음.
2. **v4 BD+C MR 누락**: xlsx에서 MR이 파싱 안 됨 → PDF 값으로 대체.
3. **O+M 만점이 BD+C와 다름**: `categories_possible` 우선 참조로 자동 보정.
