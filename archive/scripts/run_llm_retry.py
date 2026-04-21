"""
LLM 경로 건물 재처리 스크립트 (Rate Limit 대응)

대상 선정 (2가지):
  1. pipeline_errors.log 에서 429 에러가 발생한 PDF 파일
  2. project_features.parquet 에서 drift > 0.20 + standardization_track == "rule" 인 건물
     (위와 겹치지 않는 것만 추가)

재처리 후:
  - project_features.parquet 해당 project_id 행 업데이트
  - standardized_credits.parquet 해당 project_id 행 업데이트
  - outputs/phase_C/llm_retry_result.log 기록
"""

import os
import re
import sys
import json
import logging
import time
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

# ── 경로 ─────────────────────────────────────────────────────────────────────
SCORECARD_DIR = Path("data/raw/scorecards")
PROCESSED_DIR = Path("data/processed")
OUTPUT_DIR    = Path("outputs/phase_C")
ERROR_LOG     = OUTPUT_DIR / "pipeline_errors.log"
RETRY_LOG     = OUTPUT_DIR / "llm_retry_result.log"

logging.basicConfig(
    filename=str(RETRY_LOG),
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    encoding="utf-8",
    filemode="w",
)
logger = logging.getLogger(__name__)

DRIFT_THRESHOLD = 0.20


def get_retry_targets() -> list[Path]:
    """재처리 대상 PDF 목록 수집."""
    targets: set[str] = set()

    # 1) pipeline_errors.log 에서 429 에러 파일 추출
    if ERROR_LOG.exists():
        with open(ERROR_LOG, encoding="utf-8", errors="replace") as f:
            for line in f:
                if "429" in line or "rate_limit" in line.lower():
                    m = re.search(r"\[WARNING\] (Scorecard_[^\s:]+\.pdf)", line)
                    if m:
                        targets.add(m.group(1))
        print(f"에러 로그에서 429 파일: {len(targets)}개")

    # 2) parquet 에서 drift > threshold + rule track 인 건물 project_name 으로 PDF 매핑
    feat_path = PROCESSED_DIR / "project_features.parquet"
    if feat_path.exists():
        feat_df = pd.read_parquet(feat_path)
        high_drift = feat_df[
            (feat_df["drift"] > DRIFT_THRESHOLD) &
            (feat_df["standardization_track"] == "rule")
        ]
        print(f"parquet drift>{DRIFT_THRESHOLD:.0%} + rule: {len(high_drift)}개")

        # project_name → PDF 파일명 매핑 (퍼지 매칭)
        all_pdfs = {p.name: p for p in SCORECARD_DIR.glob("*.pdf")}
        for _, row in high_drift.iterrows():
            pname = str(row.get("project_name", "")).lower().replace(" ", "")
            for fname in all_pdfs:
                fname_lower = fname.lower().replace("scorecard_", "").replace(".pdf", "")
                fname_lower = fname_lower.replace("_", "").replace("-", "")
                if pname and len(pname) > 5 and pname[:8] in fname_lower:
                    targets.add(fname)
                    break

    # 3) PDF 파일 객체로 변환
    all_pdf_map = {p.name: p for p in SCORECARD_DIR.glob("*.pdf")}
    result = []
    not_found = []
    for fname in sorted(targets):
        if fname in all_pdf_map:
            result.append(all_pdf_map[fname])
        else:
            not_found.append(fname)

    if not_found:
        print(f"[경고] PDF 파일 없음: {not_found}")

    return result


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


