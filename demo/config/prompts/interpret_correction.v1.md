---
name: interpret_correction
version: 1
---
An estimator wrote a correction in plain language. Turn it into proposed changes on the targets listed below. Only use target ids from the list and only allowed values when a target lists them. If a part of the correction does not match any target (for example an item that is not in the takeoff), put it in not_applied with the reason. Do not change anything the estimator did not ask for. Never propose prices.

Correction:
"""{text}"""

Targets (id | what it is | current value | allowed values):
{targets}
