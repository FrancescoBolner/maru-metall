# Maru Metall — Takeoff & Quoting Assistant (demo)

Reads a client's inquiry folder (e-mails, IFC/Tekla models, material lists, PDF drawings, images), builds a
metal-only takeoff with a reference for every number, predicts what is missing, prices it with Maru's own rules
(two methods: quick €/t and part-by-part), adds a carbon balance, and produces an interactive report, a client
offer PDF, an internal report PDF and an Excel file. The estimator reviews (direct edits or written corrections),
recalculates (`_rev2`, `_rev3` …) and approves; approvals feed the learning data. **The AI never produces a price.**

## Run (one command)

| Option | Command | Open |
|---|---|---|
| Docker | `docker compose up --build` | http://localhost:8000 |
| Windows, no Docker | `powershell -ExecutionPolicy Bypass -File scripts\start.ps1` | http://localhost:8000 |
| macOS / Linux, no Docker | `./scripts/start.sh` or `make run` | http://localhost:8000 |
| Development | `make dev` (Windows: `scripts\dev.ps1`) | http://localhost:5173 |

Needs Python 3.12 (3.11–3.13 work) for the non-Docker path. Node 22 is only needed to rebuild the web app;
the built app is already in `frontend/dist`. All versions are pinned (`backend/requirements.txt`,
`frontend/package-lock.json`).

**AI key (optional).** Copy `.env.example` to `.env` and set `ANTHROPIC_API_KEY`. The key is read by the server
only and never sent to the browser. Without a key the app runs with the **offline rules provider** (nothing leaves
the computer); this is what produced the numbers below. `AI_PROVIDER=local` switches to a private model on Maru's
own server (any OpenAI-compatible endpoint: Ollama, vLLM, LM Studio — see `LOCAL_AI_BASE_URL`, `LOCAL_AI_MODEL`).

**PDFs on Windows.** WeasyPrint needs the GTK/Pango libraries. In Docker they are installed. On plain Windows,
if they are missing, the app automatically uses a simpler PDF layout (PyMuPDF); install GTK3 (see WeasyPrint docs)
for the full layout.

## How to use
1. **Clients** → choose a client → choose a project (each folder under `drives/client/<client>/<project>/` is one inquiry).
2. **Prepare quote** → live progress per stage (Extract → Predict → Present) and per file.
3. **Report**: Summary, Takeoff, Working hours, Painting, Cost, Carbon, Risks & questions, File map, Revisions.
   Click any number to see where it comes from (PDF page with highlight, Excel row, e-mail text, IFC elements with
   plan view, image, knowledge-file row, formula and inputs). Colours/labels: Extracted · Calculated · Predicted.
4. **Review**: change a value in the source panel, change scope/surface per category, change a file's status, or
   *Write a correction* in plain words → proposed changes → tick → **Recalculate** → new revision with "what changed".
5. **Approve** → status Approved, PDF without DRAFT mark, learning data written.
6. Downloads: client offer PDF, internal report PDF, Excel (all values + references). Files are also saved in
   `drives/maru/reports/<client>/` next to a `.json` that links report ↔ project folder.
7. Footer → **Technical details**: AI provider, AI call log (attempts, validation errors, tokens, cost), knowledge
   file version, training data, guidelines, rate-calibration suggestions (never applied automatically).

## Folder structure
```
demo/
  backend/app/        FastAPI + pipeline (filemap, extract, takeoff, predict, rules, carbon, report), ai/, parsers/,
                      knowledge/, reports/ (PDF/Excel templates), storage/, service.py, main.py
  backend/tests/      pytest
  frontend/           React + Vite + TypeScript (src/, built app in dist/); UI text in src/i18n/en.json
  config/             app.json (AI, pipeline), companies/maru.json (branding, numbering, offer texts), prompts/*.vN.md
  drives/client/      client drive: <client>/<project>/ (input, copied unchanged from materials/)
  drives/maru/        knowledge/Maru_knowledge.xlsx (read every run), reports/ (outputs)
  data/               SQLite, revisions, caches, training/ (JSONL), reference/ (Maru actuals for the accuracy check)
  logs/               ai_calls.jsonl (every AI call)
  scripts/            start.ps1, start.sh, dev.ps1, build_knowledge.py, seed_drives.py, accuracy_check.py
  docs/               implementation_notes.md, accuracy.md
```

## Knowledge file
`drives/maru/knowledge/Maru_knowledge.xlsx` is re-read on every run (swappable `KnowledgeSource` interface). Each
sheet has `id`, `status` (`derived` from a Maru workbook, `assumed`, `placeholder`) and `source`. Rebuild from Maru's
workbooks with `python scripts/build_knowledge.py` (`--verify --materials <path>` checks every derived cell).
Sheets: General, Labour_rates, Steel_prices, Waste, Cutting_speeds, Time_norms, Handling, Drilling, Paint_systems,
Surface_rates, Fire_protection, Transport, Fasteners, Price_per_tonne, Categories, Category_map, Predictions,
CO2_factors (placeholders), Profiles, Remnant_stock (empty — Maru's list needed).

## Training data (`data/training/`)
`filemap_decisions.jsonl`, `values.jsonl` (extracted/predicted values with references), `corrections.jsonl`
(before → after, reason, source), `approved/` (test cases), `guidelines/` (versioned, used in prompts),
`calibration_suggestions.jsonl` (to review by Maru).

## Data protection and local AI
Files stay on the drive. Code reads models, lists and PDFs; only the snippets that need reading (e-mail text, RFQ
forms, images) are sent to the AI, never whole folders. The API key stays in `.env` on the server. Every call is
logged in `logs/ai_calls.jsonl`. With `AI_PROVIDER=offline` or `local`, nothing leaves Maru's network.

## Accuracy (offline provider) — details in `docs/accuracy.md` (`python scripts/accuracy_check.py`)
| | Akkasæter | Kotka |
|---|---|---|
| Total price vs Maru | €322 400 vs €333 395 (−3.3 %) | €493 026 vs €591 285 (−16.6 %; −12.8 % with Maru's 1.10 margins) |
| Takeoff kg | +0.1 % | +0.4 % |
| Workshop hours | −5.8 % | −21 % (weld length −32 %) |
| Time to report | ≈3 s (+PDF/Excel in background) | ≈2–3 s |

Main gaps: Kotka welding of built-up WI members is under-estimated; Akkasæter painted area −13 % (IFC net area);
turnbuckle rods priced by weight, Maru prices them per piece (€17.6k line); transport adds a special truck for a
21 m piece (client said ~15 m, flagged as a question); margins default 1.05 (Maru used 1.10 on Kotka).

## Assumptions and conflicts
See `docs/implementation_notes.md` §5 (A1–A9). Guide used: *Maru Metall – Guida al progetto.pdf* (8 Oct 2026); the
online version could not be opened from the build environment. The guide's `assumed` type is called `predicted`.
Docker image was not built in the build environment (registry blocked); the non-Docker path was tested.
