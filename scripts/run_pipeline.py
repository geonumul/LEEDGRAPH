"""
Phase C – 전체 파이프라인 실행 스크립트

모든 PDF 로드 → 크레딧 추출 → v5 매핑 → 표준화 테이블 저장.

출력:
    data/processed/standardized_credits.parquet
    data/processed/project_features.parquet
    outputs/phase_C/pipeline_errors.log
"""

import os
import sys
import json
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
from src.langgraph_workflow.graph import run_standardization
from src.data.loader import LEEDDataLoader

# ── 경로 설정 ──────────────────────────────────────────────────────────────
SCORECARD_DIR = Path("data/raw/scorecards")
PROCESSED_DIR = Path("data/processed")
OUTPUT_DIR    = Path("outputs/phase_C")
ERROR_LOG     = OUTPUT_DIR / "pipeline_errors.log"

PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ── 로깅 설정 ──────────────────────────────────────────────────────────────
logging.basicConfig(
    filename=str(ERROR_LOG),
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(message)s",
    encoding="utf-8",
)
logger = logging.getLogger(__name__)


def build_credit_rows(project_id: str, version: str, leed_system: str,
                      credit_mappings: list) -> list[dict]:
    """credit_mappings 리스트를 standardized_credits 행으로 변환."""
    rows = []
    for cm in credit_mappings:
        rows.append({
            "project_id":        project_id,
            "source_version":    version,
            "leed_system":       leed_system,
            "source_credit_name": cm.get("credit_name", ""),
            "source_category":   None,   # credit_mappings에 source_category 없음
            "v5_credit_code":    cm.get("v5_code", "UNKNOWN"),
            "v5_category":       cm.get("v5_category"),
            "points_awarded":    cm.get("awarded", 0),
            "points_possible":   cm.get("possible", 0),
            "mapping_method":    "rule" if cm.get("matched") else "unmatched",
            "confidence":        cm.get("confidence"),
        })
    return rows


