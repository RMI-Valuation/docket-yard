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
# the store and blobs live on a mounted volume owned by this uid (infra/deploy/README.md)
RUN useradd --uid 1000 --create-home --shell /usr/sbin/nologin docketyard \
    && mkdir -p /data && chown docketyard:docketyard /data
USER docketyard
WORKDIR /home/docketyard
VOLUME ["/data"]
EXPOSE 8000
ENTRYPOINT ["docketyard", "--db", "/data/docketyard.sqlite", "--data-dir", "/data"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8000"]
