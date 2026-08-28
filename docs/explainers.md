# Docket-type explainers — draft for review

**Status: reviewed by the operator 2026-08-28 and published** as `/about/prefixes` (the index:
reading a number, the other prefixes, suffixes, decision types, not-the-Board) and
`/about/FD`, `/about/AB`, `/about/NOR`, `/about/EP`, `/about/MCF`, linked from every sheet's
"About this record" block and from the registry-by-prefix table on `/stats`. The pages are
templates (`web/templates/explain_*.html`) carrying this text; every figure is measured on
request (`store/explainers.py`), so the numbers below are the draft's and the pages' are
live. The operator's decisions on the open questions: rows graded [?] publish, marked
unconfirmed, so the gap is public; the ICC-era prefixes share one page; counts render live;
the address is `/about/<PREFIX>`. Capability P2: what each prefix and suffix means, what is
being asked for, what the Board can and cannot do, and what happens next.

**How this was written, and how far to trust each part.** Every statement is graded:

- **[B]** — the Board's own words, from a page on stb.gov or a Board document, cited inline.
- **[R]** — the regulation or statute, cited by section (49 CFR / 49 U.S.C.).
- **[N]** — the National Archives' description of the ICC/STB docket series (records schedules
  N1-134-99-002 and DAA-0134-2013-0017).
- **[C]** — read off the record itself: what the captions in Docket Yard's registry say a series
  contains. This is evidence, not authority; the figures are measured from the store.
- **[?]** — inferred and **unconfirmed**; published marked as such (the operator's decision,
  2026-08-28), so the gap is public rather than hidden.

Never inferred here: what any filing argues, or which side a party is on. The explainers
describe kinds of proceeding, never the merits of one.

Sources used, all fetched 2026-08-26: the Board's *Tips for Searching STB Records* (the only
page on stb.gov that defines prefixes) [B-tips]; *About STB* [B-about]; *Litigation
Alternatives* [B-alt]; *Need Assistance?* [B-help]; *Environmental Overview* and its FAQs
[B-env]; *Household Goods Tariff Guidance* [B-hhg]; *Legal Resources* [B-legal]; the Board's
*Frequently Asked Questions: Major Railroad Mergers* [B-merger]; press release PR-22-55 on
smaller rate disputes [B-rates]; 49 CFR §1152.50, §1180.2, Parts 1150 and 1111 [R]; the two
NARA schedules [N]; and the search form's own prefix and suffix lists (35 prefixes, 20
suffixes, scraped 2026-08-26) [B-form].

---

## Reading a docket number

`FD 36873`, `AB 55 (Sub-No. 785X)`, `EP 711 (Sub-No. 1)`, `NOR 42175`, `MCF 21155`.

- The **prefix** says what kind of proceeding it is. "Board proceedings are assigned a docket
  prefix based on the type of case." [B-tips]
- The **number** is a sequence within the prefix. The count runs from the ICC era: the record
  holds Finance Dockets from 1165 to 36948 and AB dockets 1 to 1351. [C]
- A **Sub-No.** is a proceeding filed under an existing docket — a related transaction, a
  later phase, or, for the big abandonment dockets, each line a carrier abandons. AB 55 is
  CSX Transportation's abandonment docket; its sub-numbers pass 1,000. Sub-numbers are the
  norm for AB (5,536 of 6,640 in the registry) and common for EP (251 of 446) and FD (1,220 of
  8,706); rare elsewhere. [C]
- A **suffix letter** qualifies the proceeding. `X` marks an exemption (below). [C]
- Docket Yard folds a docket and its sub-numbers into one sheet (ADR 0005), because the Board's
  own search treats a sub-docket as risky to find on its own.

The Board's search form offers 35 prefixes and 20 suffix letters and defines none of them
[B-form]; its tips page defines five. What follows covers all 35.

---

## The five prefixes that carry the living record

Together these hold 24,000 of the registry's 32,604 dockets and nearly every filing since
2024. [C]

### FD — Finance Docket

