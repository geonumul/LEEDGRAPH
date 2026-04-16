"""
Phase 4 — 단일 PDF 신규 파이프라인(V2) 테스트

확인 항목:
  1. 노드 방문 순서 (hallucination_checker PASS 시 llm_validator 경유)
  2. validation_target이 "rule"으로 초기 세팅 → llm_validator가 rule 검증
  3. LLM이 rule 결과에 대해 어떤 피드백을 주는지
  4. 최종 final_v5_data
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import os
import json
from src.langgraph_workflow.graph import run_standardization
from src.data.loader import LEEDDataLoader


def main():
    # v2009 PDF 1개 선택 (매핑 복잡도 높은 버전)
    scorecard_dir = Path("data/raw/scorecards")
    candidates = sorted(scorecard_dir.glob("Scorecard_*.pdf"))

    # v2009 또는 v2.2 PDF 우선 - 그냥 첫 번째 PDF 사용
    pdf_path = candidates[0]
    print(f"[Phase 4 Test] 대상 PDF: {pdf_path.name}")
    print(f"[Phase 4 Test] API KEY: {'SET' if os.environ.get('OPENAI_API_KEY') else 'NOT SET'}")

    try:
        csv_df = LEEDDataLoader().load_project_directory()
    except Exception as e:
        print(f"[경고] CSV 로딩 실패: {e}")
        csv_df = None

    state = run_standardization(pdf_path=str(pdf_path), directory_df=csv_df)

    print("\n" + "=" * 70)
    print("  [1] 노드 방문 로그")
    print("=" * 70)
    for log in state.get("logs", []):
        print(f"  {log}")

    print("\n" + "=" * 70)
    print("  [2] validation_target")
    print("=" * 70)
    print(f"  validation_target: {state.get('validation_target')}")
    print(f"  validation_mode:   {state.get('validation_mode')}")
    print(f"  current_iteration: {state.get('current_iteration')}")

    print("\n" + "=" * 70)
    print("  [3] Rule 매핑 결과")
    print("=" * 70)
    rule = state.get("rule_mapping_result", {})
    print(f"  카테고리: {rule.get('mapped_categories', {})}")
    print(f"  v5 총점: {rule.get('total_score_v5', '?')}")
    print(f"  credit_rule_hit_rate: {rule.get('credit_rule_hit_rate', 'N/A')}")

    print("\n" + "=" * 70)
    print("  [4] 수학 검증")
    print("=" * 70)
    math = state.get("math_validation_result", {})
    print(f"  passed: {math.get('passed')}")
    print(f"  ratio_drift: {math.get('ratio_drift')}")
    print(f"  issues: {math.get('issues', [])}")

    print("\n" + "=" * 70)
    print("  [5] LLM Validator 결과")
    print("=" * 70)
    val = state.get("validation_result")
    if val is None:
        print("  (LLM Validator가 호출되지 않음 — API KEY 없거나 math FAIL)")
    else:
        print(f"  target:           {val.get('target')}")
        print(f"  is_valid:         {val.get('is_valid')}")
        print(f"  validation_score: {val.get('validation_score')}")
        print(f"  issues:")
        for i in val.get("issues", []):
            print(f"    - {i}")
        print(f"  feedback:         {val.get('feedback', '')[:400]}")

    print("\n" + "=" * 70)
    print("  [6] 최종 v5 결과")
    print("=" * 70)
    final = state.get("final_v5_data", {}) or {}
    print(f"  project_name:          {final.get('project_name')}")
    print(f"  original_version:      {final.get('original_version')}")
    print(f"  certification_level:   {final.get('certification_level')}")
    print(f"  total_score_v5:        {final.get('total_score_v5')}")
    print(f"  achievement_ratio_v5:  {final.get('achievement_ratio_v5')}")
    print(f"  standardization_track: {final.get('standardization_track')}")
    print(f"  status:                {state.get('status')}")

    print("\n" + "=" * 70)
    print(f"  완료 — 노드 순서 요약")
    print("=" * 70)
    logs = state.get("logs", [])
    order = [l.split("]")[0].lstrip("[") for l in logs if "]" in l]
    print("  " + " → ".join(order))


if __name__ == "__main__":
    main()
