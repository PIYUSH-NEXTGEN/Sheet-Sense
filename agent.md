# AGENT_PROMPT.md — SheetSense (Spreadsheet Inheritance Translator)

You are building **SheetSense**: a fully local app that takes an inherited Excel workbook and produces (1) a plain-English explanation of what it does, (2) a ranked list of suspicious cells, (3) a dependency map, and (4) a Q&A box that traces where a number comes from.

Everything runs on the user's machine. No cloud calls. The AI is a local open-weight **Gemma** model served by **Ollama**.

Work **one phase at a time** (see "Build Phases"). Do not start a phase until the previous phase's acceptance tests pass. After each phase, summarize what you built and what you tested.

---

## 0. Golden rules (read before writing any code)

1. **Code determines facts. The model only phrases them.** Cells, formulas, dependencies, and issues come from deterministic Python. The model never decides what is an error and never invents a dependency.
2. **Never send a whole workbook to the model.** Prompts contain one small structured fact bundle (one formula group, one sheet summary, one traced chain).
3. **All model output is JSON-schema constrained** and validated. Every cell address the model mentions must be checked against the graph; drop any that do not exist.
4. **Mock the LLM in all automated tests.** Tests must pass with Ollama not installed.
5. **No network calls except to the local Ollama URL.** No telemetry, no analytics, no CDN assets at runtime (bundle everything).
6. **Never execute formulas or macros.** Read only.
7. **Model name and Ollama URL come from config** (env vars). Never hardcode a model.
8. **Show evidence next to every claim:** the original formula, the cell address, and the source text of the issue.
9. Label output as "suspicious cells to review", never as proof of errors. This is not an audit certificate.
10. Keep code typed (Python type hints, TypeScript strict) and small-function. Write tests as you go.

---

## 1. Tech stack (fixed — do not substitute)

**Backend (Python 3.11+):** FastAPI, uvicorn, openpyxl, networkx, pydantic v2, SQLAlchemy (SQLite), httpx, pytest.
**Frontend:** React + Vite + TypeScript (strict), React Router, TanStack Query, Tailwind CSS, React Flow (`@xyflow/react`) for the dependency map.
**Model runtime:** Ollama (`http://localhost:11434`) running a Gemma instruct model. Default `MODEL_NAME` is read from env; document in README that the user should run `ollama list` and pick an installed Gemma variant their hardware can handle.
**Storage:** SQLite file in a local data dir.

---

## 2. Repository layout

```
sheetsense/
├─ README.md
├─ docs/ARCHITECTURE.md
├─ backend/
│  ├─ pyproject.toml
│  ├─ app/
│  │  ├─ main.py                  # FastAPI app, CORS limited to localhost dev origin
│  │  ├─ config.py                # OLLAMA_URL, MODEL_NAME, MAX_FILE_MB, MAX_CELLS, DATA_DIR
│  │  ├─ api/
│  │  │  ├─ workbooks.py          # upload, list, get, delete
│  │  │  ├─ analysis.py           # start, SSE progress, overview, sheets, issues, graph
│  │  │  ├─ chat.py               # ask
│  │  │  └─ export.py             # markdown export
│  │  ├─ core/
│  │  │  ├─ models.py             # pydantic domain models
│  │  │  ├─ parser/{reader.py, refs.py, labels.py}
│  │  │  ├─ graph/{builder.py, queries.py}
│  │  │  ├─ grouping/patterns.py
│  │  │  ├─ detectors/{base.py, hardcoded_constant.py, pattern_break.py,
│  │  │  │            range_gap.py, orphan_input.py, error_values.py,
│  │  │  │            circular.py, unit_mismatch.py}
│  │  │  ├─ llm/{client.py, prompts.py, schemas.py, explainer.py, qa.py, cache.py}
│  │  │  └─ pipeline.py
│  │  ├─ db/{session.py, tables.py}
│  │  └─ export/markdown.py
│  └─ tests/
│     ├─ fixtures/make_fixture.py
│     └─ test_{parser,graph,patterns,detectors,pipeline,llm,api}.py
└─ frontend/
   ├─ package.json, vite.config.ts, tsconfig.json, tailwind config
   └─ src/
      ├─ main.tsx, App.tsx
      ├─ api/{client.ts, types.ts}
      ├─ hooks/{useProgress.ts, useWorkbook.ts}
      ├─ pages/{SetupPage, UploadPage, OverviewPage, SheetPage, IssuesPage, AskPage}.tsx
      └─ components/{FileDropzone, ProgressBar, DependencyGraph, FormulaGroupCard,
                     IssueList, CellChip, ChatPanel}.tsx
```

