.PHONY: install
## Install for production
## @category Install
install:
	pip install --upgrade pip
	pip install --upgrade poetry
	poetry install --no-root
	npm install

.PHONY: install-dev
## Install dev requirements
## @category Install
install-dev: install
	poetry install  --no-root --extras=dev

.PHONY: install-all
## Install all extras
## @category Install
install-all: install
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

.PHONY: lint
## Lint front and back end
## @category Lint
lint:
	./bin/lint-backend.sh

.PHONY: test
## Run Tests
## @category Test
test:
	./bin/test.sh

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