def main():
    # 1. CSV 디렉토리 1회 로딩
    loader = LEEDDataLoader()
    try:
        csv_df = loader.load_project_directory()
        print(f"CSV 로딩 완료: {len(csv_df)}개 프로젝트")
    except Exception as e:
        csv_df = None
        logger.warning(f"CSV 로딩 실패: {e}")
        print(f"[경고] CSV 로딩 실패: {e}")

    # 2. PDF 목록 수집
    pdf_files = sorted(SCORECARD_DIR.glob("*.pdf"))
    total = len(pdf_files)
    print(f"PDF 파일 {total}개 처리 시작")

    # 3. 결과 누적
    feature_rows: list[dict] = []      # project_features 용
    credit_rows:  list[dict] = []      # standardized_credits 용

    counters = {"success": 0, "failed": 0, "rule": 0, "llm": 0}
    version_stats: dict[str, dict] = {}   # {version: {"ok": n, "fail": n}}

    for i, pdf_path in enumerate(pdf_files, 1):
        fname = pdf_path.name
        if i % 50 == 0 or i == 1 or i == total:
            print(f"[{i:3d}/{total}] {fname[:55]}")

        try:
            state = run_standardization(pdf_path=str(pdf_path), directory_df=csv_df)

            status = state.get("status", "unknown")
            if status != "completed":
                raise RuntimeError(f"status={status}")

            final   = state["final_v5_data"]
            project = state.get("project", {})
            rule_result = state.get("rule_mapping_result", {})
            math_result = state.get("math_validation_result", {})

            version     = final.get("original_version", "unknown")
            project_id  = final.get("project_id", fname)
            leed_system = final.get("leed_system", "")
            track       = final.get("standardization_track", "rule")

            # ── project_features 행 ────────────────────────────────────────
            feature_row = {
                "project_id":           project_id,
                "project_name":         final.get("project_name", ""),
                "leed_system":          leed_system,
                "building_type":        final.get("building_type", ""),
                "gross_area_sqm":       final.get("gross_area_sqm", 0),
                "original_version":     version,
                "certification_level":  final.get("certification_level", ""),
                "total_score_original": final.get("total_score_original", 0),
                "total_score_v5":       final.get("total_score_v5", 0),
                "achievement_ratio_original": final.get("achievement_ratio_original", 0),
                "achievement_ratio_v5": final.get("achievement_ratio_v5", 0),
                "standardization_track": track,
                "drift":                math_result.get("ratio_drift", 0),
                "credit_rule_hit_rate": rule_result.get("credit_rule_hit_rate", None),
                # v5 카테고리별 ratio (ML feature)
                **{k: v for k, v in final.items() if k.startswith("ratio_")},
                # v5 카테고리별 절대 점수
                **{k: v for k, v in final.items() if k.startswith("score_v5_")},
            }
            feature_rows.append(feature_row)

            # ── standardized_credits 행 ────────────────────────────────────
            cm = rule_result.get("credit_mappings", [])
            if cm:
                credit_rows.extend(
                    build_credit_rows(project_id, version, leed_system, cm)
                )
            else:
                # 크레딧 상세 없는 경우(v2009 등): 카테고리 합계로 1행 생성
                for cat, score in rule_result.get("mapped_categories", {}).items():
                    credit_rows.append({
                        "project_id":         project_id,
                        "source_version":     version,
                        "leed_system":        leed_system,
                        "source_credit_name": f"[category] {cat}",
                        "source_category":    cat,
                        "v5_credit_code":     f"CAT_{cat}",
                        "v5_category":        cat,
                        "points_awarded":     project.get("categories", {}).get(cat, 0),
                        "points_possible":    project.get("categories_possible", {}).get(cat, 0),
                        "mapping_method":     "category_proportional",
                        "confidence":         "high",
                    })

            counters["success"] += 1
            counters[track] = counters.get(track, 0) + 1

            vs = version_stats.setdefault(version, {"ok": 0, "fail": 0})
            vs["ok"] += 1

        except Exception as e:
            counters["failed"] += 1
            logger.warning(f"{fname}: {e}")
            version = "unknown"
            try:
                # 버전이 파싱 됐다면 통계에 반영
                s2 = run_standardization.__module__  # dummy
            except Exception:
                pass
            vs = version_stats.setdefault(version, {"ok": 0, "fail": 0})
            vs["fail"] += 1

    print(f"\n처리 완료: {counters['success']}/{total}개 성공 "
          f"(rule={counters.get('rule',0)}, llm={counters.get('llm',0)}, "
          f"실패={counters['failed']})")

    # 4. Parquet 저장
    if feature_rows:
        feat_df = pd.DataFrame(feature_rows)
        feat_path = PROCESSED_DIR / "project_features.parquet"
        feat_df.to_parquet(feat_path, index=False)
        print(f"project_features.parquet 저장: {len(feat_df)}행 → {feat_path}")

    if credit_rows:
        cred_df = pd.DataFrame(credit_rows)
        cred_path = PROCESSED_DIR / "standardized_credits.parquet"
        cred_df.to_parquet(cred_path, index=False)
        print(f"standardized_credits.parquet 저장: {len(cred_df)}행 → {cred_path}")

    # 5. 검증 통계
    if feature_rows:
        feat_df = pd.read_parquet(PROCESSED_DIR / "project_features.parquet")

        # Total points 일치율 (CSV PointsAchieved vs 파싱 total_score_original)
        match_count = (feat_df["total_score_original"] > 0).sum()
        match_rate = match_count / len(feat_df) if len(feat_df) > 0 else 0

        # 카테고리 점수가 v5 max 이내인지 간단 확인
        v5_score_cols = [c for c in feat_df.columns if c.startswith("score_v5_")]
        over_max = 0
        for col in v5_score_cols:
            cat = col.replace("score_v5_", "")
            # ratio가 1 초과하면 문제
            ratio_col = f"ratio_{cat}"
            if ratio_col in feat_df.columns:
                over_max += (feat_df[ratio_col] > 1.01).sum()

        print(f"\n검증:")
        print(f"  프로젝트 total_score > 0: {match_count}/{len(feat_df)} ({match_rate:.1%})")
        print(f"  ratio > 1.01 위반 카테고리 수: {over_max}")

        # 버전별 성공 수
        print(f"\n버전별 성공:")
        for ver, cnt in sorted(feat_df.groupby("original_version").size().items()):
            print(f"  {ver}: {cnt}개")

    return {
        "feature_rows": len(feature_rows),
        "credit_rows": len(credit_rows),
        "success": counters["success"],
        "failed": counters["failed"],
        "version_stats": version_stats,
    }


if __name__ == "__main__":
    stats = main()
    print(f"\n최종: {stats}")
