ARG CODEX_BUILDER_BASE_VERSION
FROM ajslater/codex-builder-base:$CODEX_BUILDER_BASE_VERSION

WORKDIR /app
RUN rm -rf python_cacher
# hadolint ignore=DL3018, DL3059
RUN apk add --no-cache \
  shellcheck

COPY package.json package-lock.json pyproject.toml poetry.lock setup-dev.sh ./
RUN ./setup-dev.sh

COPY . .
