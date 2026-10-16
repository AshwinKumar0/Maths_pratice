from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import unquote, urlsplit
import json, sqlite3, uuid, datetime, mimetypes, os, base64

ROOT = Path(__file__).parent
LOCAL_CONFIG = ROOT / 'local_settings.json'
configured_pdf_root = os.environ.get('MATHS_HERO_PDF_ROOT')
if not configured_pdf_root and LOCAL_CONFIG.is_file():
    try:
        configured_pdf_root = json.loads(LOCAL_CONFIG.read_text(encoding='utf-8')).get('pdfSourceRoot')
    except (OSError, json.JSONDecodeError):
        pass
PDF_SOURCE_ROOT = Path(configured_pdf_root or ROOT).expanduser().resolve()
DB = ROOT / 'practice_progress.sqlite3'
DATA = ROOT / 'data' / 'questions.json'

def db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.execute('''CREATE TABLE IF NOT EXISTS sessions (
        id TEXT PRIMARY KEY, chapter_id TEXT NOT NULL, sheet_index INTEGER NOT NULL,
        question_index INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'active',
        started_at TEXT NOT NULL, updated_at TEXT NOT NULL, finished_at TEXT,
        total_questions INTEGER NOT NULL DEFAULT 0)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS answers (
        id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL, chapter_id TEXT NOT NULL,
        sheet_index INTEGER NOT NULL, question_index INTEGER NOT NULL, question_number INTEGER NOT NULL,
        question_text TEXT NOT NULL, self_rating TEXT NOT NULL, attempted_answer TEXT NOT NULL DEFAULT '', answered_at TEXT NOT NULL)''')
    cols={r['name'] for r in conn.execute('PRAGMA table_info(answers)')}
    if 'attempted_answer' not in cols:
        conn.execute("ALTER TABLE answers ADD COLUMN attempted_answer TEXT NOT NULL DEFAULT ''")
    for name, declaration in [('selected_answer', "TEXT NOT NULL DEFAULT ''"), ('option_id', 'TEXT'), ('correct', 'INTEGER'), ('response_seconds', 'REAL NOT NULL DEFAULT 0')]:
        if name not in cols: conn.execute(f'ALTER TABLE answers ADD COLUMN {name} {declaration}')
    session_cols={r['name'] for r in conn.execute('PRAGMA table_info(sessions)')}
    if 'total_questions' not in session_cols: conn.execute('ALTER TABLE sessions ADD COLUMN total_questions INTEGER NOT NULL DEFAULT 0')
    return conn

def now(): return datetime.datetime.now().astimezone().isoformat(timespec='seconds')
def load_data(): return json.loads(DATA.read_text(encoding='utf-8'))

