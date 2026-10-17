# SheetSense — Spreadsheet Inheritance Translator

SheetSense helps you make sense of an Excel workbook you inherited — the kind named `pricing_FINAL_v7_use_this_one.xlsx` whose original author is long gone. You get a plain-English overview of each sheet, a ranked list of suspicious cells worth reviewing, a dependency map showing how sheets and cells feed into each other, and a Q&A box that traces a number back to its source cells with clickable citations.

It runs entirely on your machine. The workbook never leaves your computer.

Deterministic Python code finds the facts (formulas, cell references, dependency graphs, suspicious patterns). A local Gemma model — served through Ollama — only turns those facts into plain-English explanations. The model never decides what's wrong and never invents dependencies.

It's for anyone who's inherited a spreadsheet: an accountant taking over a client's books, a small business owner puzzling through a pricing model, an operations analyst handed a file nobody else wants to touch.

## Problem Statement

**Problem:** Understanding someone else's spreadsheet takes far longer than building your own. Files circulate with names like `pricing_FINAL_v7_use_this_one.xlsx`, the creator has left, and nobody remembers why certain formulas exist, which cells are safe to edit, or whether the bottom-line numbers are even right. A spreadsheet with a wrong formula can keep producing believable numbers for months without anyone noticing.

**Existing gap:** You could paste a formula into a chatbot and ask it to explain. That works for a single cell. It breaks down with thousands of formulas across multiple sheets — a chatbot doesn't see the full dependency structure, can't systematically spot the one formula that breaks a repeating pattern, and can't handle a workbook too large for its context window. There's also the privacy problem: client financials, payroll, and internal pricing don't belong in a hosted AI service.

**Approach:** SheetSense reads the workbook itself with openpyxl, tokenizes formulas, builds a dependency graph with networkx, and runs code-based checks that flag suspicious constants, inconsistent formula patterns, short SUM ranges, unused inputs, error values, circular references, and unit mismatches. Only then does a local Gemma model explain the verified findings in plain English. Code finds the facts; the model phrases them.

## Features

Implemented:

- **Plain-English workbook overview** — a summary of each sheet and its purpose, generated from verified structure rather than guesswork.
- **Suspicious cell review** — a ranked list of cells to look at (hardcoded values inside formulas, formula pattern breaks, SUM ranges that might miss data, unused inputs, error values, circular references, unit mismatches). These are "cells to review," not declared errors — SheetSense is not an audit.
- **Dependency map** — sheet-level view of how sheets and cells feed into one another, built from the actual formula references.
- **Q&A with citations** — ask where a number comes from, trace the dependency chain first, and get clickable, validated cell citations that point back to the evidence.
- **Fully local** — analysis and inference run on your machine; nothing uploads anywhere.
- **Markdown export** — export a handoff document documenting the workbook's structure and flagged items.

Not yet built / planned:

- Group-level dependency map toggle (the current map is sheet-level).
- Packaged desktop application and workbook handover reporting as a service (business ideas described by the author, not implemented features).

## How It Works

1. **Input:** You upload an Excel workbook (`.xlsx` works directly; legacy `.xls` is converted locally with LibreOffice when installed). `.xlsm` files with macros are rejected.
2. **Validation:** The file is parsed with openpyxl; corrupt or unreadable workbooks raise a clear error instead of a raw traceback. VBA/macros are not executed and never will be.
3. **Processing:**
   - Formulas are tokenized to extract cell and range references, including cross-sheet and absolute references.
   - A directed dependency graph (networkx) connects precedent cells to the cells that depend on them.
   - Each formula is normalized to a relative form so repetitive patterns can be grouped and outliers spotted (for example, `=B5*C5` and `=B6*C6` are the same pattern).
   - Deterministic detectors flag suspicious constants, inconsistent patterns, incomplete SUM ranges, unused inputs, error values, circular references, and unit mismatches.
