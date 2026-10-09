# Implementation notes — Maru Metall Takeoff & Quoting Assistant (demo)

Written before coding and ticked off while building. `[x]` = built and verified, `[~]` = built with a documented limitation, `[ ]` = not built.

Guide used: `Maru Metall – Guida al progetto.pdf` (Oct 8, 2026, 9 pages). The online version could not be opened from the build environment (network allowlist), see README "Guide version".

---

## 1. Flow and screens

The estimator flow is five steps: **select company → select project → run → review → approve**.

### Screens
- [ ] **Companies** — list of client companies found on the client drive, with project counts.
- [ ] **Projects** — projects of one company: folder, number of files, size, last quote number, status (Not run / Draft / Approved), last run time.
- [ ] **Project home** — folder summary, "Prepare quote" button, previous revisions.
- [ ] **Progress view** — live progress grouped by the demo phases *Extract / Predict / Present* with the guide's stage names (1 Read the shared drive, 2 AI extraction, 3 Structured takeoff, 4a Risks and assumptions, 4b Rule engine: cost + CO2, 6 Quote), per-file status (queued / reading / done / skipped / failed, read by code or by AI), elapsed time.
- [ ] **Report** (interactive) with tabs:
  - [ ] Summary (one-page summary)
  - [ ] Takeoff (metal takeoff + extracted features: commercial, scope, specs, logistics)
  - [ ] Working hours
  - [ ] Painting and surface treatment
  - [ ] Cost breakdown (both pricing methods + gap)
  - [ ] Carbon balance
  - [ ] Risks, assumptions, predicted values, questions for the client
  - [ ] File map (appendix) with per-file override
  - [ ] Revisions (history + "what changed")
- [ ] **Source panel** — opens when any number is clicked: value, type label + colour, confidence, formula with clickable inputs, knowledge-file rows, and each source rendered:
  - [ ] PDF page image with the snippet highlighted
  - [ ] Excel sheet window with the row/cell highlighted
  - [ ] Email header + body with the snippet highlighted
  - [ ] IFC elements table (GlobalId, profile, grade, weight, …) + plan view with the elements highlighted
  - [ ] Image (with region note)
  - [ ] Knowledge-file row
- [ ] **Review panel** — direct edits (any editable number, file status, category scope/surface), written correction box → proposed changes → confirm → recalculate → new revision with a diff.
- [ ] **Approve** — status Draft → Approved; triggers the learning loop.
- [ ] **Downloads** — client offer PDF, internal report PDF, Excel export (all values + references).
- [ ] **Technical details** (hidden, opened from a footer link) — AI provider and model, AI call log (attempts, validation, tokens, cost, duration), knowledge-file info, guidelines version, calibration suggestions, dataset counters.
- [ ] States: loading, empty, error (with what to do next), success.

## 2. Pipeline (guide stages → demo phases)

| Demo phase | Guide stage | Module |
|---|---|---|
| Extract | 1. Read the shared drive (file map + project level) | `pipeline/filemap.py` |
| Extract | 2. AI extraction (code first, AI only where reading is needed) | `pipeline/extract.py`, `parsers/*`, `ai/*` |
| Extract | 3. Structured takeoff | `pipeline/takeoff.py` |
| Predict | 4a. Risks and assumptions | `pipeline/predict.py` |
| Predict | 4b. Rule engine: cost + CO2 | `pipeline/rules.py`, `pipeline/carbon.py` |
| Present | 6. Quote | `pipeline/report.py`, `reports/*` |
| Review | 5. Estimator review → re-run from stage 3 | `pipeline/review.py` |
| Learning | corrections logged, rates calibrated, similar projects | `pipeline/learning.py` |

The guide's takeoff types `extracted / calculated / assumed` are named **`extracted / calculated / predicted`** in UI and code (`assumed` → `predicted`).

### Stage 1 — file map
- [ ] Walk the project folder; e-mails (`.eml`, `.msg`) are expanded so each attachment is a child entry.
- [ ] Per file: path, type, size, pages / sheets / elements, date, SHA-256, relevance status + reason, who decided (rule / AI / estimator).
- [ ] Status values: `metal-relevant`, `partly-relevant`, `not-relevant` (with reason), `unreadable` (with reason), `duplicate` (of which file).
- [ ] Code-first classification: extension, name keywords, metadata, quick content scan (IFC entity counts and materials, Excel header row, PDF text keywords, e-mail). AI `classifyFile` only for files the rules cannot decide.
- [ ] Duplicates by hash (e-mail attachment = saved file).
- [ ] Versions: IFC models sharing GlobalIds (newest kept, older marked superseded with added / removed / changed counts); combined material list = sum of phase lists; folders named "old / superseded / Ei kehti / vana / archive"; `rev A` / `rev C` name markers.
- [ ] Estimator override of any file status (re-runs the takeoff).
- [ ] Project level: **idea** (a few drawings or an e-mail), **draft** (drawings + a material list), **full project** (IFC / Tekla model + material lists + specs).