def main():
    print("=" * 60)
    print("  LLM Retry - Rate Limit 대응 재처리")
    print("=" * 60)

    # 기존 parquet 로드
    feat_path = PROCESSED_DIR / "project_features.parquet"
    cred_path = PROCESSED_DIR / "standardized_credits.parquet"

    if not feat_path.exists():
        print("[오류] project_features.parquet 없음. run_pipeline.py 먼저 실행하세요.")
        sys.exit(1)

    feat_df = pd.read_parquet(feat_path)
    cred_df = pd.read_parquet(cred_path) if cred_path.exists() else pd.DataFrame()

    print(f"\n기존 parquet: {len(feat_df)}개 건물")
    print(f"  track: {feat_df['standardization_track'].value_counts().to_dict()}")
    print(f"  drift>20%: {(feat_df['drift'] > DRIFT_THRESHOLD).sum()}개")

    # CSV 로딩
    loader = LEEDDataLoader()
    try:
        csv_df = loader.load_project_directory()
        print(f"  CSV: {len(csv_df)}개 프로젝트")
    except Exception as e:
        csv_df = None
        print(f"  [경고] CSV 로딩 실패: {e}")

    # 재처리 대상
    target_pdfs = get_retry_targets()
    total = len(target_pdfs)
    print(f"\n재처리 대상: {total}개 PDF\n")

    if total == 0:
        print("재처리 대상 없음. 종료.")
        return

    # 재처리 실행
    new_feat_rows = []
    new_cred_rows = []
    processed_ids = set()
    counters = {"success": 0, "failed": 0, "llm": 0, "rule": 0}

    for i, pdf_path in enumerate(target_pdfs, 1):
        fname = pdf_path.name
        print(f"[{i:2d}/{total}] {fname[:65]}")

        try:
            state = run_standardization(pdf_path=str(pdf_path), directory_df=csv_df)

            status = state.get("status", "unknown")
            if status != "completed":
                raise RuntimeError(f"status={status}")

            final       = state["final_v5_data"]
            project     = state.get("project", {})
            rule_result = state.get("rule_mapping_result", {})
            math_result = state.get("math_validation_result", {})

            version     = final.get("original_version", "unknown")
            project_id  = final.get("project_id", fname)
            leed_system = final.get("leed_system", "")
            track       = final.get("standardization_track", "rule")
            drift       = math_result.get("ratio_drift", 0)

            print(f"  -> {track.upper()} | drift={drift:.3f} | v5={final.get('total_score_v5', 0):.1f}")

            feat_row = {
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
                "drift":                drift,
                "credit_rule_hit_rate": rule_result.get("credit_rule_hit_rate", None),
                **{k: v for k, v in final.items() if k.startswith("ratio_")},
                **{k: v for k, v in final.items() if k.startswith("score_v5_")},
            }
            new_feat_rows.append(feat_row)
            processed_ids.add(str(project_id))

            cm = rule_result.get("credit_mappings", [])
            if cm:
                new_cred_rows.extend(build_credit_rows(project_id, version, leed_system, cm))
            else:
                for cat, score in rule_result.get("mapped_categories", {}).items():
                    new_cred_rows.append({
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
            logger.info(
                f"{'LLM' if track=='llm' else 'rule'} 처리: {fname} | "
                f"drift={drift:.3f} | v5={final.get('total_score_v5',0):.1f}"
            )

        except Exception as e:
            counters["failed"] += 1
            logger.warning(f"실패: {fname} | {type(e).__name__}: {e}")
            print(f"  -> 실패: {type(e).__name__}: {str(e)[:80]}")

    print(f"\n재처리 결과: {counters['success']}/{total} 성공 "
          f"(llm={counters.get('llm',0)}, rule={counters.get('rule',0)}, "
          f"실패={counters['failed']})")

    # 5. parquet 업데이트 (처리된 project_id 행 교체)
    if new_feat_rows:
        new_feat_df = pd.DataFrame(new_feat_rows)

        # 기존 parquet 에서 재처리된 project_id 제거 후 new 로 교체
        feat_updated = feat_df[~feat_df["project_id"].astype(str).isin(processed_ids)]
        feat_final   = pd.concat([feat_updated, new_feat_df], ignore_index=True)
        feat_final.to_parquet(feat_path, index=False)

        if new_cred_rows and not cred_df.empty:
            new_cred_df  = pd.DataFrame(new_cred_rows)
            cred_updated = cred_df[~cred_df["project_id"].astype(str).isin(processed_ids)]
            cred_final   = pd.concat([cred_updated, new_cred_df], ignore_index=True)
            cred_final.to_parquet(cred_path, index=False)
        elif new_cred_rows:
            pd.DataFrame(new_cred_rows).to_parquet(cred_path, index=False)

        print(f"\nproject_features.parquet 업데이트: {len(feat_final)}행")
        print(f"  track: {feat_final['standardization_track'].value_counts().to_dict()}")
        print(f"  drift>20%: {(feat_final['drift'] > DRIFT_THRESHOLD).sum()}개")
        logger.info(
            f"parquet 업데이트 완료: {len(feat_final)}행, "
            f"llm={feat_final[feat_final['standardization_track']=='llm'].shape[0]}"
        )

    return counters


if __name__ == "__main__":
    result = main()
    print(f"\n최종: {result}")
