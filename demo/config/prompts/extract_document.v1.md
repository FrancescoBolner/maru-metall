---
name: extract_document
version: 1
---
Extract the features that drive the price of the steel work from this document.

File: {file_name} ({file_kind}){page_note}

Allowed fact keys (use exactly these keys, one fact per value found):
{catalog}

Also return:
- scope_items: things explicitly included, excluded or offered as options (e.g. "Hilti anchors HUS4-HF", "erection", "inner H-plates in HSQ"), with quantity if stated.
- requirements: anything that changes the cost: fire rating / intumescent paint, paint system or corrosivity class, galvanising, recycled steel content, EPD, execution class, steel grade, tolerances, weld quality. Rate cost_impact high for fire rating, galvanising, recycled content and paint systems above C3.
- flags: messy input to warn the estimator about: prices in another currency, mixed units, statements that conflict, data said to be missing, models said to be incomplete.
- not_found: catalog keys you looked for and could not find (key + short reason).

Checkbox forms: a ticked box is "☒" or "[x]"; only ticked options are values.
Snippets must be copied character by character from the document text below. Use page 0 when there are no pages.

Document text:
<<<
{content}
>>>