### Stage 2 — extraction (metal only)
- [ ] IFC (IfcOpenShell): `IfcBeam`, `IfcColumn`, `IfcMember`, `IfcPlate`, `IfcElementAssembly`, `IfcMechanicalFastener`; steel filter by material; non-steel entities listed as excluded. Per element: GlobalId, assembly, profile, grade, length, weight, surface area, phase, class (colour). Bolts: count, size, length, workshop / site.
- [ ] Material lists (openpyxl): header detection, profile normaliser, subtotal rows skipped, totals cross-checked.
- [ ] PDF (PyMuPDF): text, page count, embedded assembly / part lists parsed by code (Kotka drawings), notes (paint system, execution class, fire protection) with page + bounding box for highlights.
- [ ] E-mails (`email`, `extract-msg`): headers, body, attachments.
- [ ] AI only where reading is needed: e-mail bodies, RFQ forms and specs (`extractFromDocument`), images / scans (`extractFromDrawing`). Requirement search over all text first by keyword (cheap RAG): execution class, steel grade, corrosivity / paint system, fire rating, galvanising, recycled content, tolerances, EPD.
- [ ] Feature groups: quantities, operations, technical specs, scope, commercial, logistics.
- [ ] Messy input flags: mixed units, items repeated across IFC files, conflicting values between documents, other currencies (NOK, SEK, DKK, USD).
- [ ] Cost-changing requirements go to the top of the risks.

### Stage 3 — structured takeoff
- [ ] One quantity source per piece of steel (model first, list second, drawing lists third); the other sources are cross-checks shown with both references.
- [ ] Lines grouped by category / phase / profile / grade, each with quantity, unit, type, confidence, references (GlobalIds, sheet rows, PDF pages).
- [ ] Category mapping by keywords in the knowledge file (multi-language: Danish, Norwegian, Estonian, Finnish, English); unknown names → AI `classifyFile`-style category proposal or "Other steel".
- [ ] Conflicts never resolved silently: both values shown and flagged.

### Stage 4a — risks and predictions
- [ ] Missing specs predicted from the knowledge file (reasoning, confidence, question for the client).
- [ ] Missing quantities predicted (holes when no bolts, weld lengths, allowances for items mentioned but not modelled).
- [ ] Risks ranked: cost-changing requirements → conflicts → missing scope → messy input.

### Stage 4b — rule engine (code only, never AI)
- [ ] Working hours per operation: cutting, drilling, sawing, edge cleaning, fitting / assembly, welding, blasting, painting, galvanising handling, packaging, loading — per operation, per category, total. Plate share drives the norms (plate-heavy jobs take longer per tonne).
- [ ] Paint: area × coats × consumption → litres per product, painting hours and cost.
- [ ] Material: net steel + offcuts by profile (1D nesting on stock lengths) and by plate thickness; bolts and consumables.
- [ ] Two pricing methods: quick €/t per category and detailed part-by-part; gap shown; default by level (idea → €/t, full → part-by-part, draft → part-by-part when part lists exist).
- [ ] Uncertainty range from value types and confidence.
- [ ] Carbon balance by steel origin + paint / galvanising + transport, options, flags.

### Stage 6 — report
1. [ ] One-page summary: total price + range, tonnes, working hours + labour cost, paint litres + cost, CO2e, overall confidence (share extracted / calculated / predicted), top risks, open questions.
2. [ ] Metal takeoff.
3. [ ] Working hours per operation and category, with the norm used.
4. [ ] Painting and surface treatment.
5. [ ] Cost breakdown, each line linked to its knowledge-file row.
6. [ ] Carbon balance.
7. [ ] Risks, assumptions, predicted values, questions.
8. [ ] File map appendix.
- [ ] Interactive (app), PDF (internal + client), Excel (all data + references).

### Stage 5 — review
- [ ] Direct edit of any editable value and file status.
- [ ] Written correction → `interpretCorrection` → proposed changes → estimator confirms.
- [ ] Recalculate from the takeoff → new revision `_rev2`, `_rev3` … with a "what changed" view.
- [ ] Status `Draft` → `Approved`.

### Learning
- [ ] `data/training/` JSONL: file-map decisions, extracted / predicted values with references, corrections (before → after, reason), approved values.
- [ ] Approved projects saved as test cases.
- [ ] Versioned guidelines file updated on approval, used in prompts for similar projects.
- [ ] Rate-calibration suggestions (never applied automatically).

## 3. Schemas (Pydantic, `backend/app/models.py`)