**What it is.** The Board's own definition: "Rail line sales and leases, operating rights,
trackage rights, acquisitions of control (mergers), petitions for declaratory order, rail line
constructions, and modified certificates." [B-tips] The ICC's Finance Dockets, which FD
continues, "concern railroad pooling or division of traffic, the purchase, control, merger,
lease, or consolidation of operating rights by railroads", and before 1972 held abandonments
too. [N]

**What is being asked for.** Permission — or, more often, an *exemption* from having to ask
for permission — to change who owns, controls or operates a piece of railroad. Under 49
U.S.C. §11323 "any proposed merger or acquisition of control of a railroad by another railroad
may be carried out only with the approval of the Board." [B-merger] Transactions come in
four sizes [R §1180.2; B-merger]:

- **Major** — "the control or merger of two or more Class I railroads." Full application,
  prefiling notice three to six months ahead, public interest test, at least five years of
  oversight after approval. [B-merger]
- **Significant** — not two Class I's, but "of regional or national transportation
  significance." [R §1180.2(b)]
- **Minor** — more than one railroad, and neither of the above. [R §1180.2(c)]
- **Exempt** — one of nine categories where "prior review and approval … is not necessary",
  e.g. trackage rights under a written agreement, temporary trackage rights up to a year,
  corporate-family transactions, acquiring a line whose abandonment has been permitted.
  [R §1180.2(d); B-merger] These proceed by *notice of exemption*: the carrier files, the
  Board publishes, and the exemption takes effect on a fixed timetable unless someone
  petitions to revoke it.

Also here: a non-carrier acquiring or operating a line (49 U.S.C. §10901 and the class
exemption at 49 CFR Part 1150 Subpart D), a Class III carrier doing the same (§10902, Subpart
E), building a new line, modified certificates (Part 1150 Subpart C), and **petitions for
declaratory order** — a request that the Board say what the law is on a disputed question,
typically whether federal rail law preempts a state or local rule. [B-tips; R Part 1150]

**What the Board can and cannot do.** It approves, denies, or approves with **conditions** to
"mitigate or offset harm to the public interest" — competitive conditions, employee
protection, environmental mitigation, service assurances. [B-merger] It does not regulate
safety (that is the Federal Railroad Administration; a major merger's Safety Integration Plan
is worked out "with the Federal Railroad Administration"). [B-merger]

**What happens next, typically.** For an exemption: notice filed → Federal Register notice →
effective on the timetable in the rule → *consummation notice* when the deal closes (131
in the record). For an application: filing → comments and replies → decision, with
environmental review by the Office of Environmental Analysis where a construction or a
line acquisition above the threshold is involved. [B-env] In the record since 2024-08, FD
dockets produced 367 decisions, 114 notices of exemption and 11 environmental reviews; the
commonest filings are replies, comments, letters and notices of intent to participate. [C]

**Examples in the record.** FD 36873 (the current Class I control proceeding), FD 36500
(Canadian Pacific—Control—Kansas City Southern, decided 2023 [B-merger]), FD 36947 (a town
acquiring a line by exemption), FD 36948 (a control exemption). [C]

### AB — Abandonment

**What it is.** "Rail line abandonments and discontinuances of services. This would also
include proceedings in which there is trail use (i.e., rail banking)." [B-tips] The series
began in 1972 when the ICC separated abandonments from Finance Dockets. [N]

**What is being asked for.** Permission to stop: to *abandon* a line (remove it from the rail
network) or to *discontinue* service over it (stop operating, leaving the line and the
obligation intact — often a lessee's or trackage-rights operator's request). Three routes:

- **Application** for a certificate under 49 U.S.C. §10903 — the full case, with a showing
  that the public convenience and necessity permit abandonment. [N; R Part 1152]
- **Petition for exemption** — an individual request to skip the full case. [R §1152.50 notes
  the difference]
- **Notice of exemption** under the class exemption for out-of-service lines, 49 CFR
  §1152.50 — the carrier certifies "no local traffic has moved over the line for at least 2
  years" and overhead traffic can be rerouted; the notice is filed at least 50 days before the
  planned abandonment and is "effective 30 days after publication, unless stayed." [R
  §1152.50] This is the route most AB sub-dockets take — the `X` suffix. [C]

