"""
LangGraph 노드 정의

아키텍처 (2-track 설계):
    Track 1 - 결정론적 (LLM 없음, 토큰 소모 없음):
        pdf_ingest → csv_match → rule_mapper → hallucination_checker → finalize

    Track 2 - LLM 폴백 (Track 1 실패 시에만 진입):
        hallucination_checker FAIL → llm_mapper ⇄ llm_validator (최대 3회) → finalize

설계 원칙:
    - rule_mapper: 버전별 수식 기반 매핑. 비율 공식, 교통 크레딧 분리 등을 하드코딩.
    - hallucination_checker: LLM 없이 수학적 제약 조건만 검사.
    - llm_mapper / llm_validator: 규칙으로 풀 수 없는 엣지케이스(unknown 버전 등)만 처리.
"""

import json
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from .state import LEEDStandardizationState
from src.data.loader import LEEDDataLoader, LEED_VERSION_MAX_SCORES
from src.data.rubric_loader import load_all_rubrics, get_rubric_max

# 루브릭 캐시: 모듈 로딩 시 1회 스캔 (data/raw/rubrics/ 아래 xlsx 자동 감지)
# 파일이 없으면 빈 dict → 기존 hardcoded fallback으로 동작 (에러 없음)
_RUBRIC_CACHE: dict = load_all_rubrics()


# =============================================================================
# 상수: v5 카테고리 최대 점수 (BD+C 기준)
# LEED v5 BD+C New Construction 기준값 (2024 공식 발표)
# O+M / ID+C 등 시스템마다 달라질 수 있으나, 최종 표준화 목표 기준은 BD+C v5로 통일
# =============================================================================
V5_MAX: dict = {
    "LT":  16,   # Location & Transportation
    "SS":  10,   # Sustainable Sites
    "WE":  12,   # Water Efficiency
    "EA":  33,   # Energy & Atmosphere
    "MR":  13,   # Materials & Resources
    "IEQ": 16,   # Indoor Environmental Quality
    "IN":   6,   # Innovation
    "RP":   4,   # Regional Priority
    "IP":   2,   # Integrative Process
    # TOTAL = 110
}

# =============================================================================
# 상수: 버전별 BD+C 기준 카테고리 최대 점수
# 각 버전의 "원래" 만점 구조. 이 값으로 비율을 계산한 뒤 V5_MAX에 적용.
#
# [중요] LEED O+M / ID+C 등 시스템별 실제 만점은 다를 수 있음.
#         → PDF에서 "possible" 값을 파싱했다면, 이 테이블 대신 그 값을 우선 사용.
# =============================================================================
VERSION_BD_C_MAX: dict = {
    # ── 초기 버전 (총점 69점 체계) ────────────────────────────────────────
    # 교통(Transportation) 크레딧이 SS 안에 포함되어 있음.
    # v2.2 SS 총 14점 중 교통 관련 Credits 4.1~4.4 = 최대 7점 (아래 상세 참조)
    "v1.0 pilot": {"SS": 14, "WE": 5,  "EA": 17, "MR": 13, "IEQ": 15, "IN": 5},
    "v2.0":       {"SS": 14, "WE": 5,  "EA": 17, "MR": 13, "IEQ": 15, "IN": 5},
    "v2.2":       {"SS": 14, "WE": 5,  "EA": 17, "MR": 13, "IEQ": 15, "IN": 5},

    # ── LEED 2009 / v3 (총점 110점 체계) ─────────────────────────────────
    # SS 26점 중 교통 관련 Credits 4.1~4.4 = 최대 6점
    # RP(Regional Priority) 신설 (4점)
    "v2009": {"SS": 26, "WE": 10, "EA": 35, "MR": 14, "IEQ": 15, "IN": 6, "RP": 4},
    "v3":    {"SS": 26, "WE": 10, "EA": 35, "MR": 14, "IEQ": 15, "IN": 6, "RP": 4},

    # ── v4 (총점 110점 체계) ──────────────────────────────────────────────
    # LT(Location & Transportation) 카테고리 신설 → SS에서 분리됨
    # IP(Integrative Process) 신설 (2점)
    # WE가 11점 (v4.1/v5는 12점으로 증가)
    "v4":   {"LT": 16, "SS": 10, "WE": 11, "EA": 33, "MR": 13, "IEQ": 16, "IN": 6, "RP": 4, "IP": 2},

    # ── v4.1 (총점 110점 체계) ────────────────────────────────────────────
    # WE가 12점으로 증가 (v4의 11점 → v4.1의 12점)
    # 나머지는 v5와 동일 → 직접 매핑 가능
    "v4.1": {"LT": 16, "SS": 10, "WE": 12, "EA": 33, "MR": 13, "IEQ": 16, "IN": 6, "RP": 4, "IP": 2},

    # ── v5 (총점 110점 체계) ──────────────────────────────────────────────
    # v4.1과 구조 동일. 이미 v5 → 변환 없음.
    "v5":   {"LT": 16, "SS": 10, "WE": 12, "EA": 33, "MR": 13, "IEQ": 16, "IN": 6, "RP": 4, "IP": 2},
}

# =============================================================================
# 상수: 구버전 SS 내 교통 크레딧 최대 점수
# SS에서 LT로 분리할 때 사용. 실제 크레딧명 패턴은 아래 TRANSPORT_KEYWORDS 참조.
#
# [근거]
#   v2.2 SS Credits 4.1(1) + 4.2(1) + 4.3(3) + 4.4(2) = 7점
#   v2009/v3 SS Credits 4.1(6점 total) = 6점
#   (참고: USGBC LEED Reference Guide 각 버전 SS 챕터)
# =============================================================================
SS_TRANSPORT_MAX: dict = {
    "v1.0 pilot": 7,   # v2.2와 구조 동일로 추정
    "v2.0":       7,
    "v2.2":       7,   # Credits 4.1(1)+4.2(1)+4.3(3)+4.4(2) = 7
    "v2009":      6,   # Credit 4.1~4.4 합계 = 6
    "v3":         6,
}