---

## 3. Domain models (pydantic; mirror in `frontend/src/api/types.ts`)

```python
class CellRef(BaseModel):
    sheet: str
    address: str                      # "F12"

class CellRecord(BaseModel):
    ref: CellRef
    formula: str | None               # "=D12*E12"
    value: Any | None                 # cached value; may be None if never calculated
    number_format: str | None
    label_left: str | None            # nearest text cell to the left in the same row
    label_above: str | None           # column header (nearest text above)
    kind: Literal["input", "formula", "label", "empty"]

class FormulaGroup(BaseModel):
    id: str
    sheet: str
    pattern_r1c1: str                 # normalized relative formula
    cells: list[str]                  # addresses in the contiguous block
    sample_formula: str
    labels: dict[str, str]            # column header + labels of each referenced input
    sample_values: list[Any]

class Issue(BaseModel):
    id: str
    detector: str
    severity: Literal["high", "medium", "low"]
    ref: CellRef
    message: str                      # written by code templates, never by the model
    evidence: dict[str, Any]          # formula, neighbors, expected pattern, etc.

class Explanation(BaseModel):
    target_type: Literal["group", "sheet", "workbook"]
    target_id: str
    text: str
    structured: dict[str, Any]
    model: str
    prompt_version: str
```

---

## 4. Pipeline (core/pipeline.py)

Run stages in order. Emit a progress event `{stage, percent, detail}` after each stage (consumed by SSE).

1. **Parse** — `reader.py` loads the workbook twice with openpyxl: `data_only=False` (formulas) and `data_only=True` (cached values). Build `CellRecord`s. Enforce `MAX_FILE_MB` and `MAX_CELLS`. Reject `.xlsm`/macro workbooks with a clear error in v1.
   - **Important:** workbooks written by openpyxl (including the test fixtures) have **no cached values**. The whole tool must work without them. Only `error_values` and display of sample values depend on cached values; when absent, set a workbook-level warning `cached_values_missing` and skip those parts gracefully.
2. **Resolve references** — `refs.py` uses `openpyxl.formula.Tokenizer`. Extract operands of subtype RANGE. Handle: cross-sheet refs (`'My Sheet'!A1`), absolute refs (`$A$1`), ranges (`A1:B10`), whole column refs (cap them), and defined names (resolve via workbook defined names). Expand ranges into cells, but **cap expansion** (e.g. > 5,000 cells): beyond the cap, create a single "range node" in the graph instead.
3. **Build graph** — `networkx.DiGraph`, edge direction precedent → dependent. Node attributes: sheet, address, kind (input/formula/output/range), formula. Input = numeric/text constant that is referenced by something. Output = formula with no dependents.
4. **Label** — `labels.py` attaches `label_left` and `label_above` so the model sees "Unit Cost × Qty", not `B5*C5`.
5. **Group** — `grouping/patterns.py` (see 5.1).
6. **Detect** — run every registered detector (see section 6).
7. **Explain** — `llm/explainer.py`: groups → sheets → workbook (see section 7). Cached.
8. **Persist** — write everything to SQLite so reopening is instant.

### 5.1 Relative-formula normalization (patterns.py)

For each formula cell at host position (row r, col c), convert every reference to relative notation:
- relative ref at (r2, c2) → `R[r2-r]C[c2-c]`
- absolute parts (`$`) keep absolute coordinates, e.g. `R5C2`
- preserve sheet qualifiers
- apply to both endpoints of a range

Two cells have the same pattern iff their normalized strings are equal. Form a `FormulaGroup` from each **contiguous run** (same column, or same row) of cells with the same pattern. Single-cell formulas become their own group of size 1. Group IDs are stable (hash of sheet + pattern + first address).

---

## 6. Detectors (all deterministic; messages from templates)

Interface:

```python
class Detector(Protocol):
    name: str
    def run(self, wb: ParsedWorkbook, graph: nx.DiGraph,
            groups: list[FormulaGroup]) -> list[Issue]: ...
```

Register detectors in `detectors/base.py`; the pipeline runs all registered ones.