4. **Storage / external services:** Results are cached in SQLite (`~/.sheetsense` or `DATA_DIR`). The backend calls a locally running Ollama instance (`http://localhost:11434`) for Gemma explanations only when useful. No external APIs, no telemetry.
5. **Output:** A React frontend shows the overview, issue list, dependency map, and Q&A page. Analysis progress is streamed to the interface via SSE. You can export a Markdown handoff report.

### Key Design Decisions

- **Code finds the facts, the model explains them.** Deterministic Python handles parsing, graph building, and detection. The LLM only phrases verified facts into explanations and is never allowed to declare a formula wrong or invent a dependency. Citations outside the traced chain are rejected.
- **Local inference.** Ollama + Gemma runs on your machine so client financials never leave your hardware, there's no per-request API bill, and the tool works offline once the model is installed. Trade-off: smaller local models can give weaker explanations, and you need suitable hardware.
- **Phase A first, Phase B second.** Deterministic analysis (phase A) runs and persists before model explanations (phase B). If the model fails or is interrupted, phase A results are untouched and the workbook is still usable.
- **No formula execution.** SheetSense reads formulas statically; it never executes VBA, macros, or formulas, which keeps it safe with untrusted files.

## Architecture

### System Architecture

The backend is a FastAPI service on `127.0.0.1:8000`. The frontend is a React + Vite app on `http://localhost:5173`. Analysis runs in two phases: phase A (parse → refs → graph → grouping → detectors → SQLite) and phase B (model explanations for groups, sheets, and workbook). Progress streams to the UI via SSE.

<!-- Add a Mermaid diagram or link to docs/ARCHITECTURE.md for a detailed diagram. -->

### Data Flow

Workbook file → openpyxl reader → reference tokenizer → networkx dependency graph → formula grouping → deterministic detectors → SQLite cache → (phase B) Ollama/Gemma explanations → FastAPI REST + SSE → React frontend.

### Important Components

- **Backend (`backend/app/`)** — FastAPI app (`main.py`), config, API routers for workbooks, analysis, chat/Q&A, and export.
- **Parser (`backend/app/core/parser/`)** — reads the workbook and extracts formulas and cached values.
- **References (`backend/app/core/parser/refs.py`)** — tokenizes formulas and resolves cell/range references across sheets.
- **Graph (`backend/app/core/graph/`)** — builds the dependency graph and answers precedent/dependent queries.
- **Grouping (`backend/app/core/grouping/`)** — normalizes formulas to relative patterns and groups repetitive ones.
- **Detectors (`backend/app/core/detectors.py`)** — code-based rules that flag suspicious cells.
- **Explainer (`backend/app/core/llm/`)** — talks to local Ollama; small fact bundles in, structured explanations out. Templates handle trivial groups without a model call.
- **Database (`backend/app/db/`)** — SQLite via SQLAlchemy; stores workbooks, results, and cached explanations.
- **Frontend (`frontend/src/`)** — React pages (setup, upload, overview, issues, sheet map, ask), TanStack Query for data fetching, xyflow for the dependency graph, Zustand for state.

## Tech Stack

| Technology | Purpose |
|------------|---------|
| Python 3.11+ | Core implementation |
| FastAPI | Backend web framework |
| Uvicorn | ASGI server |
| openpyxl | Reading Excel formulas and cached values |
| networkx | Dependency graph construction and queries |
| SQLAlchemy + SQLite | Persistent storage of workbooks and results |
| pytest | Automated backend tests |
| Playwright | End-to-end frontend tests |
| React 19 | Frontend UI |
| Vite | Frontend build tool and dev server |
| TypeScript | Frontend type checking |
| Tailwind CSS | Styling |
| React Router | Client-side routing |
| TanStack Query | Server state management |
| xyflow/react | Dependency graph visualization |
| Ollama + Gemma | Local LLM for plain-English explanations |

Non-obvious choices: networkx for the graph because dependency tracing needs real graph queries (precedents, dependents, cycles); SQLite because it's file-based, requires no separate server, and fits the local-first privacy goal.

## Codebase Structure

