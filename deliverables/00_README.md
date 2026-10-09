# Maru Metall — Final Competition Package (v2)
## 28DIGITAL Business Challenge 2026 · EIT Digital
### Challenge: AI-Supported Cost Estimation Tool

> **IMPORTANT — v2 replaces the previous version entirely.**
> The previous version incorrectly addressed the generic "Challenges - 28DIGITAL.pdf" brief (circular economy, GTM, BMC for a new service).
> This version correctly addresses the **specific Maru Metall brief** found in "28DIGITAL Business Challenges - Maru Metall presentation.pdf":
> **Build an AI-supported cost estimation tool** that turns diverse project documentation into a reliable quotation.

---

## What the actual challenge asks for

From the official Maru Metall brief (6-slide PDF):

| Task | Description |
|---|---|
| **01 Input Interpretation** | Identify fabrication scope from mixed-quality drawings, models, lists and specifications |
| **02 Quantity & Effort** | Extract material quantities; estimate fabrication labour, surface treatment, subcontracting, packaging, transport |
| **03 Risk & Assumptions** | Make missing information, assumptions, exclusions and technical/commercial risks explicit |
| **04 Output** | Consistent, traceable cost estimate that an experienced estimator can review and adjust |

**Success dimensions:** Traceability · Human control · Variable input handling · Scalability

**Expected deliverable:** A **proof of concept** to support a go/no-go decision — NOT a fully functional tool.

---

## File Index

| File | Purpose |
|---|---|
| `01_pitch_script.md` | 3-minute pitch script, 4 speakers, exact dialogue + timing + delivery notes |
| `02_business_model_canvas.md` | Full 9-block BMC for SteelQuote AI (internal tool + optional SaaS) |
| `03_unit_economics.md` | Financial model: hour recovery, project data (Skybridge + Akkasater), ROI table |
| `04_poc_design.md` | System architecture, PoC walkthrough on Example 4, input quality handling, human controls |
| `05_qa_defence.md` | 10 hardest jury questions: short answer + full answer, delivery tips |
| `06_pitch_deck.html` | Interactive 7-slide visual pitch deck (open in browser, navigate with ← →) |

---

## Core Concept

**SteelQuote AI** — an AI-supported cost estimation tool that interprets any combination of IFC models, Excel BOMs, PDF drawings, and email specifications, applies Maru's norm-based production logic, and produces a structured, traceable cost estimate that an experienced estimator can review, adjust, and send.

The four pipeline stages directly map to the four challenge tasks:
1. **Input Interpretation** → document parser + LLM extraction
2. **Quantity & Effort** → norm-based labour engine + surface treatment pricing
3. **Risk & Assumptions** → explicit flagging layer, assumption log
4. **Output** → structured line-item estimate in Maru's standard format

---

## Key Numbers

| Metric | Value |
|---|---:|
| Annual inquiries at Maru | 500+ |
| Engineering hours/year (est.) | ~6,000 h |
| Annual estimation cost (est.) | ~€330,000 |
| Hours recovered (base, 60%) | 1,800 h/year |
| Annual value recovered | **€99,000/year** |
| PoC build cost | **€13,000–€25,000** |
| Payback period | **2–3 months** |
| Reference project accuracy (PoC) | **−0.4% vs. actual quote** |

---

## Real Project Data Used

| Project | Weight | Total Value | Reference |
|---|---:|---:|---|
| Pedestrian Steel Skybridge (HP11257-03) | 206,414 kg | €591,285 | Example 4 workbook + actual Maru quote |
| Akkasater Storage Hall (TU4031) | 148,315 kg | €333,395 | Example 2 workbook + actual Maru quote |

---

## Evaluation Criteria Mapping

| Criterion (25% each) | Where covered |
|---|---|
| Problem & Value Proposition | Pitch slide 1, Unit economics, BMC VP |
| Business Model & Viability | BMC all 9 blocks, unit economics ROI |
| Go-to-Market & Feasibility | PoC design (internal deploy first), pitch slide 4 |
| Pitch Quality & Q&A | Script with delivery notes, Q&A playbook |
