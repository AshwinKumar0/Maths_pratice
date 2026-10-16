from pathlib import Path
from pypdf import PdfReader
import re, json
root=Path('.')
chapters=[]
for chapter_dir in sorted([p for p in root.iterdir() if p.is_dir()], key=lambda p:p.name):
    practice=chapter_dir/'Practice Sheet'
    if not practice.exists():
        continue
    sheets=[]
    for pdf in sorted(practice.glob('*.pdf'), key=lambda p:p.name.casefold()):
        reader=PdfReader(str(pdf))
        text='\n'.join((page.extract_text() or '') for page in reader.pages)
        questions=[]
        # Sheet PDFs vary between Q1:, Q1 on its own line, and (Q1).
        candidates=list(re.finditer(r"(?im)^[ \t]*(?:\([ \t]*Q[ \t]*(\d{1,4})[ \t]*\)|Q[ \t]*(\d{1,4})[ \t]*[:.)-]|\([ \t]*(\d{1,4})[ \t]*\)(?=[ \t]*(?:\r?$)))\s*",text))
        # Numbered questions are sequential; this skips standalone parenthetical
        # numbers from fractions/exponents that PDF extraction places on their own lines.
        marks=[]; expected=1
        for candidate in candidates:
            number=int(next(g for g in candidate.groups() if g))
            if number==expected:
                marks.append(candidate); expected+=1
        for mi,mark in enumerate(marks):
            number=int(next(g for g in mark.groups() if g))
            end=marks[mi+1].start() if mi+1<len(marks) else len(text)
            body=text[mark.end():end]
            body=re.sub(r"6206068272|Complete Maths Subscription","",body,flags=re.I)
            body=re.sub(r"\s+"," ",body).strip(" \r\n:-")
            if body:
                questions.append({'number':number,'text':body,'answer':None,'answerNote':'Answer not available in source'})
        # Preserve first occurrence if page text extraction repeats a question.
        seen=set(); unique=[]
        for q in questions:
            if q['number'] not in seen:
                seen.add(q['number']); unique.append(q)
        sheets.append({'title':pdf.stem,'source':str(pdf.relative_to(root)).replace('\\','/'),'questions':unique,'pageCount':len(reader.pages)})
    chapters.append({'id':chapter_dir.name[:2], 'title':chapter_dir.name[3:] if len(chapter_dir.name)>3 else chapter_dir.name,'sheets':sheets})
Path('data').mkdir(exist_ok=True)
Path('data/questions.json').write_text(json.dumps({'chapters':chapters},ensure_ascii=False,indent=2),encoding='utf-8')
print('chapters',len(chapters),'sheets',sum(len(c['sheets']) for c in chapters),'questions',sum(len(s['questions']) for c in chapters for s in c['sheets']))
for c in chapters:
 print(c['id'],c['title'],[(s['title'],len(s['questions'])) for s in c['sheets']])
