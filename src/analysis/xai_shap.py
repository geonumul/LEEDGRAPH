"""
XAI - SHAP 분석 및 시각화
- 핵심 연구 모듈: 등급 결정에 영향을 미치는 요인 도출
- 등급 '예측'이 아닌 '영향 요인' 분석이 본 연구의 목적
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib
import shap
from pathlib import Path

# 한글 폰트 설정
matplotlib.rcParams["font.family"] = "Malgun Gothic"
matplotlib.rcParams["axes.unicode_minus"] = False

GRADE_LABELS = {0: "Certified", 1: "Silver", 2: "Gold", 3: "Platinum"}

# 카테고리 한국어 이름 매핑 (그래프 가독성)
CATEGORY_KOR = {
    "score_v5_LT": "입지·교통 (LT)",
    "score_v5_SS": "지속가능 부지 (SS)",
    "score_v5_WE": "물 효율 (WE)",
    "score_v5_EA": "에너지·대기 (EA)",
    "score_v5_MR": "재료·자원 (MR)",
    "score_v5_IEQ": "실내환경 (IEQ)",
    "score_v5_IN": "혁신 (IN)",
    "score_v5_RP": "지역 우선 (RP)",
    "score_v5_IP": "통합 프로세스 (IP)",
    "log_area": "연면적(log)",
}


class LEEDSHAPAnalyzer:
    """
    SHAP 기반 LEED 등급 영향 요인 분석기.

    핵심 분석 내용:
    1. 전체 데이터셋 기준 글로벌 특성 중요도
    2. 등급별 SHAP 값 분포 (어떤 카테고리가 해당 등급에 영향?)
    3. 특정 카테고리의 점수 변화가 등급에 미치는 영향 (의존성 플롯)
    4. 개별 프로젝트 SHAP 설명 (Force Plot)
    """

    def __init__(self, model, feature_names: list, output_dir: str = "outputs/figures"):
        self.model = model
        self.feature_names = feature_names
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.explainer = None
        self.shap_values = None
        self.X_analyzed = None

    # ─────────────────────────────────────────────
    # SHAP 값 계산
    # ─────────────────────────────────────────────
    def compute_shap_values(self, X: pd.DataFrame):
        """
        SHAP Explainer 생성 및 SHAP 값 계산.

        TreeExplainer를 사용 (Random Forest, XGBoost, LightGBM 지원).
        """
        print("SHAP 값 계산 중... (시간이 걸릴 수 있습니다)")
        self.explainer = shap.TreeExplainer(self.model)
        self.shap_values = self.explainer.shap_values(X)
        self.X_analyzed = X.copy()

        if isinstance(self.shap_values, list):
            # 멀티클래스: shap_values[i] = i번째 클래스에 대한 SHAP 값
            print(f"SHAP 값 계산 완료 - {len(self.shap_values)}개 클래스, {X.shape[0]}개 샘플")
        else:
            print(f"SHAP 값 계산 완료 - {X.shape[0]}개 샘플")

        return self.shap_values

    # ─────────────────────────────────────────────
    # 1. 글로벌 특성 중요도 (Summary Plot)
    # ─────────────────────────────────────────────
    def plot_summary(self, class_idx: int = 2, save: bool = True):
        """
        전체 데이터 기준 특성 중요도 Summary Plot.

        Args:
            class_idx: 분석할 등급 인덱스 (기본: 2=Gold)
                       0=Certified, 1=Silver, 2=Gold, 3=Platinum
        """
        if self.shap_values is None:
            raise RuntimeError("먼저 compute_shap_values()를 실행하세요.")

        grade_name = GRADE_LABELS.get(class_idx, f"Class_{class_idx}")
        shap_vals = (
            self.shap_values[class_idx]
            if isinstance(self.shap_values, list)
            else self.shap_values
        )

        # 피처명 한국어로 변환
        display_names = [
            CATEGORY_KOR.get(f, f) for f in self.feature_names
        ]

        fig, ax = plt.subplots(figsize=(10, 7))
        shap.summary_plot(
            shap_vals,
            self.X_analyzed,
            feature_names=display_names,
            show=False,
            plot_type="dot",
        )
        plt.title(f"SHAP Summary Plot - {grade_name} 등급 영향 요인", fontsize=14, pad=15)
        plt.tight_layout()

        if save:
            save_path = self.output_dir / f"shap_summary_{grade_name.lower()}.png"
            plt.savefig(save_path, dpi=150, bbox_inches="tight")
            print(f"저장: {save_path}")
        plt.show()
        plt.close()

    # ─────────────────────────────────────────────
    # 2. 특성 중요도 바 차트 (전체 등급 통합)
    # ─────────────────────────────────────────────
    def plot_feature_importance(self, save: bool = True):
        """
        전체 등급에 걸친 평균 |SHAP| 값 기준 특성 중요도 바 차트.
        등급 결정에 가장 많은 영향을 주는 카테고리를 한눈에 파악.
        """
        if self.shap_values is None:
            raise RuntimeError("먼저 compute_shap_values()를 실행하세요.")

        if isinstance(self.shap_values, list):
            # 멀티클래스: 모든 클래스의 |SHAP| 평균
            mean_abs_shap = np.mean(
                [np.abs(sv).mean(axis=0) for sv in self.shap_values], axis=0
            )
        else:
            mean_abs_shap = np.abs(self.shap_values).mean(axis=0)

        display_names = [CATEGORY_KOR.get(f, f) for f in self.feature_names]

        importance_df = pd.DataFrame({
            "Feature": display_names,
            "Mean_SHAP": mean_abs_shap,
        }).sort_values("Mean_SHAP", ascending=True)

        fig, ax = plt.subplots(figsize=(10, 7))
        bars = ax.barh(
            importance_df["Feature"],
            importance_df["Mean_SHAP"],
            color=plt.cm.RdYlGn(
                importance_df["Mean_SHAP"] / importance_df["Mean_SHAP"].max()
            ),
        )
        ax.set_xlabel("평균 |SHAP 값| (등급 결정 영향력)", fontsize=12)
        ax.set_title("LEED 등급 결정에 미치는 카테고리별 영향력\n(한국 건물 451개 기준)", fontsize=13)
        ax.bar_label(bars, fmt="%.3f", padding=3, fontsize=9)
        plt.tight_layout()

        if save:
            save_path = self.output_dir / "shap_feature_importance.png"
            plt.savefig(save_path, dpi=150, bbox_inches="tight")
            print(f"저장: {save_path}")
        plt.show()
        plt.close()

        return importance_df.sort_values("Mean_SHAP", ascending=False)

    # ─────────────────────────────────────────────
    # 3. 의존성 플롯 (Dependence Plot)
    # ─────────────────────────────────────────────
    def plot_dependence(
        self,
        feature: str = "score_v5_EA",
        class_idx: int = 2,
        interaction_feature: str = "auto",
        save: bool = True,
    ):
        """
        특정 카테고리 점수 변화 → SHAP 값 변화 관계 시각화.

        예) "EA 점수가 높아질수록 Gold 등급 획득 가능성이 어떻게 변하는가?"

        Args:
            feature: 분석할 카테고리 컬럼명
            class_idx: 등급 인덱스 (2=Gold)
            interaction_feature: 색상으로 표시할 상호작용 변수 ("auto"=자동)
        """
        if self.shap_values is None:
            raise RuntimeError("먼저 compute_shap_values()를 실행하세요.")

        grade_name = GRADE_LABELS.get(class_idx, f"Class_{class_idx}")
        shap_vals = (
            self.shap_values[class_idx]
            if isinstance(self.shap_values, list)
            else self.shap_values
        )

        feature_display = CATEGORY_KOR.get(feature, feature)

        fig, ax = plt.subplots(figsize=(10, 6))
        shap.dependence_plot(
            feature,
            shap_vals,
            self.X_analyzed,
            feature_names=self.feature_names,
            interaction_index=interaction_feature,
            ax=ax,
            show=False,
        )
        ax.set_xlabel(f"{feature_display} 점수 (v5 환산)", fontsize=12)
        ax.set_ylabel(f"SHAP 값 ({grade_name} 등급 영향)", fontsize=12)
        ax.set_title(
            f"{feature_display} 점수가 {grade_name} 등급에 미치는 영향\n"
            f"(한국 LEED 인증 건물 분석)",
            fontsize=13,
        )
        plt.tight_layout()

        if save:
            safe_feat = feature.replace("/", "_").replace(" ", "_")
            save_path = self.output_dir / f"shap_dependence_{safe_feat}_{grade_name.lower()}.png"
            plt.savefig(save_path, dpi=150, bbox_inches="tight")
            print(f"저장: {save_path}")
        plt.show()
        plt.close()

    # ─────────────────────────────────────────────
    # 4. 등급별 SHAP 박스플롯 비교
    # ─────────────────────────────────────────────
    def plot_grade_comparison(
        self,
        feature: str = "score_v5_EA",
        y: pd.Series = None,
        save: bool = True,
    ):
        """
        특정 카테고리의 SHAP 값을 등급별로 비교하는 박스플롯.

        "EA 점수의 SHAP 영향이 Certified vs Gold 간에 얼마나 다른가?"
        """
        if self.shap_values is None or y is None:
            raise RuntimeError("shap_values와 y(레이블)가 필요합니다.")

        feature_display = CATEGORY_KOR.get(feature, feature)
        feat_idx = list(self.feature_names).index(feature)

        data_by_grade = {}
        for grade_idx, grade_name in GRADE_LABELS.items():
            mask = y.values == grade_idx
            if isinstance(self.shap_values, list):
                shap_vals_for_grade = self.shap_values[grade_idx][mask, feat_idx]
            else:
                shap_vals_for_grade = self.shap_values[mask, feat_idx]
            data_by_grade[grade_name] = shap_vals_for_grade

        fig, ax = plt.subplots(figsize=(10, 6))
        bp = ax.boxplot(
            [data_by_grade[GRADE_LABELS[i]] for i in range(4)],
            labels=list(GRADE_LABELS.values()),
            patch_artist=True,
        )
        colors = ["#e8e8e8", "#c0c0c0", "#FFD700", "#e5e4e2"]
        for patch, color in zip(bp["boxes"], colors):
            patch.set_facecolor(color)

        ax.axhline(y=0, color="red", linestyle="--", alpha=0.5, label="SHAP=0 (영향 없음)")
        ax.set_xlabel("LEED 인증 등급", fontsize=12)
        ax.set_ylabel(f"SHAP 값 ({feature_display})", fontsize=12)
        ax.set_title(
            f"등급별 {feature_display} 점수의 영향력 비교\n"
            f"(SHAP 값 분포, 한국 LEED 인증 건물)",
            fontsize=13,
        )
        ax.legend()
        plt.tight_layout()

        if save:
            safe_feat = feature.replace("/", "_").replace(" ", "_")
            save_path = self.output_dir / f"shap_grade_comparison_{safe_feat}.png"
            plt.savefig(save_path, dpi=150, bbox_inches="tight")
            print(f"저장: {save_path}")
        plt.show()
        plt.close()

    # ─────────────────────────────────────────────
    # 5. 개별 프로젝트 Force Plot
    # ─────────────────────────────────────────────
    def plot_force(self, sample_idx: int = 0, class_idx: int = 2, save: bool = True):
        """
        개별 프로젝트의 SHAP 기여도 Force Plot.

        "이 특정 건물이 Gold 등급을 받은 이유를 각 카테고리별 기여로 설명"
        """
        if self.shap_values is None:
            raise RuntimeError("먼저 compute_shap_values()를 실행하세요.")

        grade_name = GRADE_LABELS.get(class_idx, f"Class_{class_idx}")
        shap_vals = (
            self.shap_values[class_idx]
            if isinstance(self.shap_values, list)
            else self.shap_values
        )
        expected_val = (
            self.explainer.expected_value[class_idx]
            if isinstance(self.explainer.expected_value, list)
            else self.explainer.expected_value
        )

        display_names = [CATEGORY_KOR.get(f, f) for f in self.feature_names]

        shap.initjs()
        force_plot = shap.force_plot(
            expected_val,
            shap_vals[sample_idx],
            self.X_analyzed.iloc[sample_idx],
            feature_names=display_names,
            matplotlib=True,
            show=False,
        )
        plt.title(f"Sample #{sample_idx} - {grade_name} 등급 영향 요인 분해", fontsize=12)

        if save:
            save_path = self.output_dir / f"shap_force_sample{sample_idx}_{grade_name.lower()}.png"
            plt.savefig(save_path, dpi=150, bbox_inches="tight")
            print(f"저장: {save_path}")
        plt.show()
        plt.close()

    # ─────────────────────────────────────────────
    # 6. 종합 분석 리포트
    # ─────────────────────────────────────────────
    def generate_report(self, y: pd.Series) -> pd.DataFrame:
        """
        전체 카테고리의 등급별 평균 SHAP 값 테이블 생성.
        연구 논문의 핵심 결과표로 활용 가능.
        """
        if self.shap_values is None:
            raise RuntimeError("먼저 compute_shap_values()를 실행하세요.")

        display_names = [CATEGORY_KOR.get(f, f) for f in self.feature_names]
        records = []

        for feat_idx, feat_name in enumerate(display_names):
            row = {"카테고리": feat_name}
            for grade_idx, grade_name in GRADE_LABELS.items():
                mask = y.values == grade_idx
                if isinstance(self.shap_values, list):
                    shap_for_grade = self.shap_values[grade_idx][mask, feat_idx]
                else:
                    shap_for_grade = self.shap_values[mask, feat_idx]

                row[f"{grade_name}_avg_SHAP"] = round(shap_for_grade.mean(), 4)
                row[f"{grade_name}_abs_SHAP"] = round(np.abs(shap_for_grade).mean(), 4)

            records.append(row)

        report_df = pd.DataFrame(records)

        # 저장
        save_path = self.output_dir.parent / "reports" / "shap_grade_report.csv"
        save_path.parent.mkdir(parents=True, exist_ok=True)
        report_df.to_csv(save_path, index=False, encoding="utf-8-sig")
        print(f"SHAP 분석 리포트 저장: {save_path}")

        return report_df

    # ─────────────────────────────────────────────
    # 7. 전체 플롯 일괄 실행
    # ─────────────────────────────────────────────
    def run_full_analysis(self, X: pd.DataFrame, y: pd.Series):
        """전체 SHAP 분석 일괄 실행"""
        print("=" * 60)
        print("  LEED XAI (SHAP) 분석 시작")
        print("  목적: 등급 결정 영향 요인 도출 (예측 X)")
        print("=" * 60)

        # 1. SHAP 값 계산
        self.compute_shap_values(X)

        # 2. 특성 중요도
        print("\n[1/5] 전체 특성 중요도 분석...")
        importance_df = self.plot_feature_importance()
        print(importance_df.to_string(index=False))

        # 3. 등급별 Summary Plot (Gold 기준)
        print("\n[2/5] Gold 등급 영향 요인 Summary Plot...")
        self.plot_summary(class_idx=2)

        # 4. EA(에너지) 의존성 플롯 - 가장 중요한 카테고리
        top_feature = f"score_v5_{importance_df.iloc[0]['Feature'].split('(')[0].strip().split('_')[-1] if 'v5' not in importance_df.iloc[0]['Feature'] else importance_df.iloc[0]['Feature']}"
        ea_feature = "score_v5_EA"
        print(f"\n[3/5] 에너지·대기(EA) 의존성 플롯...")
        if ea_feature in self.feature_names:
            self.plot_dependence(feature=ea_feature, class_idx=2)

        # 5. 등급별 EA 영향력 비교
        print(f"\n[4/5] 등급별 EA 영향력 비교...")
        if ea_feature in self.feature_names:
            self.plot_grade_comparison(feature=ea_feature, y=y)

        # 6. 종합 리포트
        print("\n[5/5] 종합 SHAP 리포트 생성...")
        report = self.generate_report(y)

        print("\n전체 SHAP 분석 완료")
        return report
