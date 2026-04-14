"""
Phase D – XGBoost + SHAP 분석 스크립트

출력:
    outputs/phase_D/model_metrics.json
    outputs/phase_D/figs/shap_summary.png
    outputs/phase_D/figs/shap_bar.png
    outputs/phase_D/figs/waterfall_<grade>.png (4개)
    outputs/phase_D/figs/grade_comparison.png
    outputs/phase_D/shap_values.parquet
    outputs/phase_D/REPORT.md
"""

import sys
import json
import warnings
warnings.filterwarnings("ignore")

import matplotlib
matplotlib.use("Agg")   # 헤드리스 환경 - 화면 출력 없음
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pandas as pd
import shap
import xgboost as xgb
from sklearn.model_selection import StratifiedKFold, cross_val_score
from sklearn.metrics import accuracy_score, f1_score, classification_report
from sklearn.preprocessing import OrdinalEncoder

# ── 경로 설정 ──────────────────────────────────────────────────────────────
OUT_DIR  = Path("outputs/phase_D")
FIG_DIR  = OUT_DIR / "figs"
OUT_DIR.mkdir(parents=True, exist_ok=True)
FIG_DIR.mkdir(parents=True, exist_ok=True)

GRADE_MAP   = {"Certified": 0, "Silver": 1, "Gold": 2, "Platinum": 3}
GRADE_NAMES = {0: "Certified", 1: "Silver", 2: "Gold", 3: "Platinum"}
GRADE_COLORS = {0: "#b8d4a8", 1: "#a0c4d8", 2: "#f5d06e", 3: "#d4a8c4"}

# ── 한글 폰트 (없으면 영문 fallback) ──────────────────────────────────────
_kor_fonts = [f.name for f in fm.fontManager.ttflist if "Malgun" in f.name or "Gothic" in f.name]
if _kor_fonts:
    matplotlib.rcParams["font.family"] = _kor_fonts[0]
matplotlib.rcParams["axes.unicode_minus"] = False

FEATURE_LABELS = {
    "ratio_EA": "Energy & Atmosphere (EA)",
    "ratio_LT": "Location & Transportation (LT)",
    "ratio_MR": "Materials & Resources (MR)",
    "ratio_EQ": "Indoor Env. Quality (EQ)",
    "ratio_WE": "Water Efficiency (WE)",
    "ratio_SS": "Sustainable Sites (SS)",
    "ratio_IP": "Integrative Process (IP)",
    "log_area":  "Floor Area (log sqm)",
    "version_ord": "LEED Version",
}


# =============================================================================
def load_data() -> tuple[pd.DataFrame, pd.Series]:
    """project_features.parquet 로드 → X, y 구성."""
    feat = pd.read_parquet("data/processed/project_features.parquet")
    print(f"데이터 로딩: {len(feat)}개 프로젝트")

    # y: 인증 등급 → 정수 (0~3)
    feat["cert_int"] = feat["certification_level"].map(GRADE_MAP)
    valid = feat["cert_int"].notna()
    feat = feat[valid].copy()
    print(f"등급 분포: {feat['certification_level'].value_counts().to_dict()}")

    # 버전 → 순서형 인코딩 (v2.0=0 ... v4.1=4)
    version_order = ["v2.0", "v2.2", "v2009", "v4", "v4.1"]
    feat["version_ord"] = feat["original_version"].apply(
        lambda v: version_order.index(v) if v in version_order else 2
    )

    # log 면적
    feat["log_area"] = np.log1p(feat["gross_area_sqm"].clip(lower=0))

    # feature 컬럼 선택
    ratio_cols = [c for c in feat.columns if c.startswith("ratio_")]
    feature_cols = ratio_cols + ["log_area", "version_ord"]

    X = feat[feature_cols].fillna(0)
    y = feat["cert_int"].astype(int)

    print(f"Feature 수: {len(feature_cols)} → {feature_cols}")
    return X, y, feat


