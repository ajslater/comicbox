# hadolint ignore=DL3007
FROM nikolaik/python-nodejs:python3.14-nodejs24
LABEL maintainer="AJ Slater <aj@slater.net>"

COPY debian.sources /etc/apt/sources.list.d/
# hadolint ignore=DL3008
RUN apt-get clean \
    && apt-get update \
    && apt-get install --no-install-recommends -y \
        bash \
        unrar \
        zlib1g \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY . .
RUN PYMUPDF_SETUP_PY_LIMITED_API=0 make install