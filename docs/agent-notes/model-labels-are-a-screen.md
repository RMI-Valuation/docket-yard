---
name: model-labels-are-a-screen
description: Blind model label passes miscalibrate in BOTH directions; a rate is only publishable after Cameron checks a subsample
metadata:
  type: feedback
---

A blind pass of model labellers is a screen for finding candidates, never the measurement
itself. Measured twice in one session (2026-09-17, the text-quality work):

- a single 64-page pass was **too kind** — 4 of Cameron's 7 corrections moved a page from
  `partial`/`noisy` to `garbage`;
- two independent passes over 102 pages agreeing with each other 97 times were **too harsh** —
  he overruled both on 8 of 13 pages they called faulty, and confirmed 0 faults they had
  missed. Uncorrected they would have claimed 201,000 faulty pages where his check gives 58,000.

**Why:** agreement between model passes measures shared bias, not truth. The two-phase fix
works and is cheap: blind pass(es) over the sample, then he checks every disagreement plus a
random subsample of the agreements, and the rate is computed class by class from HIS labels.

**How to apply:** never publish or store a rate from model labels; build the check sheet
(`tools/rmi-ai-machine/text_quality_check_page.py` takes sample + drafts + images) and ask for
30-ish pages of his time, not 100. Show the drafts but never the score the sample was drawn by.
Also: a figure from one stratum's 16 pages is not a rate — garbage recall was 0.92 from a cell
that held no garbage, and 0.68 once 102 more pages existed.
See [[claims-are-not-measurements]] and [[state-the-question-before-measuring]].