# 교통 관련 크레딧을 판별할 키워드
# PDF의 credits 딕셔너리 키(크레딧명)를 소문자 비교
TRANSPORT_KEYWORDS: tuple = (
    "alternative transportation",
    "public transportation",
    "transit",
    "bicycle",
    "low-emitting",
    "fuel-efficient",
    "parking capacity",
    "green vehicles",
    "electric vehicle",
)

# 검증 허용 오차: 달성률(achieved/max) 변화가 이 값 초과 시 hallucination으로 판정
RATIO_DRIFT_THRESHOLD: float = 0.20   # 20%

# hallucination_checker 실패 시 LLM 폴백 허용 최대 반복 횟수
LLM_MAX_ITERATIONS: int = 3


# =============================================================================
# 헬퍼 함수
# =============================================================================

def _extract_transport_from_credits(credits: dict, version: str) -> float:
    """
    PDF에서 파싱된 개별 크레딧(credits)에서 교통 관련 점수 합산.

    PDF 스코어카드에 크레딧 상세 데이터가 있으면 정확하게 분리 가능.
    없으면 역사적 비율(SS_TRANSPORT_MAX 기반)로 추정.

    Args:
        credits: {"Credit: Alternative Transportation - ...": {"awarded": 1, "possible": 1}, ...}
        version: "v2.2" 등 원본 LEED 버전 문자열

    Returns:
        float: 교통 관련 크레딧 획득 점수 합계
    """
    if not credits:
        return 0.0

    total_transport = 0.0
    for credit_name, scores in credits.items():
        name_lower = credit_name.lower()
        if any(kw in name_lower for kw in TRANSPORT_KEYWORDS):
            total_transport += scores.get("awarded", 0)

    return total_transport


def _proportional(awarded: float, old_max: float, new_max: float) -> float:
    """
    비율 환산 공식: (획득점수 / 구버전최대) × 신버전최대

    단, 결과를 new_max로 클램핑하여 초과 방지.

    예시) v4 WE: awarded=8, old_max=11, new_max=12
         → 8/11 × 12 = 8.73 → round(8.73, 2) = 8.73
    """
    if old_max <= 0:
        return 0.0
    raw = (awarded / old_max) * new_max
    return round(min(raw, new_max), 2)


def _clamp(value: float, max_val: float) -> float:
    """값을 [0, max_val] 범위로 클램핑"""
    return round(max(0.0, min(value, max_val)), 2)


def get_llm(model: str = "gpt-4.1", temperature: float = 0.1) -> ChatOpenAI:
    """LLM 인스턴스 생성. LLM 노드에서만 호출됨."""
    return ChatOpenAI(model=model, temperature=temperature)


# =============================================================================
# Node 1: PDF Ingest
# =============================================================================

def pdf_ingest_node(state: LEEDStandardizationState) -> LEEDStandardizationState:
    """
    [PDF Ingest Node]
    역할: Scorecard PDF를 파싱하여 프로젝트 기초 정보와 카테고리/크레딧 점수 추출.
          pdf_path가 없으면 state의 project를 그대로 사용(수동 입력 모드).
    """
    pdf_path = state.get("pdf_path")
    if not pdf_path:
        return {**state, "logs": ["[PDF Ingest] pdf_path 없음 - project 직접 사용 모드"]}

    loader = LEEDDataLoader()
    try:
        parsed = loader.parse_scorecard_pdf(pdf_path)
        log = (
            f"[PDF Ingest] 완료 - {parsed.get('project_name', '?')} "
            f"(ID: {parsed.get('project_id', '?')}, 버전: {parsed.get('version', '?')}, "
            f"총점: {parsed.get('total_awarded', '?')}/{parsed.get('total_possible', '?')})"
        )
        return {**state, "parsed_pdf": parsed, "logs": [log]}
    except Exception as e:
        return {**state, "status": "failed", "logs": [f"[PDF Ingest] 오류: {e}"]}


# =============================================================================
# Node 2: CSV Match
# =============================================================================

