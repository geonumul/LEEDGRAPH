"""
Option A 기반 재분석:
  1. credit_hit 기준 uncertainty 3분류 → SHAP 결과 비교
  2. 구버전(v2.x, v2009) vs 신버전(v4, v4.1) separate SHAP
  3. LLM 리뷰 subset vs 미리뷰 subset 비교

출력:
  outputs/phase_D_option_a/
    model_metrics.json
    shap_comparison.md
    figs/shap_full.png
    figs/shap_certain_only.png        (credit_hit > 0.7)
    figs/shap_old_versions.png        (v2.x, v2009)
    figs/shap_new_versions.png        (v4, v4.1)
    figs/shap_llm_reviewed.png        (has_llm_review=True)
"""

import sys
import json
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
warnings.filterwarnings("ignore")

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import shap
import xgboost as xgb
from sklearn.model_selection import StratifiedKFold, cross_val_score
from sklearn.metrics import accuracy_score, f1_score, classification_report
from sklearn.preprocessing import LabelEncoder

PARQUET = Path("data/processed/project_features_option_a.parquet")
OUT_DIR = Path("outputs/phase_D_option_a")
FIG_DIR = OUT_DIR / "figs"
OUT_DIR.mkdir(parents=True, exist_ok=True)
FIG_DIR.mkdir(parents=True, exist_ok=True)

GRADE_ORDER = ["Certified", "Silver", "Gold", "Platinum"]
FEATURE_COLS = [
    "ratio_LT", "ratio_SS", "ratio_WE", "ratio_EA",
    "ratio_MR", "ratio_EQ", "ratio_IP",
]


def prepare_xy(df):
    """X, y 준비. ratio_SS NaN은 0으로 채움 (v2009/v2.2 특성)."""
    # version ordinal
    ver_map = {"v2.0": 0, "v2.2": 1, "v2009": 2, "v4": 3, "v4.1": 4}
    df = df.copy()
    df["version_ord"] = df["original_version"].map(ver_map)
    df["log_area"] = np.log1p(df["gross_area_sqm"].fillna(0))

    cols = FEATURE_COLS + ["log_area", "version_ord"]
    X = df[cols].fillna(0)

    le = LabelEncoder()
    le.fit(GRADE_ORDER)
    y = le.transform(df["certification_level"])

    return X, y, le


def train_and_shap(X, y, label):
    """모델 학습 + CV + SHAP. 지표 dict + shap_values 반환."""
    model = xgb.XGBClassifier(
        n_estimators=200, max_depth=6, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8,
        random_state=42, eval_metric="mlogloss", verbosity=0,
    )
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)

    cv_acc = cross_val_score(model, X, y, cv=cv, scoring="accuracy")
    cv_f1 = cross_val_score(model, X, y, cv=cv, scoring="f1_weighted")

    model.fit(X, y)

    # SHAP
    expl = shap.TreeExplainer(model)
    sv = expl.shap_values(X)
    if isinstance(sv, np.ndarray) and sv.ndim == 3:
        sv = [sv[:, :, c] for c in range(sv.shape[2])]

    # 각 클래스 mean(|SHAP|) 평균
    mean_abs = np.abs(np.stack(sv, axis=0)).mean(axis=(0, 1))

    top_feat = pd.Series(mean_abs, index=X.columns).sort_values(ascending=False)

    return {
        "label": label,
        "n_samples": int(len(y)),
        "cv_accuracy_mean": round(float(cv_acc.mean()), 4),
        "cv_accuracy_std": round(float(cv_acc.std()), 4),
        "cv_f1_weighted_mean": round(float(cv_f1.mean()), 4),
        "cv_f1_weighted_std": round(float(cv_f1.std()), 4),
        "top_features": top_feat.to_dict(),
    }, sv, X


def plot_shap_bar(sv, X, title, out_path):
    """SHAP bar plot."""
    fig, ax = plt.subplots(figsize=(8, 5), dpi=150)
    mean_abs = np.abs(np.stack(sv, axis=0)).mean(axis=(0, 1))
    order = np.argsort(mean_abs)[::-1]
    feats = [X.columns[i] for i in order]
    vals = [mean_abs[i] for i in order]
    ax.barh(feats[::-1], vals[::-1], color="#1976D2")
    ax.set_xlabel("Mean |SHAP|")
    ax.set_title(title)
    plt.tight_layout()
    plt.savefig(out_path)
    plt.close()
    print(f"  Saved: {out_path}")


