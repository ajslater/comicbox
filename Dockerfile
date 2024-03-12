FROM python:3.12-bookworm
LABEL maintainer="AJ Slater <aj@slater.net>"

COPY debian.sources /etc/apt/sources.list.d/
# hadolint ignore=DL3008
RUN apt-get clean \
  && apt-get update \
  && apt-get install --no-install-recommends -y \
    bash \
    mupdf \
    npm \
    ruamel.yaml.clib \
    unrar \
    zlib1g \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY bin ./bin
COPY .eslintignore .gitignore .prettierignore .remarkignore eslint.config.js package.json package-lock.json pyproject.toml poetry.lock Makefile ./
RUN make install-all

COPY . .
