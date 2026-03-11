"""
LangGraph 노드 정의
- Mapper Agent: 구버전 카테고리 → v5 카테고리 매핑
- Validator Agent: 매핑 결과 건축 환경적 타당성 검증
"""

import json
from typing import Any
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from .state import LEEDStandardizationState

# ─────────────────────────────────────────────────────────
# LLM 초기화
# ─────────────────────────────────────────────────────────
def get_llm(model: str = "gpt-4.1", temperature: float = 0.1) -> ChatOpenAI:
    """LLM 인스턴스 생성"""
    return ChatOpenAI(model=model, temperature=temperature)


# ─────────────────────────────────────────────────────────
# LEED 버전별 카테고리 매핑 가이드 (하드코딩 레퍼런스)
# ─────────────────────────────────────────────────────────
VERSION_MAPPING_GUIDE = {
    "v2.2": {
        "SS → SS": "Sustainable Sites 항목. v2.2(14pts) → v5(10pts). 교통 관련 항목은 v5의 LT로 이동됨.",
        "WE → WE": "Water Efficiency. v2.2(5pts) → v5(12pts). 기준 강화됨.",
        "EA → EA": "Energy & Atmosphere. v2.2(17pts) → v5(33pts). 재생에너지 비중 확대.",
        "MR → MR": "Materials & Resources. v2.2(13pts) → v5(13pts). 유사 구조.",
        "IEQ → IEQ": "Indoor Environmental Quality. v2.2(15pts) → v5(16pts). 거의 동일.",
        "IN → IN": "Innovation. v2.2(5pts) → v5(6pts).",
        "SS → LT": "v2.2의 SS 내 교통 관련 항목(Alternative Transportation 등)을 v5의 LT로 매핑.",
        "없음 → IP": "Integrative Process는 v5 신설 항목. v2.2에 해당 없음 → 0점 처리.",
        "없음 → RP": "Regional Priority는 v3부터 추가. v2.2에 없음 → 0점 처리.",
    },
    "v3": {
        "SS → SS+LT": "v3의 SS는 교통 항목 포함. 교통 관련은 LT로, 나머지는 SS로 분리.",
        "WE → WE": "Water Efficiency. v3(10pts) → v5(12pts).",
        "EA → EA": "Energy & Atmosphere. v3(35pts) → v5(33pts). 거의 동일.",
        "MR → MR": "Materials & Resources. v3(14pts) → v5(13pts).",
        "IEQ → IEQ": "Indoor Environmental Quality. v3(15pts) → v5(16pts).",
        "IN → IN": "Innovation. v3(6pts) → v5(6pts). 동일.",
        "RP → RP": "Regional Priority. v3(4pts) → v5(4pts). 동일.",
        "없음 → IP": "Integrative Process는 v4부터 신설. v3에 없음 → 0점 처리.",
    },
    "v4": {
        "LT → LT": "Location & Transportation. v4(16pts) → v5(16pts). 동일.",
        "SS → SS": "Sustainable Sites. v4(10pts) → v5(10pts). 동일.",
        "WE → WE": "Water Efficiency. v4(11pts) → v5(12pts). 소폭 증가.",
        "EA → EA": "Energy & Atmosphere. v4(33pts) → v5(33pts). 동일.",
        "MR → MR": "Materials & Resources. v4(13pts) → v5(13pts). 동일.",
        "IEQ → IEQ": "Indoor Environmental Quality. v4(16pts) → v5(16pts). 동일.",
        "IN → IN": "Innovation. v4(6pts) → v5(6pts). 동일.",
        "RP → RP": "Regional Priority. v4(4pts) → v5(4pts). 동일.",
        "IP → IP": "Integrative Process. v4(2pts) → v5(2pts). 동일.",
    },
}


