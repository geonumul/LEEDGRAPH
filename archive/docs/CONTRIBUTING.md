# 기여 가이드

## 개발 환경 설정

```bash
git clone https://github.com/your-username/LEEDGRAPH.git
cd LEEDGRAPH
python -m venv .venv
.venv\Scripts\activate  # Windows
pip install -r requirements.txt
```

## 코드 스타일

- Python 3.11+
- Black 포맷터 사용 (`black src/`)
- 한국어 주석 권장

## 브랜치 전략

```
main        ← 안정 버전
develop     ← 개발 브랜치
feature/*   ← 기능 개발
```

## Pull Request 절차

1. `develop` 브랜치에서 `feature/기능명` 브랜치 생성
2. 변경사항 커밋
3. PR 생성 → develop 병합
4. 리뷰 후 main 병합

## 이슈 보고

버그 리포트 또는 기능 제안은 GitHub Issues에 등록해주세요.
