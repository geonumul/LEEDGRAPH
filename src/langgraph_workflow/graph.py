"""
LangGraph 그래프 구성
- Mapper → Validator → (조건부) 순환 또는 Finalize
"""

from langgraph.graph import StateGraph, END
from .state import LEEDStandardizationState
from .nodes import mapper_agent, validator_agent, finalize_node


def should_retry(state: LEEDStandardizationState) -> str:
    """
    [조건부 엣지 함수]
    Validator 검증 결과에 따라 다음 노드 결정.

    - 검증 통과(is_valid=True) → "finalize"
    - 검증 실패 + 반복 횟수 남음 → "mapper" (재매핑)
    - 최대 반복 초과 → "finalize" (강제 통과)
    """
    validation = state.get("validation_result")
    current_iter = state.get("current_iteration", 0)
    max_iter = state.get("max_iterations", 3)

    if validation is None:
        return "mapper"

    if validation["is_valid"] or current_iter >= max_iter:
        return "finalize"

    return "mapper"


def build_standardization_graph() -> StateGraph:
    """
    LEED 버전 표준화 LangGraph 워크플로우 구성.

    그래프 구조:
        START → mapper → validator → (조건부) → finalize → END
                   ↑                     ↓ (재시도)
                   └─────────────────────┘
    """
    graph = StateGraph(LEEDStandardizationState)

    # 노드 등록
    graph.add_node("mapper", mapper_agent)
    graph.add_node("validator", validator_agent)
    graph.add_node("finalize", finalize_node)

    # 엣지 연결
    graph.set_entry_point("mapper")
    graph.add_edge("mapper", "validator")

    # 조건부 엣지: Validator 결과에 따라 분기
    graph.add_conditional_edges(
        "validator",
        should_retry,
        {
            "mapper": "mapper",      # 검증 실패 → 재매핑
            "finalize": "finalize",  # 검증 통과 → 최종화
        },
    )
    graph.add_edge("finalize", END)

    return graph.compile()


def run_standardization(project_data: dict, max_iterations: int = 3) -> dict:
    """
    단일 프로젝트에 대해 버전 표준화 워크플로우 실행.

    Args:
        project_data: 단일 LEED 프로젝트 딕셔너리
        max_iterations: 최대 재시도 횟수

    Returns:
        dict: 표준화된 v5 데이터
    """
    graph = build_standardization_graph()

    initial_state: LEEDStandardizationState = {
        "project": project_data,
        "mapping_result": None,
        "validation_result": None,
        "max_iterations": max_iterations,
        "current_iteration": 0,
        "final_v5_data": None,
        "status": "pending",
        "logs": [],
    }

    final_state = graph.invoke(initial_state)
    return final_state


def run_batch_standardization(
    projects: list, max_iterations: int = 3, verbose: bool = True
) -> list:
    """
    여러 프로젝트에 대해 일괄 표준화 실행.

    Args:
        projects: 프로젝트 딕셔너리 리스트
        max_iterations: 최대 재시도 횟수
        verbose: 진행 상황 출력 여부

    Returns:
        list: 표준화된 v5 데이터 리스트
    """
    results = []
    total = len(projects)

    for i, project in enumerate(projects):
        if verbose:
            print(f"[{i+1}/{total}] 처리 중: {project.get('project_id', 'unknown')}")

        try:
            final_state = run_standardization(project, max_iterations)
            if final_state["final_v5_data"]:
                results.append(final_state["final_v5_data"])
                if verbose:
                    v5_total = final_state["final_v5_data"]["total_score_v5"]
                    iters = final_state["current_iteration"]
                    print(f"  완료 (v5 총점: {v5_total:.1f}, 반복: {iters}회)")
            else:
                if verbose:
                    print(f"  실패: {project.get('project_id')}")
        except Exception as e:
            if verbose:
                print(f"  오류: {e}")

    print(f"\n일괄 처리 완료: {len(results)}/{total}개 성공")
    return results
