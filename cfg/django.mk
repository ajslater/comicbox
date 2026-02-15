.PHONY: fix
## Fix django lint errors
## @category Fix
fix::
	 uv run --group lint djlint --reformat **/templates/**/*.html

.PHONY: lint
## Fix django lint errors
## @category Lint
lint::
	 uv run --group lint djlint --lint **/templates/**/*.html

.PHONY: dev-server
## Run the dev webserver
## @category Serve
dev-server:
	./bin/dev-server.sh


