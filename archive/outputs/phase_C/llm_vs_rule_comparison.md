# LLM vs Rule 매핑 비교 (쉬운 버전)

## 이 문서가 뭐야

V1 파이프라인 결과에서 **LLM 경로로 간 47건 vs Rule 경로로 간 413건**을 비교. 어떤 건물이 LLM까지 갔고, 결과가 얼마나 달랐는지 분석.

---

## 처리 경로는 어떻게 갈리나?

수학 검증 단계에서 2가지 조건 중 하나라도 실패하면 LLM 경로:
- **drift > 20%**: 원본 달성률과 v5 달성률 차이가 20% 초과
- **카테고리 최대값 초과**: ratio > 1.0

통과하면 Rule 결과 그대로 저장.

---

## 두 경로 비교 통계

| 지표 | Rule 경로 (413건) | LLM 경로 (47건) |
|------|------------------|-----------------|
| drift 평균 | 10.7% | **22.6%** |
| drift 최대 | 19.7% | 48.3% |
| v5 총점 평균 | 46.0 | 37.4 |
| Rule hit rate 평균 | - | ~87% |

→ LLM 경로 건물은 **drift가 구조적으로 큼**. v5 점수도 Rule 경로 대비 낮음.

---

## LLM 경로 47건이 어떤 건물들인가

대부분 **구버전(v2.x, v2009)** + **고급 소매(Prada, Tiffany, Gucci)** + **물류센터(Cheongna, Siheung)**.

| 건물 유형 | 이유 |
|----------|------|
| v2.2 건물 | SS에 교통 포함 → LT 분리 비율 추정 오차 |
| 고급 소매 | LT 비중 높고 EA 낮은 비정형 패턴 |
| 물류센터 | 외곽 위치 + 에너지 집약형 → 구조적 drift |

**최악 케이스**: Gucci Yeoju Premium Outlet (v2.2, Gold) — drift 48.3%, Rule hit rate 11.1% (매핑 실패율 높음).

---

## 어떤 크레딧에서 차이가 발생하나

LLM 경로 건물 47건의 크레딧 매핑 분포:

| v5 카테고리 | 크레딧 수 |
|------------|---------|
| EA (에너지) | 151 (37%) |
| LT (입지/교통) | 68 (17%) |
| EQ (실내환경) | 54 (13%) |
| WE (물) | 48 (12%) |
| MR (재료) | 37 (9%) |
| SS (부지) | 21 (5%) |
| IP (혁신) | 15 (4%) |

매핑 방식: rule 87%, unmatched 13%.

---

## LLM 판단의 타당성

### Case 1: Gucci Yeoju (v2.2, drift 48.3%)
- Rule hit rate 11.1% → 매핑 규칙으로 거의 해결 안 됨
- v2.2는 SS에 교통 포함 → LT 추정 구조적 어려움
- **LLM 개입 타당** (Rule이 잘 안 되는 케이스)

### Case 2: 고급 소매 건물군
- Rule hit rate 87%로 매핑 자체는 잘 됨
- 하지만 건물 특성상 drift 20% 넘음
- LLM 개입해도 drift 해소 한계 (구조적 특성)

### Case 3: 물류센터
- 외곽 위치 → LT 비중 구조적으로 낮음
- drift 20% 넘는 건 v4 체계 자체의 한계

---

## 결론 및 논문 활용

1. **LLM 경로 10.2%는 구조적 엣지 케이스** (구버전 / 비정형 건물 유형)
2. **LLM 개입이 drift를 완전히 해소하진 못함** — v2.2 같은 구조적 한계 존재
3. 논문 표현: "4.2% of samples exceeding the 20% drift threshold were routed through an LLM-based fallback mapper (gpt-4.1) to address structural version incompatibilities."

---

## 주의사항

이 문서는 **V1 파이프라인** 결과 기반. V2(Option A)에서는 LLM이 점수를 바꾸지 않고 검증만 하므로 "LLM 경로" 개념이 달라짐. Option A 분석은 `outputs/phase_D_option_a/shap_comparison.md` 참고.
