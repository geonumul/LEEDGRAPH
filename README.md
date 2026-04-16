# LEEDGRAPH

> Korean LEED-certified building analysis pipeline: multi-version standardization to LEED v5 + XAI (SHAP) for grade determinant factor analysis.

---

## 1. Research Overview

This project analyzes 460 Korean LEED-certified buildings spanning LEED versions v2.0–v4.1. The core contributions are:
1. **Version harmonization**: Proportional-scaling rules (107 rule-based mappings) to unify all versions under the LEED v5 schema.
2. **Grade factor analysis**: XGBoost + SHAP TreeExplainer to identify which categories most influence certification grade.

Key finding: **Energy & Atmosphere (EA)** is the dominant grade determinant (mean |SHAP|=0.8840), followed by **Indoor Env. Quality (EQ)** and **Water Efficiency (WE)**.

---

## 2. Research Differentiators

| Item | Previous Studies | This Study |
|------|-----------------|-----------|
| Version coverage | Single version | v2.0 / v2.2 / v2009 / v4 / v4.1 |
| Standardization | Manual / none | Rule-based proportional scaling to v5 |
| Sample size | < 100 (typical) | **460 Korean buildings** |
| XAI method | Feature importance | SHAP TreeExplainer (credit-level) |
| Focus | Global benchmarks | Korean building stock |

---

## 3. Pipeline Diagram

```
460 PDFs  →  PDF Ingest + CSV Match  →  Rule Mapper (107 rules)
                                              ↓ PASS (100%)
                                       v5 Standardized Scores
                                              ↓
                                       XGBoost + SHAP  →  Grade Determinants
```

See `outputs/final/Figure1_pipeline.png` for the full diagram.

---

## 4. Data

| Item | Detail |
|------|--------|
| Raw scorecards | 460 PDFs (Korean LEED projects) |
| Building directory | PublicLEEDProjectDirectory.csv (456 rows) |
| LEED versions | v2.0, v2.2, v2009 (v3), v4, v4.1 |
| Post-standardization | v5 schema, 9,747 credit records, 7 categories |
| Grade distribution | Gold 235 (51%) / Silver 118 (26%) / Platinum 56 (12%) / Certified 51 (11%) |

---

## 5. Key Results

### Model Performance (XGBoost, 5-Fold CV)

| Metric | Value |
|--------|-------|
| CV Accuracy | **0.8174 ± 0.0502** |
| CV Weighted F1 | **0.8157 ± 0.0504** |
| Features | 9 (ratio_EA/LT/MR/EQ/WE/SS/IP + log_area + version) |

### SHAP Top-5 Grade Determinants

| Rank | Category | Mean ㅣSHAPㅣ |
|------|----------|------------|
| 2 | Energy & Atmosphere (EA) | 0.8840 |
| 3 | Indoor Env. Quality (EQ) | 0.6533 |
| 4 | Water Efficiency (WE) | 0.5895 |
| 5 | Location & Transportation (LT) | 0.4377 |
| 6 | LEED Version | 0.2880 |

---

## 6. Quickstart

```bash
pip install -r requirements_frozen.txt

# Step 1: Run full pipeline (PDF → standardized parquet)
python scripts/run_pipeline.py

# Step 2: Run XGBoost + SHAP analysis
python scripts/run_analysis.py
```

---

## 7. Directory Structure

```
LEEDGRAPH/
├── data/
│   ├── raw/
│   │   ├── scorecards/          # 460 PDF scorecards
│   │   ├── buildings_list/      # PublicLEEDProjectDirectory.csv
│   │   └── rubrics/             # LEED rubric xlsx + mapping_rules.yaml
│   └── processed/
│       ├── project_features.parquet   # ML input (460 × 28)
│       └── standardized_credits.parquet  # 9,747 credit-level records
├── src/
│   ├── data/
│   │   ├── loader.py            # PDF + CSV parser
│   │   └── rubric_loader.py     # Rubric xlsx loader
│   ├── langgraph_workflow/
│   │   ├── state.py             # LangGraph state
│   │   ├── nodes.py             # Pipeline nodes (rule mapper, hallucination checker)
│   │   └── graph.py             # LangGraph graph definition
│   └── analysis/
│       ├── ml_models.py         # ML training utilities
│       └── xai_shap.py          # SHAP analysis utilities
├── scripts/
│   ├── run_pipeline.py          # Phase C: full pipeline runner
│   └── run_analysis.py          # Phase D: XGBoost + SHAP
├── outputs/
│   ├── phase_A/ ~ phase_D/      # Phase-wise reports
│   └── final/                   # Paper-ready figures & tables
├── docs/
│   └── RUBRIC_1DAY.md           # 1-day sprint plan
└── requirements_frozen.txt
```

---

## 8. Limitations & Future Work

- **10.2% high-drift cases** (47 buildings): Newly certified LEED v5 buildings with uncertain version detection. Standardization results carry higher uncertainty for these.
- **12% unmatched credits**: Credit names not covered by mapping rules (primarily v5-format PDFs and rare credits).
- **Model overfitting on training data**: CV accuracy 82.4% is reliable; train accuracy 100% reflects memorization — future work should use a holdout test set.
- **v2009 credit-level data unavailable**: Only category totals parsed; credit-level SHAP analysis excluded for these 114 buildings.

Future directions: expand mapping rules for v5 native buildings, incorporate building-level metadata (location, program type) as additional features.

---

## 9. License / Citation / Contact

- Data: USGBC Public LEED Project Directory (public domain)
- Code: MIT License
- Contact: geonumul (GitHub)
