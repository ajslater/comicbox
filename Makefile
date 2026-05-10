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

## Bootstrap a calibration fixtures.json from already-tagged comics.
## Use CALIBRATE_PATHS=... to override paths; defaults to a Milliways layout.
## @category Test
CALIBRATE_PATHS ?= ~/Milliways/Comics/Test ~/Milliways/Comics/full/demo
.PHONY: calibrate-bootstrap
calibrate-bootstrap:
	uv run python -m tests.calibration.bootstrap $(CALIBRATE_PATHS)