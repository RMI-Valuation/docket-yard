# What to take from the UP–NS tracker, and what not to

The sibling project `../up-ns-merger-tracker` tracks one proceeding — STB Finance Docket
No. 36873, *Union Pacific — Control — Norfolk Southern* — end to end: ingest, PDF extraction,
per-document summarisation, position labelling, a dated calendar, and a daily narrative brief.
It is the reason this project exists. It is **tabled as of 2026-08-26** and is not being
developed further; the intent is to fold parts of its capability in here.

**Do not modify that project.** It is a reference and a fixture, not a dependency.

*The mistake this document prevents:* folding the tracker in wholesale. Two of its behaviours —
stance labelling and the narrative brief — are correct for one contested mega-case and wrong for
an agency-wide record, and adopting them by default would break a non-negotiable rule and a
positioning decision that were both settled deliberately.

## Already inherited, as principles rather than code

| From the tracker | Where it lives here |
| --- | --- |
| 91 of 605 "Filed For" cells are *lists* of parties, not one name | ADR 0004 — party is an entity, not a string |
| A procedural filing takes no position regardless of who filed it | `CLAUDE.md` § Rules that are not negotiable |
| Dates are quoted from the document, never computed from context | `CLAUDE.md`, same section |
| The AJAX endpoint mechanics and their silent-failure traps | `docs/stb-data-source.md` |

These transferred in their durable form. Nothing further is owed to them.

## Worth taking

**Tiered summarisation — the A/B/C routing.** The tracker assigns every document a tier before
reading it: **A** substantive (decisions, motions, replies, applications, discovery) gets a full
analytical brief; **B** position documents (comments, letters, support statements) get a short
brief plus a stance; **C** routine (bare notices of intent, counsel substitutions, errata) is
logged and never read. Page caps go with the tier — 40 pages for A, 12 for B.

This is the cost-control mechanism, and it is the same question `docs/extraction-benchmark.md`
exists to answer at 75,000–125,000 documents rather than 988. The tier assignment is a cheap
decision made from document type alone, before any model is invoked. Read
`../up-ns-merger-tracker/tracker/extract.py` and `AGENT_BRIEF.md` before designing the
equivalent here; the tier boundaries are the part that took iteration.

**Multi-attachment row folding.** `fetch_docket.merge_attachments()` folds STB rows that carry
several attachments into one record and prefers the PDF among them. It cut null-URL records from
18 to 7 in a 988-document docket. The same rows exist agency-wide; ingest will meet this.

**The calendar as a shape.** The brief's calendar table — one row per dated obligation, each
quoted from the decision that set it, with the decision identified — is the output shape `C4`
should produce per docket. It is already noted as a fixture below.

## Not to be taken

**Stance labelling as a default.** It earns its keep in a proceeding with 594 distinct parties
where the balance of the record is itself the story. Across 32,606 dockets, most proceedings have
no position to take, and a labeller run by default would manufacture exactly the inference
`CLAUDE.md` forbids. If it ever ships here it belongs to a *contested-proceeding* view that a
docket must qualify for, never to the standard sheet — and it would need the tracker's
`payload.effective_stance()` discipline, which excludes Board decisions, applicants' own filings
and all procedural filings from the count, carried across intact.

**The daily narrative brief.** A generated agency-wide digest is editorial. The decision not to
be a watchdog (ADR 0009, and the naming discussion behind it) was made on purpose; a daily
editorial voice is how that decision gets reversed by accident. Per-docket, on-demand summary is
a different thing and is not excluded by this.

**The dashboard.** Superseded entirely.

## The fixture — probably the most useful part

The tracker holds **988 hand-checked documents in one docket**: 33 Board and ALJ decisions, 904
filings from 594 distinct parties, 51 environmental comments, spanning the abeyance, the
discovery fights and the return to an evidentiary schedule. Party attributions, position labels
and dated obligations were each verified by hand against the source PDFs.

Two uses:

1. **`docs/extraction-benchmark.md` step 1** is blocked awaiting a 60-decision labelled sample.
   Some of that labour is already done, on a docket rich in exactly the document types the
   benchmark needs to discriminate.
2. **A regression fixture for the citator and `C4`.** `briefs/2026-08-25.md` carries 13 dated
   obligations, each quoted and attributable to a numbered decision — enough to test a deadline
   extractor against before the capability is chosen.

Caveat before either use: the tracker's text extraction is page-capped (40/12), so its briefs for
long exhibits cover opening pages only, and a handful of filings are scanned images with no
extractable text. Labels derived from those documents are weaker evidence than the rest.

---

*Written 2026-08-26 when the tracker was tabled. Nothing here is chosen; it is what to read and
what to refuse when a capability that touches this ground is chosen.*
