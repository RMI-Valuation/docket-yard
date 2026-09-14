# One image for both services (ADR 0012): `serve` for web, `poll --every` for ingest.
# Built by .github/workflows/release.yml, tagged with the release (ADR 0010).
FROM python:3.12-slim AS build
WORKDIR /src
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir --prefix=/install .

FROM python:3.12-slim
ARG VERSION=0.0.0
ENV DOCKETYARD_VERSION=$VERSION \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
COPY --from=build /install /usr/local
# SECURITY FIXES THE BASE IMAGE HAS NOT PICKED UP (2026-09-14). `python:3.12-slim` of 2026-09-01
# ships `libsqlite3-0 3.46.1-7+deb13u1`; Debian's `deb13u2` (2026-06-14) backports CVE-2026-11822
# and CVE-2026-11824, both in FTS5, which search is built on — and a rebuild alone does not take
# it. `--only-upgrade` touches this one package; it is NOT pinned, because a pinned version leaves
# Debian's mirror when the next update lands and the build would then fail. Verify a release with
# `dpkg -s libsqlite3-0`. Moving past 3.46 is its own decision (docs/deferred.md § SQLite 3.53.4).
RUN apt-get update \
    && apt-get install -y --no-install-recommends --only-upgrade libsqlite3-0 \
    && rm -rf /var/lib/apt/lists/*
# the store and blobs live on a mounted volume owned by this uid (infra/deploy/README.md)
RUN useradd --uid 1000 --create-home --shell /usr/sbin/nologin docketyard \
    && mkdir -p /data && chown docketyard:docketyard /data
USER docketyard
WORKDIR /home/docketyard
VOLUME ["/data"]
EXPOSE 8000
ENTRYPOINT ["docketyard", "--db", "/data/docketyard.sqlite", "--data-dir", "/data"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8000"]