**What the Board can and cannot do.** Grant, deny, or grant subject to conditions; and hold
the door open for someone else to keep the line alive. An **offer of financial assistance**
(OFA) lets a party offer to buy or subsidise the line (49 U.S.C. §10904); a **public use
condition** (§10905) and a **trail use / rail banking** request under 16 U.S.C. §1247(d)
can stay an abandonment so the corridor is preserved as a trail with the possibility of
future rail use. [R §1152.50] The Board does not decide who owns the land afterwards, or what
a state or town may do with a crossing; those are matters of property law and of other
agencies.

**What happens next, typically.** Notice or application → environmental and historic review
(an Environmental Assessment is required for "line abandonment, service discontinuance" [B-env
FAQ]) → decision or effective date → OFA, public-use or trail-use requests if any → the
carrier's *consummation notice*, or its lapse. In the record since 2024-08: 152 decisions, 72
environmental reviews, 33 notices of exemption; the commonest filings are replies, comments,
notices of exemption and consummation notices. [C]

### NOR — formal complaints, including rate cases

**What it is.** "Formal complaint proceedings (including rate cases, unreasonable practice
cases, and violations of the common carrier obligation)." [B-tips] The caption is always
*complainant v. carrier*. [C]

**What is being asked for.** A finding that a railroad's rate, rule or practice is unlawful,
and an order to fix it — most famously that a rate is unreasonable, which the Board may only
decide where the carrier has *market dominance* over the traffic. Complaints are filed under
49 CFR Part 1111; the Board may also open an investigation on its own. [R Part 1111]

**The rate-case methods**, in the Board's words: **stand-alone cost (SAC)** — "a railroad may
not charge a shipper more than it would cost to build and operate a hypothetical new,
optimally efficient railroad … tailored to serve a selected traffic group that includes the
complainant's traffic"; the **Three-Benchmark** method for smaller cases, which "examines the
R/VC ratio produced by the challenged rate in relation to three benchmark figures"; and, since
2022, **Final Offer Rate Review**, where "the Board will decide the rate by selecting either
the complainant's or the defendant's final offer", and a voluntary **arbitration** program,
both "limited to rate disputes worth up to $4 million in relief over two years." [B-rates; STB
Ex Parte 646 (Sub-No. 1), Ex Parte 755, 765]

**What the Board can and cannot do.** Prescribe a maximum reasonable rate, order reparations
for past overcharges, order a practice stopped, order service under the common carrier
obligation (49 U.S.C. §11101). It cannot award damages for things outside its statute, and it
does not hear personal-injury, crossing or property claims. Amtrak's on-time-performance
complaints under 49 U.S.C. §24308(f) are also NOR cases (NOR 42175, the Sunset Limited). [C]

**What happens next, typically.** Complaint → answer → procedural schedule → discovery and
evidence (much of it under protective order: 190 motions for protective order in the record)
→ decision. Rate cases take years under SAC and months under the smaller-case methods.
Since 2024-08: 49 decisions; replies, status reports and motions dominate the filings. [C]

### EP — Ex Parte

**What it is.** "Rulemaking or information gathering proceedings." [B-tips] *Ex parte*
here means the Board opened the docket itself, not on a party's complaint or application.

**What is being asked for.** Usually nothing by a party: the Board proposes a rule, sets a
policy, holds a hearing, or makes an annual determination, and the public comments. The
record's EP dockets include the yearly **revenue adequacy** determinations (EP 552 and its
sub-numbers), the **cost of capital** (EP 558), fee schedules (EP 542), the review of
commodity exemptions (EP 704), and procedural rules such as filing deadlines during a
shutdown (EP 721). [C] Sub-numbers track the years or phases.

**What the Board can and cannot do.** Adopt rules within 49 U.S.C. subtitle IV, issue policy
statements, set the reference numbers the rest of its work depends on. A rule can be
challenged in a court of appeals — hence *Notice of Court Action* entries. [C]

**What happens next, typically.** Notice of proposed rulemaking → comments and replies →
final rule, effective on a stated date; or a hearing notice → the hearing → a decision or
report. EP dockets carry the record's *ex parte meeting summaries* (125) and most of its
*status reports* (1,426), because the Board requires parties who meet it informally to file a
summary. Since 2024-08: 84 decisions and 20 notices. [C]

