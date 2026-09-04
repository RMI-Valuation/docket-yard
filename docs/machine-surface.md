# The machine-agent surface (F7)

Chosen 2026-08-31. A read-only MCP server over the reads that already exist, a discovery
document at `/.well-known/mcp.json`, and an explicit crawler and AI-training policy in
`robots.txt` and on `/data` in place of the silence that was there before.

The reason is not that MCP is fashionable. The audience already puts regulatory questions
to assistants, and assistants answer them from training data — inventing docket numbers and
service dates that look exactly like real ones. Being the grounded source they reach
instead is a distribution channel, and it is the one failure mode this surface exists to
prevent. Effort was **Low because F5 shipped**: this is a wrapper over existing reads, not
new retrieval.

## The two constraints, and where they are enforced

Both travel with the capability, and neither is left to good intentions.

**Read-only.** No capability writes, subscribes, or spends on a reader's behalf. Three
things enforce it: `web/mcp.py` imports the read side only; the web tier's connection sets
`PRAGMA query_only = ON`, so a write raises at SQLite rather than landing; and
`tests/test_mcp.py` parses the module's own imports and refuses `alerts`, `subscriptions`,
`capture`, `backfill`, `poll` and `dump`, so a later tool that writes fails the suite.

**Every answer carries its caveats.** A person reading a sheet has the coverage page a click
away, "as printed" on every quoted cell, and the standing line that nothing here says what
any party argued. An assistant is handed a string and will quote it, so the caveats travel
**in** the string: every tool result ends with what the record does not hold, every record
names the Board's own file, and the standing caveats are handed over at `initialize` so they
are in front of the model before it asks anything. A test asserts this on every tool,
including the ones that find nothing — an assistant quoting this record without its caveats
is worse than no source.

The third rule is about absence. **A miss must read as a miss**: "the record holds nothing
matching X — that is an absence in this record, not proof of absence at the Board." Filling
a gap from memory is the specific failure being designed against, so the surface never
returns an empty result that an assistant could mistake for permission to guess.

## The protocol, and why these choices

Streamable HTTP (MCP 2025-11-25), checked against the specification rather than recalled:

- **One endpoint, `POST /mcp`, answering JSON.** No SSE. `GET /mcp` answers **405**, which
  the spec allows for a server that never initiates a message — and this one never does.
- **Stateless: no session id.** A read-only server can afford it, and it means a restart
  strands nobody and a redeploy needs no reconnect handling.
- **Version negotiation.** A request naming a version we speak gets it back; an unknown one
  gets the newest we speak, not the oldest we tolerate, so a client that supports only newer
  versions is not handed 2025-03-26 and disconnected. A missing header is the spec's own
  default rather than a refusal; an unsupported header is a 400, as the spec requires.
- **The SQLite work runs in a threadpool.** The route must be `async` to await the body, and
  every other database route here is a plain `def` that Starlette threads for you. Left on
  the event loop, one docket sheet on a 995-sub-docket family would stall the whole site,
  which is single-process.
- **Failures are results, not transport errors** — `isError: true` — and the exception's own
  text stays in the operator's log. Echoing it handed an unauthenticated caller internal
  detail ("no such table: …" names the schema); a fixed sentence goes back instead.
- **`params` and `arguments` are type-checked.** The body is unauthenticated and arbitrary;
  they are dicts only because a client chose to send dicts. `{"params": [1,2]}` was an
  unhandled 500 from one line before they were checked.

## The tools

Four, deliberately: each is a read a person could do, and none composes into a write.

| Tool | Answers |
| --- | --- |
| `search_the_record` | proceedings, parties, decisions and comments by their own words, and pages of the Board's documents by their machine-read text (each `[page]` line labelled with who read it, the band's operand or its absence, and the scan); a docket number resolves directly. `limit` bounds the record lines; page lines are at most 20 |
| `get_docket_sheet` | one proceeding's chronological sheet, newest first, each entry with the Board's own file and the sub-docket it was entered in |
| `get_environmental_comment` | one comment by its Board number, with the commenter's own words as printed — quotation, never characterisation |
| `coverage` | what the record holds and what it does not, measured; the tool an assistant is told to call before calling the record complete |

A comment is folded by its **row ref**, not its number: one comment entered in a docket and
its sub-docket is one comment, while two comments the Board gave the same number are two
(`stb-data-source.md`). Folding by number would tell a reader that a cross-posted comment
was two different people.

## The AI policy

The operator's decision, 2026-08-31: **name the AI crawlers and welcome them**, and say that
training on the raw index is permitted, because it is dedicated to the public domain and
cannot be un-dedicated. Silence is not neutral — some crawlers read it as disallowed — and
the record is more useful being read than being guessed at.

One carve-out, and the **rule matches the prose**: the party module (`/p/`, `/parties`) is
derived work held back from that dedication pending a licence review, so it is `Disallow`ed
for the agents named, and the discovery document does not label the whole surface CC0. It
stays readable to people and to ordinary crawlers — this is about the dedication, not
secrecy. A permission whose rules hand over what its own text withholds would be a promise
contradicted by its own file.

What is asked rather than required, in `robots.txt` and on `/data`: if you answer from this
record, carry what a reader would have seen — coverage is not uniform, dates and captions
are quoted rather than computed, and nothing here says what any party argued.

## What this surface is not

It does not write, subscribe, spend, or accept a reader's identity. It holds no session and
no reader data of any kind (ADR 0011). It adds no retrieval the site did not already have —
every answer comes from the same reads the pages use, so a defect here is a defect there
too, and there is no second copy of the record to drift.
