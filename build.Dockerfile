FROM ajslater/codex-builder-base:b97c828671282570b919908a38d2c3ce-x86_64

ARG DEBIAN_FRONTEND=noninteractive

#############
# APP SETUP #
#############

RUN echo "**** copying source for dev build ****"
WORKDIR /app
RUN apk add --no-cache \
  shellcheck

COPY . .

RUN ./setup-dev.sh

########
# TEST #
########

WORKDIR /app
RUN echo "*** run lint ***" && \
  ./lint.sh

RUN echo "*** run tests ***" && \
  ./test.sh

#########
# BUILD #
#########

RUN echo "*** build and package application ***" && \
  poetry build

VOLUME /dist
VOLUME /test-results
CMD ["./build-copy-artifacts.sh"]