def read_source_pdf(relative):
    relative=str(relative or '').replace('\\','/')
    if not relative or Path(relative).is_absolute() or Path(relative).suffix.lower() != '.pdf': return None
    for base in (ROOT.resolve(), PDF_SOURCE_ROOT):
        try:
            candidate=(base / relative).resolve()
            candidate.relative_to(base)
        except (OSError, ValueError):
            continue
        if candidate.is_file(): return candidate.read_bytes()
    return None

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs): super().__init__(*args, directory=str(ROOT), **kwargs)
    def log_message(self, format, *args):
        # Browser integrations may probe the site root for an MCP endpoint;
        # keep those unrelated probes out of the practice server's console.
        if urlsplit(self.path).path == '/mcp': return
        super().log_message(format, *args)
    def send_json(self, value, status=200):
        body=json.dumps(value, ensure_ascii=False).encode()
        self.send_response(status); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Content-Length',str(len(body))); self.send_header('Cache-Control','no-store'); self.end_headers(); self.wfile.write(body)
    def body(self): return json.loads(self.rfile.read(int(self.headers.get('Content-Length','0'))))
    def do_GET(self):
        request_path=urlsplit(self.path).path
        if request_path == '/favicon.ico':
            self.send_response(204); self.send_header('Cache-Control','public, max-age=86400'); self.end_headers(); return
        if request_path == '/api/data': return self.send_json(load_data())
        if request_path.startswith('/source/'):
            relative=unquote(request_path[len('/source/'):]).replace('\\','/')
            content=read_source_pdf(relative)
            if content is not None:
                self.send_response(200)
                self.send_header('Content-Type','application/pdf')
                self.send_header('Content-Length',str(len(content)))
                self.send_header('Content-Disposition','inline')
                self.send_header('Cache-Control','no-store')
                self.end_headers(); self.wfile.write(content)
                return
            return self.send_json({'error':'Source PDF not found'},404)
        if request_path == '/api/state':
            c=db(); sessions=[dict(r) for r in c.execute("SELECT * FROM sessions ORDER BY updated_at DESC")]
            answers=[dict(r) for r in c.execute("SELECT * FROM answers ORDER BY answered_at DESC, id DESC")]
            c.close(); return self.send_json({'sessions':sessions,'answers':answers})
        return super().do_GET()
    def do_POST(self):
        if urlsplit(self.path).path == '/mcp':
            return self.send_json({'error':'This local practice app does not provide an MCP endpoint.'},404)
        if urlsplit(self.path).path == '/api/source':
            payload=self.body()
            content=read_source_pdf(payload.get('path'))
            if content is None: return self.send_json({'error':'Source PDF not found'},404)
            return self.send_json({'data':base64.b64encode(content).decode('ascii')})
        payload=self.body(); c=db(); stamp=now()
        if self.path == '/api/session':
            if payload.get('restart'):
                c.execute("UPDATE sessions SET status='abandoned',updated_at=? WHERE chapter_id=? AND sheet_index=? AND status IN ('active','paused')",(stamp,payload['chapterId'],payload['sheetIndex']))
            row=None if payload.get('restart') else c.execute("SELECT * FROM sessions WHERE chapter_id=? AND sheet_index=? AND status IN ('active','paused') ORDER BY updated_at DESC LIMIT 1",(payload['chapterId'],payload['sheetIndex'])).fetchone()
            if row:
                c.execute("UPDATE sessions SET status='active', updated_at=?, total_questions=CASE WHEN total_questions=0 THEN ? ELSE total_questions END WHERE id=?",(stamp,payload.get('totalQuestions',0),row['id'])); sid=row['id']
            else:
                sid=str(uuid.uuid4()); c.execute("INSERT INTO sessions(id,chapter_id,sheet_index,question_index,status,started_at,updated_at,total_questions) VALUES(?,?,?,?,?,?,?,?)",(sid,payload['chapterId'],payload['sheetIndex'],0,'active',stamp,stamp,payload.get('totalQuestions',0)))
            c.commit(); c.close(); return self.send_json({'id':sid})
        if self.path == '/api/answer':
            existing=c.execute("SELECT id FROM answers WHERE session_id=? AND question_index=? ORDER BY id DESC LIMIT 1",(payload['sessionId'],payload['questionIndex'])).fetchone()
            values=(payload.get('rating','answered'),payload.get('selectedAnswer',''),payload.get('optionId'),payload.get('correct'),payload.get('selectedAnswer',''),max(0,float(payload.get('responseSeconds',0))),stamp)
            if existing:
                c.execute("UPDATE answers SET self_rating=?,selected_answer=?,option_id=?,correct=?,attempted_answer=?,response_seconds=?,answered_at=? WHERE id=?",(*values,existing['id']))
            else:
                c.execute("INSERT INTO answers(session_id,chapter_id,sheet_index,question_index,question_number,question_text,self_rating,selected_answer,option_id,correct,attempted_answer,response_seconds,answered_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",(payload['sessionId'],payload['chapterId'],payload['sheetIndex'],payload['questionIndex'],payload['questionNumber'],payload['questionText'],values[0],values[1],values[2],values[3],values[4],values[5],values[6]))
            c.execute("UPDATE sessions SET question_index=?,updated_at=? WHERE id=?",(payload.get('currentIndex',payload['questionIndex']),stamp,payload['sessionId']))
            c.commit(); c.close(); return self.send_json({'ok':True})
        if self.path == '/api/progress':
            c.execute("UPDATE sessions SET question_index=?,status='active',updated_at=? WHERE id=?",(payload['questionIndex'],stamp,payload['sessionId']))
            c.commit(); c.close(); return self.send_json({'ok':True})
        if self.path == '/api/submit':
            session=c.execute("SELECT total_questions FROM sessions WHERE id=?",(payload['sessionId'],)).fetchone()
            answered=c.execute("SELECT COUNT(DISTINCT question_index) AS n FROM answers WHERE session_id=?",(payload['sessionId'],)).fetchone()['n']
            complete=bool(session and session['total_questions'] and answered>=session['total_questions'])
            status='complete' if complete else 'paused'
            c.execute("UPDATE sessions SET status=?,updated_at=?,finished_at=CASE WHEN ?='complete' THEN ? ELSE NULL END WHERE id=?",(status,stamp,status,stamp,payload['sessionId']))
            c.commit(); c.close(); return self.send_json({'ok':True,'status':status,'answered':answered,'total':session['total_questions'] if session else 0})
        if self.path == '/api/session-status':
            status=payload['status']; finished=stamp if status=='complete' else None
            c.execute("UPDATE sessions SET status=?,updated_at=?,finished_at=COALESCE(?,finished_at) WHERE id=?",(status,stamp,finished,payload['sessionId']))
            c.commit(); c.close(); return self.send_json({'ok':True})
        if self.path == '/api/clear-history':
            answers=c.execute('DELETE FROM answers').rowcount
            sessions=c.execute('DELETE FROM sessions').rowcount
            c.commit(); c.close(); return self.send_json({'ok':True,'answers':answers,'sessions':sessions})
        c.close(); return self.send_json({'error':'Not found'},404)

if __name__ == '__main__':
    db().close()
    print('Maths Hero practice is running at http://127.0.0.1:8765')
    ThreadingHTTPServer(('127.0.0.1',8765),Handler).serve_forever()
