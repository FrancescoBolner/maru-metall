# Maru Metall — Q&A Defence Playbook
### SteelQuote AI · 28DIGITAL Business Challenge 2026

---

## DELIVERY RULE
Short answer first — always. One sentence, stop. Expand only if the jury asks.

---

## CATEGORY 1 — TECHNICAL FEASIBILITY

### Q1: Can an AI tool really read an IFC model and produce an accurate cost estimate? These files are extremely complex.

**Short answer:** Yes — because we are not asking the AI to understand all of IFC. We ask it to extract the specific data points the estimator already uses: element types, profiles, steel grades, dimensions, and weights.

**Full answer:** An IFC model contains far more than what a cost estimator needs. We use IfcOpenShell, an open-source library that reads IFC and extracts structural elements with their properties — profile type, length, material grade, weight — directly. This is a solved problem technically. The AI's role is to handle the cases where the IFC is incomplete or where the input is not an IFC at all, which is often the case with early-stage inquiries.

---

### Q2: What happens when the input is a sketch or a poorly scanned PDF? Your system cannot extract clean data from that.

**Short answer:** Correct — and the system does not pretend otherwise. It produces an indicative estimate, flags every assumption made, and marks the output "budget only."

**Full answer:** The PoC has four operating modes, matched to four input quality levels: full IFC + BOM, BOM only, PDF drawings only, and email/description only. In the lowest-quality mode, the AI extracts what it can from the text, fills gaps with conservative assumptions, and generates an order-of-magnitude estimate. The output clearly states the confidence level and lists every assumption. The estimator then decides whether to invest time refining the estimate or send a budget range. This is better than the alternative: either refusing to estimate at all, or estimating without documentation.

---

### Q3: Labour norms are extremely project-specific. How can you encode expert judgment in a norm database?

**Short answer:** The same way Maru already does — through historical quote data and the documented cost principles in the workbook Maru provided.

**Full answer:** Maru already uses norm-based logic internally. The cost estimation principles workbook lists every cost component with its unit and measurement basis: plasma cutting in min/m, welding in min/m equivalent a5, drilling in min/pcs. These norms are the expert knowledge, encoded already in Maru's practice. SteelQuote AI does not invent new norms — it automates the application of existing ones. Over time, the system learns correction factors from comparing its estimates against actual quotes, improving accuracy project by project.

---

### Q4: What if the AI makes a pricing error that results in Maru winning a loss-making contract?

**Short answer:** The estimator reviews and approves every output before it is sent. The AI does not send quotes — it drafts them.

**Full answer:** The human control points are built into the design, not added as an afterthought. Six specific points require estimator sign-off: scope boundaries, weld specifications, final unit prices, the assumption log, the transport plan, and surface treatment class when ambiguous. The AI never touches a quote that goes to a client without a human reviewing it. As the system's accuracy is demonstrated over time, the review scope can narrow — but the approval authority stays with the estimator permanently.

---

## CATEGORY 2 — BUSINESS MODEL

### Q5: This sounds like an internal tool. Where is the business model? Why is this a challenge for EIT Digital?

**Short answer:** Internal efficiency at scale is a business model. Recovering hundreds of engineering hours per year is revenue-equivalent to winning additional contracts.

**Full answer:** Phase 1 is internal: Maru recovers 50–70% of the time currently spent on estimation. At 500 inquiries and 12 hours average, that is up to 3,600 hours recovered — worth €200,000+ per year in estimator cost. Phase 2 applies the same model to the broader Nordic steel fabrication market: other fabricators have identical problems and no existing solution. The external licensing model — SaaS at €15k–€60k per year per client — is Phase 3. The EIT Digital framing is: this is a solution to a real industrial problem that does not yet exist in the market, with clear commercial value and a scalable technology path.

---

### Q6: Maru is a manufacturer, not a software company. Why would they build this?

**Short answer:** They would not build it alone — they would partner with a software team, which is exactly what this challenge simulates.

**Full answer:** The challenge asks for a proof of concept that supports a go/no-go decision. If Maru approves the PoC, they would partner with a software development team — either an internal hire, a startup, or an EIT Digital spinout — to build the production system. The manufacturing expertise and the training data (historical quotes) come from Maru. The AI and software engineering come from the partner. This is the standard model for industrial AI products.

---

## CATEGORY 3 — THE POC

### Q7: Your PoC accuracy of -0.4% on the reference project looks suspiciously good. Is this real?

**Short answer:** The PoC is a demonstration of the methodology, not a production accuracy claim. The reference project was used to calibrate the model, which is standard practice.

**Full answer:** Using the reference project to show accuracy is intentionally transparent about the calibration — we are not claiming this accuracy on unseen projects. The meaningful accuracy target is ±10% on new projects after training on historical data. The ±0.4% figure shows that when the model has clean input and the norm logic is correctly applied, the architecture can produce highly accurate results. Real-world accuracy on new projects will be lower initially and improve as the model trains on more data.

---

### Q8: You say the PoC can be built quickly and cheaply. How quickly? What does the MVP actually look like?

**Short answer:** The MVP is a Python pipeline: IFC parser + LLM prompt chain + norm calculation engine + Excel output. It can be demonstrated in days, not months.

**Full answer:** The minimum viable PoC is not a web application or a deployed service. It is a structured script that: (1) reads a BOM from Excel, (2) classifies elements by type, (3) applies labour and material norms from the cost principles workbook, (4) calculates surface treatment area and cost, (5) adds transport, and (6) outputs a structured Excel cost sheet with an assumption log. The LLM is added for PDF and unstructured input handling. This is a realistic 5–10 day build for a competent developer with access to Maru's data. The demonstration in this challenge uses Example 4 as the input.

---

## CATEGORY 4 — SCALE AND COMPETITION

### Q9: Are there existing tools that already do this? Why hasn't this been solved before?

**Short answer:** Existing tools handle BIM quantity take-off but not steel fabrication cost estimation with norm-based labour logic. The gap is in the fabrication-specific cost layer.

**Full answer:** Tools like Autodesk Quantity Takeoff and similar BIM-based estimators handle material quantities from IFC models. What they do not do is apply fabrication-specific labour norms — the time required to plasma-cut a plate, drill a hole, assemble a built-up profile, and weld to the required quality class. These norms are proprietary, company-specific, and not encoded in any general tool. SteelQuote AI fills that gap by combining standard IFC parsing with Maru's own production knowledge.

---

### Q10: What stops a larger software company from building this the day after Maru validates the concept?

**Short answer:** The moat is the training data — Maru's historical quotation database — which no external company can replicate.

**Full answer:** The technology components (LLM, IFC parser, norm engine) are available to anyone. The competitive advantage is the calibration data: years of Maru quotes, actual project outcomes, and the norm values refined through real production experience. A competitor starting from zero would need 2–3 years of data accumulation to match a system trained on Maru's history. In the meantime, the tool's accuracy advantage is decisive for any client considering it.

---

## THE THREE HARDEST QUESTIONS — RAPID-FIRE FORMAT

| Question | One-sentence answer |
|---|---|
| "What is your single biggest risk?" | The norm database is incomplete — but we start with the workbook Maru already provided, which covers all major cost components. |
| "What does success look like in 6 months?" | Three inquiries per week processed with AI assistance; estimator review time under 2 hours each; zero undetected assumption gaps. |
| "Why should Maru invest in this now?" | Because every week without it, Maru spends 200+ hours on manual estimation — and 60–70% of those quotes will never become orders. |
