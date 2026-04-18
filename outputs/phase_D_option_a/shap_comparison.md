# SHAP Robustness 비교 (Option A, 쉬운 버전)

## 이 문서가 뭐야

"460건 전체에서 EA가 Top이었는데, 다른 subset으로 잘라도 EA가 Top인가?"를 확인한 결과.
여러 subset에서 결과가 일관되면 모델이 **robust** (흔들리지 않음).

---

## Subset별 성능

| Subset | N | CV 정확도 | CV F1 | Top Feature |
|--------|---|----------|------|-------------|
| **전체** | 460 | 0.8152 | 0.8133 | **ratio_EA** |
| credit_hit > 0.7 (신뢰군) | 324 | **0.8333** | 0.8267 | **ratio_EA** |
| 구버전 (v2.0/v2.2/v2009) | 136 | 0.7865 | 0.7794 | **ratio_EA** |
| 신버전 (v4/v4.1) | 324 | **0.8333** | 0.8267 | **ratio_EA** |
| LLM 리뷰된 75건 | 75 | 0.7067 | 0.6694 | **ratio_EA** |

→ **모든 subset에서 Top feature는 EA**. 결과 흔들리지 않음 ✅

---

## Top 5 Feature 순서 비교

| Subset | 1st | 2nd | 3rd | 4th | 5th |
|--------|-----|-----|-----|-----|-----|
| 전체 | EA | EQ | WE | LT | version |
| credit_hit>0.7 | EA | EQ | WE | LT | SS |
| 구버전 | EA | WE | LT | EQ | log_area |
| 신버전 | EA | EQ | WE | LT | SS |
| LLM 리뷰 75 | EA | WE | LT | EQ | log_area |

**관찰**:
- EA는 어디서든 1등
- EQ와 WE가 subset에 따라 2/3위 교체
- 구버전은 EQ 순위가 낮아짐 → **v2.x 시절 실내환경 기준이 달랐음을 시사**

---

## 해석

### Full vs credit_hit > 0.7
Top feature 순서 거의 동일 (EA/EQ/WE/LT). credit_hit 낮은 건물들이 모델에 noise를 주지 않음을 의미.

### 구버전 vs 신버전
- 신버전은 EQ 2위, 구버전은 EQ 4위
- LEED 버전 진화 과정에서 실내환경 기준이 강화됨을 반영
- 그래도 EA 1등은 동일 → 에너지 중심의 LEED 철학은 모든 버전 관통

### LLM 리뷰 75건 subset
샘플이 작지만 Top feature가 전체와 일치 → 리뷰 표본이 대표성 가짐.

---

## 결론

**"EA가 한국 LEED 등급을 결정한다"는 주장은 robust**. 표본을 어떻게 잘라도 바뀌지 않음. 논문 main finding으로 가기 충분.
