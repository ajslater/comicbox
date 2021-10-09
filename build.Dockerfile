FROM ajslater/codex-builder:hirsute_2.0.1

ARG DEBIAN_FRONTEND=noninteractive

#############
# APP SETUP #
#############

RUN echo "**** copying source for dev build ****"
WORKDIR /app
COPY . .

RUN ./setup-dev.sh

########
# TEST #
########

WORKDIR /app
RUN echo "*** run lint ***"
RUN ./lint.sh

RUN echo "*** run tests ***"
RUN ./test.sh

#########
# BUILD #
#########

RUN echo "*** build and package application ***" && \
  poetry build

VOLUME /dist
VOLUME /test-results
CMD ["./build-copy-artifacts.sh"]
