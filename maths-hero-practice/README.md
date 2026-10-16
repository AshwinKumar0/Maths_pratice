# Maths Hero Practice

A local practice app for the chapter practice sheets in this folder. The app keeps practice sessions and answer history in `practice_progress.sqlite3` on this computer.

## Run it

On Windows, double-click `start.bat`. Keep the terminal window open while practicing, then visit <http://127.0.0.1:8765> in your browser. The app does not need an internet connection for progress saving. Google Fonts are used when available; system fonts are used otherwise.

## What is included

- Chapter and sheet ordering follows the numbered source filenames.
- Questions and options are extracted from all 22 PDFs under the chapter `Practice Sheet` folders. Multiple choice questions show selectable options; other questions accept a typed answer.
- The app calculates a key only when it can verify one from the arithmetic in the question. Other items say “Answer not available in source” and are saved as unscored, so the score counts only questions with a reliable key.
- You can submit at any point. If the sheet still has unanswered questions, the score is shown and progress is kept; re-entering the sheet asks whether to continue or start over. A fully answered sheet is marked complete and does not prompt to resume.
- Progress, answer changes, pause/resume position, scores, and practice history are stored locally in SQLite. The score shown for a sheet follows the latest attempt.
- Use “View source PDF” to open the original sheet.

The source PDFs remain in the original folder on this computer. The app serves
them locally through its `/source/` route while keeping the app and progress
database in this project folder. Set `MATHS_HERO_PDF_ROOT` to their root folder,
or add a local-only `local_settings.json` file beside `app.py` containing
`{"pdfSourceRoot":"C:\\path\\to\\your\\PDFs"}`. The local settings file and
progress database are excluded from Git.

Some scanned pages may not have selectable text. Those sheets stay linked in the app for reference, and cannot be practiced as individual app questions until their text is transcribed.

The question extraction script can be rerun after installing `pypdf` with `python -m pip install pypdf`, then run `python extract_questions.py` and `python enrich_questions.py`.