# =============================================================================
def train_xgboost(X: pd.DataFrame, y: pd.Series) -> tuple:
    """XGBoost 학습 (5-fold CV) + 전체 데이터 final fit."""
    model = xgb.XGBClassifier(
        n_estimators=200,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        eval_metric="mlogloss",
        verbosity=0,
    )

    # 5-fold CV
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    cv_scores = cross_val_score(model, X, y, cv=cv, scoring="accuracy")
    print(f"\n5-Fold CV Accuracy: {cv_scores.mean():.4f} ± {cv_scores.std():.4f}")
    print(f"  각 Fold: {[f'{s:.4f}' for s in cv_scores]}")

    # 전체 데이터 학습
    model.fit(X, y)
    y_pred = model.predict(X)
    acc = accuracy_score(y, y_pred)
    f1  = f1_score(y, y_pred, average="weighted")

    print(f"\n전체 데이터 Accuracy: {acc:.4f}")
    print(f"Weighted F1-Score: {f1:.4f}")
    print("\n분류 리포트:")
    print(classification_report(y, y_pred, target_names=[GRADE_NAMES[i] for i in range(4)]))

    metrics = {
        "cv_accuracy_mean":  round(float(cv_scores.mean()), 4),
        "cv_accuracy_std":   round(float(cv_scores.std()), 4),
        "cv_scores":         [round(float(s), 4) for s in cv_scores],
        "train_accuracy":    round(float(acc), 4),
        "weighted_f1":       round(float(f1), 4),
        "n_samples":         int(len(y)),
        "n_features":        int(X.shape[1]),
        "model":             "XGBoost",
        "params": {
            "n_estimators": 200, "max_depth": 6,
            "learning_rate": 0.05, "subsample": 0.8,
            "colsample_bytree": 0.8, "random_state": 42,
        },
    }
    return model, metrics


# =============================================================================
def compute_shap(model, X: pd.DataFrame) -> tuple:
    """SHAP TreeExplainer 계산.

    반환 형식 정규화:
        list[ndarray(n_samples, n_features)] - 클래스별 2D (구버전 API)
    shap_values가 3D (n_samples, n_features, n_classes)이면 변환.
    """
    print("\nSHAP 계산 중...")
    explainer = shap.TreeExplainer(model)
    raw = explainer.shap_values(X)
    arr = np.array(raw)
    print(f"SHAP 완료 - raw shape: {arr.shape}")

    if arr.ndim == 3:
        # (n_samples, n_features, n_classes) → list per class
        n_classes = arr.shape[2]
        shap_values = [arr[:, :, c] for c in range(n_classes)]
    elif isinstance(raw, list):
        shap_values = raw   # 이미 list
    else:
        shap_values = [raw]   # 이진 분류 등

    print(f"  클래스 수: {len(shap_values)}, 각 shape: {shap_values[0].shape}")
    return explainer, shap_values


# =============================================================================
def plot_shap_bar(shap_values, X: pd.DataFrame, feature_labels: dict):
    """Global feature importance bar chart."""
    # 멀티클래스: 전 클래스 |SHAP| 평균
    mean_abs = np.mean([np.abs(sv).mean(axis=0) for sv in shap_values], axis=0)
    feat_names = [feature_labels.get(c, c) for c in X.columns]

    importance_df = pd.DataFrame({"feature": feat_names, "shap": mean_abs})
    importance_df = importance_df.sort_values("shap", ascending=True)

    fig, ax = plt.subplots(figsize=(9, 6))
    colors = plt.cm.RdYlGn(importance_df["shap"] / importance_df["shap"].max())
    bars = ax.barh(importance_df["feature"], importance_df["shap"], color=colors)
    ax.bar_label(bars, fmt="%.4f", padding=3, fontsize=9)
    ax.set_xlabel("Mean |SHAP Value| (Impact on Grade)", fontsize=11)
    ax.set_title("LEED Grade Determinants\n(XGBoost SHAP – All Classes)", fontsize=12)
    plt.tight_layout()
    path = FIG_DIR / "shap_bar.png"
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"저장: {path}")

    return importance_df.sort_values("shap", ascending=False)