# ─────────────────────────────────────────────────────────
# Mapper Agent Node
# ─────────────────────────────────────────────────────────
def mapper_agent(state: LEEDStandardizationState) -> LEEDStandardizationState:
    """
    [Mapper Agent]
    역할: 구버전(v2.2/v3/v4) LEED 카테고리 점수를 v5 기준으로 매핑.

    - 비율 계산: (원본점수 / 버전최대점수) × v5최대점수
    - 버전별 카테고리 구조 차이를 LLM이 파악하여 적절히 분배
    - Validator의 피드백이 있으면 반영하여 재매핑
    """
    llm = get_llm()
    project = state["project"]
    version = project["version"]
    current_iter = state.get("current_iteration", 0)
    feedback = ""

    # Validator 피드백 있으면 반영
    if state.get("validation_result") and not state["validation_result"]["is_valid"]:
        feedback = f"\n\n이전 매핑의 문제점:\n{state['validation_result']['feedback']}"

    mapping_guide = VERSION_MAPPING_GUIDE.get(version, VERSION_MAPPING_GUIDE["v4"])
    guide_text = "\n".join([f"  - {k}: {v}" for k, v in mapping_guide.items()])

    system_prompt = """당신은 LEED(Leadership in Energy and Environmental Design) 인증 전문가입니다.
구버전 LEED 카테고리 점수를 최신 버전(v5) 기준으로 정확하게 매핑하는 것이 역할입니다.

반드시 JSON 형식으로만 응답하세요:
{
  "mapped_categories": {
    "LT": <점수>,
    "SS": <점수>,
    "WE": <점수>,
    "EA": <점수>,
    "MR": <점수>,
    "IEQ": <점수>,
    "IN": <점수>,
    "RP": <점수>,
    "IP": <점수>
  },
  "mapping_rationale": "<매핑 근거 설명>",
  "proportional_scores": {<비율 계산 상세>}
}"""

    user_prompt = f"""다음 LEED 프로젝트 데이터를 v5 기준으로 매핑해주세요.

프로젝트 정보:
- 버전: {version}
- 인증 등급: {project['certification_level']}
- 원본 총점: {project['total_score_raw']}
- 원본 카테고리 점수: {json.dumps(project['categories'], ensure_ascii=False)}

버전별 매핑 가이드:
{guide_text}

v5 카테고리 최대 점수:
- LT: 16, SS: 10, WE: 12, EA: 33, MR: 13, IEQ: 16, IN: 6, RP: 4, IP: 2 (합계: 110)

비율 계산 원칙: 각 카테고리에서 (획득점수 / 해당버전최대점수) × v5최대점수
{feedback}

JSON으로만 응답하세요."""

    response = llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ])

    # 응답 파싱
    try:
        response_text = response.content.strip()
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0].strip()

        parsed = json.loads(response_text)
        mapped_cats = parsed.get("mapped_categories", {})
        total_v5 = sum(mapped_cats.values())

        mapping_result = {
            "mapped_categories": mapped_cats,
            "mapping_rationale": parsed.get("mapping_rationale", ""),
            "proportional_scores": parsed.get("proportional_scores", {}),
            "total_score_v5": round(total_v5, 2),
        }

        log_entry = (
            f"[Iter {current_iter+1}] Mapper 완료 - "
            f"v5 총점: {total_v5:.1f}/110"
        )

    except Exception as e:
        # 파싱 실패 시 수학적 비율 계산으로 폴백
        from src.data.loader import LEED_VERSION_MAX_SCORES
        ver_max = LEED_VERSION_MAX_SCORES.get(version, LEED_VERSION_MAX_SCORES["v4"])
        v5_max = LEED_VERSION_MAX_SCORES["v5"]

        mapped_cats = {}
        for cat, v5_max_score in v5_max.items():
            if cat == "TOTAL":
                continue
            raw = project["categories"].get(cat, 0)
            ver_cat_max = ver_max.get(cat, v5_max_score)
            ratio = raw / ver_cat_max if ver_cat_max > 0 else 0
            mapped_cats[cat] = round(ratio * v5_max_score, 2)

        mapping_result = {
            "mapped_categories": mapped_cats,
            "mapping_rationale": f"파싱 실패({e}), 수학적 비율 계산 적용",
            "proportional_scores": {},
            "total_score_v5": round(sum(mapped_cats.values()), 2),
        }
        log_entry = f"[Iter {current_iter+1}] Mapper 폴백 적용 (파싱 오류)"

    return {
        **state,
        "mapping_result": mapping_result,
        "current_iteration": current_iter + 1,
        "logs": [log_entry],
    }


