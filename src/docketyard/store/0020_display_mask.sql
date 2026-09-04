-- Migration 0020: the display rule omits contact details. ADR 0021 D9, addendum 2026-09-04.
--
-- `document_text_display` IS the display rule (ADR 0021 D9; ADR 0022 D4 indexes it), so the
-- omission lives here and nowhere else: what a reader is shown, what the page index holds and
-- the text a 'delete' must carry are all `dy_display_text(text)` — a function every connection
-- registers (`store/display.py`, from `store.db.connect` and the web tier's connections) that
-- replaces email addresses and North American telephone numbers with a marker. The stored
-- reading is untouched: `document_text.text` remains the document's own words, append-only,
-- and the Board's file is one click from every text page.
--
-- A store opened without the function cannot read this view ("no such function"), which is
-- the intended failure: a copy restored elsewhere and queried raw shows nothing rather than
-- the unmasked text under this project's display rule. Every table reads as before.
--
-- The view's version and the rule's are the page index's format: `search.PAGE_INDEX_FORMAT`
-- becomes `display@0020.1` with this migration, so the index must be rebuilt after the
-- deploy by `docketyard search rebuild-pages`, and `web` refuses to serve a store whose
-- index predates the format until it has been. A whole rebuild holds the write lock for its
-- run (8 m 49 s at 1.1 M rows, measured 2026-09-04): the maintenance wall keeps readers'
-- subscribe writes off it, and the poller loses one pass to it, which its trailing window
-- covers. A change to the rule's patterns is a new migration of this shape, never a code
-- edit alone (`display.py`); and a rollback of this release is a Litestream restore, not a
-- tag change — a schema-19 image refuses a schema-20 store.
--
-- The SELECT below is migration 0018's, column for column, with the one expression. Its
-- reasoning — no `agreement_distance`, the human row over the primary — is recorded there.
BEGIN TRANSACTION;

DROP VIEW document_text_display;

CREATE VIEW document_text_display AS
SELECT t.text_id, t.document_sha256, t.page_no, t.reading_channel, t.reading_role,
       t.route_class, t.method, t.method_version, t.render_profile,
       dy_display_text(t.text) AS text, t.confidence_state, t.asserted_at
  FROM document_text t
 WHERE t.superseded_by IS NULL
   AND t.reading_role IN ('primary', 'human')
   AND NOT (t.reading_role = 'primary'
            AND EXISTS (SELECT 1 FROM document_text h
                         WHERE h.document_sha256 = t.document_sha256
                           AND h.page_no = t.page_no
                           AND h.reading_role = 'human'
                           AND h.superseded_by IS NULL));

-- ADR 0021 D1 made the reading append-only, and both `page_index.leave` (a 'delete' must
-- carry the text as indexed) and the view above rest on `text` never changing. Until now
-- that was an obligation; the schema says it (schema-critic, 2026-09-04).
CREATE TRIGGER document_text_text_is_immutable
BEFORE UPDATE OF text ON document_text
BEGIN
  SELECT RAISE(ABORT, 'document_text.text is append-only (ADR 0021 D1): supersede, never update');
END;

PRAGMA user_version = 20;

COMMIT;