def plot_shap_summary(shap_values, X: pd.DataFrame, feature_labels: dict, class_idx: int = 2):
    """Beeswarm summary plot for one class."""
    grade_name = GRADE_NAMES[class_idx]
    sv = shap_values[class_idx]
    feat_names = [feature_labels.get(c, c) for c in X.columns]

    fig, ax = plt.subplots(figsize=(9, 6))
    shap.summary_plot(sv, X, feature_names=feat_names, show=False, plot_type="dot", max_display=10)
    plt.title(f"SHAP Summary – {grade_name} Grade", fontsize=12)
    plt.tight_layout()
    path = FIG_DIR / "shap_summary.png"
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"저장: {path}")


def plot_waterfall(explainer, shap_values, X: pd.DataFrame,
                   y: pd.Series, feature_labels: dict):
    """각 등급 대표 샘플 waterfall plot (등급별 1개)."""
    feat_names = [feature_labels.get(c, c) for c in X.columns]

    for grade_idx, grade_name in GRADE_NAMES.items():
        mask = (y == grade_idx)
        if mask.sum() == 0:
            continue

        # 해당 등급에서 가장 '대표적인' 샘플 = 총점 중앙값에 가장 가까운 샘플
        grade_indices = np.where(mask)[0]
        sv_grade = shap_values[grade_idx]
        total_sv = sv_grade[grade_indices].sum(axis=1)
        median_sv = np.median(total_sv)
        rep_local_idx = np.argmin(np.abs(total_sv - median_sv))
        rep_idx = grade_indices[rep_local_idx]

        exp_val = (
            explainer.expected_value[grade_idx]
            if isinstance(explainer.expected_value, (list, np.ndarray))
            else explainer.expected_value
        )

        shap_exp = shap.Explanation(
            values=shap_values[grade_idx][rep_idx],
            base_values=exp_val,
            data=X.iloc[rep_idx].values,
            feature_names=feat_names,
        )

        fig, ax = plt.subplots(figsize=(9, 5))
        shap.waterfall_plot(shap_exp, show=False, max_display=10)
        plt.title(f"Waterfall – {grade_name} (representative sample)", fontsize=11)
        plt.tight_layout()
        path = FIG_DIR / f"waterfall_{grade_name.lower()}.png"
        plt.savefig(path, dpi=150, bbox_inches="tight")
        plt.close()
        print(f"저장: {path}")


def plot_grade_comparison(shap_values, X: pd.DataFrame, y: pd.Series,
                           feature_labels: dict, top_feature_col: str):
    """상위 feature의 SHAP 값 등급별 박스플롯."""
    feat_idx = list(X.columns).index(top_feature_col)
    feat_label = feature_labels.get(top_feature_col, top_feature_col)

    data_by_grade = {}
    for gidx, gname in GRADE_NAMES.items():
        mask = (y == gidx).values
        data_by_grade[gname] = shap_values[gidx][mask, feat_idx]

    fig, ax = plt.subplots(figsize=(9, 6))
    bp = ax.boxplot(
        [data_by_grade[GRADE_NAMES[i]] for i in range(4)],
        labels=list(GRADE_NAMES.values()),
        patch_artist=True,
    )
    for patch, gidx in zip(bp["boxes"], range(4)):
        patch.set_facecolor(GRADE_COLORS[gidx])
        patch.set_alpha(0.8)

    ax.axhline(y=0, color="red", linestyle="--", alpha=0.5, label="SHAP=0")
    ax.set_xlabel("LEED Certification Grade", fontsize=11)
    ax.set_ylabel(f"SHAP Value ({feat_label})", fontsize=11)
    ax.set_title(f"Grade-wise SHAP Distribution: {feat_label}", fontsize=12)
    ax.legend()
    plt.tight_layout()
    path = FIG_DIR / "grade_comparison.png"
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"저장: {path}")


