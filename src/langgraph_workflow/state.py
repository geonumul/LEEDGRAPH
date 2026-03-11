"""
LangGraph State 정의
- LEED 버전 표준화 워크플로우에서 공유되는 상태
"""

from typing import TypedDict, Annotated, Optional
import operator


class ProjectData(TypedDict):
    """개별 LEED 프로젝트 데이터"""
    project_id: str
    project_name: str
    version: str                    # 원본 버전 (v2.2, v3, v4 등)
    building_type: str
    gross_area_sqm: float
    certification_level: str        # 원본 등급
    categories: dict                # 원본 카테고리별 점수
    total_score_raw: float          # 원본 총점


class MappingResult(TypedDict):
    """Mapper Agent의 카테고리 매핑 결과"""
    mapped_categories: dict         # v5 기준으로 매핑된 카테고리 점수
    mapping_rationale: str          # 매핑 근거 설명
    proportional_scores: dict       # 비율 환산 점수
    total_score_v5: float           # v5 환산 총점


class ValidationResult(TypedDict):
    """Validator Agent의 검증 결과"""
    is_valid: bool                  # 검증 통과 여부
    validation_score: float         # 검증 품질 점수 (0~1)
    issues: list                    # 발견된 문제점 목록
    feedback: str                   # Mapper에게 전달할 피드백
    iteration: int                  # 현재 반복 횟수


class LEEDStandardizationState(TypedDict):
    """
    LangGraph 전체 워크플로우 공유 State.

    흐름:
        [Mapper Agent] → [Validator Agent] → 검증 통과? → END
                              ↑                   ↓ No
                              └───────────────────┘ (순환)
    """
    # 입력 데이터
    project: ProjectData

    # Mapper 출력 (매핑 결과)
    mapping_result: Optional[MappingResult]

    # Validator 출력 (검증 결과)
    validation_result: Optional[ValidationResult]

    # 반복 제어
    max_iterations: int             # 최대 반복 횟수 (기본 3)
    current_iteration: int          # 현재 반복 횟수

    # 최종 결과
    final_v5_data: Optional[dict]   # 최종 표준화된 v5 데이터
    status: str                     # "pending" | "completed" | "failed"

    # 로그 (Annotated로 append 방식 누적)
    logs: Annotated[list, operator.add]
