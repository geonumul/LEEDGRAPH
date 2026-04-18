"""
Option A 데이터셋 재구성 (재실행 없이)

입력:
    data/processed/project_features.parquet      (V1 - Rule-only 460건)
    outputs/phase_E/llm_validation_log.csv        (75건 LLM 리뷰)

출력:
    data/processed/project_features_option_a.parquet
        → 모든 460건 Rule 결과 + 75건에 LLM 리뷰 메타데이터 추가
        → 나머지 385건은 LLM 리뷰 필드 NaN
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd

V1_PATH = Path("data/processed/project_features.parquet")
LOG_PATH = Path("outputs/phase_E/llm_validation_log.csv")
OUT_PATH = Path("data/processed/project_features_option_a.parquet")


def main():
    print("=" * 60)
    print("  Option A 데이터셋 재구성")
    print("=" * 60)

    # V1 Rule-only 460건 로드
    feat = pd.read_parquet(V1_PATH)
    print(f"V1 parquet: {len(feat)}행 (Rule 기반)")

    # LLM 리뷰 로그 75건 로드
    log = pd.read_csv(LOG_PATH)
    print(f"LLM 리뷰 로그: {len(log)}건")

    # project_id로 매칭
    log = log.rename(columns={
        "val_target":   "llm_review_target",
        "val_is_valid": "llm_review_is_valid",
        "val_score":    "llm_review_score",
        "val_issues":   "llm_review_issues",
        "val_feedback": "llm_review_feedback",
        "iterations":   "llm_review_iterations",
    })
    log_cols = [
        "project_id",
        "llm_review_target",
        "llm_review_is_valid",
        "llm_review_score",
        "llm_review_issues",
        "llm_review_feedback",
        "llm_review_iterations",
    ]
    log_slim = log[log_cols].copy()
    log_slim["project_id"] = log_slim["project_id"].astype(str)

    # V1에 LLM 리뷰 붙이기 (left join)
    feat["project_id"] = feat["project_id"].astype(str)
    merged = feat.merge(log_slim, on="project_id", how="left")

    # 리뷰 유무 플래그
    merged["has_llm_review"] = merged["llm_review_target"].notna()

    print(f"\n최종: {len(merged)}행")
    print(f"  has_llm_review: {merged['has_llm_review'].sum()}건")
    print(f"  llm_review_is_valid=True: {(merged['llm_review_is_valid'] == True).sum()}건")
    print(f"  llm_review_target 분포: {merged['llm_review_target'].value_counts(dropna=False).to_dict()}")

    # 저장
    merged.to_parquet(OUT_PATH, index=False)
    print(f"\n저장: {OUT_PATH}")

    # 버전별 리뷰 현황
    print(f"\n버전별 LLM 리뷰 커버리지:")
    for ver in sorted(merged["original_version"].unique()):
        sub = merged[merged["original_version"] == ver]
        n_rev = sub["has_llm_review"].sum()
        print(f"  {ver}: {n_rev}/{len(sub)}건 리뷰됨")


if __name__ == "__main__":
    main()