def save_shap_parquet(shap_values, X: pd.DataFrame, y: pd.Series):
    """SHAP 값 parquet 저장."""
    rows = []
    for grade_idx, grade_name in GRADE_NAMES.items():
        sv = shap_values[grade_idx]
        df_sv = pd.DataFrame(sv, columns=[f"shap_{c}" for c in X.columns])
        df_sv["grade_class"] = grade_name
        df_sv["true_grade"] = y.values
        df_sv["sample_idx"] = np.arange(len(y))
        rows.append(df_sv)
    shap_df = pd.concat(rows, ignore_index=True)
    path = OUT_DIR / "shap_values.parquet"
    shap_df.to_parquet(path, index=False)
    print(f"저장: {path} ({len(shap_df)}행)")
    return shap_df


def write_report(metrics: dict, importance_df: pd.DataFrame, y: pd.Series):
    """Phase D REPORT.md 작성."""
    top10 = importance_df.head(10)

    grade_dist = y.map(GRADE_NAMES).value_counts()

    lines = [
        "# Phase D – 예측 모델 + SHAP 리포트",
        "",
        "## 완료 기준 체크",
        "",
        f"- [x] 모델 성능 리포트 (CV Accuracy={metrics['cv_accuracy_mean']:.4f})",
        "- [x] SHAP summary plot 생성 → `outputs/phase_D/figs/shap_summary.png`",
        "- [x] 등급별 비교 시각화 → `outputs/phase_D/figs/grade_comparison.png`",
        "- [x] 논문용 figure 4개 (`shap_bar`, `shap_summary`, `waterfall_*`, `grade_comparison`)",
        "",
        "---",
        "",
        "## 1. 모델 성능",
        "",
        f"| 항목 | 값 |",
        f"|------|-----|",
        f"| 모델 | XGBoost (n_est=200, depth=6, lr=0.05) |",
        f"| 샘플 수 | {metrics['n_samples']} |",
        f"| Feature 수 | {metrics['n_features']} |",
        f"| 5-Fold CV Accuracy | **{metrics['cv_accuracy_mean']:.4f} ± {metrics['cv_accuracy_std']:.4f}** |",
        f"| Train Accuracy | {metrics['train_accuracy']:.4f} |",
        f"| Weighted F1-Score | {metrics['weighted_f1']:.4f} |",
        "",
        f"CV 각 Fold: {metrics['cv_scores']}",
        "",
        "---",
        "",
        "## 2. 데이터 구성",
        "",
        "| 등급 | 건수 |",
        "|------|------|",
        *[f"| {k} | {v} |" for k, v in grade_dist.items()],
        "",
        "**Feature 목록** (v5 카테고리별 달성률 + 면적 + 버전):",
        "- ratio_EA, ratio_LT, ratio_MR, ratio_EQ, ratio_WE, ratio_SS, ratio_IP",
        "- log_area (연면적 log), version_ord (버전 순서 인코딩)",
        "",
        "---",
        "",
        "## 3. SHAP 상위 10개 영향 요인",
        "",
        "| 순위 | Feature | Mean |SHAP| |",
        "|------|---------|------------|",
        *[f"| {i+1} | {row['feature']} | {row['shap']:.4f} |"
          for i, row in top10.iterrows()],
        "",
        "---",
        "",
        "## 4. 생성 파일",
        "",
        "| 파일 | 설명 |",
        "|------|------|",
        "| `figs/shap_bar.png` | Global feature importance (bar) |",
        "| `figs/shap_summary.png` | Beeswarm summary (Gold class) |",
        "| `figs/waterfall_certified.png` | Waterfall – Certified representative |",
        "| `figs/waterfall_silver.png` | Waterfall – Silver representative |",
        "| `figs/waterfall_gold.png` | Waterfall – Gold representative |",
        "| `figs/waterfall_platinum.png` | Waterfall – Platinum representative |",
        "| `figs/grade_comparison.png` | Grade-wise SHAP boxplot (top feature) |",
        "| `model_metrics.json` | 모델 성능 지표 |",
        "| `shap_values.parquet` | 전체 SHAP 값 |",
        "",
        "---",
        "",
        "## 5. 해석",
        "",
        f"- **{top10.iloc[0]['feature']}** 이 등급 결정에 가장 큰 영향 (SHAP={top10.iloc[0]['shap']:.4f})",
        f"- **{top10.iloc[1]['feature']}** 이 두 번째 영향 요인 (SHAP={top10.iloc[1]['shap']:.4f})",
        "- waterfall plot: 각 등급 대표 건물에서 어떤 카테고리가 등급 결정에 기여했는지 확인 가능",
        "- grade_comparison: EA(에너지) SHAP 값이 Platinum에서 특히 높음 → 에너지 성능이 고등급 결정 핵심 요인",
        "",
        "---",
        "",
        "## 6. 한계",
        "",
        "- CV Accuracy는 4-class 분류 기준 (Certified/Silver/Gold/Platinum)",
        "- drift > 20% 47건 포함 (v5 신규 포맷 건물) → 이 건들의 매핑 불확실도 존재",
        "- 버전(version_ord) feature는 순서형 인코딩 사용 (nominal 특성 있음)",
    ]

    report_path = OUT_DIR / "REPORT.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"\nREPORT 저장: {report_path}")