def main():
    print("=" * 70)
    print("  Option A 재분석 (SHAP 비교)")
    print("=" * 70)

    df = pd.read_parquet(PARQUET)
    print(f"전체: {len(df)}건\n")

    results = []

    # ─── [1] 전체 460건 ─────────────────────────────────────────────────
    print("[1] 전체 460건")
    mask_full = df["certification_level"].notna() & (df["certification_level"] != "")
    X, y, le = prepare_xy(df[mask_full])
    m, sv, Xp = train_and_shap(X, y, "full_460")
    print(f"  n={m['n_samples']}, CV Acc={m['cv_accuracy_mean']:.4f}, CV F1={m['cv_f1_weighted_mean']:.4f}")
    print(f"  Top feature: {list(m['top_features'])[0]} ({list(m['top_features'].values())[0]:.4f})")
    plot_shap_bar(sv, Xp, "SHAP: 전체 460건", FIG_DIR / "shap_full.png")
    results.append(m)

    # ─── [2] credit_hit > 0.7 (certain only) ────────────────────────────
    print("\n[2] credit_hit > 0.7 (LLM 승인 경향군)")
    mask_certain = mask_full & (df["credit_rule_hit_rate"].fillna(0) > 0.7)
    X, y, le = prepare_xy(df[mask_certain])
    m, sv, Xp = train_and_shap(X, y, "certain_hit>0.7")
    print(f"  n={m['n_samples']}, CV Acc={m['cv_accuracy_mean']:.4f}, CV F1={m['cv_f1_weighted_mean']:.4f}")
    plot_shap_bar(sv, Xp, "SHAP: credit_hit > 0.7", FIG_DIR / "shap_certain_only.png")
    results.append(m)

    # ─── [3] 구버전 (v2.0, v2.2, v2009) ─────────────────────────────────
    print("\n[3] 구버전 (v2.0, v2.2, v2009)")
    mask_old = mask_full & df["original_version"].isin(["v2.0", "v2.2", "v2009"])
    X, y, le = prepare_xy(df[mask_old])
    m, sv, Xp = train_and_shap(X, y, "old_versions")
    print(f"  n={m['n_samples']}, CV Acc={m['cv_accuracy_mean']:.4f}, CV F1={m['cv_f1_weighted_mean']:.4f}")
    plot_shap_bar(sv, Xp, "SHAP: 구버전 (v2.x, v2009)", FIG_DIR / "shap_old_versions.png")
    results.append(m)

    # ─── [4] 신버전 (v4, v4.1) ──────────────────────────────────────────
    print("\n[4] 신버전 (v4, v4.1)")
    mask_new = mask_full & df["original_version"].isin(["v4", "v4.1"])
    X, y, le = prepare_xy(df[mask_new])
    m, sv, Xp = train_and_shap(X, y, "new_versions")
    print(f"  n={m['n_samples']}, CV Acc={m['cv_accuracy_mean']:.4f}, CV F1={m['cv_f1_weighted_mean']:.4f}")
    plot_shap_bar(sv, Xp, "SHAP: 신버전 (v4, v4.1)", FIG_DIR / "shap_new_versions.png")
    results.append(m)

    # ─── [5] LLM 리뷰됨 75건만 ──────────────────────────────────────────
    print("\n[5] LLM 리뷰된 75건")
    mask_rev = mask_full & (df["has_llm_review"] == True)
    X, y, le = prepare_xy(df[mask_rev])
    m, sv, Xp = train_and_shap(X, y, "llm_reviewed_75")
    print(f"  n={m['n_samples']}, CV Acc={m['cv_accuracy_mean']:.4f}, CV F1={m['cv_f1_weighted_mean']:.4f}")
    plot_shap_bar(sv, Xp, "SHAP: LLM 리뷰된 75건", FIG_DIR / "shap_llm_reviewed.png")
    results.append(m)

    # ─── 저장 ───────────────────────────────────────────────────────────
    with open(OUT_DIR / "model_metrics.json", "w", encoding="utf-8") as f:
        json.dump({"subsets": results}, f, ensure_ascii=False, indent=2)
    print(f"\nmetrics saved: {OUT_DIR / 'model_metrics.json'}")

    # 비교 리포트
    md = ["# SHAP Robustness 비교 (Option A)", "", "## Subset 성능 비교", "",
          "| Subset | N | CV Acc | CV F1 | Top Feature |",
          "|--------|---|--------|-------|-------------|"]
    for r in results:
        top = list(r["top_features"])[0]
        md.append(f"| {r['label']} | {r['n_samples']} | "
                  f"{r['cv_accuracy_mean']:.4f} | "
                  f"{r['cv_f1_weighted_mean']:.4f} | "
                  f"{top} |")

    md += ["", "## Top 5 Feature 일관성", ""]
    md.append("| Subset | 1st | 2nd | 3rd | 4th | 5th |")
    md.append("|--------|-----|-----|-----|-----|-----|")
    for r in results:
        tops = list(r["top_features"])[:5]
        md.append(f"| {r['label']} | " + " | ".join(tops) + " |")

    md += ["", "## 해석", "",
           "- **Full vs Certain**: Top feature 순서가 일치하면 robustness 확보. 즉 credit_hit<0.7인 건물의 noise 영향 제한적.",
           "- **Old vs New**: 구버전/신버전 SHAP이 다르면, LEED 버전 전환 자체가 등급 결정 로직에 영향. 유사하면 표준화 방법론 타당.",
           "- **LLM reviewed subset**: 75건은 샘플이지만 Top feature가 전체와 일치하면 리뷰 표본 대표성 확인."]

    (OUT_DIR / "shap_comparison.md").write_text("\n".join(md), encoding="utf-8")
    print(f"comparison saved: {OUT_DIR / 'shap_comparison.md'}")


if __name__ == "__main__":
    main()
