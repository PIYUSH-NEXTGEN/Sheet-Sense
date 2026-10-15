# SheetSense — Spreadsheet Inheritance Translator

SheetSense takes an inherited Excel workbook and produces, fully offline:

1. A plain-English explanation of what it does,
2. A ranked list of **suspicious cells to review** (never "errors found" — this is not an audit),
3. A dependency map (sheet-level and group-level),
4. A Q&A box that traces where a number comes from, with clickable, validated cell citations.

Deterministic Python finds the facts (cells, formulas, dependencies, issues);
a local Gemma model via Ollama only phrases them.

## Privacy statement

Everything runs on your machine. The only network traffic is between local
processes: the browser → backend (`http://127.0.0.1:8000`) and the backend →
Ollama (`http://localhost:11434`). There is no telemetry, no analytics, no
CDN assets (fonts are system fonts, all JS/CSS is bundled), and uploaded
workbooks stay in a local data directory (`~/.sheetsense`, or `DATA_DIR`).

## Prerequisites

- Python 3.11+
- Node.js 18+ (for the frontend)
- [Ollama](https://ollama.com) with enough disk/RAM for a Gemma instruct model
  (e.g. `gemma3:4b` needs ~3.3 GB; run `ollama list` to see what you have)

## Install

```bash
# Backend
cd backend
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
# source .venv/bin/activate
pip install -e ".[test]"

# Point the backend at your model (copy, then edit MODEL_NAME to the exact
# installed name — never commit your .env):
copy .env.example .env        # Windows
# cp .env.example .env        # macOS/Linux

# Model (one time; needs network once, then never again)
ollama pull gemma3:4b         # or any installed Gemma variant your hardware handles
ollama serve                  # only if Ollama isn't already running

# Frontend
cd ../frontend
npm install
```

## Run

```bash
# Terminal 1 — backend (from backend/)
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# Terminal 2 — frontend (from frontend/)
npm run dev
```

Open **http://localhost:5173** (important: use `localhost`, not `127.0.0.1` —
the backend's CORS list allows exactly `http://localhost:5173`).

Upload `backend/tests/fixtures/dirty.xlsx` and follow the progress bar into
the overview, the dependency map, the issues list, and the Ask page.

## Tests

```bash
cd backend
python -m pytest               # mocked LLM; passes with Ollama not installed
python -m pytest -m ollama     # one live test, skipped unless Ollama is up
```

Frontend checks: `cd frontend && npm run build` (runs `tsc --noEmit` + Vite build).

## 60-second demo (do installs/pulls online first, then turn off Wi-Fi)

1. (0:00) With Wi-Fi **off**, open http://localhost:5173 — Setup shows green.
2. (0:10) Drag in `backend/tests/fixtures/dirty.xlsx`; watch the SSE progress bar.
3. (0:20) Overview: plain-English summary, stats, dependency map (toggle Sheets/Groups).
4. (0:30) "Suspicious cells to review": filter severity — the hardcoded `1.15` in `Summary!B5`, the `99.5` pattern break in `Pricing!C13`, the short `SUM` in `Summary!B3`, two orphan inputs, one loop.
5. (0:50) Ask page: *"Where does the total with surcharge come from?"* → traced answer with clickable cells; click one to land on its sheet/group.
6. Export the Markdown handoff document.

## Known limitations (v1 — not solved on purpose)

- VBA/macros are unsupported (`.xlsm` files are rejected).
- Cached values may be missing; value-based checks degrade gracefully.
- Very large workbooks are processed with range-node collapsing and are slower to explain.
- Model explanations can be imperfect; the formula and evidence beside each claim are the source of truth.
- Results are suspicious cells to review, not an audit.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Page shows "Cannot reach the backend" | Start uvicorn (see Run); check nothing else squats port 8000: `curl http://127.0.0.1:8000/api/health` must print `{"backend":"ok",…}` |
| Blank page / blocked fetches | Open `http://localhost:5173`, not `http://127.0.0.1:5173` (CORS) |
| "Unexpected response … Is the SheetSense backend running on port 8000?" | Another app is answering on :8000 — stop it and restart uvicorn |
| Explanations say "unavailable" | `ollama list` → set exact name in `backend/.env` as `MODEL_NAME`, restart backend |
| First analysis is slow | Normal — Gemma loads once (~4 min for `dirty.xlsx` on CPU); reruns are instant from SQLite cache |

## How it works (short)

`reader → refs → graph → labels → grouping → detectors → explainer → SQLite`,
then REST + SSE to a React UI. See `backend/app/` for the code; the deterministic
core never executes formulas or macros, and prompts sent to the model contain
one small fact bundle each.
