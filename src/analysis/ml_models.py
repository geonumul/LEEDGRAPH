"""
ML 모델 학습 및 평가
- 표준화된 v5 데이터를 기반으로 분류 모델 학습
- 목표: 등급 '예측'이 아닌 XAI를 위한 '설명 가능한 모델' 확보
"""

import pandas as pd
import numpy as np
import joblib
from pathlib import Path
from typing import Tuple, Optional

from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.model_selection import StratifiedKFold, cross_val_score
from sklearn.preprocessing import label_binarize
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    accuracy_score,
)

try:
    import xgboost as xgb
    XGB_AVAILABLE = True
except ImportError:
    XGB_AVAILABLE = False

try:
    import lightgbm as lgb
    LGB_AVAILABLE = True
except ImportError:
    LGB_AVAILABLE = False

GRADE_LABELS = {0: "Certified", 1: "Silver", 2: "Gold", 3: "Platinum"}


class LEEDMLTrainer:
    """
    LEED 등급 분류 모델 학습기.

    [연구 목적 주의사항]
    본 연구의 목적은 등급 예측이 아닌 XAI(SHAP)를 통한 영향 요인 도출임.
    따라서 모델 성능(accuracy) 극대화보다 해석 가능성(interpretability)을
    우선시하는 모델(Random Forest, XGBoost)을 사용.
    """

    def __init__(self, output_dir: str = "outputs"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.models = {}
        self.best_model = None
        self.best_model_name = None
        self.feature_names = None

    # ─────────────────────────────────────────────
    # 모델 정의
    # ─────────────────────────────────────────────
    def _get_models(self) -> dict:
        """학습할 모델 목록 반환"""
        models = {
            "RandomForest": RandomForestClassifier(
                n_estimators=200,
                max_depth=8,
                min_samples_leaf=3,
                random_state=42,
                class_weight="balanced",  # 클래스 불균형 처리
            ),
        }

        if XGB_AVAILABLE:
            models["XGBoost"] = xgb.XGBClassifier(
                n_estimators=200,
                max_depth=6,
                learning_rate=0.05,
                subsample=0.8,
                colsample_bytree=0.8,
                random_state=42,
                use_label_encoder=False,
                eval_metric="mlogloss",
            )

        if LGB_AVAILABLE:
            models["LightGBM"] = lgb.LGBMClassifier(
                n_estimators=200,
                max_depth=6,
                learning_rate=0.05,
                random_state=42,
                class_weight="balanced",
                verbose=-1,
            )

        return models

    # ─────────────────────────────────────────────
    # 교차 검증으로 최적 모델 선택
    # ─────────────────────────────────────────────
    def evaluate_models(
        self, X: pd.DataFrame, y: pd.Series, cv_folds: int = 5
    ) -> pd.DataFrame:
        """
        Stratified K-Fold 교차 검증으로 모델 성능 비교.

        Args:
            X: Feature 행렬
            y: 등급 레이블 (0~3)
            cv_folds: K-Fold 수

        Returns:
            DataFrame: 모델별 성능 비교표
        """
        models = self._get_models()
        cv = StratifiedKFold(n_splits=cv_folds, shuffle=True, random_state=42)
        results = []

        print(f"{cv_folds}-Fold 교차 검증 시작...\n")
        for name, model in models.items():
            acc_scores = cross_val_score(model, X, y, cv=cv, scoring="accuracy")
            f1_scores  = cross_val_score(model, X, y, cv=cv, scoring="f1_weighted")
            results.append({
                "Model": name,
                "Mean_Accuracy": acc_scores.mean(),
                "Std_Accuracy":  acc_scores.std(),
                "Min_Accuracy":  acc_scores.min(),
                "Max_Accuracy":  acc_scores.max(),
                "CV_F1_Weighted": f1_scores.mean(),
                "CV_F1_Weighted_Std": f1_scores.std(),
            })
            print(f"  {name}: acc={acc_scores.mean():.4f} ± {acc_scores.std():.4f} | "
                  f"f1_weighted={f1_scores.mean():.4f} ± {f1_scores.std():.4f}")

        results_df = pd.DataFrame(results).sort_values("Mean_Accuracy", ascending=False)

        # 최고 성능 모델 선택
        best_name = results_df.iloc[0]["Model"]
        self.best_model_name = best_name
        print(f"\n최고 성능 모델: {best_name}")
        return results_df

    # ─────────────────────────────────────────────
    # 최종 모델 학습
    # ─────────────────────────────────────────────
    def train(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        model_name: Optional[str] = None,
    ) -> object:
        """
        선택한 모델로 전체 데이터 학습.

        Args:
            X: Feature 행렬
            y: 등급 레이블
            model_name: 학습할 모델명 (None이면 best_model_name 사용)

        Returns:
            학습된 모델 객체
        """
        self.feature_names = list(X.columns)

        if model_name is None:
            model_name = self.best_model_name or "RandomForest"

        models = self._get_models()
        if model_name not in models:
            raise ValueError(f"알 수 없는 모델: {model_name}. 선택 가능: {list(models.keys())}")

        model = models[model_name]
        print(f"{model_name} 학습 시작 (샘플: {len(X)}개, 피처: {len(X.columns)}개)")
        model.fit(X, y)

        self.models[model_name] = model
        self.best_model = model
        self.best_model_name = model_name

        print("학습 완료")
        return model

    # ─────────────────────────────────────────────
    # 성능 평가
    # ─────────────────────────────────────────────
    def evaluate(self, X: pd.DataFrame, y: pd.Series) -> dict:
        """학습된 모델의 성능 평가"""
        if self.best_model is None:
            raise RuntimeError("먼저 train()을 실행하세요.")

        y_pred = self.best_model.predict(X)
        acc = accuracy_score(y, y_pred)

        print(f"\n모델 성능 평가 ({self.best_model_name})")
        print(f"  전체 정확도: {acc:.4f}")
        print("\n  분류 리포트:")
        target_names = [GRADE_LABELS[i] for i in sorted(GRADE_LABELS.keys())]
        print(classification_report(y, y_pred, target_names=target_names))

        cm = confusion_matrix(y, y_pred)
        print("  혼동 행렬:")
        cm_df = pd.DataFrame(
            cm,
            index=[f"실제_{GRADE_LABELS[i]}" for i in range(len(cm))],
            columns=[f"예측_{GRADE_LABELS[i]}" for i in range(len(cm))],
        )
        print(cm_df)

        return {
            "accuracy": acc,
            "confusion_matrix": cm,
            "classification_report": classification_report(
                y, y_pred, target_names=target_names, output_dict=True
            ),
        }

    # ─────────────────────────────────────────────
    # 모델 저장/로딩
    # ─────────────────────────────────────────────
    def save_model(self, filename: str = "leed_model.pkl"):
        """학습된 모델 저장"""
        if self.best_model is None:
            raise RuntimeError("저장할 모델이 없습니다. 먼저 train()을 실행하세요.")

        save_path = self.output_dir / filename
        joblib.dump({
            "model": self.best_model,
            "model_name": self.best_model_name,
            "feature_names": self.feature_names,
        }, save_path)
        print(f"모델 저장 완료: {save_path}")

    def load_model(self, filename: str = "leed_model.pkl"):
        """저장된 모델 로딩"""
        load_path = self.output_dir / filename
        data = joblib.load(load_path)
        self.best_model = data["model"]
        self.best_model_name = data["model_name"]
        self.feature_names = data["feature_names"]
        print(f"모델 로딩 완료: {self.best_model_name}")
        return self.best_model