| Detector | Rule | Severity |
|---|---|---|
| `hardcoded_constant` | Formula contains a numeric literal not in a configurable allow-list (default `{0, 1, 2, 100}`). **Ignore** literals that are: the 2nd arg of `ROUND/ROUNDUP/ROUNDDOWN`, the match-type arg of `MATCH`, the column index / range_lookup args of `VLOOKUP`/`HLOOKUP`, `INDEX` row/col args, and `IF` branch results of 0/1. | medium |
| `pattern_break` | Per column and per row: find the dominant normalized pattern. Flag a cell that is **sandwiched** (the cells immediately before and after it in that column/row both have the dominant pattern) but is itself a different formula pattern **or a hardcoded constant**. | high |
| `range_gap` | `SUM/AVERAGE/MIN/MAX/COUNT` whose range ends and the cell immediately after the range end (same column/row, excluding the host cell itself) contains a numeric value or formula result that looks like part of the same data block. | high |
| `orphan_input` | A constant numeric input cell with a label, no dependents, and not part of a data column where other cells in that column are referenced. | low |
| `error_values` | Cached values equal to `#REF!`, `#DIV/0!`, `#N/A`, `#NAME?`, `#VALUE!`, `#NUM!`, `#NULL!`. Also formulas containing the literal `#REF!`. Skip with warning if no cached values. | high |
| `circular` | Use `nx.strongly_connected_components`; report SCCs with size > 1 and self-loops. Do **not** use `simple_cycles` on large graphs. | high |
| `unit_mismatch` | Percent-formatted cells holding values > 1, or cells holding 0.0x vs x in the same column where the number format says percent. Conservative; low false-positive rate matters more than recall. | low |

Every `Issue.evidence` includes the cell's formula, its normalized pattern, and the neighbor formulas used for the comparison.

**False positives are worse than misses.** Prefer conservative rules and cover them with tests, including a "clean workbook produces zero issues" test.

---

## 7. LLM layer

### 7.1 Client (llm/client.py)
- `POST {OLLAMA_URL}/api/chat`, `stream: false`, `options: {temperature: 0}`.
- Use Ollama's structured output: pass a JSON Schema in `format`. If the installed Ollama rejects schema-format, fall back to `format: "json"` and validate with pydantic.
- Put all instructions in the **user** message (do not rely on a system role).
- Retry once on invalid JSON, then raise a typed `LLMError`; the pipeline stores a placeholder explanation ("Explanation unavailable") and continues.
- Worker pool of 2–4 concurrent calls (configurable).
- `GET /api/health` checks: Ollama reachable? Is `MODEL_NAME` in the model list?

### 7.2 Prompts (llm/prompts.py) — each has a `PROMPT_VERSION` constant
1. **group_explanation** — input: sample formula (A1), column header, labels of each referenced input, up to 3 sample values, cell count and range. Output schema: `{"summary": str, "plain_formula": str}`. Instruction: 1–2 plain sentences, no jargon, no speculation beyond the given facts.
2. **sheet_summary** — input: list of group summaries, counts of inputs/outputs. Output: `{"purpose": str, "key_inputs": [str], "key_outputs": [str]}`.
3. **workbook_overview** — input: sheet summaries + sheet-level edges. Output: `{"overview": str, "reading_order": [str]}`.
4. **qa_answer** — see section 8.

Prompts must say: "Use only the facts provided. If the facts are insufficient, say so."

### 7.3 Cache (llm/cache.py)
Key = sha256(normalized formula + labels JSON + model name + prompt version). Store in SQLite. Identical requests never hit the model twice.

---

## 8. Question answering (llm/qa.py)

1. Input: user question.
2. **Candidate targets:** code fuzzy-matches the question against cell labels (`label_left`, `label_above`, sheet names) and returns up to 8 candidate cells. Ask the model to pick the best one via schema `{"target": "Sheet!A1"}`; validate it is among the candidates.
3. **Trace:** `graph/queries.py` returns ancestors of the target up to depth N (default 6), collapsed into formula groups and input cells.
4. Gather the existing group explanations along the chain.
5. Ask the model, using only that chain, for `{"answer": str, "cited_cells": [str]}`.
6. **Validate:** remove any cited cell not present in the traced chain. If nothing valid remains, return an "I couldn't trace that" message.
7. Response includes the answer, the validated cited cells, and the chain's formulas for display.

---

