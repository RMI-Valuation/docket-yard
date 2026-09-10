# The text-layer parser (ADR 0024 D2): pymupdf, the standard library, and nothing else.
#
# It is a SEPARATE IMAGE from the application deliberately. The application image carries the
# store's schema, the mail sender, the vault and every credential the instance uses; this one
# parses bytes a third party wrote. Sharing an image would mean the component handling the
# most hostile input in the system also carried the most to lose, which is the arrangement
# D2 exists to end.
#
# The version here IS the pin. The loader refuses a reading whose producer contradicts the
# declaration in `producer_declaration` (D6), so bumping this line without re-declaring the
# pin stops the stage rather than silently re-reading 74,295 documents at a new version.
FROM python:3.13-slim

# pymupdf pinned exactly: `pymupdf` IS the reading key's `method_version`, so an unpinned
# install would change the key on a rebuild and every document would look unread.
RUN pip install --no-cache-dir pymupdf==1.26.0

# A parser that does not need to be root is not root. THE UID IS THE APPLICATION IMAGE'S,
# 1000, and that is not cosmetic: the spool is a bind mount shared with the loader, which runs
# as 1000, so a parser at any other uid writes files the loader cannot read — and the stage
# would fail on a fresh deploy with a permission error rather than a reason (security review,
# 2026-09-10). The two containers share nothing else.
RUN useradd --create-home --uid 1000 --shell /usr/sbin/nologin extract
USER extract

COPY extract.py /app/extract.py

# no ENTRYPOINT arguments, no shell: the request directory is the only input surface
CMD ["python", "-u", "/app/extract.py"]