def csv_match_node(state: LEEDStandardizationState) -> LEEDStandardizationState:
    """
    [CSV Match Node]
    역할: PDF에서 추출한 project_id를 PublicLEEDProjectDirectory CSV와 매칭.
          매칭 결과로 건물 메타데이터(면적, 건물유형 등)를 보완하고 project 필드 구성.

    매칭 우선순위:
        1. project_id 정확 매칭 (신뢰도 최고)
        2. 건물명 소문자 비교 매칭 (fallback)
        3. 매칭 실패 시 PDF 데이터만으로 project 구성

    [면적 변환]
        USGBC CSV의 GrossFloorArea는 sq ft 단위.
        → sq ft × 0.0929 = sqm 변환.
    """
    parsed = state.get("parsed_pdf")
    existing_project = state.get("project")

    # PDF 없이 project 직접 주어진 경우 건너뜀
    if not parsed and existing_project:
        return {**state, "logs": ["[CSV Match] 직접 project 사용 - 매칭 건너뜀"]}

    directory_df = state.get("directory_df")
    if directory_df is None:
        loader = LEEDDataLoader()
        try:
            directory_df = loader.load_project_directory()
        except Exception as e:
            return {**state, "logs": [f"[CSV Match] CSV 로딩 실패: {e}"]}

    loader = LEEDDataLoader()
    matched = loader.match_scorecard_to_directory(parsed, directory_df)

    # PDF 카테고리 → mapper용 형태로 변환 (awarded 값만 추출)
    raw_cats = parsed.get("categories", {})
    cats_for_mapper = {cat: scores.get("awarded", 0) for cat, scores in raw_cats.items()}

    # 기본값: PDF에서
    version = parsed.get("version", "unknown")
    cert_level = parsed.get("certification_level", "")
    total_score = float(parsed.get("total_score", 0))

    # CSV 매칭으로 보완
    if matched:
        cert_level = cert_level or str(matched.get("CertLevel", ""))
        total_score = total_score or float(matched.get("PointsAchieved", 0) or 0)
        if version == "unknown":
            version = str(matched.get("LEEDSystemVersion", "v4"))

    # 면적: sq ft → sqm 변환
    gross_area_sqm = 0.0
    if matched:
        try:
            area_val = float(matched.get("GrossFloorArea", 0) or 0)
            unit = str(matched.get("UnitOfMeasurement", "sq ft"))
            gross_area_sqm = area_val * 0.0929 if "ft" in unit else area_val
        except (ValueError, TypeError):
            gross_area_sqm = 0.0

    project = {
        "project_id":          parsed.get("project_id", ""),
        "project_name":        parsed.get("project_name", ""),
        "version":             version,
        "leed_system":         parsed.get("leed_system", ""),   # BD+C, O+M 등 시스템명 보존
        "building_type":       str(matched.get("ProjectTypes", "")) if matched else "",
        "gross_area_sqm":      gross_area_sqm,
        "certification_level": cert_level,
        "categories":          cats_for_mapper,
        "credits":             parsed.get("credits", {}),       # 크레딧 상세 (SS→LT 분리에 사용)
        "total_score_raw":     total_score,
        # PDF 카테고리의 possible(만점) 값도 보존 → rule_mapper에서 O+M 등 시스템별 만점에 활용
        "categories_possible": {cat: s.get("possible", 0) for cat, s in raw_cats.items()},
    }

    match_method = matched.get("_match_method", "none") if matched else "none"
    if matched:
        log = (
            f"[CSV Match] 매칭 성공 (방법: {match_method}) - "
            f"{project['project_name']} | 버전: {version} | 등급: {cert_level} "
            f"| 면적: {gross_area_sqm:.0f}sqm"
        )
    else:
        log = (
            f"[CSV Match] CSV 매칭 실패 - PDF 데이터만 사용 "
            f"({project['project_name']}, ID: {project['project_id']})"
        )

    return {
        **state,
        "matched_building": matched,
        "project":          project,
        "logs":             [log],
    }


# =============================================================================
# Node 3: Rule Mapper (결정론적 매핑 - LLM 없음)
# =============================================================================