## 9. REST API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Backend + Ollama + model status |
| POST | `/api/workbooks` | Multipart upload `.xlsx`, returns `workbook_id` |
| GET | `/api/workbooks` | List saved analyses |
| DELETE | `/api/workbooks/{id}` | Delete workbook, file, and data |
| POST | `/api/workbooks/{id}/analyze` | Start pipeline (background thread) |
| GET | `/api/workbooks/{id}/progress` | SSE: `{stage, percent, detail}` |
| GET | `/api/workbooks/{id}/overview` | Workbook explanation + stats + warnings |
| GET | `/api/workbooks/{id}/sheets/{name}` | Groups + explanations + issues on that sheet |
| GET | `/api/workbooks/{id}/issues?severity=` | Issues |
| GET | `/api/workbooks/{id}/graph?level=sheet\|group` | Nodes and edges for the map |
| POST | `/api/workbooks/{id}/ask` | `{question}` → answer + cited cells + chain |
| GET | `/api/workbooks/{id}/export?format=md` | Markdown documentation |

Security: bind uvicorn to `127.0.0.1`; CORS allows only `http://localhost:5173`; uploaded files stored under `DATA_DIR` with random names; file type validated by extension and by opening with openpyxl.

---

## 10. Frontend requirements

- **SetupPage:** shown if `/api/health` reports Ollama down or model missing; display the exact commands to fix it (install Ollama, `ollama pull <model>`, set `MODEL_NAME`).
- **UploadPage:** drag-and-drop, file validation, start analysis, progress bar fed by SSE; list previously analyzed workbooks with delete.
- **OverviewPage:** plain-English overview, stats (sheets, formulas, inputs, outputs, issues by severity), the dependency map (sheet-level by default, toggle to group-level), warnings such as "cached values missing".
- **SheetPage:** a `FormulaGroupCard` per group: explanation, original formula, range, input labels, and any issues on those cells.
- **IssuesPage:** filter by severity and detector; each issue shows message, the formula, neighbor evidence, and a `CellChip` linking to its sheet/group.
- **AskPage:** chat panel; answers show clickable `CellChip`s and the formulas in the traced chain.
- **Export button** downloads the Markdown file.
- UI states: loading, empty, error for every page. Keyboard accessible. Works at 1280px and above; usable on a laptop screen.
- Copy: use "suspicious cells to review", never "errors found".

---

## 11. Testing requirements

### 11.1 Fixture generator — `tests/fixtures/make_fixture.py`
Generate two workbooks with openpyxl: `dirty.xlsx` and `clean.xlsx`.

**Layout (both):**
- Sheet `Inputs`: A1 "Item", B1 "Unit Cost", C1 "Qty"; rows 2–21 hold 20 items with numeric cost and qty.
- Sheet `Settings`: A1 "Markup" B1 `0.25`; A2 "Tax rate" B2 `0.08`; A4 "Surcharge" B4 `0.15`.
- Sheet `Pricing`, rows 2–21 (header row 1: Item, Cost Total, Price, With Tax):
  - A: `=Inputs!A{r}`
  - B: `=Inputs!B{r}*Inputs!C{r}`
  - C: `=B{r}*(1+Settings!$B$1)`
  - D: `=C{r}+C{r}*Settings!$B$2`
- Sheet `Summary` (labels in column A, formulas in column B):
  - B2 "Total cost": `=SUM(Pricing!B2:B21)`
  - B3 "Total price": `=SUM(Pricing!C2:C21)`
  - B4 "Total with tax": `=SUM(Pricing!D2:D21)`
  - B5 "Total with surcharge": `=B4*(1+Settings!B4)`

**`dirty.xlsx` differs from clean in exactly five places (the planted problems):**
1. `Summary!B5` = `=B4*1.15` → **hardcoded_constant**
2. `Pricing!C13` = the number `99.5` (constant inside a formula column) → **pattern_break**
3. `Summary!B3` = `=SUM(Pricing!C2:C20)` (skips row 21) → **range_gap**
4. `Settings!A3` "Unused discount", `Settings!B3` = `0.10`, referenced by nothing → **orphan_input**
5. `Summary!A7` "Loop A" `B7` = `=B8+1`; `Summary!A8` "Loop B" `B8` = `=B7*2` → **circular**

