---
name: state-the-question-before-measuring
description: "Write down the question and its grain BEFORE measuring; run the shipped code rather than re-implementing it; look for what breaks a conclusion, not what supports it"
metadata:
  type: feedback
---

Four analyses went wrong in one session (2026-09-11/12) and every one failed the same way:
**the two sides of a comparison were at different grains.**

- `judgement='span'` where the vocabulary says `span_names_document` — a name never checked.
- Counted per resolution row where the projection is DISTINCT over (decision, kind, key).
- Checked the FIRST occurrence of a key on a page where the finder folds EVERY occurrence.
- Compared per-page caption judgements against a truth set keyed per (decision, key), which
  silently included captions.

Two of the four I reported to Cameron as findings before catching them. He caught both — "we
need to make sure we aren't evaluating over an imperfect source", then "the measurement is the
citations, the captions are incidental". A schema-critic pass then caught a third: a draft that
asserted validation query 2 was unaffected when it would have returned a negative treatment
beside a DIFFERENT occurrence's passage.

**What to do instead, in this project:**

1. **Write the question down before running anything**, including what grain each side is at
   and what result would falsify it. Most of these would have died at that sentence.
2. **Run the shipped code, never re-implement its logic.** `project.projected()`,
   `review.pending()`, `find.find()` — a re-implementation of a WHERE clause was wrong twice
   in one night. When the answer needs the projection, call the projection.
3. **Look for what breaks the conclusion, not what supports it.** Twice I reached an answer and
   then assembled evidence for it. The caption framing and the grain framing were both
   over-claimed and both had to be corrected in the record.
4. **Cameron's decisions are better than my framings** — when he pushes back on a premise,
   stop and re-measure rather than defend. He was right every time this session.
5. For design problems with interacting constraints, **use the adversarial agents early**
   (schema-critic, stb-ingest-specialist), and consider multi-agent planning before proposing
   a shape, not after drafting one. His words, 2026-09-12: "revise your methods, possibly with
   some multi-agent planning when we tackle these problems, when needed."

See [[claims-are-not-measurements]] — the same discipline, one level up.