# ─────────────────────────────────────────────────────────
# Validator Agent Node
# ─────────────────────────────────────────────────────────
def validator_agent(state: LEEDStandardizationState) -> LEEDStandardizationState:
    """
    [Validator Agent]
    역할: Mapper의 매핑 결과가 건축 환경적으로 타당한지 교차 검증.

    검증 항목:
    1. v5 최대 점수 초과 여부
    2. 원본 총점 대비 v5 환산 총점의 비율 타당성
    3. 카테고리 간 점수 분포 이상치 탐지
    4. 건축 유형별 기대 점수 범위 준수 여부
    """
    llm = get_llm()
    project = state["project"]
    mapping = state["mapping_result"]
    current_iter = state.get("current_iteration", 0)
    max_iter = state.get("max_iterations", 3)

    # 최대 반복 횟수 초과 시 강제 통과
    if current_iter >= max_iter:
        validation_result = {
            "is_valid": True,
            "validation_score": 0.6,
            "issues": ["최대 반복 횟수 초과로 강제 승인"],
            "feedback": "",
            "iteration": current_iter,
        }
        return {
            **state,
            "validation_result": validation_result,
            "logs": [f"[Iter {current_iter}] 최대 반복 도달, 강제 승인"],
        }

    system_prompt = """당신은 LEED 인증 심사 전문가입니다.
제시된 버전 매핑 결과의 건축 환경적 타당성을 검증하세요.

반드시 JSON 형식으로만 응답하세요:
{
  "is_valid": true/false,
  "validation_score": 0.0~1.0,
  "issues": ["문제점1", "문제점2"],
  "feedback": "Mapper Agent에게 전달할 개선 지시사항"
}"""

    user_prompt = f"""다음 LEED 버전 매핑 결과를 검증해주세요.

원본 프로젝트:
- 버전: {project['version']}
- 인증 등급: {project['certification_level']}
- 원본 총점: {project['total_score_raw']}
- 원본 카테고리: {json.dumps(project['categories'], ensure_ascii=False)}

매핑 결과 (v5 기준):
- v5 총점: {mapping['total_score_v5']}
- 카테고리별 점수: {json.dumps(mapping['mapped_categories'], ensure_ascii=False)}
- 매핑 근거: {mapping['mapping_rationale']}

검증 기준:
1. v5 카테고리 최대 점수 초과 금지 (LT:16, SS:10, WE:12, EA:33, MR:13, IEQ:16, IN:6, RP:4, IP:2)
2. 원본 등급({project['certification_level']})과 v5 환산 총점의 일관성
   - Certified: 40~49점, Silver: 50~59점, Gold: 60~79점, Platinum: 80+점
3. 카테고리 점수가 음수이거나 최대값을 극단적으로 초과하지 않는지 확인
4. 원본 버전의 총점 달성률과 v5 총점 달성률이 크게 다르지 않은지 확인

validation_score >= 0.8이면 is_valid=true로 설정하세요.
JSON으로만 응답하세요."""

    response = llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ])

    try:
        response_text = response.content.strip()
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0].strip()

        parsed = json.loads(response_text)
        validation_result = {
            "is_valid": parsed.get("is_valid", False),
            "validation_score": parsed.get("validation_score", 0.0),
            "issues": parsed.get("issues", []),
            "feedback": parsed.get("feedback", ""),
            "iteration": current_iter,
        }

        status = "통과" if validation_result["is_valid"] else "재검토 필요"
        log_entry = (
            f"[Iter {current_iter}] Validator {status} "
            f"(score: {validation_result['validation_score']:.2f})"
        )

    except Exception as e:
        # 파싱 실패 시 기본 검증 로직으로 폴백
        mapped = mapping["mapped_categories"]
        v5_max = {"LT": 16, "SS": 10, "WE": 12, "EA": 33, "MR": 13, "IEQ": 16, "IN": 6, "RP": 4, "IP": 2}
        issues = []

        for cat, score in mapped.items():
            max_s = v5_max.get(cat, 0)
            if score > max_s:
                issues.append(f"{cat} 점수({score}) > 최대값({max_s})")
            if score < 0:
                issues.append(f"{cat} 점수가 음수({score})")

        is_valid = len(issues) == 0
        validation_result = {
            "is_valid": is_valid,
            "validation_score": 0.9 if is_valid else 0.5,
            "issues": issues if issues else [],
            "feedback": "; ".join(issues) if issues else "",
            "iteration": current_iter,
        }
        log_entry = f"[Iter {current_iter}] Validator 폴백 적용 (파싱 오류: {e})"

    return {
        **state,
        "validation_result": validation_result,
        "logs": [log_entry],
    }


# ─────────────────────────────────────────────────────────
# Finalize Node
# ─────────────────────────────────────────────────────────
def finalize_node(state: LEEDStandardizationState) -> LEEDStandardizationState:
    """
    [Finalize Node]
    검증 통과 후 최종 v5 표준화 데이터를 State에 저장.
    """
    project = state["project"]
    mapping = state["mapping_result"]

    final_data = {
        "project_id": project.get("project_id", ""),
        "project_name": project.get("project_name", ""),
        "original_version": project["version"],
        "building_type": project.get("building_type", ""),
        "gross_area_sqm": project.get("gross_area_sqm", 0),
        "certification_level": project["certification_level"],
        "total_score_v5": mapping["total_score_v5"],
        **{f"score_v5_{k}": v for k, v in mapping["mapped_categories"].items()},
        "mapping_rationale": mapping["mapping_rationale"],
        "standardization_iterations": state.get("current_iteration", 1),
    }

    return {
        **state,
        "final_v5_data": final_data,
        "status": "completed",
        "logs": [f"표준화 완료 - v5 총점: {mapping['total_score_v5']:.1f}"],
    }
