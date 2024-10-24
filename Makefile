.PHONY: install-deps
## Update pip and install poetry and npm packages
## @category Install
install-deps:
	pip install --upgrade pip
	pip install --upgrade poetry
	npm install

.PHONY: install
## Install for production
## @category Install
install: install-deps
	poetry install --no-root

.PHONY: install-dev
## Install dev requirements
## @category Install
install-dev: install-deps
	poetry install --no-root --extras dev

.PHONY: install-all
## Install all extras
## @category Install
install-all: install-deps
	poetry install --no-root --all-extras

.PHONY: clean
## Clean pycaches
## @category Build
clean:
	 ./bin/clean-pycache.sh

.PHONY: build
## Build package
## @category Build
build:
	poetry build

.PHONY: publish
## Publish package to pypi
## @category Deploy
publish:
	poetry publish

.PHONY: update
## Update dependencies
## @category Update
update:
	./bin/update-deps.sh

## version
## @category Update
V :=
.PHONY: version
## Show or set project version
## @category Update
version:
	bin/version.sh $(V)

.PHONY: kill-eslint_d
## Kill eslint daemon
## @category Lint
kill-eslint_d:
	bin/kill-eslint_d.sh

.PHONY: fix
## Fix front and back end lint errors
## @category Lint
fix:
	./bin/fix-lint-backend.sh

.PHONY: lint-schemas
## Lint schemas
## @category Lint
lint-schemas:
	./bin/lint-schemas.sh

.PHONY: lint
## Lint
## @category Lint
lint: lint-schemas
	./bin/lint-backend.sh

## test
## @category Test
T :=
.PHONY: test
## Run Tests
## @category Test
test:
	./bin/test.sh $(T)

.PHONY: test-docker
## Run Tests
## @category Test
test-docker:
	./bin/test-docker.sh

.PHONY: news
## Show recent NEWS
## @category Deploy
news:
	head -40 NEWS.md

.PHONY: all

include bin/makefile-help.mk
