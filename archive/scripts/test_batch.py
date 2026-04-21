import sys
sys.path.insert(0, 'd:/RAG/LEEDGRAPH')
from src.data.loader import LEEDDataLoader
from pathlib import Path

loader = LEEDDataLoader()
pdf_files = sorted(Path('data/raw/scorecards').glob('*.pdf'))

print(f'전체 PDF: {len(pdf_files)}개')
print('-'*100)

ok, err = 0, 0
no_grade, no_version, no_cats = [], [], []
version_dist = {}
grade_dist = {}

for pdf in pdf_files:
    try:
        p = loader.parse_scorecard_pdf(str(pdf))
        cats = list(p['categories'].keys())
        missing = [c for c in ['SS','WE','EA','MR','IEQ'] if c not in cats]
        ver = p['version']
        grade = p['certification_level']

        version_dist[ver] = version_dist.get(ver, 0) + 1
        grade_dist[grade] = grade_dist.get(grade, 0) + 1

        if not grade:
            no_grade.append(pdf.name)
        if ver == 'unknown':
            no_version.append(pdf.name)
        if missing:
            no_cats.append((pdf.name, missing))

        status = 'OK ' if not missing else 'CAT'
        print(f'{status} {pdf.name[:55]:<55} ver={ver:<8} grade={grade:<10} score={p["total_awarded"]}/{p["total_possible"]} miss={missing if missing else "-"}')
        ok += 1
    except Exception as e:
        print(f'ERR {pdf.name[:55]:<55} {e}')
        err += 1

print('\n' + '='*100)
print(f'성공: {ok}개 / 오류: {err}개')
print(f'버전 분포: {dict(sorted(version_dist.items()))}')
print(f'등급 분포: {dict(sorted(grade_dist.items()))}')
if no_version:
    print(f'\n[버전 미감지] {len(no_version)}개:')
    for f in no_version:
        print(f'  {f}')
if no_grade:
    print(f'\n[등급 미감지] {len(no_grade)}개:')
    for f in no_grade:
        print(f'  {f}')
if no_cats:
    print(f'\n[카테고리 누락] {len(no_cats)}개:')
    for f, m in no_cats:
        print(f'  {f} -> {m}')