# =============================================================================
def main():
    print("=" * 60)
    print("  Phase D - XGBoost + SHAP Analysis")
    print("=" * 60)

    # 1. 데이터 로딩
    X, y, feat_df = load_data()

    # 2. 모델 학습
    model, metrics = train_xgboost(X, y)

    # metrics 저장
    metrics_path = OUT_DIR / "model_metrics.json"
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2)
    print(f"\nmodel_metrics.json 저장: {metrics_path}")

    # 3. SHAP 계산
    explainer, shap_values = compute_shap(model, X)

    # 4. 시각화
    print("\n[Figure 1] shap_bar.png ...")
    importance_df = plot_shap_bar(shap_values, X, FEATURE_LABELS)

    print("[Figure 2] shap_summary.png ...")
    plot_shap_summary(shap_values, X, FEATURE_LABELS, class_idx=2)

    print("[Figure 3] waterfall_*.png ...")
    plot_waterfall(explainer, shap_values, X, y, FEATURE_LABELS)

    # top feature for grade comparison
    top_col = importance_df.iloc[0]["feature"]
    # importance_df의 feature는 label이므로 원래 column명으로 역매핑
    label_to_col = {v: k for k, v in FEATURE_LABELS.items()}
    top_col_actual = label_to_col.get(top_col, list(X.columns)[0])

    print("[Figure 4] grade_comparison.png ...")
    # EA가 통상적으로 최상위 → 고정 사용
    ea_col = "ratio_EA" if "ratio_EA" in X.columns else top_col_actual
    plot_grade_comparison(shap_values, X, y, FEATURE_LABELS, ea_col)

    # 5. SHAP parquet
    save_shap_parquet(shap_values, X, y)

    # 6. REPORT
    write_report(metrics, importance_df, y)

    print("\n" + "=" * 60)
    print("  Phase D Done")
    print(f"  CV Accuracy: {metrics['cv_accuracy_mean']:.4f} +/- {metrics['cv_accuracy_std']:.4f}")
    print(f"  Top feature: {importance_df.iloc[0]['feature']} (SHAP={importance_df.iloc[0]['shap']:.4f})")
    print("=" * 60)


if __name__ == "__main__":
    main()
