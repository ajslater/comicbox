FROM ajslater/python-alpine:3.11.5-alpine3.18_0
ARG VERSION
LABEL maintainer="AJ Slater <aj@slater.net>"
LABEL version=$VERSION

# hadolint ignore=DL3018
RUN echo "@old http://dl-cdn.alpinelinux.org/alpine/v3.14/main" >> /etc/apk/repositories && \
  apk add --no-cache \
    bash \
    bsd-compat-headers \
    git \
    mupdf \
    npm \
    unrar@old \
    yaml \
    zlib

WORKDIR /app
RUN rm -rf python_cacher
# hadolint ignore=DL3018, DL3059
RUN apk add --no-cache \
  shellcheck

COPY bin ./bin
COPY package.json package-lock.json pyproject.toml poetry.lock Makefile ./
RUN make install-all

COPY . .