def rule_mapper_node(state: LEEDStandardizationState) -> LEEDStandardizationState:
    """
    [Rule Mapper Node] - LLM 없음, 토큰 소모 없음

    역할: LEED 버전별 수식 기반 카테고리 매핑.
          모든 한국 LEED 인증 버전(v1.0 pilot ~ v4.1)을 v5 BD+C 기준으로 변환.

    매핑 전략 (버전별):
    ┌─────────────────────────────────────────────────────────────────────────┐
    │ v4.1, v5 → 직접 매핑 (구조 동일)                                        │
    │                                                                         │
    │ v4 → WE만 비율 환산 (11pt→12pt), 나머지 직접                            │
    │                                                                         │
    │ v2009/v3 → SS에서 교통 분리(SS_transport → LT),                         │
    │            WE/EA/MR/IEQ 비율 환산, RP 직접, IP=0                        │
    │                                                                         │
    │ v2.2/v2.0/v1.0 pilot → SS에서 교통 분리,                               │
    │                         WE/EA/MR/IEQ/IN 전부 비율 환산, RP=IP=0        │
    └─────────────────────────────────────────────────────────────────────────┘

    SS→LT 교통 분리 우선순위:
        1. PDF 크레딧 상세 데이터 있음 → 키워드 매칭으로 정확히 추출
        2. 크레딧 데이터 없음 → 버전별 역사적 평균 비율로 추정
           (v2.2: 교통max=7, v2009: 교통max=6 기준 비율 적용)

    [O+M 등 비-BD+C 시스템 처리]
        PDF의 categories_possible (스코어카드에 명시된 만점)이 BD+C 만점과
        다를 경우(예: O+M EA=56), 해당 카테고리에만 PDF possible 값을 사용.
        이렇게 하면 시스템별 만점 차이가 자동으로 반영됨.
    """
    project = state.get("project", {})
    version = project.get("version", "unknown")
    cats = project.get("categories", {})          # {카테고리: 획득점수}
    credits = project.get("credits", {})           # {크레딧명: {awarded, possible}}
    cats_possible = project.get("categories_possible", {})  # PDF에서 파싱한 만점
    leed_system = project.get("leed_system", "")

    # ── 버전별 BD+C 기준 만점 테이블 ──────────────────────────────────────
    # unknown 버전은 v4로 fallback (한국 건물 중 가장 많은 비중)
    bd_c_max = VERSION_BD_C_MAX.get(version, VERSION_BD_C_MAX["v4"])

    # ── 카테고리별 실제 만점 결정 ──────────────────────────────────────────
    # 우선순위:
    #   1. PDF possible (스코어카드에 명시된 값 - O+M/ID+C 등 시스템별 차이 자동 반영)
    #   2. 루브릭 xlsx 조회 (data/raw/rubrics/{version}/*.xlsx - 파일 있을 때만)
    #   3. 하드코딩 BD+C 기준 (VERSION_BD_C_MAX + V5_MAX 최후 fallback)
    def get_old_max(cat: str) -> float:
        pdf_possible = cats_possible.get(cat, 0)
        if pdf_possible > 0:
            return float(pdf_possible)
        rubric_max = get_rubric_max(_RUBRIC_CACHE, version, leed_system, cat)
        if rubric_max is not None and rubric_max > 0:
            return float(rubric_max)
        return float(bd_c_max.get(cat, V5_MAX.get(cat, 1)))

    # ── 1. 교통 크레딧 분리 (SS → SS + LT) ───────────────────────────────
    # v4 이상은 LT가 이미 독립 카테고리이므로 분리 불필요
    needs_lt_split = version in ("v1.0 pilot", "v2.0", "v2.2", "v2009", "v3")

    transport_awarded = 0.0
    transport_max = 0.0
    ss_pure_awarded = float(cats.get("SS", 0))
    ss_pure_max = get_old_max("SS")

    if needs_lt_split:
        # 우선 1: PDF 크레딧 상세 데이터로 정확히 추출
        transport_awarded = _extract_transport_from_credits(credits, version)

        if transport_awarded > 0:
            # 크레딧 데이터 기반 → 교통 만점도 같은 방식으로 추출
            transport_max = sum(
                s.get("possible", 0)
                for name, s in credits.items()
                if any(kw in name.lower() for kw in TRANSPORT_KEYWORDS)
            )
            transport_max = max(transport_max, 1.0)
            ss_pure_awarded = max(0.0, ss_pure_awarded - transport_awarded)
            ss_pure_max = max(0.0, ss_pure_max - transport_max)
            lt_source = "credit-exact"

        else:
            # 우선 2: 크레딧 데이터 없음 → 역사적 비율로 추정
            # v2.2/v2.0/v1.0: 교통max=7, v2009/v3: 교통max=6
            transport_max = float(SS_TRANSPORT_MAX.get(version, 6))
            ss_non_transport_max = max(0.0, ss_pure_max - transport_max)

            # SS 내 교통 점수 = 전체 SS 중 교통 비율만큼 가중
            if ss_pure_max > 0:
                transport_ratio = transport_max / ss_pure_max
                transport_awarded = round(ss_pure_awarded * transport_ratio, 2)
            else:
                transport_awarded = 0.0

            ss_pure_awarded = max(0.0, round(ss_pure_awarded - transport_awarded, 2))
            ss_pure_max = ss_non_transport_max
            lt_source = "ratio-estimated"

    # ── 2. v5 각 카테고리 점수 계산 ──────────────────────────────────────
    mapped: dict = {}

    if needs_lt_split:
        # LT: 분리된 교통 크레딧을 v5 LT 만점(16)으로 비율 환산
        mapped["LT"] = _proportional(transport_awarded, transport_max, V5_MAX["LT"])

        # SS: 순수 SS(교통 제외)를 v5 SS 만점(10)으로 비율 환산
        ss_non_transport_v5_base = {
            "v1.0 pilot": 7,   # 14 - 7 = 7 (교통 제외)
            "v2.0":       7,
            "v2.2":       7,   # 14 - 7 = 7
            "v2009":      20,  # 26 - 6 = 20
            "v3":         20,
        }.get(version, ss_pure_max)
        actual_ss_max = ss_pure_max if ss_pure_max > 0 else ss_non_transport_v5_base
        mapped["SS"] = _proportional(ss_pure_awarded, actual_ss_max, V5_MAX["SS"])

    elif version in ("v4", "v4.1", "v5"):
        # v4 이상: LT/SS 이미 분리됨 → 직접 또는 비율 환산
        lt_awarded = float(cats.get("LT", 0))
        lt_max = get_old_max("LT")
        mapped["LT"] = _proportional(lt_awarded, lt_max, V5_MAX["LT"])

        ss_awarded = float(cats.get("SS", 0))
        ss_max = get_old_max("SS")
        mapped["SS"] = _proportional(ss_awarded, ss_max, V5_MAX["SS"])

    else:
        # unknown 버전 fallback
        mapped["LT"] = 0.0
        mapped["SS"] = _proportional(float(cats.get("SS", 0)), get_old_max("SS"), V5_MAX["SS"])

    # ── WE ────────────────────────────────────────────────────────────────
    # v4: 11pt → v5: 12pt (소폭 증가)
    # v4.1/v5: 12pt → 12pt (동일)
    # 구버전: 5pt → 12pt (대폭 증가 - 수자원 기준 강화 반영)
    mapped["WE"] = _proportional(float(cats.get("WE", 0)), get_old_max("WE"), V5_MAX["WE"])

    # ── EA ────────────────────────────────────────────────────────────────
    # v2009/v3: 35pt → v5: 33pt (소폭 감소)
    # v2.2: 17pt → 33pt (에너지 기준 대폭 강화 반영)
    # O+M v4: 56pt → 33pt (O+M은 에너지 운영에 더 높은 비중 부여했으나 BD+C v5 기준으로 환산)
    mapped["EA"] = _proportional(float(cats.get("EA", 0)), get_old_max("EA"), V5_MAX["EA"])

    # ── MR ────────────────────────────────────────────────────────────────
    # v2009/v3: 14pt → 13pt (소폭 감소)
    # v2.2: 13pt → 13pt (동일 - 비율만 적용)
    # O+M v4: 8pt → 13pt (O+M은 운영 자재에 낮은 배점 → BD+C 기준으로 상향 환산)
    mapped["MR"] = _proportional(float(cats.get("MR", 0)), get_old_max("MR"), V5_MAX["MR"])

    # ── IEQ ───────────────────────────────────────────────────────────────
    # v2009/v3: 15pt → 16pt (소폭 증가)
    # v2.2: 15pt → 16pt (실내환경 기준 강화)
    # O+M v4: 17pt → 16pt (O+M이 실내 쾌적성에 약간 더 높은 배점)
    mapped["IEQ"] = _proportional(float(cats.get("IEQ", 0)), get_old_max("IEQ"), V5_MAX["IEQ"])

    # ── IN (Innovation) ───────────────────────────────────────────────────
    # v2.2: 5pt → 6pt (소폭 증가)
    # v2009 이상: 6pt → 6pt (동일)
    mapped["IN"] = _proportional(float(cats.get("IN", 0)), get_old_max("IN"), V5_MAX["IN"])

    # ── RP (Regional Priority) ────────────────────────────────────────────
    # v2.2 이전: RP 없음 → 0
    # v2009 이상: 4pt → 4pt (동일)
    if version in ("v1.0 pilot", "v2.0", "v2.2"):
        mapped["RP"] = 0.0   # 해당 버전에 없는 카테고리
    else:
        mapped["RP"] = _proportional(float(cats.get("RP", 0)), get_old_max("RP"), V5_MAX["RP"])

    # ── IP (Integrative Process) ──────────────────────────────────────────
    # v4 이전: IP 없음 → 0
    # v4 이상: 2pt → 2pt (동일)
    if version in ("v1.0 pilot", "v2.0", "v2.2", "v2009", "v3"):
        mapped["IP"] = 0.0   # 해당 버전에 없는 카테고리
    else:
        mapped["IP"] = _proportional(float(cats.get("IP", 0)), get_old_max("IP"), V5_MAX["IP"])

    total_v5 = round(sum(mapped.values()), 2)

    # ── 매핑 근거 문자열 구성 ─────────────────────────────────────────────
    if needs_lt_split:
        lt_note = (
            f"SS→LT 교통 분리({lt_source}): "
            f"교통점수={transport_awarded:.1f}/{transport_max:.0f}"
        )
    else:
        lt_note = "LT/SS 이미 분리됨 (v4 이상)"

    rationale = (
        f"[Rule Mapper] 버전={version} | {lt_note} | "
        f"v5 총점={total_v5}/110 | "
        f"원본 총점={project.get('total_score_raw', '?')}"
    )

    rule_mapping_result = {
        "mapped_categories":  mapped,
        "mapping_rationale":  rationale,
        "proportional_scores": {
            cat: f"{cats.get(cat, 0):.1f}/{get_old_max(cat):.0f} → {score:.2f}/{V5_MAX.get(cat, 0)}"
            for cat, score in mapped.items()
        },
        "total_score_v5": total_v5,
    }

    log = f"[Rule Mapper] {version} → v5 매핑 완료: {total_v5:.1f}/110"
    return {
        **state,
        "rule_mapping_result": rule_mapping_result,
        "validation_mode":     "rule",
        "logs":                [log],
    }


