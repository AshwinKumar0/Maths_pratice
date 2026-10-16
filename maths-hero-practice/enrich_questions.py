"""Turn extracted practice text into selectable choices and safe arithmetic keys."""
import ast, json, operator, re
from pathlib import Path

OPS={ast.Add:operator.add,ast.Sub:operator.sub,ast.Mult:operator.mul,ast.Div:operator.truediv,ast.Pow:operator.pow,ast.USub:operator.neg,ast.UAdd:operator.pos,ast.Mod:operator.mod,ast.FloorDiv:operator.floordiv}
def calc(expr):
    expr=expr.replace('×','*').replace('÷','/').replace('−','-').replace('–','-').replace('^','**').replace(',','')
    tree=ast.parse(expr,mode='eval')
    def visit(n):
        if isinstance(n,ast.Expression): return visit(n.body)
        if isinstance(n,ast.Constant) and isinstance(n.value,(int,float)): return n.value
        if isinstance(n,ast.BinOp) and type(n.op) in OPS:
            a,b=visit(n.left),visit(n.right)
            if abs(a)>1e10 or abs(b)>1e10: raise ValueError()
            value=OPS[type(n.op)](a,b)
            if abs(value)>1e12: raise ValueError()
            return value
        if isinstance(n,ast.UnaryOp) and type(n.op) in OPS: return OPS[type(n.op)](visit(n.operand))
        raise ValueError()
    return visit(tree)
def close(a,b): return abs(float(a)-float(b))<1e-8
def number(v):
    v=v.strip()
    if not re.fullmatch(r'[+-]?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?',v): return None
    try: return float(v.replace(',',''))
    except Exception: return None
def enrich(q):
    text=q['text'].strip()
    # Some source sheets attach a short solution note to the end of a prompt.
    # Keep it separately for the post-submit review instead of showing it while practicing.
    explanation_match=re.search(r'\b(?:solution|explanation)\s*:\s*(.+)$',text,re.I)
    if explanation_match:
        q['explanation']=explanation_match.group(1).strip()
        text=text[:explanation_match.start()].strip()
    else:
        q.pop('explanation',None)
    marks=list(re.finditer(r'\(\s*([a-e])\s*\)\s*',text,re.I))
    options=[]
    if marks:
        stem=text[:marks[0].start()].strip()
        for i,m in enumerate(marks):
            end=marks[i+1].start() if i+1<len(marks) else len(text)
            label=m.group(1).lower(); value=text[m.end():end].strip()
            if value: options.append({'id':label,'text':value})
        q['prompt']=stem or text
    else:
        q['prompt']=text
    q['options']=options
    q['correctOption']=None
    q['correctAnswer']=None
    # Safely evaluate plain numeric arithmetic, or solve one missing value by
    # checking each numeric multiple-choice candidate in a single equation.
    equation=re.sub(r'\s+',' ',q['prompt']).strip()
    if equation.count('=')==1:
        left,right=[part.strip() for part in equation.split('=',1)]
        if '?' in equation and options:
            numeric=[]
            for o in options:
                v=number(o['text'])
                if v is not None:numeric.append((o['id'],v))
            hits=[]
            for oid,v in numeric:
                try:
                    if close(calc(left.replace('?',str(v))),calc(right.replace('?',str(v)))):hits.append(oid)
                except Exception:pass
            if len(hits)==1:q['correctOption']=hits[0]
            elif options and not hits:
                none=next((o['id'] for o in options if 'none of these' in o['text'].lower()),None)
                if none:q['correctOption']=none
        elif not options and '?' not in equation:
            try:
                if not right:q['correctAnswer']=str(calc(left))
                elif not left:q['correctAnswer']=str(calc(right))
            except Exception:pass
    q['answerNote']='Calculated from the question' if q['correctAnswer'] is not None or q['correctOption'] is not None else 'Answer not available in source'

data_path=Path('data/questions.json')
data=json.loads(data_path.read_text(encoding='utf-8'))
for chapter in data['chapters']:
    for sheet in chapter['sheets']:
        for question in sheet['questions']:enrich(question)
data_path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
total=sum(len(s['questions']) for c in data['chapters'] for s in c['sheets'])
scored=sum(q['correctAnswer'] is not None or q['correctOption'] is not None for c in data['chapters'] for s in c['sheets'] for q in s['questions'])
print(f'Enriched {total} questions; {scored} have a reliably calculated answer.')
