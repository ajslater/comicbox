SHELL := /usr/bin/env bash

# include cfg/django.mk
# include cfg/frontend.mk
include cfg/python.mk
include cfg/gha_std.mk
include cfg/ci.mk
include cfg/docker.mk
include cfg/docs.mk
include cfg/node.mk
include cfg/node_root.mk
include cfg/common.mk
include cfg/help.mk

.PHONY: all

.PHONY: calibrate
## Run the online-tagging calibration harness against tests/calibration/fixtures.json
## @category Test
calibrate:
	uv run python -m tests.calibration.run

## Re-run only the fixtures that previously failed (wrong / no-candidates / error).
## Reads tests/calibration/fixtures.outcomes.json from the last full run.
## @category Test
.PHONY: calibrate-retry
calibrate-retry:
	uv run python -m tests.calibration.run --retry-misses

## Fast iteration: previously-failed fixtures, one per series (drops the
## 19 other Conan issues that all probe the same code path).
## @category Test
.PHONY: calibrate-retry-sampled
calibrate-retry-sampled:
	uv run python -m tests.calibration.run --retry-misses --one-per-series

## Bootstrap a calibration fixtures.json from already-tagged comics.
## Use CALIBRATE_PATHS=... to override paths; defaults to a Milliways layout.
## @category Test
CALIBRATE_PATHS ?= ~/Milliways/Comics/Test ~/Milliways/Comics/full/demo
.PHONY: calibrate-bootstrap
calibrate-bootstrap:
	uv run python -m tests.calibration.bootstrap $(CALIBRATE_PATHS)

## M7 stress test: -j 8 against a directory of comics, cold cache, dry-run.
## Validates rate-limiter compliance + no exceptions under parallel load.
## Use STRESS_PATH=... and STRESS_LIMIT=... (defaults below). See tests/stress/README.md.
## @category Test
STRESS_PATH ?= ~/Milliways/Comics/Test
STRESS_LIMIT ?= 50
STRESS_JOBS ?= 8
.PHONY: stress
stress:
	uv run python -m tests.stress.run $(STRESS_PATH) --limit $(STRESS_LIMIT) --jobs $(STRESS_JOBS)

## M7 prompt-UX validation: -j 8 with always-prompt policy + recording
## selector. Verifies _PROMPT_LOCK serialises under contention.
## See tests/stress/README.md.
## @category Test
.PHONY: stress-prompt-ux
stress-prompt-ux:
	uv run python -m tests.stress.prompt_ux $(STRESS_PATH) --limit $(STRESS_LIMIT) --jobs $(STRESS_JOBS)