# =============================================================================
# Node 4: Hallucination Checker (수학적 검증 - LLM 없음)
# =============================================================================

def hallucination_checker_node(state: LEEDStandardizationState) -> LEEDStandardizationState:
    """
    [Hallucination Checker Node] - LLM 없음, 토큰 소모 없음

    역할: rule_mapper 결과의 수학적 타당성을 검증.
          다음 5가지 조건을 모두 통과해야 PASS.

    검증 항목:
        1. 카테고리 점수 범위: 0 ≤ score ≤ V5_MAX[cat]
        2. 총점 일관성: sum(categories) ≈ total_score_v5 (오차 0.5 이내)
        3. 달성률 드리프트: |원본달성률 - v5달성률| ≤ RATIO_DRIFT_THRESHOLD(20%)
        4. 음수 점수 없음
        5. v5에 존재하지 않는 카테고리 없음

    [달성률 계산]
        원본 달성률 = total_score_raw / version_total_max
        v5 달성률   = total_score_v5  / 110
        드리프트가 크면 SS→LT 분리 비율 추정이 잘못됐거나 버전 식별 오류일 가능성.

    [PASS 기준]
        모든 항목 통과 시 → finalize로 이동 (LLM 호출 없음)
    [FAIL 기준]
        하나라도 실패 시 → llm_mapper로 이동 (LLM 폴백)
    """
    project = state.get("project", {})
    mapping = state.get("rule_mapping_result", {})

    if not mapping:
        return {
            **state,
            "math_validation_result": {"passed": False, "issues": ["rule_mapping_result 없음"],
                                       "achievement_ratio_original": 0, "achievement_ratio_v5": 0,
                                       "ratio_drift": 1.0},
            "logs": ["[Hallucination Check] rule_mapping_result 없음 - LLM 폴백"],
        }

    mapped = mapping.get("mapped_categories", {})
    total_v5 = mapping.get("total_score_v5", 0.0)
    version = project.get("version", "v4")
    issues = []

    # ── 검증 1: 카테고리 점수 범위 ────────────────────────────────────────
    for cat, score in mapped.items():
        v5_max = V5_MAX.get(cat)
        if v5_max is None:
            issues.append(f"v5에 없는 카테고리: {cat}")
            continue
        if score < 0:
            issues.append(f"{cat} 음수: {score}")
        if score > v5_max + 0.01:   # 부동소수점 오차 0.01 허용
            issues.append(f"{cat} 초과: {score:.2f} > max {v5_max}")

    # ── 검증 2: 총점 일관성 ───────────────────────────────────────────────
    computed_total = sum(mapped.values())
    if abs(computed_total - total_v5) > 0.5:
        issues.append(
            f"총점 불일치: sum={computed_total:.2f}, reported={total_v5:.2f}"
        )

    # ── 검증 3: 달성률 드리프트 ───────────────────────────────────────────
    # 원본 달성률
    ver_max_total = sum(VERSION_BD_C_MAX.get(version, VERSION_BD_C_MAX["v4"]).values())
    ver_max_total = max(ver_max_total, 1)
    raw_total = float(project.get("total_score_raw", 0))
    ratio_orig = raw_total / ver_max_total

    # v5 달성률
    ratio_v5 = total_v5 / 110.0

    drift = abs(ratio_orig - ratio_v5)
    if drift > RATIO_DRIFT_THRESHOLD:
        issues.append(
            f"달성률 드리프트 {drift:.1%} > 허용({RATIO_DRIFT_THRESHOLD:.0%}): "
            f"원본={ratio_orig:.1%}, v5={ratio_v5:.1%}"
        )

    passed = len(issues) == 0
    result = {
        "passed":                    passed,
        "issues":                    issues,
        "achievement_ratio_original": round(ratio_orig, 4),
        "achievement_ratio_v5":       round(ratio_v5, 4),
        "ratio_drift":                round(drift, 4),
    }

    if passed:
        log = (
            f"[Hallucination Check] PASS - "
            f"달성률: 원본={ratio_orig:.1%} / v5={ratio_v5:.1%} "
            f"(drift={drift:.1%})"
        )
    else:
        log = f"[Hallucination Check] FAIL - 문제 {len(issues)}건: {issues}"

    return {
        **state,
        "math_validation_result": result,
        "logs":                   [log],
    }


