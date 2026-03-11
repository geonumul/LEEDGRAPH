"""
LEED 데이터 전처리기
- 버전별 카테고리 점수 정규화
- 결측치 처리
- 등급 인코딩
"""

import pandas as pd
import numpy as np
from typing import Tuple

from .loader import LEED_VERSION_MAX_SCORES, LEED_GRADE_THRESHOLDS

# v5 기준 카테고리 목록 (표준화 후 최종 컬럼)
V5_CATEGORIES = ["LT", "SS", "WE", "EA", "MR", "IEQ", "IN", "RP", "IP"]
V5_MAX_SCORES = LEED_VERSION_MAX_SCORES["v5"]

# 등급 → 정수 인코딩
GRADE_ENCODING = {
    "Certified": 0,
    "Silver": 1,
    "Gold": 2,
    "Platinum": 3,
}


class LEEDPreprocessor:
    """LEED 데이터 전처리 클래스"""

    def __init__(self):
        self.version_max_scores = LEED_VERSION_MAX_SCORES
        self.v5_categories = V5_CATEGORIES
        self.v5_max = V5_MAX_SCORES

    # ─────────────────────────────────────────────
    # 1. 버전별 점수 비율 정규화 (proportional scaling)
    # ─────────────────────────────────────────────
    def normalize_by_version(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        각 카테고리 점수를 해당 버전의 최대 점수로 나누어 비율(0~1)로 변환.
        이후 v5 최대 점수를 곱해 v5 기준 점수로 환산.

        예) v3의 EA 점수 28점 → 28/35 = 0.8 → 0.8 × 33 = 26.4
        """
        df = df.copy()
        normalized_records = []

        for _, row in df.iterrows():
            ver = row.get("version", "v4")
            max_scores = self.version_max_scores.get(ver, self.version_max_scores["v4"])
            record = row.to_dict()

            for cat in self.v5_categories:
                score_col = f"score_{cat}"
                raw_score = row.get(score_col, np.nan)
                ver_max = max_scores.get(cat, None)
                v5_max = self.v5_max.get(cat, 0)

                if pd.isna(raw_score) or ver_max is None:
                    # 구버전에 없던 카테고리(LT, IP 등)는 0으로 처리
                    record[f"score_v5_{cat}"] = 0.0
                else:
                    ratio = raw_score / ver_max if ver_max > 0 else 0
                    record[f"score_v5_{cat}"] = round(ratio * v5_max, 2)

            normalized_records.append(record)

        return pd.DataFrame(normalized_records)

    # ─────────────────────────────────────────────
    # 2. 결측치 처리
    # ─────────────────────────────────────────────
    def handle_missing_values(self, df: pd.DataFrame) -> pd.DataFrame:
        """결측치 처리 - 카테고리 점수는 0으로, 등급은 드롭"""
        df = df.copy()

        # 카테고리 점수 결측치 → 0
        score_cols = [c for c in df.columns if c.startswith("score_v5_")]
        df[score_cols] = df[score_cols].fillna(0)

        # 등급 결측치 → 해당 행 제거
        if "certification_level" in df.columns:
            before = len(df)
            df = df.dropna(subset=["certification_level"])
            dropped = before - len(df)
            if dropped > 0:
                print(f"[경고] 등급 결측 {dropped}개 행 제거")

        # 유효하지 않은 등급 필터링
        valid_grades = list(GRADE_ENCODING.keys())
        df = df[df["certification_level"].isin(valid_grades)]

        return df

    # ─────────────────────────────────────────────
    # 3. v5 총점 재계산
    # ─────────────────────────────────────────────
    def recalculate_v5_total(self, df: pd.DataFrame) -> pd.DataFrame:
        """v5 기준으로 환산된 카테고리 점수의 합산 총점 계산"""
        df = df.copy()
        v5_score_cols = [f"score_v5_{cat}" for cat in self.v5_categories]
        existing_cols = [c for c in v5_score_cols if c in df.columns]
        df["total_score_v5"] = df[existing_cols].sum(axis=1).round(2)
        return df

    # ─────────────────────────────────────────────
    # 4. 등급 인코딩
    # ─────────────────────────────────────────────
    def encode_grade(self, df: pd.DataFrame) -> pd.DataFrame:
        """등급 문자열 → 정수 인코딩"""
        df = df.copy()
        df["grade_encoded"] = df["certification_level"].map(GRADE_ENCODING)
        return df

    # ─────────────────────────────────────────────
    # 5. 연면적 로그 변환
    # ─────────────────────────────────────────────
    def log_transform_area(self, df: pd.DataFrame) -> pd.DataFrame:
        """연면적 로그 변환 (왜도 제거)"""
        df = df.copy()
        if "gross_area_sqm" in df.columns:
            df["log_area"] = np.log1p(df["gross_area_sqm"])
        return df

    # ─────────────────────────────────────────────
    # 6. 건물 유형 원-핫 인코딩
    # ─────────────────────────────────────────────
    def encode_building_type(self, df: pd.DataFrame) -> pd.DataFrame:
        """건물 유형 원-핫 인코딩"""
        df = df.copy()
        if "building_type" in df.columns:
            dummies = pd.get_dummies(
                df["building_type"], prefix="type", drop_first=False
            )
            df = pd.concat([df, dummies], axis=1)
        return df

    # ─────────────────────────────────────────────
    # 7. 전체 파이프라인
    # ─────────────────────────────────────────────
    def run_pipeline(self, df: pd.DataFrame) -> pd.DataFrame:
        """전처리 전체 파이프라인 실행"""
        print("전처리 파이프라인 시작...")

        print("  1/5. 버전별 비율 정규화 (→ v5 환산)")
        df = self.normalize_by_version(df)

        print("  2/5. v5 총점 재계산")
        df = self.recalculate_v5_total(df)

        print("  3/5. 결측치 처리")
        df = self.handle_missing_values(df)

        print("  4/5. 등급 인코딩")
        df = self.encode_grade(df)

        print("  5/5. 연면적 로그 변환 + 건물 유형 인코딩")
        df = self.log_transform_area(df)
        df = self.encode_building_type(df)

        print(f"\n전처리 완료: {len(df)}개 프로젝트, {len(df.columns)}개 컬럼")
        return df

    # ─────────────────────────────────────────────
    # 8. Feature / Target 분리
    # ─────────────────────────────────────────────
    def split_features_target(
        self, df: pd.DataFrame, use_log_area: bool = True
    ) -> Tuple[pd.DataFrame, pd.Series]:
        """
        ML 학습용 Feature(X)와 Target(y) 분리.

        Features:
            - v5 환산 카테고리 점수 (9개)
            - 연면적 (log 변환)
            - 건물 유형 (원-핫)

        Target:
            - grade_encoded (0=Certified, 1=Silver, 2=Gold, 3=Platinum)
        """
        feature_cols = [f"score_v5_{cat}" for cat in self.v5_categories]
        feature_cols = [c for c in feature_cols if c in df.columns]

        if use_log_area and "log_area" in df.columns:
            feature_cols.append("log_area")

        type_cols = [c for c in df.columns if c.startswith("type_")]
        feature_cols.extend(type_cols)

        X = df[feature_cols].copy()
        y = df["grade_encoded"].copy()

        print(f"Feature 수: {len(feature_cols)}, 샘플 수: {len(X)}")
        print(f"   등급 분포:\n{y.value_counts().sort_index()}")
        return X, y

    def get_feature_names(self, df: pd.DataFrame) -> list:
        """Feature 컬럼명 반환 (SHAP 시각화용)"""
        feature_cols = [f"score_v5_{cat}" for cat in self.v5_categories]
        feature_cols = [c for c in feature_cols if c in df.columns]
        if "log_area" in df.columns:
            feature_cols.append("log_area")
        type_cols = [c for c in df.columns if c.startswith("type_")]
        feature_cols.extend(type_cols)
        return feature_cols
