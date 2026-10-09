---
name: classify_file
version: 1
---
Decide whether this file is relevant for pricing the steel work.

File: {file_name}
Type: {file_kind}
What the code could read:
<<<
{content}
>>>

Return:
- status: "metal-relevant" (describes steel to fabricate or requirements for it), "partly-relevant" (mixed content, some steel info), or "not-relevant" (no steel information: architecture, concrete, MEP, timber, logos, signatures...).
- discipline, a one-sentence reason a non-technical estimator understands, and your confidence (0-1).
