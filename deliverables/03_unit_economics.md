# Maru Metall — Unit Economics & Financial Model
### SteelQuote AI · 28DIGITAL Business Challenge 2026

---

## 1. THE CORE ECONOMIC ARGUMENT

The business case for SteelQuote AI does not rest on speculative market sizing. It rests on a simple internal calculation: how many engineering hours are spent quoting projects, what is the cost of those hours, and what is the value of recovering them?

---

## 2. CURRENT STATE — COST OF MANUAL ESTIMATION

### Volume and effort

| Metric | Value | Source |
|---|---|---|
| Annual price inquiries received | 500+ | Maru challenge brief |
| Estimated effort per inquiry | Several hundred hours (total) | Maru challenge brief |
| Assumed average per inquiry | ~8–20 hours | Engineering estimate: simple inquiry 4–8h; complex IFC+specs 20–40h |
| Senior estimator daily rate (est.) | €350–€500/day | Typical Nordic industrial rate |
| Total annual estimation cost (mid estimate) | 500 x 12h x €55/h | ~€330,000/year |

### The hidden cost
Not all 500 inquiries become orders. If Maru wins 30–40% of bids, then 300–350 inquiries per year are quoted and lost. Those are pure overhead — engineering hours spent generating no revenue. **AI assistance can dramatically reduce the cost of non-winning bids.**

---

## 3. REFERENCE PROJECT DATA

### Example 4 — Pedestrian Steel Skybridge (HP11257-03)

| Metric | Value |
|---|---:|
| Project revenue | €591,285 |
| Fabrication revenue | €576,885 |
| Transport | €14,400 |
| Steel weight | 206,414 kg |
| Paint system | C3.07 (all elements) |

#### Element breakdown and unit prices

| Element | Weight (kg) | Revenue (EUR) | Unit price (EUR/kg) |
|---|---:|---:|---:|
| WI columns | 72,143 | 222,073 | 3.08 |
| WI beams | 40,264 | 99,130 | 2.46 |
| Beams | 60,473 | 154,949 | 2.56 |
| Bracings (horiz+vert) | 22,389 | 59,523 | 2.66 |
| Frame | 4,357 | 12,820 | 2.94 |
| CFJ parts (separately) | 755 | 3,604 | 4.77 |
| Erection/support plates | 6,033 | 24,785 | 4.11 |
| **Total** | **206,414** | **576,885** | **avg 2.79** |

**Key insight:** Unit price varies 94% between cheapest (WI beams €2.46/kg) and most expensive (CFJ parts €4.77/kg). This variation reflects fabrication complexity — drilling density, weld length, surface-to-weight ratio — which is precisely the logic SteelQuote AI must encode.

---

### Example 2 — Akkasater Storage Hall (TU4031)

| Metric | Value |
|---|---:|
| Project revenue | €333,395 |
| Steel weight | 148,315 kg |
| Phase 1+2 paint system | C2M |
| Phase 3 | HDG (hot-dip galvanizing) |

#### Element breakdown

| Element | Weight (kg) | Revenue (EUR) | Unit price (EUR/kg) |
|---|---:|---:|---:|
| Columns (C2M) | 35,141 | 68,314 | 1.94 |
| WQ beams (C2M) | 11,381 | 22,637 | 1.99 |
| Beams (C2M) | 75,914 | 131,863 | 1.74 |
| Bracings (C2M) | 12,601 | 23,161 | 1.84 |
| Window/door frames (C2M) | 10,276 | 18,877 | 1.84 |
| Outside entrance (HDG) | 2,714 | 6,413 | 2.36 |
| Indoor bollards (HDG) | 288 | 954 | 3.31 |
| Bracings D30 w. turnbuckles | 72 pcs | 17,564 | 243.94/pc |
| Hilti anchors | 150 pcs | 935 | 6.23/pc |
| Fasteners | 1 set | 5,302 | — |
| Transport | 1 set | 37,375 | — |
| **Total** | **148,315 kg** | **333,395** | **avg 2.25** |

---

## 4. COST COMPONENT STRUCTURE

Based on the `Basic cost estimation principles.xlsx` provided by Maru, a correct cost estimate must cover:

