# Maru Metall — Business Model Canvas
### SteelQuote AI · 28DIGITAL Business Challenge 2026

---

## PRODUCT NAME

**SteelQuote AI**

An AI-supported cost estimation tool that interprets mixed-quality project documentation (IFC models, PDF drawings, material lists, specifications) and generates a structured, traceable cost quotation that an experienced estimator can review, adjust, and send — in a fraction of the time required by the manual process.

---

## CHALLENGE CONTEXT

Maru Metall receives 500+ price inquiries per year. Each requires manual interpretation of heterogeneous inputs (IFC, BOM, PDF, DWG, email) and expert translation into a detailed cost estimate covering: material, fabrication labour (plasma cutting, sawing, drilling, assembling, welding), surface treatment (paint systems C2M–C4H, HDG), packaging and transport. The process is slow, expert-dependent, and not scalable.

SteelQuote AI addresses this directly, addressing all four challenge tasks:
1. Input interpretation
2. Quantity and effort extraction
3. Risk and assumption flagging
4. Traceable output generation

---

## 1. CUSTOMER SEGMENTS

### Primary user
**Maru Metall's cost estimation team** — specifically senior cost engineers and sales managers who currently perform manual quotation work. The product is internal-facing at launch.

### Secondary beneficiaries
- **Sales and business development team** at Maru: faster quotes = more bids = more revenue opportunity.
- **Project managers**: faster go/no-go decisions on inquiry intake.
- **Board / management**: capacity to scale bid volume without proportional headcount increase.

### Long-term expansion
Other Nordic steel fabricators facing identical operational challenges (the model is replicable across the industry).

---

## 2. VALUE PROPOSITION

**For cost engineers:**
- Interpret project documentation in minutes rather than hours.
- Receive a structured draft estimate with every assumption made explicit.
- Focus review time on complex decisions and client-specific adjustments — not on mechanical quantity extraction.

**For sales management:**
- Quote more projects in the same time window.
- Reduce the dependency on a small number of senior estimators.
- Improve bid-to-win ratio by responding faster to inquiries.

**For the business:**
- Recover hundreds of engineering hours per year.
- Scale bid capacity without proportional cost increase.
- Improve margin control through more consistent, norm-based cost logic.

**The core promise:** SteelQuote AI does not replace the experienced estimator. It eliminates the mechanical work so the estimator can focus on judgment, client relationship, and margin protection.

---

## 3. CHANNELS

**Phase 1 — Internal deployment (PoC):**
- Direct deployment within Maru's estimation team.
- Used on live incoming inquiries in parallel with the manual process.
- Accuracy measured against actual quotes produced.

**Phase 2 — Internal roll-out:**
- Full integration into Maru's quotation workflow.
- Connected to existing ERP / project management systems.
- Trained on historical Maru quotes to improve accuracy over time.

**Phase 3 — External licensing (optional):**
- License the tool to other steel fabricators in non-competing geographies.
- SaaS model: per-inquiry fee or annual subscription.

---

## 4. CUSTOMER RELATIONSHIPS

| Stage | Mode | Mechanism |
|---|---|---|
| PoC | Human-in-the-loop | Estimator reviews every AI output; feedback loop trains the model |
| Production use | AI-assisted | AI drafts, estimator reviews and adjusts exceptions |
| Mature use | AI-primary | AI handles standard inquiries autonomously; human reviews complex cases |
| External licensing | SaaS support | Onboarding, accuracy calibration, ongoing updates |

The relationship model is designed to build trust gradually: the tool earns autonomy as its accuracy is demonstrated, not assumed.

---

## 5. REVENUE STREAMS

**Internal value (Phase 1–2):**
- Cost savings from recovered engineering hours.
- Revenue increase from higher bid volume.
- Margin improvement from more consistent pricing logic.

**External value (Phase 3, optional):**

| Stream | Model | Estimate |
|---|---|---|
| SaaS licensing to other fabricators | Annual subscription | €15k–€60k/year per client |
| Per-inquiry processing fee | Usage-based | €50–€200 per quote generated |
| Implementation and calibration services | Professional services | €10k–€30k per client onboarding |

---

## 6. KEY RESOURCES

