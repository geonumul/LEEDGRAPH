"""
LEED 데이터 로더
- USGBC PublicLEEDProjectDirectory.xlsx 로딩
- 개별 Scorecard PDF 파싱
"""

import os
import re
import pandas as pd
import pdfplumber
from pathlib import Path
from typing import Optional


# ─────────────────────────────────────────────────────────
# LEED 버전별 카테고리 최대 점수 정의
# ─────────────────────────────────────────────────────────
LEED_VERSION_MAX_SCORES = {
    "v2.2": {
        "SS": 14,   # Sustainable Sites
        "WE": 5,    # Water Efficiency
        "EA": 17,   # Energy & Atmosphere
        "MR": 13,   # Materials & Resources
        "IEQ": 15,  # Indoor Environmental Quality
        "IN": 5,    # Innovation & Design
        "TOTAL": 69,
    },
    "v3": {
        "SS": 26,
        "WE": 10,
        "EA": 35,
        "MR": 14,
        "IEQ": 15,
        "IN": 6,
        "RP": 4,    # Regional Priority
        "TOTAL": 110,
    },
    "v4": {
        "LT": 16,   # Location & Transportation
        "SS": 10,
        "WE": 11,
        "EA": 33,
        "MR": 13,
        "IEQ": 16,
        "IN": 6,
        "RP": 4,
        "IP": 2,    # Integrative Process
        "TOTAL": 110,
    },
    "v4.1": {
        "LT": 16,
        "SS": 10,
        "WE": 12,
        "EA": 33,
        "MR": 13,
        "IEQ": 16,
        "IN": 6,
        "RP": 4,
        "IP": 2,
        "TOTAL": 110,
    },
    "v5": {
        "LT": 16,
        "SS": 10,
        "WE": 12,
        "EA": 33,
        "MR": 13,
        "IEQ": 16,
        "IN": 6,
        "RP": 4,
        "IP": 2,
        "TOTAL": 110,
    },
}

# LEED 등급 기준 (v4/v5 기준)
LEED_GRADE_THRESHOLDS = {
    "Certified": (40, 49),
    "Silver": (50, 59),
    "Gold": (60, 79),
    "Platinum": (80, 110),
}