### 4.1 Steel material
| Component | Unit | Notes |
|---|---|---|
| Material purchasing cost | EUR/kg | Base steel price by grade (S235, S355, S275) |
| Material overconsumption | EUR/kg | Profiles: depends on stock length vs. element lengths; Plates: depends on detail shape vs. plate dimensions |

### 4.2 Detail preparation (fabrication labour)
| Operation | Unit | Notes |
|---|---|---|
| Plasma cutting of plates | min/m | Varies by plate thickness |
| Cleaning of plasma cut edges | min/m | Always after plasma cut |
| Rounding of sharp edges | min/m | Varies by corrosion class requirements |
| Hole drilling — plates | min/pcs | Depends on hole diameter and depth |
| Hole drilling — profiles | min/pcs | Depends on hole diameter and depth |
| Profile sawing | min/pcs | Cross-section dependent |
| Profile plasma cutting with robot | min/m | — |
| Profile bolt-hole plasma cutting | min/pcs | — |

### 4.3 Welding
| Operation | Unit | Notes |
|---|---|---|
| Assembling | min/pcs | Tack welding to shape; size and weight dependent |
| Welding | min/m | Converted to equivalent a5 fillet weld length; position and quality dependent |
| Weld splicing | min/m | Plate/profile splicing |

### 4.4 Surface treatment
| System | Unit | Notes |
|---|---|---|
| Shot-blasting | EUR/m2 | Pre-treatment before painting |
| Paint systems C2M through C4H | EUR/m2 | Different layer thickness and paint type per class |
| Fire protection R30/R60/R90 | EUR/m2 | Complex; profile/temperature dependent |
| Hot-dip galvanizing (HDG) | EUR/kg | ISO 1461 |

### 4.5 Transport and packaging
| Item | Unit | Notes |
|---|---|---|
| Packaging | EUR/kg | Standard Maru packing procedure |
| Transport | EUR/truck | Standard (13.5m) vs. special (20m) trucks |

---

## 5. AI ESTIMATION ACCURACY — TARGET METRICS

### Benchmark: what "good" looks like

Based on the two reference projects:

| Metric | Target |
|---|---|
| Total cost estimate accuracy vs. actual | Within ±10% on first pass |
| Element-level unit price accuracy | Within ±15% per element category |
| Labour hour estimate accuracy | Within ±20% (most variable component) |
| Surface treatment cost accuracy | Within ±5% (most formulaic component) |
| Assumption flagging completeness | 100% — every gap must be documented |

---

## 6. BUSINESS CASE FOR MARU

### Conservative scenario: AI handles 30% of inquiries with 50% time reduction

| Metric | Value |
|---|---:|
| Inquiries per year | 500 |
| Inquiries AI assists (30%) | 150 |
| Average hours saved per inquiry (50% of 12h) | 6h |
| Total hours recovered | 900 h |
| Value at €55/h (blended estimator rate) | **€49,500/year** |

### Base scenario: AI handles 50% of inquiries with 60% time reduction

| Metric | Value |
|---|---:|
| Inquiries AI assists | 250 |
| Hours saved per inquiry | 7.2h |
| Total hours recovered | 1,800 h |
| Value at €55/h | **€99,000/year** |

### Optimistic scenario: AI handles 70% with 70% time reduction

| Metric | Value |
|---|---:|
| Inquiries AI assists | 350 |
| Hours saved per inquiry | 8.4h |
| Total hours recovered | 2,940 h |
| Value at €55/h | **€161,700/year** |

### PoC build cost (minimal viable version)

| Cost item | Estimate |
|---|---:|
| LLM API and IFC parsing (3 months) | €3,000–€6,000 |
| Developer time (PoC build) | €8,000–€15,000 |
| Estimator validation time | €2,000–€4,000 |
| **Total PoC investment** | **€13,000–€25,000** |
| **Payback period (base scenario)** | **2–3 months** |

The PoC investment is recovered in less than one quarter of operation at the base scenario efficiency level.

---

## 7. KEY NUMBER FOR THE PITCH

> **500 inquiries × 12 hours = 6,000 engineering hours per year.**
> **SteelQuote AI recovers up to 60% of those hours.**
> **Payback in 2–3 months. Every hour saved above that is pure capacity.**