```
Ref            kind: pdf_page | sheet_cell | ifc_elements | email | text | image | knowledge_row | user_edit
               file_id, path, page, sheet, cell, row, guids[], bbox[x0,y0,x1,y1], snippet, label
V (value)      id, label, value, unit, type: extracted | calculated | predicted, confidence 0..1,
               refs[Ref], formula, inputs[value ids], kn[knowledge row ids], reasoning, question,
               conflict[ConflictOption], edited{before, after, reason, source, at}, editable
FileEntry      id, path, parent_id, name, ext, kind, size, pages, sheets, elements, date, sha256,
               status, reason, decided_by: rule | ai | estimator, duplicate_of, superseded_by, used_for[]
Fact           key, group: commercial | scope | specs | logistics | quantities, value_id
TakeoffLine    id, category, phase, profile, grade, is_plate, pieces, kg, length_m, area_m2,
               longest_mm, surface, source, value ids for each quantity
CategorySummary name, kg, pieces, area_m2, plate_share, surface, phase, included, longest_mm
HoursRow       operation, category, quantity, unit, norm, hours (value ids)
PaintRow       category, system, area, coats, litres per product, hours, cost
CostLine       group, label, amount (value id), kn rows
Carbon         by origin, paint/galvanising, transport, options, flags
Risk           rank, severity, title, detail, value_ids, question
RunResult      project, revision, quote_number, status, timings, ai usage, filemap, facts, takeoff,
               hours, paint, material, cost {detailed, per_tonne, gap, chosen}, carbon, risks,
               questions, assumptions, summary, values{id → V}
Override       target: fact | line | category | file | param, key, field, value, reason,
               source: direct_edit | written_correction, text
```
AI output schemas (one per call, `backend/app/ai/schemas.py`): `FileClassification`, `DocumentExtraction`, `DrawingExtraction`, `MissingPrediction`, `CorrectionProposal`. Every AI fact carries `value` (string, empty when not found), `found`, `snippet`, `page`, `reason`; no value without a snippet.

## 4. Knowledge file layout (`drives/maru/knowledge/Maru_knowledge.xlsx`)

Every sheet has an `id` column (row reference used in reports), a `status` column (`derived` = taken from a Maru workbook, `assumed` = team assumption, `placeholder` = order-of-magnitude, to replace) and a `source` column (workbook + cell).

| Sheet | Content |
|---|---|
| `README` | How the file is used, status legend |
| `General` | labour rate, density, margins, packaging, uncertainty bands, plate threshold |
| `Labour_rates` | €/h per workshop country |
| `Steel_prices` | €/kg by profile family / thickness band and price-list date (two Maru price lists) |
| `Waste` | stock lengths, plate waste by thickness band, nesting saw kerf, benchmark |
| `Time_norms` | every operation: unit, norm, basis, source |
| `Cutting_speeds` | plasma speed and pierce time by plate thickness (fitted from Maru's workbooks) |
| `Handling` | fitting minutes by plate weight band and profile length band |
| `Paint_systems` | class → coats, DFT, volume solids, loss factor, €/l, min/m² per coat, blasting €/m², Maru all-in €/m² |
| `Surface_rates` | Maru's all-in surface rates per class (and HDG €/kg) |
| `Fire_protection` | R30 / R60 / R90 layers and rates |
| `Transport` | truck types, capacity, €/truck by destination region, coefficient |
| `Fasteners` | bolts €/kg, anchors €/pack, bolt weight formula |
| `Price_per_tonne` | quick method €/t and h/t by category (from Maru's two offers) |
| `Category_map` | keywords (multi-language) → category |
| `Predictions` | defaults for missing data (holes per tonne, weld factors, allowances) |
| `CO2_factors` | steel routes, paint, zinc, truck-km (placeholders) |
| `Profiles` | kg/m and m²/m for standard sections (calculated from nominal dimensions) |

## 5. Assumptions (also in README)
- A1. The client drive is modelled as `drives/client/<company>/<project>/`; the guide's "01 Input for pricing" folder content is copied there unchanged.
- A2. Steel prices: the engine uses the newest Maru price list on or before the inquiry date found in the files (fallback: newest list). This keeps historical projects comparable with Maru's real offers.
- A3. Margins: Maru used 1.05 / 1.05 on Akkasæter and 1.10 / 1.10 on Kotka. Default is 1.05 / 1.05; the estimator can edit margins in review.
- A4. Surface treatment: Maru prices it all-in per m². The demo decomposes it into blasting + paint material + painting labour (assumed parameters, calibrated so each class is within ±5 % of Maru's all-in rate) to give litres and hours.
- A5. Weld lengths are never in the client files; they are predicted from part geometry with Maru's workbook rules (perimeter × 2 ends for profile ends, 2 × plate length for attached plates, 4 × length for built-up sections).
- A6. CO2 factors are order-of-magnitude placeholders until supplier EPDs (EN 15804) are available. They are labelled in the app and in every report.
- A7. Holes: from IFC bolt groups (2 holes per bolt) when available, else predicted per tonne by category.
- A8. Without an API key the AI provider falls back to an offline rules provider so the demo still runs; this is shown in Technical details.
- A9. Sonnet 5.5 rejects non-default temperature; low temperature is configured for providers that accept it (local models), determinism for Claude comes from structured outputs, validation and caching.