```text
Sheet-Sense/
├── backend/
│   ├── .env.example          # Example environment config (copy to .env; never commit .env)
│   ├── pyproject.toml        # Python project config and dependencies
│   ├── app/
│   │   ├── main.py           # FastAPI entrypoint, CORS, and health check
│   │   ├── config.py         # Settings (MODEL_NAME, OLLAMA_URL, LLM_WORKERS, DATA_DIR)
│   │   ├── api/              # REST routes: workbooks, analysis, chat, export
│   │   ├── core/             # parser, refs, graph, grouping, detectors, llm, db, export
│   │   ├── db/               # SQLite session and tables
│   │   └── export/           # Markdown handoff export
│   └── tests/                # pytest suite + fixtures and edge-case workbooks
├── frontend/
│   ├── package.json          # Node project config
│   ├── vite.config.ts        # Vite build/dev config
│   ├── tsconfig.json         # TypeScript config
│   ├── playwright.config.ts  # E2E test config
│   ├── src/
│   │   ├── api/              # API client and types
│   │   ├── components/       # UI components (graph, issues, chat, upload, etc.)
│   │   ├── hooks/            # useProgress, useWorkbook
│   │   └── pages/            # Setup, Upload, Overview, Issues, Sheet, Ask
│   └── test-results/         # Playwright results
├── docs/
│   ├── screenshots/          # setup, home, overview, map, issues, ask, keyboard
│   ├── ARCHITECTURE.md       # architecture notes (full doc pending)
│   └── index.html
├── .gitignore
├── LICENSE                   # MIT
├── README.md
├── agent.md                  # agent working notes
├── TEST_REPORT.md            # QA test report
└── design.jpg
```

Where to contribute:

- `backend/app/core/detectors.py` — add or tune suspicious-cell rules.
- `backend/app/core/parser/` and `backend/app/core/graph/` — change how workbooks are read or how references are resolved.
- `backend/app/core/llm/` — adjust prompts, model client, or templates.
- `frontend/src/pages/` and `frontend/src/components/` — UI changes (pages are Setup, Upload, Overview, Issues, Sheet, Ask).
- `backend/app/main.py` — CORS, health, and router wiring (the backend is locked to `127.0.0.1` by design).

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 18+ (for the frontend)
- [Ollama](https://ollama.com) with enough disk/RAM for a Gemma instruct model, e.g. `gemma3:4b` (~3.3 GB). Check installed models with `ollama list`.

### Installation

```bash
# Clone the repository
git clone https://github.com/PIYUSH-NEXTGEN/Sheet-Sense.git
cd Sheet-Sense

# Backend
cd backend
python -m venv .venv

# Windows:
.venv\Scripts\activate
# macOS/Linux:
# source .venv/bin/activate

pip install -e ".[test]"

# Copy env config and edit MODEL_NAME to an installed model (never commit .env):
copy .env.example .env        # Windows
# cp .env.example .env        # macOS/Linux

# Pull the model (needs network once, then never again):
ollama pull gemma3:4b
ollama serve                  # only if Ollama isn't already running

# Frontend
cd ../frontend
npm install
```

### Configuration

Copy `backend/.env.example` to `backend/.env` and set `MODEL_NAME` to the exact Gemma variant you pulled (e.g. `gemma3:4b`). Optional overrides: `OLLAMA_URL` (default `http://localhost:11434`) and `LLM_WORKERS` (default 1 — a stock Ollama server answers one request at a time, so more workers on the client side can actually slow things down unless you also raise `OLLAMA_NUM_PARALLEL` on the server).

Never include real API keys, credentials, or production secrets. There are no API keys in this project — everything is local.

### Run Locally

Terminal 1 — backend (from `backend/`):

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Terminal 2 — frontend (from `frontend/`):

```bash
npm run dev
```

Open `http://localhost:5173` (use `localhost`, not `127.0.0.1` — the backend's CORS list allows exactly that origin).

Upload `backend/tests/fixtures/harbor-supply-pricing.xlsx` and follow the progress bar into the overview, dependency map, issues list, and Ask page.

Verify the backend is reachable: `curl http://127.0.0.1:8000/api/health` should print `{"backend":"ok", ...}`.

## Usage

- **Upload:** Drag a workbook onto the setup page. `.xlsx` works directly; `.xls` is converted locally if LibreOffice is installed; `.xlsm` is rejected.
- **Overview:** Read the plain-English summary of each sheet and the dependency map.
- **Issues:** Review the ranked list of suspicious cells, filterable by severity. Examples from the sample fixture: a hardcoded `1.15` in `Summary!B5`, a pattern break in `Pricing!C13`, a short `SUM` in `Summary!B3`, orphan inputs, and a circular reference.
- **Ask:** Type a question like *"Where does the total with surcharge come from?"* The app traces the dependency chain first, then explains it with clickable cell citations that land you on the relevant sheet.
- **Export:** Download a Markdown handoff document summarizing structure and flagged items.

Example API call:

```bash
curl http://127.0.0.1:8000/api/health
```

Screenshots: see `docs/screenshots/` — `setup.png`, `home.png`, `overview.png`, `map.png`, `issues.png`, `ask.png`, `keyboard.png`.

## Configuration Reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `MODEL_NAME` | Yes | None | Installed Gemma model name, e.g. `gemma3:4b` — see `ollama list` |
| `OLLAMA_URL` | No | `http://localhost:11434` | Local Ollama endpoint |
| `LLM_WORKERS` | No | `1` | Parallel explanation workers; keep at 1 unless you raise `OLLAMA_NUM_PARALLEL` server-side |
| `DATA_DIR` | No | `~/.sheetsense` | Local directory for stored workbooks and cached results |

## Testing

```bash
cd backend
python -m pytest            # mocked LLM; passes without Ollama
python -m pytest -m ollama  # one live test, skipped unless Ollama is running
```

The suite covers parsing, reference extraction, graph building, detectors, grouping, API endpoints, Q&A, and edge cases (corrupt files, array formulas, cycles, unusual sheet names, etc.).

Frontend:

```bash
cd frontend
npm run build   # runs tsc --noEmit + Vite build
```

There is no ESLint config, so linting is N/A. End-to-end Playwright checks live under `frontend/` (`setup.spec.ts`, `upload.spec.ts`, `flow.spec.ts`, `audit.spec.ts`).

## Performance

No formal benchmarks have been published. Measured during QA on the sample fixture (cold cache, CPU, Gemma via Ollama): roughly 16 model calls for about four minutes of model wall time, dominated by single-token-per-second CPU inference. Results are cached in SQLite, so reruns are instant. Template descriptions handle trivial groups without a model call, and batching reduces round trips. These observations are specific to one machine and workload — treat them as informal, not guarantees.

## Security

- **Local-first:** The workbook is parsed and stored on your machine (`~/.sheetsense` or `DATA_DIR`). Nothing is uploaded, and there is no telemetry or analytics.
- **Network:** The only traffic is between local processes — browser → backend (`http://127.0.0.1:8000`) and backend → Ollama (`http://localhost:11434`). No CDN assets; fonts are system fonts and all JS/CSS is bundled.
- **Macros:** `.xlsm` files are rejected. Formulas are read statically, never executed.
- **Backend binding:** FastAPI binds to `127.0.0.1` only, not a public interface.
- **No secrets:** There are no API keys or production secrets in the project.

To report a security vulnerability, contact the repository owner privately (do not open a public issue).

## Status

SheetSense is an early release (v0.1.0). The deterministic core — parsing, graphing, detection, local explanations, Q&A — is implemented. Known limitations: VBA/macros unsupported, cached values may be missing, very large workbooks are slower, model explanations can be imperfect and are always presented alongside the underlying evidence, and results are cells to review, not an audit. The group-level map toggle and desktop packaging are not yet built.

## Contributing

Bug reports, feature proposals, and pull requests are welcome. Run the backend test suite (`python -m pytest`) and the frontend build (`npm run build`) before submitting. There is no separate `CONTRIBUTING.md` yet — open an issue to discuss larger changes first.

## License

MIT License. See the [`LICENSE`](LICENSE) file.

