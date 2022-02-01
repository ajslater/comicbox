ARG CODEX_BUILDER_BASE_VERSION
FROM ajslater/codex-builder-base:$CODEX_BUILDER_BASE_VERSION

WORKDIR /app
# hadolint ignore=DL3018
RUN apk add --no-cache \
  shellcheck

COPY package.json package-lock.json pyproject.toml poetry.lock setup-dev.sh ./
RUN ./setup-dev.sh

COPY . .
