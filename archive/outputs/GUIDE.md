# outputs/ 폴더 가이드

이 폴더는 분석 결과물이 담긴 곳. 어디에 뭐가 있는지 한눈에 보는 용.

---

## 📁 폴더별 역할 (시간 순서)

| 폴더 | 뭐가 있나 | 단계 |
|------|----------|------|
| `phase_A/` | 5개 PDF로 파이프라인 작동 확인 | smoke test |
| `phase_B/` | 매핑 규칙 107개 구축 + 10건 샘플 검증 | 규칙 설계 |
| `phase_C/` | 460건 전체 파이프라인 실행 결과 | V1 전수 실행 |
| `phase_D/` | XGBoost + SHAP 분석 (460건) | 기본 분석 |
| `phase_E/` | V2 파이프라인 75건 실행 + 체크포인트 | LLM 검증 추가 |
| `phase_D_option_a/` | Option A Robustness SHAP 비교 | 재분석 |
| **`final/`** | **논문에 바로 들어갈 figure + table** | **최종 산출물** |
| `reports/` | 논문 방법론 초안 md | 서술 |
| `figures/` | (사용 안 함 - 비어있음) | - |

---

## 📄 핵심 파일 목록 (가장 중요한 것만)

### 논문에 들어갈 것 (`outputs/final/`)

| 파일 | 내용 |
|------|------|
| `Figure1_pipeline.png` | V1 파이프라인 다이어그램 |
| `Figure_pipeline_v2.png` | V2 파이프라인 다이어그램 (LLM 검증 추가) |
| `Figure2_version_dist.png` | 버전별 분포 |
| `Figure3_shap_summary.png` | SHAP summary plot |
| `Figure4_grade_factors.png` | 등급별 카테고리 달성률 |
| `Table1_dataset_spec.csv` | 데이터셋 사양 |
| `Table2_model_performance.csv` | 모델 성능 |
| `Table3_shap_top10.csv` | SHAP Top 10 |
| `Table_validation_summary.csv` | V2 버전별 검증 통계 |
| `paper_draft_section4.md` | **논문 4장 초안** |

### 방법론 서술 초안

- `reports/methodology_summary.md` — 논문 3장 초안

### 상세 리포트

- `phase_C/REPORT.md` — 460건 처리 결과
- `phase_C/llm_vs_rule_comparison.md` — LLM 경로 vs Rule 경로 비교
- `phase_D/REPORT.md` — SHAP 기본 분석
- `phase_D_option_a/shap_comparison.md` — Subset별 robustness 비교
- `phase_E/validation_batch_10_summary.md` — 10건 배치 요약

---

## 🎯 논문 쓸 때 어떤 순서로 보면 좋은가

1. `README.md` (루트) — 프로젝트 전체 개요
2. `outputs/reports/methodology_summary.md` — 3장 방법론 자료
3. `outputs/final/paper_draft_section4.md` — 4장 본문 초안
4. `outputs/final/Figure*.png` + `Table*.csv` — 도표 삽입용
5. `docs/IMPLEMENTATION_V2.md` — 심사 질문 대비 + 구현 상세

---

## 📝 데이터셋 파일 (`data/processed/`)

| 파일 | 행수 | 용도 |
|------|-----|------|
| `project_features.parquet` | 460 | V1 기본 — ML 학습에 사용 |
| `project_features_v2.parquet` | 75 | V2 LLM 재매핑 결과 (참고용, 안 씀) |
| `project_features_option_a.parquet` | 460 | **Option A 최종 (Rule 점수 + LLM 리뷰 메타)** |
| `standardized_credits.parquet` | 9,747 | 크레딧 단위 상세 |
| `standardized_credits_v2.parquet` | 1,650 | V2 파티션 (참고용) |