# =============================================================================
# Node 5: LLM Mapper (폴백 - LLM 사용, 토큰 소모 있음)
# =============================================================================

def llm_mapper_node(state: LEEDStandardizationState) -> LEEDStandardizationState:
    """
    [LLM Mapper Node] - 토큰 소모 있음 (폴백 전용)

    역할: hallucination_checker 실패 시에만 진입.
          rule_mapper가 처리하지 못한 엣지케이스(unknown 버전, 비정형 PDF 등)를
          LLM에게 매핑 요청.

    입력:
        - project (rule_mapper가 구성한 project 필드)
        - math_validation_result (왜 rule_mapper가 실패했는지 - LLM에게 컨텍스트 제공)
        - validation_result (이전 llm_validator의 피드백 - 있으면 재매핑에 반영)

    LLM 프롬프트 전략:
        - rule_mapper의 실패 사유를 명시적으로 전달
        - 버전별 매핑 가이드 텍스트 포함
        - 이전 validator 피드백 포함 (반복 시)
        - JSON only 응답 강제
    """
    llm = get_llm()
    project = state.get("project", {})
    version = project.get("version", "unknown")
    current_iter = state.get("current_iteration", 0)

    # ── 실패 사유 수집 ────────────────────────────────────────────────────
    math_result = state.get("math_validation_result", {})
    math_issues = math_result.get("issues", [])

    # llm_validator 피드백 (재시도 시)
    prev_feedback = ""
    prev_validation = state.get("validation_result")
    if prev_validation and not prev_validation.get("is_valid", True):
        prev_feedback = f"\n\n[이전 검증 실패 피드백]\n{prev_validation.get('feedback', '')}"

    # ── 버전 매핑 가이드 ──────────────────────────────────────────────────
    version_guides = {
        "v1.0 pilot / v2.0 / v2.2": (
            "총점 69점 체계. SS(14)에 교통크레딧 포함(약 7pt). "
            "LT 없음→SS 교통분 비율로 LT 추정. RP/IP 없음→0."
        ),
        "v2009 / v3": (
            "총점 110점. SS(26)에 교통크레딧 포함(약 6pt). "
            "LT 없음→SS 교통분 비율로 LT 추정. IP 없음→0."
        ),
        "v4": "총점 110점. LT/SS 이미 분리. WE만 11→12 비율 환산 필요.",
        "v4.1 / v5": "v5와 구조 동일. 직접 매핑.",
    }
    guide_text = "\n".join(f"  {k}: {v}" for k, v in version_guides.items())

    system_prompt = """당신은 LEED(Leadership in Energy and Environmental Design) 버전 표준화 전문가입니다.
구버전 LEED 카테고리 점수를 최신 v5 BD+C 기준으로 정확하게 매핑합니다.

v5 카테고리 최대점수: LT=16, SS=10, WE=12, EA=33, MR=13, IEQ=16, IN=6, RP=4, IP=2 (합계=110)

반드시 다음 JSON 형식으로만 응답하세요:
{
  "mapped_categories": {"LT": <숫자>, "SS": <숫자>, "WE": <숫자>, "EA": <숫자>,
                        "MR": <숫자>, "IEQ": <숫자>, "IN": <숫자>, "RP": <숫자>, "IP": <숫자>},
  "mapping_rationale": "<매핑 근거>",
  "proportional_scores": {}
}"""

    user_prompt = f"""다음 LEED 프로젝트를 v5 기준으로 매핑해주세요.

[프로젝트]
버전: {version}
인증등급: {project.get('certification_level', '?')}
원본 총점: {project.get('total_score_raw', '?')}
원본 카테고리 점수(획득): {json.dumps(project.get('categories', {}), ensure_ascii=False)}
원본 카테고리 만점(possible): {json.dumps(project.get('categories_possible', {}), ensure_ascii=False)}

[규칙 기반 매핑 실패 사유]
{chr(10).join(f"  - {i}" for i in math_issues) if math_issues else "  (사유 없음 - 정밀도 향상 목적)"}

[버전별 매핑 가이드]
{guide_text}

주의사항:
1. 각 카테고리 점수가 v5 최대값을 초과하지 않도록 할 것
2. 원본 버전에 없는 카테고리(예: v2.2의 LT, RP, IP)는 0으로 설정
3. 달성률(획득/최대)을 최대한 보존할 것
{prev_feedback}
JSON으로만 응답하세요."""

    response = llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ])

    try:
        resp_text = response.content.strip()
        if "```json" in resp_text:
            resp_text = resp_text.split("```json")[1].split("```")[0].strip()
        elif "```" in resp_text:
            resp_text = resp_text.split("```")[1].split("```")[0].strip()

        parsed = json.loads(resp_text)
        mapped_cats = parsed.get("mapped_categories", {})

        # LLM 출력도 클램핑 (환각 방지 보정)
        for cat in mapped_cats:
            mapped_cats[cat] = _clamp(float(mapped_cats[cat]), V5_MAX.get(cat, 999))

        total_v5 = round(sum(mapped_cats.values()), 2)
        mapping_result = {
            "mapped_categories":  mapped_cats,
            "mapping_rationale":  parsed.get("mapping_rationale", ""),
            "proportional_scores": parsed.get("proportional_scores", {}),
            "total_score_v5":      total_v5,
        }
        log = f"[LLM Mapper Iter {current_iter+1}] 완료 - v5 총점: {total_v5:.1f}/110"

    except Exception as e:
        # LLM 파싱 실패 → rule_mapper 결과 재사용 (최후 수단)
        fallback = state.get("rule_mapping_result") or {}
        mapping_result = {
            "mapped_categories":  fallback.get("mapped_categories", {}),
            "mapping_rationale":  f"LLM 파싱 실패({e}) - rule_mapper 결과 재사용",
            "proportional_scores": {},
            "total_score_v5":      fallback.get("total_score_v5", 0),
        }
        log = f"[LLM Mapper Iter {current_iter+1}] 파싱 실패 ({e}) - 폴백 적용"

    return {
        **state,
        "mapping_result":    mapping_result,
        "validation_mode":   "llm",
        "current_iteration": current_iter + 1,
        "logs":              [log],
    }