Also write `expected_issues.json` listing the expected `{detector, sheet, address}` for `dirty.xlsx`. **Known side effect:** in `dirty.xlsx`, replacing the surcharge reference in `Summary!B5` with a literal leaves `Settings!B4` unreferenced, so `orphan_input` will correctly report **both** `Settings!B3` and `Settings!B4`. The expected file must therefore contain six entries (the five planted problems plus this one extra orphan), and tests must assert exactly that set.

If LibreOffice is available (`soffice --headless --convert-to xlsx`), the generator may optionally recalculate to add cached values; **tests must pass without it.**

### 11.2 Required tests
- Parser returns correct formulas, kinds, and labels for fixture cells.
- Reference extraction: cross-sheet, absolute, range, quoted sheet names, defined names.
- Graph: precedents/dependents of `Summary!B4` are correct.
- Grouping: `Pricing!C2:C21` in `clean.xlsx` collapses to **one** group of 20 cells; in `dirty.xlsx` the pattern-break is detected, not silently merged.
- Detectors: all five planted issues are found on `dirty.xlsx` with the correct detector and address; `clean.xlsx` produces **zero** issues.
- LLM layer (mocked): schema validation, retry-then-placeholder behavior, cache hit on second run, hallucinated cell citation is dropped.
- Pipeline end to end with mocked LLM.
- API: upload → analyze → poll progress → get overview/issues/graph/ask (mocked LLM) → export → delete.
- Optional integration test marked `@pytest.mark.ollama`, skipped unless Ollama is reachable.

---

## 12. Build phases (give yourself one at a time)

### Phase 1 — Parser, references, graph
Build `config.py`, `models.py`, `reader.py`, `refs.py`, `labels.py`, `graph/builder.py`, `graph/queries.py`, and `make_fixture.py`.
**Done when:** parser, reference, and graph tests pass on both fixtures.

### Phase 2 — Grouping and detectors
Build `patterns.py`, the detector registry, and all seven detectors.
**Done when:** the six expected issues are detected on `dirty.xlsx` (five planted plus the extra orphan), `clean.xlsx` yields zero issues, and grouping tests pass.

### Phase 3 — Persistence and REST API (LLM stubbed)
Build SQLAlchemy tables, the pipeline (with a stub explainer that returns placeholder text), all REST endpoints, SSE progress, and export.
**Done when:** upload → analyze → issues/overview/graph/export works with `curl` and in API tests.

### Phase 4 — Gemma via Ollama
Build `client.py`, prompts, schemas, `explainer.py`, `cache.py`, and the health check.
**Done when:** with Ollama running, real explanations appear for the fixture; a second run is served from cache; mocked tests cover failure paths.

### Phase 5 — Frontend core
Scaffold Vite + TS + Tailwind. Build SetupPage, UploadPage with SSE progress, OverviewPage (without the map), SheetPage, IssuesPage.
**Done when:** the full flow works in the browser against the real backend using `dirty.xlsx`.

### Phase 6 — Dependency map and Q&A
Build `DependencyGraph` with React Flow (sheet-level and group-level toggle), `qa.py`, the `/ask` endpoint, AskPage, and `CellChip` navigation.
**Done when:** asking "Where does the total with surcharge come from?" on `dirty.xlsx` returns a traced answer with validated, clickable cells.

### Phase 7 — Polish and handoff
Markdown export refinement, empty/error states, README with: install steps, `ollama pull` instructions, how to run backend and frontend, how to run tests, a privacy statement, and known limitations. Add `docs/ARCHITECTURE.md`. Include a 60-second demo script (turn off Wi-Fi, upload `dirty.xlsx`, show the five findings and the Q&A).
**Done when:** a fresh clone can be run from the README alone.

---

## 13. Known limitations to document (do not try to solve in v1)
- VBA/macros are unsupported (`.xlsm` rejected).
- Cached values may be missing; value-based checks degrade gracefully.
- Very large workbooks are processed with range-node collapsing and are slower to explain.
- Model explanations can be imperfect; the formula and evidence are always displayed beside them.
- Results are suspicious cells to review, not an audit.

---

## 14. Definition of done
- All automated tests pass without Ollama installed.
- With Ollama + Gemma running, the full demo works offline.
- `dirty.xlsx` yields exactly the six expected issues in `expected_issues.json` (the five planted problems plus the extra orphan `Settings!B4`); `clean.xlsx` yields none.
- No outbound network requests other than to `OLLAMA_URL` (verify by inspection of the code and a quick check with the network disabled).
- README lets a new user run everything.
