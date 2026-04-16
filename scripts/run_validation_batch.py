"""
Phase 5 - 10개 샘플 배치 검증 (비용·품질 체감)

대상: 버전 골고루 섞이게 10개 샘플링
출력:
    outputs/phase_E/validation_batch_10.csv
    outputs/phase_E/validation_batch_10_summary.md
"""

import sys
import time
import json
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
OUT_DIR = Path("outputs/phase_E")
OUT_DIR.mkdir(parents=True, exist_ok=True)


def sample_pdfs_by_version() -> list[Path]:
    """기존 parquet에서 버전별로 PDF 추출 - 다양성 확보."""
    feat = pd.read_parquet("data/processed/project_features.parquet")

    # 버전별 2~3개씩 project_name 추출
    targets = []
    for ver, n in [("v2.2", 2), ("v2009", 3), ("v4", 3), ("v4.1", 2)]:
        subset = feat[feat["original_version"] == ver].head(n)
        targets.extend(subset["project_name"].tolist())

    # PDF 파일과 매칭
    all_pdfs = {p.name: p for p in SCORECARD_DIR.glob("*.pdf")}
    matched = []
    for pname in targets:
        # project_name에서 공백 제거 후 PDF 파일명과 prefix 매칭
        needle = pname.replace(" ", "").lower()[:8]
        for fname, pth in all_pdfs.items():
            stem = fname.lower().replace("scorecard_", "").replace("_", "")
            if needle and needle in stem:
                matched.append(pth)
                break
    return matched[:10]


def main():
    print("=" * 60)
    print("  Phase 5 - 10개 샘플 배치 검증")
    print("=" * 60)

    pdfs = sample_pdfs_by_version()
    print(f"\n샘플 PDF {len(pdfs)}개:")
    for p in pdfs:
        print(f"  - {p.name}")

    csv_df = LEEDDataLoader().load_project_directory()

    rows = []
    total_time = 0
    for i, pdf in enumerate(pdfs, 1):
        print(f"\n[{i}/{len(pdfs)}] {pdf.name}")
        t0 = time.time()
        try:
            state = run_standardization(pdf_path=str(pdf), directory_df=csv_df)
            elapsed = time.time() - t0
            total_time += elapsed

            final = state.get("final_v5_data", {}) or {}
            rule_r = state.get("rule_mapping_result", {}) or {}
            math_r = state.get("math_validation_result", {}) or {}
            val_r  = state.get("validation_result", {}) or {}

            row = {
                "pdf": pdf.name,
                "project_name": final.get("project_name", ""),
                "version": final.get("original_version", ""),
                "certification_level": final.get("certification_level", ""),
                "rule_total_v5": rule_r.get("total_score_v5", None),
                "rule_credit_hit_rate": rule_r.get("credit_rule_hit_rate", None),
                "math_passed": math_r.get("passed"),
                "math_drift": math_r.get("ratio_drift"),
                "val_target": val_r.get("target"),
                "val_is_valid": val_r.get("is_valid"),
                "val_score": val_r.get("validation_score"),
                "val_issues": "; ".join(val_r.get("issues", []))[:300],
                "val_feedback": (val_r.get("feedback") or "")[:400],
                "final_total_v5": final.get("total_score_v5"),
                "final_track": final.get("standardization_track"),
                "current_iteration": state.get("current_iteration", 0),
                "elapsed_s": round(elapsed, 1),
            }
            rows.append(row)
            print(f"  target={row['val_target']}, is_valid={row['val_is_valid']}, "
                  f"track={row['final_track']}, {elapsed:.1f}s")
        except Exception as e:
            rows.append({"pdf": pdf.name, "error": str(e)})
            print(f"  실패: {e}")

    # CSV 저장
    df = pd.DataFrame(rows)
    csv_path = OUT_DIR / "validation_batch_10.csv"
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"\nCSV 저장: {csv_path}")

    # 요약
    is_valid_rate = df["val_is_valid"].mean() if "val_is_valid" in df else None
    issues_all = []
    for s in df.get("val_issues", []):
        if isinstance(s, str):
            issues_all.extend([x.strip() for x in s.split(";") if x.strip()])

    from collections import Counter
    top_issues = Counter(issues_all).most_common(5)

    # 460건 추정
    avg_time = total_time / max(len(pdfs), 1)
    est_460_time_min = (avg_time * 460) / 60
    # 토큰 추정: validator 1 call (~2000 in + 500 out) + optional mapper call → ~4000 tokens avg
    # gpt-4.1 price: $5/1M in, $15/1M out → avg $0.015 per call, *460 = ~$7
    # V1(현재)에서 mapper + validator 호출이 평균 ~1.5회 이므로 유사

    summary_md = f"""# Phase 5 - 검증 배치 요약

- 샘플: **{len(pdfs)}개** (버전별 분산)
- **is_valid=True 비율**: {is_valid_rate:.1%} ({df['val_is_valid'].sum()}/{df['val_is_valid'].notna().sum()})
- 평균 실행 시간: **{avg_time:.1f}초** / 건
- 460건 예상 시간: **{est_460_time_min:.1f}분**
- 460건 예상 비용: **$6~12** (gpt-4.1, 호출당 ~4000 토큰 가정)

## is_valid=False 사례

{chr(10).join(f"- {r['project_name']} (v{r['version']}, {r['certification_level']}): {r['val_issues']}" for _, r in df.iterrows() if r.get('val_is_valid') is False)}

## 상위 issue 패턴

{chr(10).join(f"- ({c}) {iss}" for iss, c in top_issues)}

## 버전별 is_valid 비율

| 버전 | 건수 | is_valid=True |
|------|------|---------------|
"""
    for ver in df["version"].unique():
        sub = df[df["version"] == ver]
        n_valid = sub["val_is_valid"].sum()
        summary_md += f"| {ver} | {len(sub)} | {n_valid}/{sub['val_is_valid'].notna().sum()} |\n"

    md_path = OUT_DIR / "validation_batch_10_summary.md"
    md_path.write_text(summary_md, encoding="utf-8")
    print(f"\n요약 저장: {md_path}")
    print("\n" + summary_md)


if __name__ == "__main__":
    main()