### MCF — motor carrier (passenger) finance

**What it is.** "Motor carrier passenger proceedings." [B-tips] The Board keeps the ICC's
authority over mergers and control among **intercity bus** companies (49 U.S.C. §14303) —
"the intercity bus industry" is on the Board's own list of what it regulates. [B-about]

**What is being asked for.** Approval, or an exemption, for one bus company to acquire
another or to be brought under common control: "Flixbus … and Greyhound Lines — Control —
Greyhound Central" (MCF 21155), "First Student — Acquisition of Control" (MCF 21154). [C]
The registry's 6,727 MCF dockets are overwhelmingly ICC-era trucking and bus transactions —
the "(T1)/(T2)/(EX-NR)" caption codes are the ICC's own [C] — of which 1,388 carry the `TA`
suffix, which in this series marks the ICC's *temporary authority* grants [?]. Since 1996
the live MCF work is bus control transactions only. [C]

**What happens next.** Application → Federal Register notice → comments → decision (45
decisions since 2024-08; applications are the commonest filing). [C]

---

## Prefixes with a smaller or older record

Two of the 35 hold a live, small stream today; most of the rest are ICC-era series the Board
inherited and keeps searchable. The "record" column is what the registry holds. [C]

| Prefix | Record | What it is | Grade |
|---|---|---|---|
| **WB** | 116 dockets, 89 filings, live | **Waybill data requests.** "The Carload Waybill Sample is a stratified sample of carload waybills for U.S. rail traffic" [B, Reports & Data]. WB 26 is the current series; each sub-number is one request, answered by a decision under 49 CFR 1244.9, with objections from the railroads whose data it is. Every caption reads "Request for / Release of Waybill Data". 27 decisions since 2024-08. | [B][C] |
| **RR** | 6 dockets, 3 filings, live | **Released rates** — a carrier's request to limit its liability for loss or damage in exchange for a lower rate (49 U.S.C. §14706 for motor carriers, §10502 exemptions for rail). Household-goods movers' released-rates orders live here; the Board "oversees tariff requirements for interstate moving companies" and refers moving disputes to FMCSA. [B-hhg] Captions: "Released Rates of Motor Common Carriers of Household Goods". | [B][C] |
| **SO** | 22 | **Service orders** — emergency orders directing service when a carrier cannot or will not provide it (49 U.S.C. §11123): "Petition for Emergency Service Order", "Request for Service Order under 49 U.S.C. 11123". | [C][R] |
| **PTO** | 6 | **Passenger train operation orders** — numbered orders concerning a freight carrier's handling of passenger trains (the captions name the Indiana Harbor Belt). Statutory basis to be confirmed (49 U.S.C. §24308 governs Amtrak's use of freight facilities). | [C][?] |
| **DOP** | 4 | **Designated operator** certificates — a carrier designated to operate a line another carrier is abandoning, under 49 CFR Part 1150 Subpart B. Captions: "Application for Designated Operator Certificate", "Cancellation of Certificate of Designated Operator". | [R][C] |
| **SDM** | 569 | **System diagram maps** — each carrier's mandated map of its lines by category (Category 1 = anticipated abandonment within three years), 49 CFR §1152.10–.13. One docket per carrier: "Union RR. Co.", "The Blackland Railroad — System Diagram Narrative". | [R][C] |
| **CU** | 16, live | **Paperwork Reduction Act notices** — the Board's 60- and 30-day notices seeking OMB clearance for its information collections: "Rail Depreciation 60-Day PRA Notice", "Waybill Sample". Not proceedings between parties. | [C] |
| **SUB** | 26 | **Depreciation rates** — "In the matter of prescribing depreciation rates for use in computing depreciation charges" for a named carrier (the Board's accounting authority, 49 U.S.C. §11143). Suffix letters distinguish successive prescriptions. | [C] |
| **AM** | 3 | **Administrative matters** of the agency itself: "Senior Executive Service Performance Review Board", "Implementation of the Regulatory Flexibility Act". | [C] |
| **STA** | 7 | **Special tariff authority** for non-contiguous domestic water carriers — permission to change a tariff on short notice: "Fuel Surcharge Increase on One Day's Notice, Crowley Marine Services", "Electronic Filing of Noncontiguous Domestic Trade Tariffs". The Board keeps "rate regulation of non-contiguous domestic water transportation" [B-about]. | [B][C][?name] |
| **WCC** | 5 | **Water carrier complaints** in the non-contiguous domestic trade (Hawaii, Alaska, Puerto Rico, Guam): "DHX, Inc. v. Matson Navigation Company", "Government of the Territory of Guam v. Sea-Land". | [B-about][C] |
| **WC** | 2 | **Water carrier** authority, ICC-era: "Champion's Auto Ferry, Inc. — Algonac, MI". | [C] |
| **EPM** | 164 | **Ex Parte, motor** — ICC rulemakings for the trucking industry: "Review of Motor Tariff Regulations — 1993", "Single State Insurance Registration — 1994 Rules". Closed series. | [C] |
| **MC** | 178 (of ICC's ~247,000) | **Motor carrier operating authority** — the ICC's certificates and permits by carrier docket number; the sub-number is the application. Live motor authority is FMCSA's since 1996. | [C][B-legal] |
| **MCC** | 726 | **Motor carrier complaints and declaratory orders**: "AAA Cooper Transportation v. Ross Neely Express", "Tyco International — Petition for Declaratory Order — Means of Contracting for Motor…". The Board retains a narrow motor-carrier jurisdiction (49 U.S.C. subtitle IV part B) [B-legal]. | [C] |
| **NOM** | 1,446 | **Motor carrier rate and practice petitions** — overwhelmingly shippers' *petitions for declaratory order* on "certain rates and practices" of a trucking company (the 1990s undercharge cases): "BJ's Wholesale Club — Petition for Declaratory Order — Certain Rates and Practices of…". Closed series. | [C] |
| **ISM** | 1,949 | **Investigation and suspension, motor** — ICC proceedings suspending and investigating a proposed motor tariff: "Increased Small Shipment Rates and Minimum Charges", "Petition for Suspension and Investigation NMFC 100-AP Supplement 2". Closed. | [C][N: "investigation and suspension of carrier tariffs"] |
| **IS** | 270 | **Investigation and suspension, rail** — the same for rail tariffs: "Surcharge on Furniture, Conrail, October 1979", "Cancellation of Reciprocal Switching". Closed. | [C][N] |
| **FSA** | 14 | **Fourth Section applications** — carriers seeking permission to charge more for a shorter haul than a longer one over the same line (the Interstate Commerce Act's "long-and-short-haul" clause): "Proportional Rates on Ex-Motor Wheat", "Joint Rail-Water Container Rates". Closed. | [N: "Fourth Section dockets of carriers seeking permission to maintain higher rates at intermediate points than at more distant points"][C] |
| **S5M** | 240 | **Section 5a agreements, motor** — ICC approval of rate-bureau agreements among motor carriers under §5a of the Interstate Commerce Act (antitrust immunity for collective ratemaking): "Western Motor Tariff Bureau, Inc. — Agreement", "National Bus Traffic Assoc. — Appl. for Approval of Amend. Agree." Closed. | [C][?name] |
| **SAI** | 11 | **Shipper agreements** — approval of agreements among shippers' associations: "American Petroleum Institute Agreement", "Chlorine Institute Rail Shippers Discussion Group". Statutory basis to confirm (49 U.S.C. §10706 rate agreements). | [C][?] |
| **MXC** | 13 | **Mexican carrier certificates** — ICC-era operating authority for Mexico-domiciled motor carriers (FMCSA's "MX" numbering continues the idea). Captions are personal names. | [C][?] |
| **CNO** | 1 | Captioned "Classification" — a single ICC-era docket; meaning unconfirmed. | [?] |
| **ARB, ASC, DSO, RER, S5A, SUS** | 0 | Offered by the search form; nothing in the record. Likely: **ARB** arbitration; **S5A** Section 5a agreements (rail); **SUS** suspension; **DSO** directed service orders; **ASC**, **RER** unknown. | [B-form][?] |

---

## Suffixes

The form offers twenty letters; the record uses them unevenly. [B-form; C]

| Suffix | Where | Meaning | Grade |
|---|---|---|---|
| **X** | AB (3,365) | **Exemption** — the sub-docket proceeds by notice or petition for exemption rather than application. Every `X` caption reads "…Abandonment Exemption…" or "…Discontinuance of Service Exemption…". | [C] |
| **TA** | MCF (1,388), one FD | ICC **temporary authority** — provisional approval pending a decision (the MCF captions carry the ICC's "(T1)/(T2)" transaction codes). | [?] |
| **S** | NOR (865) | Attached to ICC-era rate complaints of the late 1970s–80s ("…v. Burlington Northern"). Meaning unconfirmed; candidates: *suspended*, *small*, or the ICC's "S" docket sub-series. | [?] |
| **N** | AB 167 (476) | Attached to Conrail's abandonment sub-dockets (AB 167 is Conrail's docket) around the 1980s. Meaning unconfirmed; candidate: *notice* under the then-new class exemption. | [?] |
| **A, B, C … U** | FD, SUB, S5M, EP, SO | Successive related proceedings under one sub-docket — FD 28640 (Sub-No. 9) A–M are the Milwaukee Road reorganisation's many pieces; SUB 851 C–F are successive depreciation prescriptions; S5M …A are amended agreements. | [C] |
| **0** | FD, EP (3) | A literal zero, appearing on a few captions; probably an entry artefact. | [?] |

---

## Decision types, as the Board labels them

The Board's search offers nine [B-form]; the record since 2024-08 holds them in this
proportion [C]: **Decision** (the Board's or a delegated official's ruling), **Notice of
Exemption** (a class exemption taking effect on notice), **Environmental Review** (the Office
of Environmental Analysis's assessments — AB and FD only), **Notice** (procedural notices,
hearing notices, Federal Register notices), **Notice of Court Action** (a court has ruled on
a Board decision), **Corrected Decision / Corrected Notice** (an errata reissue — Docket Yard
records both versions), **Policy Statement**, **Corrected Environmental Review**.

---

## Not the Board — where a reader with a rail problem should look

A large share of people who reach the Board are at the wrong agency [capability map P1].
From the Board's own material [B-help; B-hhg; B-merger; B-about]:

| Concern | Who handles it |
|---|---|
| A train blocking a crossing; crossing signals; horn noise; track and equipment safety; hazardous materials; derailments | The **Federal Railroad Administration** (safety, 49 U.S.C. chapter 201) and state agencies. The Board hears crossing evidence only inside a merger case [B-merger]. |
| A household-goods mover's conduct, damage claims, licensing | **FMCSA**; the Board only "oversees tariff requirements" [B-hhg]. |
| Trucking authority, MC numbers, insurance | **FMCSA** (since 1996). |
| Amtrak on-time performance | The Board, on complaint (49 U.S.C. §24308(f); NOR). |
| Rail rates, car supply, service failures, interchange, a community concern about a railroad's activities | The Board — start with **Rail Customer and Public Assistance**, "a free service" whose staff "informally advise disputing parties" but "cannot order a specific resolution" [B-alt]. |
| A pipeline (non-energy) or a water carrier in the domestic offshore trades | The Board [B-about]. |
| Energy pipelines, ports, ocean shipping | **FERC**, the **FMC**. |

---

## Open questions for the reviewer

1. `TA`, `S`, `N` suffix meanings and the names of S5M/SAI/STA/MXC/CNO — none is defined on
   stb.gov; the Board's Office of Proceedings or its records staff would settle them in one
   email. Until then those rows do not publish.
2. PTO's statutory basis (the captions name a switching carrier, not Amtrak).
3. Whether to publish the ICC-era prefixes at all, or a single "inherited series" note.
4. Tone: these are written as explainers, not legal advice; the standard disclaimer from
   `licensing.md` ("Summaries are a reading aid, not legal advice…") should head each page.
5. Whether "what happens next" should carry the measured counts (they date the page) or
   link to `/stats` instead.
