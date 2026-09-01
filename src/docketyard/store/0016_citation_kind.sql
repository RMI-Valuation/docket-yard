-- Migration 0016: the `kind` judgement gets its vocabulary, so the finder can ship.
--
-- Migration 0014 declared `judgement_vocab` with three questions and gave `kind` an EMPTY
-- value domain on purpose: "the typing pass has not decided its values, and an empty domain
-- means no `kind` judgement can be written until it does. That is the point of declaring a
-- domain rather than a column type." This is that decision, taken by the operator on
-- 2026-09-01, and it is two rows.
--
-- WHAT `kind` ANSWERS, and what it does not. ADR 0017 D1 keeps the own-docket rule with the
-- extractor: a mention is a CAPTION when the number is the citing decision's own proceeding
-- and no document word is near it, and a CITATION otherwise. The record already knows which
-- docket a decision sits in, so it is the one judgement no extractor has to guess at — which
-- is why the API model is explicitly not bought for it (D1: "that is the one thing no
-- extractor should be asked to decide"). Measured 95.1% recall at 88.1% precision on the
-- sixty-decision sheet; that is this judgement's own figure and NOT the span test's 98.1%.
--
-- IT IS NOT THE SPAN TEST, though the two ask a neighbouring question. `span_names_document`
-- runs a narrower pattern at projection and decides what a published edge IS (ADR 0017 D4);
-- `kind` is the finder's own reading of the page, made where the extraction happens. They
-- are measured separately, they disagree sometimes, and keeping both is what makes that
-- visible. One of them being wrong is a thing the other can show.
--
-- WHY BOTH KINDS ARE STORED. Until today the measured finder emitted only what it called a
-- citation and dropped the captions — 401 of them against 356 citations on the sixty
-- decisions. That is a silent discard in a store whose first discipline is that a row is
-- never discarded, and it made "not kept" a number nobody could check. A caption is now a
-- finding like any other: stored, judged, and suppressed at projection by the family
-- closure, which is registry data and not the extractor's opinion.

-- ============================================================================
-- § The figures, restated and RE-DERIVABLE — the authoritative table
-- ============================================================================
-- ADR 0017 § The figures published 97.8 / 93.3 / 89.3 and 98.0%, measured on the finder with
-- its registry filter removed. That run directory was never in `data/`, and the registry it
-- was scored against dropped the suffix from 2,711 held dockets, so the table could not be
-- re-derived and two of its lines were low. THE OPERATOR'S DECISION, 2026-09-01: re-run it
-- and keep the run reproducible.
--
-- `tools/rmi-ai-machine/citation_dryrun.py` now runs the SHIPPED finder over
-- `data/benchmark/text` and regenerates the run every time, so `data/` stays disposable and
-- the numbers stay checkable. Measured 2026-09-01, sixty decisions, 225 docket-shaped truth
-- targets:
--
--     extraction   the finder saw it                    222   98.7%   (0017 said 97.8%)
--     resolution   and the registry resolved it         216   96.0%   (0017 said 93.3%)
--     PROJECTION   and the rule would show it           213   94.7%   (0017 said 89.3%)
--     precision    213 true of 218 shown                        97.7%   (0017 said 98.0%)
--
--     and what a READER sees, which is a different question:  210   93.3%
--     precision    210 true of 215 shown                        97.7%
--
-- EVERY LINE MOVED, and not for one reason, so the reasons are separated:
--
--   * resolution and projection rose because the scorer's registry defect was fixed — it
--     dropped the suffix from 2,711 held dockets, so every finding naming one scored as
--     unresolvable.
--   * extraction rose from 97.8% because the shipped finder joins EVERY occurrence of a
--     target on a page rather than keeping the first. ADR 0017 D4 settled the span test as
--     disjunctive over occurrences precisely because "the extractor quotes the FIRST
--     match's line, which is usually the running caption" — and the measured tool left that
--     defect alive within a page.
--   * PRECISION FELL, from 98.0% to 97.7%, and that is the honest trade: finding more
--     brings more extras with it. The record should not report the recall rise without it.
--   * the reader's line is lower again because migration 0015's gate holds five edges —
--     `AB 284`, `AB 511`, `AB 1014`, `AB 1071`, `AB 1242` — until a human answers. ADR 0017
--     measured the exposed class at 3 of 225 against a finder that emitted fewer targets;
--     PROJECTED RECALL IS NOW A FUNCTION OF REVIEW BACKLOG, and both numbers have to be
--     quoted with what they are.
--
-- THE GRAMMAR IS NOT THE MEASURED TOOL'S, so this reproduces ADR 0017's configuration
-- rather than being it: `keys.DOCKET` allows six digits where `benchmark_regex.py` capped at
-- five, does not accept `NOR Docket No. 42183`'s interposed words, and takes a bare `(X)`
-- parenthetical the old pattern did not. Two grammars landing near one number is evidence,
-- not identity, and the deltas are named in `docs/deferred.md`.
--
-- THIS TABLE IS THE ONE TO QUOTE. Migration 0014's header carries an earlier restatement and
-- is committed; where they differ, this is later and re-derivable. Better still, run the
-- tool: the store's own `class_measurement` rows are written from it, and a figure with no
-- row behind it is one nobody has checked.

BEGIN TRANSACTION;

INSERT INTO judgement_value_vocab VALUES
    ('kind', 'citation'),                     -- names a proceeding other than its own, or
                                              -- carries a document word near the number
    ('kind', 'caption');                      -- its own proceeding, with no document word

PRAGMA user_version = 16;

COMMIT;
