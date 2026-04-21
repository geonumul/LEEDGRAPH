"""
Phase 6 - 전체 460개 전수 실행 (신규 V2 파이프라인: rule + 의무 LLM 검증)

출력:
    data/processed/project_features_v2.parquet
    data/processed/standardized_credits_v2.parquet
    outputs/phase_E/llm_validation_log.csv
    outputs/phase_E/standardized_credits_checkpoint.parquet (중간 저장)
    outputs/phase_E/pipeline_v2_errors.log

재개 옵션: python scripts/run_pipeline_v2.py --resume
"""

import os
import sys
import json
import logging
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import pandas as pd
from src.langgraph_workflow.graph import run_standardization
from src.data.loader import LEEDDataLoader

SCORECARD_DIR = Path("data/raw/scorecards")
PROCESSED_DIR = Path("data/processed")
OUT_DIR       = Path("outputs/phase_E")
CKPT_FEAT     = OUT_DIR / "checkpoint_features.parquet"
CKPT_CRED     = OUT_DIR / "checkpoint_credits.parquet"
CKPT_LOG      = OUT_DIR / "llm_validation_log.csv"
ERROR_LOG     = OUT_DIR / "pipeline_v2_errors.log"

OUT_DIR.mkdir(parents=True, exist_ok=True)
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    filename=str(ERROR_LOG),
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    encoding="utf-8",
)
logger = logging.getLogger(__name__)


def build_credit_rows(project_id, version, leed_system, credit_mappings):
    rows = []
    for cm in credit_mappings:
        rows.append({
            "project_id":         project_id,
            "source_version":     version,
            "leed_system":        leed_system,
            "source_credit_name": cm.get("credit_name", ""),
            "source_category":    None,
            "v5_credit_code":     cm.get("v5_code", "UNKNOWN"),
            "v5_category":        cm.get("v5_category"),
            "points_awarded":     cm.get("awarded", 0),
            "points_possible":    cm.get("possible", 0),
            "mapping_method":     "rule" if cm.get("matched") else "unmatched",
            "confidence":         cm.get("confidence"),
        })
    return rows


def save_checkpoint(feat_rows, cred_rows, log_rows):
    if feat_rows:
        pd.DataFrame(feat_rows).to_parquet(CKPT_FEAT, index=False)
    if cred_rows:
        pd.DataFrame(cred_rows).to_parquet(CKPT_CRED, index=False)
    if log_rows:
        pd.DataFrame(log_rows).to_csv(CKPT_LOG, index=False, encoding="utf-8-sig")


def load_checkpoint():
    feat_rows, cred_rows, log_rows = [], [], []
    processed_pdfs = set()
    if CKPT_FEAT.exists():
        feat_rows = pd.read_parquet(CKPT_FEAT).to_dict("records")
    if CKPT_CRED.exists():
        cred_rows = pd.read_parquet(CKPT_CRED).to_dict("records")
    if CKPT_LOG.exists():
        df = pd.read_csv(CKPT_LOG)
        log_rows = df.to_dict("records")
        processed_pdfs = set(df["pdf"].astype(str))
    return feat_rows, cred_rows, log_rows, processed_pdfs


def main(resume: bool = False):
    print("=" * 60)
    print("  Phase 6 - Full 460 run (V2 pipeline)")
    print("=" * 60)

    loader = LEEDDataLoader()
    try:
        csv_df = loader.load_project_directory()
    except Exception as e:
        csv_df = None
        logger.warning(f"CSV 로딩 실패: {e}")

    pdf_files = sorted(SCORECARD_DIR.glob("*.pdf"))
    total = len(pdf_files)
    print(f"PDF 총 {total}개")

    if resume:
        feat_rows, cred_rows, log_rows, processed = load_checkpoint()
        print(f"Resume: 이미 처리된 {len(processed)}건 skip")
    else:
        feat_rows, cred_rows, log_rows, processed = [], [], [], set()

    counters = {"success": 0, "failed": 0, "rule_path": 0, "llm_path": 0,
                "val_rule_pass": 0, "val_rule_fail": 0, "val_llm_pass": 0, "val_llm_fail": 0}

    for i, pdf in enumerate(pdf_files, 1):
        fname = pdf.name
        if fname in processed:
            continue
        if i % 5 == 0 or i == 1 or i == total:
            print(f"[{i:3d}/{total}] {fname[:60]}", flush=True)

        try:
            state = run_standardization(pdf_path=str(pdf), directory_df=csv_df)
            final = state.get("final_v5_data") or {}
            if state.get("status") != "completed":
                raise RuntimeError(f"status={state.get('status')}")

            project = state.get("project", {})
            rule_r  = state.get("rule_mapping_result", {}) or {}
            math_r  = state.get("math_validation_result", {}) or {}
            val_r   = state.get("validation_result", {}) or {}

            version     = final.get("original_version", "unknown")
            project_id  = final.get("project_id", fname)
            leed_system = final.get("leed_system", "")
            track       = final.get("standardization_track", "rule")

            feat_rows.append({
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
                "drift":                math_r.get("ratio_drift", 0),
                "credit_rule_hit_rate": rule_r.get("credit_rule_hit_rate", None),
                "llm_val_target":       val_r.get("target"),
                "llm_val_is_valid":     val_r.get("is_valid"),
                "llm_val_score":        val_r.get("validation_score"),
                **{k: v for k, v in final.items() if k.startswith("ratio_")},
                **{k: v for k, v in final.items() if k.startswith("score_v5_")},
            })

            cm = rule_r.get("credit_mappings", [])
            if cm:
                cred_rows.extend(build_credit_rows(project_id, version, leed_system, cm))
            else:
                for cat in rule_r.get("mapped_categories", {}):
                    cred_rows.append({
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

            log_rows.append({
                "pdf": fname,
                "project_id": project_id,
                "version": version,
                "certification_level": final.get("certification_level", ""),
                "drift": math_r.get("ratio_drift", 0),
                "val_target": val_r.get("target"),
                "val_is_valid": val_r.get("is_valid"),
                "val_score": val_r.get("validation_score"),
                "val_issues": "; ".join(val_r.get("issues", []))[:300],
                "val_feedback": (val_r.get("feedback") or "")[:300],
                "final_track": track,
                "iterations": state.get("current_iteration", 0),
            })

            counters["success"] += 1
            counters["rule_path" if track == "rule" else "llm_path"] += 1
            if val_r.get("target") == "rule":
                counters["val_rule_pass" if val_r.get("is_valid") else "val_rule_fail"] += 1
            elif val_r.get("target") == "llm":
                counters["val_llm_pass" if val_r.get("is_valid") else "val_llm_fail"] += 1

        except Exception as e:
            counters["failed"] += 1
            logger.warning(f"{fname}: {type(e).__name__}: {e}")

        # 5건마다 체크포인트 (세션 끊김 방지)
        if i % 5 == 0:
            save_checkpoint(feat_rows, cred_rows, log_rows)
            print(f"  체크포인트 저장 ({i}/{total})", flush=True)

    # 최종 저장
    save_checkpoint(feat_rows, cred_rows, log_rows)

    # processed/ 에 최종 parquet
    if feat_rows:
        pd.DataFrame(feat_rows).to_parquet(PROCESSED_DIR / "project_features_v2.parquet", index=False)
    if cred_rows:
        pd.DataFrame(cred_rows).to_parquet(PROCESSED_DIR / "standardized_credits_v2.parquet", index=False)

    print(f"\n완료: {counters}")
    logger.info(f"Phase 6 완료: {counters}")
    return counters


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    main(resume=args.resume)