# =============================================================================
# Node 6: LLM Validator (LLM 경로 전용 검증 - 토큰 소모 있음)
# =============================================================================

def llm_validator_node(state: LEEDStandardizationState) -> LEEDStandardizationState:
    """
    [LLM Validator Node] - 토큰 소모 있음 (LLM 경로 전용)

    역할: llm_mapper 결과의 건축 환경적 타당성 검증.
          수학적 체크(hallucination_checker)보다 전문적 판단 포함.

    검증 기준:
        1. 수학적 제약 (카테고리 초과, 음수) - 재확인
        2. 원본 등급과 v5 환산 총점의 일관성
           (Certified: 40~49, Silver: 50~59, Gold: 60~79, Platinum: 80+)
        3. 달성률 드리프트 (origin vs v5)
        4. 비존재 카테고리에 점수 부여 여부

    [validation_score >= 0.8] → is_valid=True → finalize
    [validation_score < 0.8 & iter < LLM_MAX_ITERATIONS] → 재매핑 (llm_mapper)
    [iter >= LLM_MAX_ITERATIONS] → 강제 통과 (무한 루프 방지)
    """
    llm = get_llm()
    project = state.get("project", {})
    mapping = state.get("mapping_result", {})
    current_iter = state.get("current_iteration", 0)
    max_iter = state.get("max_iterations", LLM_MAX_ITERATIONS)

    # 최대 반복 초과 시 강제 통과
    if current_iter >= max_iter:
        result = {
            "is_valid": True,
            "validation_score": 0.6,
            "issues": ["최대 반복 도달 - 강제 승인"],
            "feedback": "",
            "iteration": current_iter,
        }
        return {
            **state,
            "validation_result": result,
            "logs": [f"[LLM Validator] 최대 반복({max_iter}) 도달 - 강제 승인"],
        }

    system_prompt = """당신은 LEED 인증 심사 전문가입니다.
제시된 버전 매핑 결과의 건축 환경적 타당성을 검증하세요.

반드시 JSON 형식으로만 응답하세요:
{
  "is_valid": true/false,
  "validation_score": 0.0~1.0,
  "issues": ["문제점1", "문제점2"],
  "feedback": "LLM Mapper에게 전달할 개선 지시"
}"""

    user_prompt = f"""다음 LEED 버전 매핑 결과를 검증하세요.

[원본]
버전: {project.get('version', '?')}
인증등급: {project.get('certification_level', '?')}
원본 총점: {project.get('total_score_raw', '?')}
원본 카테고리: {json.dumps(project.get('categories', {}), ensure_ascii=False)}

[v5 매핑 결과]
v5 총점: {mapping.get('total_score_v5', '?')}
카테고리별: {json.dumps(mapping.get('mapped_categories', {}), ensure_ascii=False)}
근거: {mapping.get('mapping_rationale', '')}

[검증 기준]
1. 각 카테고리 ≤ v5 최대값 (LT=16,SS=10,WE=12,EA=33,MR=13,IEQ=16,IN=6,RP=4,IP=2)
2. 인증등급 일관성: Certified=40~49, Silver=50~59, Gold=60~79, Platinum=80+
3. 달성률 드리프트 ≤ 20%
4. 원본 버전에 없는 카테고리(v2.2→LT/RP/IP, v2009→IP)에 0 이상 점수 부여 금지

validation_score >= 0.8 → is_valid=true
JSON으로만 응답하세요."""

    response = llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ])

    try:
        resp_text = response.content.strip()
        if "```json" in resp_text:
            resp_text = resp_text.split("```json")[1].split("```")[0].strip()
        elif "```" in resp_text:
            resp_text = resp_text.split("```")[1].split("```")[0].strip()

        parsed_resp = json.loads(resp_text)
        result = {
            "is_valid":         parsed_resp.get("is_valid", False),
            "validation_score": parsed_resp.get("validation_score", 0.0),
            "issues":           parsed_resp.get("issues", []),
            "feedback":         parsed_resp.get("feedback", ""),
            "iteration":        current_iter,
        }
        status_str = "PASS" if result["is_valid"] else "FAIL"
        log = (
            f"[LLM Validator Iter {current_iter}] {status_str} "
            f"(score={result['validation_score']:.2f})"
        )

    except Exception as e:
        # 파싱 실패 → 수학적 체크만으로 판정
        mapped = mapping.get("mapped_categories", {})
        fallback_issues = [
            f"{cat} 초과: {s:.2f} > {V5_MAX.get(cat, 0)}"
            for cat, s in mapped.items()
            if s > V5_MAX.get(cat, 0) + 0.01
        ]
        is_valid = len(fallback_issues) == 0
        result = {
            "is_valid":         is_valid,
            "validation_score": 0.85 if is_valid else 0.5,
            "issues":           fallback_issues,
            "feedback":         "; ".join(fallback_issues),
            "iteration":        current_iter,
        }
        log = f"[LLM Validator Iter {current_iter}] 파싱 실패 ({e}) - 수학적 폴백"

    return {
        **state,
        "validation_result": result,
        "logs":              [log],
    }