| Resource | Why it matters |
|---|---|
| Historical Maru quotations | Training data — the ground truth for what a correct estimate looks like |
| Cost estimation norm database | The production logic (labour norms, surface treatment rates, transport rates) from the principles workbook |
| IFC / BOM parsing capability | The technical core — ability to read and interpret structural data formats |
| LLM / AI inference capability | The interpretation layer for unstructured inputs (PDF drawings, emails, specs) |
| Experienced estimator validation | Human feedback loop that improves model accuracy over time |
| EN 1090-2 domain knowledge | The regulatory standard that governs all fabrication quality and scope assumptions |

---

## 7. KEY ACTIVITIES

| Activity | Description |
|---|---|
| **Document interpretation** | Parse IFC, BOM, PDF, DWG, email to extract fabrication scope |
| **Quantity extraction** | Identify element types, profiles, steel grades, weights, lengths |
| **Labour estimation** | Apply norm-based production logic: cutting, sawing, drilling, assembling, welding |
| **Surface treatment pricing** | Map corrosion class and paint system to m2-based cost model |
| **Risk and assumption flagging** | Identify and document every information gap, inconsistency, or exclusion |
| **Output generation** | Produce structured, line-item cost estimate in Maru's standard format |
| **Accuracy measurement** | Compare AI output to actual quote; feed delta back into training |

---

## 8. KEY PARTNERS

| Partner | Role |
|---|---|
| AI / LLM provider | Core language model for document interpretation |
| IFC / BIM software ecosystem | Data format standards and parsing libraries |
| Maru's existing ERP system | Integration for historical data and output delivery |
| EN 1090-2 standard body | Regulatory framework embedded in the estimation logic |
| External steel fabricators (Phase 3) | Future licensing clients |

---

## 9. COST STRUCTURE

| Cost category | Description |
|---|---|
| AI infrastructure | LLM API usage, inference compute, vector database for document storage |
| Development | Software engineering for parsing, estimation logic, UI, ERP integration |
| Training data curation | Cleaning and structuring historical Maru quotes for model training |
| Validation and calibration | Estimator time spent reviewing PoC outputs and providing feedback |
| Ongoing maintenance | Model updates, new input format support, accuracy monitoring |

**PoC cost (minimal viable version):**
The PoC does not require a full software platform. It can run as a structured pipeline: document parser (open-source IFC/PDF tools) + LLM prompt chain + norm-based calculation engine in Python/Excel. Initial build is measured in days, not months.

---

## CANVAS SUMMARY

```
KEY PARTNERS          KEY ACTIVITIES           VALUE PROPOSITION       CUSTOMER          CUSTOMER
                                                                        RELATIONSHIPS     SEGMENTS
AI/LLM provider       Document interpretation  Estimates in            Human-in-loop     Maru cost
IFC/BIM ecosystem     Quantity extraction      minutes not hours       AI-assisted       engineers
Maru ERP system       Labour estimation        Every assumption        AI-primary        Sales team
EN 1090-2 bodies      Surface treatment price  explicit                (mature)          Management
External fabricators  Risk/assumption flag     Scalable bid            SaaS support      Future: other
                      Output generation        capacity                (external)        fabricators
KEY RESOURCES                                  Margin consistency
                                               Estimator freed
Historical quotes     COST STRUCTURE           for judgment            CHANNELS
Norm database                                                          Internal deploy
IFC/BOM parsers       AI infrastructure        REVENUE STREAMS         ERP integration
LLM capability        Development                                      External SaaS
Estimator feedback    Data curation            Hour recovery (internal)
EN 1090-2 knowledge   Validation/calibration   Higher bid volume       licensing
                      Maintenance              SaaS licensing (ext.)
                                               Per-inquiry fee
```

---

## EVALUATION AGAINST JUDGING CRITERIA

| Criterion (25%) | Evidence |
|---|---|
| **Problem & Value Proposition** | Pain is precise and documented: 500+ inquiries/year, hundreds of hours each, expert-dependent. Value is concrete: hours recovered, bids scaled. |
| **Business Model & Viability** | All 9 BMC blocks complete. Revenue from internal efficiency gains (Phase 1–2) and optional external SaaS (Phase 3). Cost of PoC is minimal. |
| **Go-to-Market & Feasibility** | Internal deployment first eliminates market risk. PoC uses real Maru data (Example 4 BOM). No customer acquisition required for Phase 1. |
| **Pitch Quality & Q&A** | Story maps directly to the 4 challenge tasks. Numbers grounded in real project data. PoC is concrete and demonstrable. |
