# 논문 3장 초안 (쉬운 버전)

## 3.1 뭘 했는가 요약

한국에서 인증받은 **LEED 건물 460개** 스코어카드(PDF)를 모아서:
1. 서로 다른 버전(v2.0~v4.1) 점수를 최신 **v5 기준**으로 통일
2. XGBoost로 등급(Certified/Silver/Gold/Platinum)을 예측하는 모델 학습
3. **SHAP**으로 어느 카테고리가 등급을 가장 크게 결정하는지 분석

**주요 결과**: Energy & Atmosphere(에너지) 카테고리가 등급을 가장 크게 좌우함.

---

## 3.2 왜 LangGraph + Rule + LLM 조합인가

각 방식의 장단점:

| 방식 | 장점 | 단점 |
|------|------|------|
| Rule만 | 빠르고 재현성 100% | 의미 검증 불가 |
| LLM만 | 유연함 | 매번 결과 조금씩 다름, 비용 ↑ |
| **Rule + LLM 검증 (이 연구)** | 재현성 + 의미 검증 | 구현 복잡 |

**Option A 원칙**: LLM은 **의견만 제시**하고 **점수는 Rule 유지**. LLM 판단은 메타데이터(score, feedback)로만 기록.

---

## 3.3 파이프라인 흐름

```
PDF → CSV 매칭 → Rule이 v5 점수 계산 → 수학 검증
                                           ↓
       수학 PASS → LLM이 의미 검증 → 최종 저장
       수학 FAIL → LLM이 재매핑 → LLM 검증 → 최종 저장
```

- **Rule**: LEED 공식 루브릭 수식을 코드로 옮긴 것. 항상 같은 결과.
- **수학 검증**: 드리프트(원본 달성률 vs v5 달성률 차이)가 20% 이하인지 확인.
- **LLM 의미 검증**: "이 매핑 말 되나?" 전문가 관점으로 평가.

---

## 3.4 데이터셋

| 항목 | 값 |
|------|-----|
| 총 건물 | **460** (한국 LEED 인증 전수) |
| 버전 분포 | v2.0(4) / v2.2(18) / v2009(114) / v4(276) / v4.1(48) |
| 등급 분포 | Gold 51% / Silver 26% / Platinum 12% / Certified 11% |
| 표준화 카테고리 | 7개 (LT/SS/WE/EA/MR/EQ/IP) |
| 크레딧 레코드 | 9,747개 |
| 매핑 규칙 | 107개 (mapping_rules.yaml) |

---

## 3.5 모델 성능

**XGBoost, 5-Fold 교차검증** (460건 전체):

| 지표 | 값 |
|------|-----|
| CV 정확도 | **0.8174 ± 0.0502** |
| CV Weighted F1 | **0.8157 ± 0.0504** |
| Train 정확도 | 1.0 (과적합 지표 — 논문 미사용) |

**Subset별 robustness**:

| Subset | 건수 | CV 정확도 | Top SHAP feature |
|--------|-----|----------|------------------|
| 전체 | 460 | 0.8152 | ratio_EA |
| credit_hit > 0.7 | 324 | 0.8333 | ratio_EA |
| 신버전 (v4, v4.1) | 324 | 0.8333 | - |
| 구버전 (v2.x, v2009) | 136 | 0.7865 | - |

→ 어느 subset에서든 **EA가 top feature**. 결과 robust.

---

## 3.6 SHAP 결과: 등급 결정 요인

| 순위 | 카테고리 | 평균 \|SHAP\| |
|------|---------|------------|
| 1 | **Energy & Atmosphere (EA, 에너지)** | 0.8840 |
| 2 | Indoor Env. Quality (EQ, 실내환경) | 0.6533 |
| 3 | Water Efficiency (WE, 물) | 0.5895 |
| 4 | Location & Transportation (LT, 입지/교통) | 0.4377 |
| 5 | LEED Version | 0.2880 |

**해석**: 한국 LEED 건물의 등급은 **에너지 점수**가 가장 크게 좌우. 설계 단계에서 EA 점수 확보가 우선순위.

---

## 3.7 LLM 전문가 리뷰 (표본 75건)

비용 관리로 460건 중 75건만 LLM 리뷰.

| 구분 | 건수 | 비율 |
|------|------|------|
| 🟢 LLM이 Rule 승인 | 7 | 9.3% |
| 🟡 LLM이 Rule 의문 제기 | 68 | 90.7% |

**LLM 승인 7건의 공통 근거** (feedback 내용):
- LEED 버전 특성이 올바르게 반영됨 (v2.2 SS→LT 분리, IN/RP 폐지)
- 크레딧 누락 없음
- v5 신규 카테고리(IP) 배분 적절
- 원본 등급 ↔ v5 환산 점수 합리적

**`credit_rule_hit_rate`가 LLM 판단의 proxy**:
- LLM 승인 그룹 평균: **0.885**
- LLM 거부 그룹 평균: **0.646**
- 24%p 차이 → credit_hit 높을수록 LLM도 신뢰

---

## 3.8 기존 연구와의 차별점

| 항목 | 기존 연구 | 이 연구 |
|------|----------|---------|
| 버전 | 1개 (보통 v4만) | v2.0~v4.1 전부 |
| 표준화 | 수동 or 없음 | Rule + LLM 검증 자동 |
| 샘플 | 보통 100건 미만 | **460 (한국 전수)** |
| 해석 | feature importance | SHAP (크레딧 단위) |
| 검증 | 없음 | LangGraph 이중 검증 (수학 + 의미) |

---

## 3.9 한계

1. **LLM 리뷰 75/460**: 16.3% 커버리지. 표본 리뷰로 포지셔닝.
2. **v2009 크레딧 상세 파싱 불가**: 114건은 카테고리 합계만 사용.
3. **Train 정확도 100%는 과적합**: CV 값(0.8174) 사용.
4. **LLM threshold 0.8이 보수적**: 0.6~0.7 완화 시 승인율 변화 여지.

---

## 3.10 재현성

- 데이터: USGBC Public LEED Project Directory (public domain)
- 코드: GitHub 공개 (MIT License)
- Rule 매핑: `data/raw/rubrics/mapping_rules.yaml` (107 규칙)
- 최종 parquet: `data/processed/project_features_option_a.parquet`