class LEEDDataLoader:
    """LEED 프로젝트 데이터 로더"""

    def __init__(self, data_dir: str = "data/raw"):
        self.data_dir = Path(data_dir)

    # ─────────────────────────────────────────────
    # 1. PublicLEEDProjectDirectory.xlsx 로딩
    # ─────────────────────────────────────────────
    def load_project_directory(
        self, filename: str = "PublicLEEDProjectDirectory.xlsx"
    ) -> pd.DataFrame:
        """
        USGBC 공개 프로젝트 디렉토리 엑셀 파일 로딩.

        주요 컬럼:
            - Project Name, Project ID, Country, State/Province
            - LEED System, Certification Level, Points Achieved
            - Registration Date, Certification Date, Gross Square Footage
        """
        filepath = self.data_dir / filename
        if not filepath.exists():
            raise FileNotFoundError(
                f"파일을 찾을 수 없습니다: {filepath}\n"
                "USGBC에서 데이터를 다운로드하여 data/raw/ 폴더에 저장해주세요."
            )

        df = pd.read_excel(filepath, engine="openpyxl")
        print(f"프로젝트 디렉토리 로딩 완료: {len(df)}개 프로젝트")
        return df

    def load_korea_projects(
        self, filename: str = "PublicLEEDProjectDirectory.xlsx"
    ) -> pd.DataFrame:
        """한국 LEED 프로젝트만 필터링"""
        df = self.load_project_directory(filename)

        # 한국 필터링 (Country 컬럼 기준)
        korea_mask = df["Country"].str.contains("Korea|KR|한국", case=False, na=False)
        korea_df = df[korea_mask].copy()

        print(f"한국 프로젝트 필터링 완료: {len(korea_df)}개")
        return korea_df

    # ─────────────────────────────────────────────
    # 2. Scorecard PDF 파싱
    # ─────────────────────────────────────────────
    def parse_scorecard_pdf(self, pdf_path: str) -> dict:
        """
        LEED Scorecard PDF에서 카테고리별 점수 추출.

        Returns:
            dict: {
                "project_name": str,
                "version": str,
                "certification_level": str,
                "total_score": int,
                "categories": {
                    "SS": int, "WE": int, "EA": int, ...
                }
            }
        """
        result = {
            "project_name": "",
            "version": "unknown",
            "certification_level": "",
            "total_score": 0,
            "categories": {},
            "raw_text": "",
        }

        with pdfplumber.open(pdf_path) as pdf:
            full_text = ""
            for page in pdf.pages:
                text = page.extract_text() or ""
                full_text += text + "\n"

            result["raw_text"] = full_text
            result.update(self._extract_scorecard_info(full_text))

        return result

    def _extract_scorecard_info(self, text: str) -> dict:
        """Scorecard 텍스트에서 정보 추출"""
        info = {}

        # 버전 추출
        version_patterns = [
            r"LEED\s+v?(\d+\.?\d*)",
            r"Version\s+(\d+\.?\d*)",
            r"v(\d+\.?\d+)",
        ]
        for pattern in version_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                ver = match.group(1)
                if "2.2" in ver:
                    info["version"] = "v2.2"
                elif ver in ["3", "2009"]:
                    info["version"] = "v3"
                elif "4.1" in ver:
                    info["version"] = "v4.1"
                elif ver == "4":
                    info["version"] = "v4"
                elif ver == "5":
                    info["version"] = "v5"
                break

        # 등급 추출
        grade_pattern = r"(Platinum|Gold|Silver|Certified)\s+(?:Certification|Level)"
        match = re.search(grade_pattern, text, re.IGNORECASE)
        if match:
            info["certification_level"] = match.group(1)

        # 총점 추출
        score_pattern = r"Total\s+(?:Points?|Score)[:\s]+(\d+)"
        match = re.search(score_pattern, text, re.IGNORECASE)
        if match:
            info["total_score"] = int(match.group(1))

        # 카테고리별 점수 추출
        category_patterns = {
            "SS": r"Sustainable\s+Sites?\s+(\d+)",
            "WE": r"Water\s+Efficienc\w+\s+(\d+)",
            "EA": r"Energy\s+(?:and|&)\s+Atmosphere\s+(\d+)",
            "MR": r"Materials?\s+(?:and|&)\s+Resources?\s+(\d+)",
            "IEQ": r"Indoor\s+Environmental\s+Quality\s+(\d+)",
            "IN": r"Innovation\s+(?:in\s+Design\s+)?(\d+)",
            "RP": r"Regional\s+Priority\s+(\d+)",
            "LT": r"Location\s+(?:and|&)\s+Transportation\s+(\d+)",
            "IP": r"Integrative\s+Process\s+(\d+)",
        }

        categories = {}
        for cat, pattern in category_patterns.items():
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                categories[cat] = int(match.group(1))

        info["categories"] = categories
        return info

    def load_scorecard_batch(self, pdf_dir: str) -> pd.DataFrame:
        """
        폴더 내 모든 Scorecard PDF를 일괄 파싱.

        Args:
            pdf_dir: PDF 파일들이 있는 디렉토리 경로

        Returns:
            DataFrame: 전체 파싱 결과
        """
        pdf_path = Path(pdf_dir)
        pdf_files = list(pdf_path.glob("*.pdf"))

        if not pdf_files:
            print(f"[경고] PDF 파일을 찾을 수 없습니다: {pdf_dir}")
            return pd.DataFrame()

        records = []
        for pdf_file in pdf_files:
            try:
                parsed = self.parse_scorecard_pdf(str(pdf_file))
                flat = {
                    "file_name": pdf_file.name,
                    "project_name": parsed["project_name"],
                    "version": parsed["version"],
                    "certification_level": parsed["certification_level"],
                    "total_score": parsed["total_score"],
                }
                flat.update(
                    {f"score_{k}": v for k, v in parsed["categories"].items()}
                )
                records.append(flat)
                print(f"  완료: {pdf_file.name}")
            except Exception as e:
                print(f"  오류: {pdf_file.name}: {e}")

        df = pd.DataFrame(records)
        print(f"\n총 {len(df)}개 Scorecard 파싱 완료")
        return df

    @staticmethod
    def create_sample_data() -> pd.DataFrame:
        """
        실제 데이터가 없을 때 테스트용 샘플 데이터 생성.
        실제 LEED 한국 프로젝트 통계를 반영한 더미 데이터.
        """
        import numpy as np

        np.random.seed(42)
        n = 451

        # 버전 분포 (한국 LEED 인증 현황 반영)
        versions = np.random.choice(
            ["v2.2", "v3", "v4", "v4.1"],
            size=n,
            p=[0.05, 0.30, 0.50, 0.15],
        )

        records = []
        for i, ver in enumerate(versions):
            max_scores = LEED_VERSION_MAX_SCORES[ver]

            # 카테고리별 점수 생성 (정규분포 기반, 최대값 범위 내)
            record = {
                "project_id": f"KR-{i+1:04d}",
                "version": ver,
                "building_type": np.random.choice(
                    ["Office", "Commercial", "Residential", "Mixed-Use", "Industrial"],
                    p=[0.40, 0.25, 0.15, 0.15, 0.05],
                ),
                "gross_area_sqm": np.random.lognormal(mean=10.2, sigma=0.8),
            }

            # 버전별 카테고리 점수 생성
            for cat, max_pt in max_scores.items():
                if cat == "TOTAL":
                    continue
                achieved_ratio = np.random.beta(a=3, b=2)  # 60~80% 달성 경향
                record[f"score_{cat}"] = min(
                    int(max_pt * achieved_ratio), max_pt
                )

            # 총점 계산
            score_cols = [k for k in record if k.startswith("score_")]
            record["total_score_raw"] = sum(record[k] for k in score_cols)

            # 등급 결정
            for grade, (lo, hi) in LEED_GRADE_THRESHOLDS.items():
                # 총점을 100점 기준으로 환산 후 등급 결정
                normalized = (
                    record["total_score_raw"] / max_scores["TOTAL"] * 110
                )
                if lo <= normalized <= hi:
                    record["certification_level"] = grade
                    break
            else:
                record["certification_level"] = (
                    "Platinum" if normalized > 80 else "Certified"
                )

            records.append(record)

        df = pd.DataFrame(records)
        print(f"샘플 데이터 생성 완료: {len(df)}개 프로젝트")
        return df
