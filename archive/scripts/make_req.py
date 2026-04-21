"""
전체 파이프라인 테스트 - LLM 호출 없음 (rule 경로만)
"""
import sys
sys.path.insert(0, 'd:/RAG/LEEDGRAPH')

# ── 1. 그래프 컴파일 확인 ─────────────────────────────────────────────────
print("=== 1. 그래프 컴파일 ===")
from src.langgraph_workflow.graph import build_standardization_graph, run_standardization
graph = build_standardization_graph()
print(f"노드: {list(graph.nodes.keys())}")

# ── 2. PDF 파싱 + IEQ 수정 확인 ──────────────────────────────────────────
print("\n=== 2. PDF 파싱 (IEQ 포함) ===")
from src.data.loader import LEEDDataLoader
loader = LEEDDataLoader()
parsed = loader.parse_scorecard_pdf('data/raw/scorecards/Scorecard.pdf')
print(f"버전: {parsed['version']}")
print(f"총점: {parsed['total_awarded']}/{parsed['total_possible']}")
print(f"카테고리: {parsed['categories']}")
print(f"크레딧 수: {len(parsed['credits'])}")
missing = [c for c in ['SS','WE','EA','MR','IEQ','LT','IN','RP'] if c not in parsed['categories']]
print(f"누락 카테고리: {missing if missing else '없음'}")

# ── 3. Rule Mapper 단독 테스트 ───────────────────────────────────────────
print("\n=== 3. Rule Mapper (LLM 없음) ===")
from src.langgraph_workflow.nodes import rule_mapper_node, hallucination_checker_node
from src.data.loader import LEEDDataLoader
import pandas as pd

df = LEEDDataLoader().load_project_directory()
matched = loader.match_scorecard_to_directory(parsed, df)
cats = {cat: s['awarded'] for cat, s in parsed['categories'].items()}
cats_possible = {cat: s['possible'] for cat, s in parsed['categories'].items()}

project = {
    'project_id': parsed['project_id'],
    'project_name': parsed['project_name'],
    'version': parsed['version'],
    'leed_system': parsed.get('leed_system', ''),
    'building_type': str(matched.get('ProjectTypes', '')) if matched else '',
    'gross_area_sqm': 0,
    'certification_level': parsed['certification_level'],
    'categories': cats,
    'credits': parsed['credits'],
    'categories_possible': cats_possible,
    'total_score_raw': float(parsed['total_awarded']),
}

fake_state = {
    'project': project,
    'pdf_path': None, 'directory_df': None, 'parsed_pdf': None,
    'matched_building': None, 'rule_mapping_result': None,
    'math_validation_result': None, 'mapping_result': None,
    'validation_result': None, 'validation_mode': 'rule',
    'max_iterations': 3, 'current_iteration': 0,
    'final_v5_data': None, 'status': 'pending', 'logs': [],
}

# rule_mapper 실행
state_after_mapper = rule_mapper_node(fake_state)
rm = state_after_mapper['rule_mapping_result']
print(f"v5 매핑 결과: {rm['mapped_categories']}")
print(f"v5 총점: {rm['total_score_v5']}")
print(f"근거: {rm['mapping_rationale']}")

# hallucination_checker 실행
state_after_check = hallucination_checker_node(state_after_mapper)
math = state_after_check['math_validation_result']
print(f"\n=== 4. Hallucination Check ===")
print(f"PASS: {math['passed']}")
print(f"달성률: 원본={math['achievement_ratio_original']:.1%}, v5={math['achievement_ratio_v5']:.1%}")
print(f"드리프트: {math['ratio_drift']:.1%}")
if math['issues']:
    print(f"문제: {math['issues']}")

print("\n=== 로그 ===")
for log in state_after_mapper['logs'] + state_after_check['logs']:
    print(f"  {log}")