# =============================================================================
# Node 7: Finalize
# =============================================================================

def finalize_node(state: LEEDStandardizationState) -> LEEDStandardizationState:
    """
    [Finalize Node]
    역할: 검증 통과된 매핑 결과를 최종 v5 표준화 데이터로 저장.
          rule_mapper 경로와 llm_mapper 경로 모두 이 노드에서 수렴.

    출력 필드:
        - project 메타데이터
        - v5 카테고리별 점수 (score_v5_{CAT})
        - 원본 카테고리별 점수 (score_orig_{CAT})
        - 표준화에 사용된 경로 (standardization_track: "rule" | "llm")
        - 달성률 정보
    """
    project = state.get("project", {})
    mode = state.get("validation_mode", "rule")

    # 경로에 따라 최종 매핑 결과 선택
    if mode == "rule":
        mapping = state.get("rule_mapping_result", {})
    else:
        mapping = state.get("mapping_result", state.get("rule_mapping_result", {}))

    mapped = mapping.get("mapped_categories", {})
    total_v5 = mapping.get("total_score_v5", sum(mapped.values()))

    # 달성률
    ver_max_total = sum(VERSION_BD_C_MAX.get(project.get("version", "v4"),
                                              VERSION_BD_C_MAX["v4"]).values())
    raw_total = float(project.get("total_score_raw", 0))
    ratio_orig = round(raw_total / max(ver_max_total, 1), 4)
    ratio_v5 = round(total_v5 / 110, 4)

    final_data = {
        # 식별 정보
        "project_id":              project.get("project_id", ""),
        "project_name":            project.get("project_name", ""),
        "leed_system":             project.get("leed_system", ""),
        "building_type":           project.get("building_type", ""),
        "gross_area_sqm":          project.get("gross_area_sqm", 0),
        # 원본 정보
        "original_version":        project.get("version", ""),
        "certification_level":     project.get("certification_level", ""),
        "total_score_original":    raw_total,
        "achievement_ratio_original": ratio_orig,
        # v5 매핑 결과
        "total_score_v5":          total_v5,
        "achievement_ratio_v5":    ratio_v5,
        # ── ML feature용 카테고리별 달성률 (0~1) ──────────────────────────
        # ratio_{cat} = score_v5_{cat} / V5_MAX[cat] = 원본 acquired / 원본 possible
        #
        # 왜 이렇게 계산해도 같은가?
        #   score_v5 = (awarded / old_max) * v5_max
        #   → score_v5 / v5_max = awarded / old_max = 달성률
        #
        # 즉 버전이 달라도 "이 카테고리에서 몇 %를 달성했냐"는 값은 동일하게 보존됨.
        # ML 모델에는 이 ratio 필드를 feature로 사용할 것.
        **{f"ratio_{cat}": round(score / V5_MAX.get(cat, 1), 4)
           for cat, score in mapped.items()},
        # 카테고리별 v5 절대점수 (논문 방법론 기술용 - ML feature로는 미사용)
        **{f"score_v5_{cat}": score for cat, score in mapped.items()},
        # 카테고리별 원본 점수 (비교용)
        **{f"score_orig_{cat}": project.get("categories", {}).get(cat, 0)
           for cat in mapped},
        # 메타
        "standardization_track":   mode,
        "standardization_iterations": state.get("current_iteration", 0),
        "mapping_rationale":       mapping.get("mapping_rationale", ""),
    }

    log = (
        f"[Finalize] 완료 ({mode} 경로) - "
        f"v5={total_v5:.1f}/110 | "
        f"달성률 원본={ratio_orig:.1%} → v5={ratio_v5:.1%}"
    )
    return {
        **state,
        "final_v5_data": final_data,
        "status":        "completed",
        "logs":          [log],
    }
