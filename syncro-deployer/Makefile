.PHONY: setup test test-py test-go test-ts test-java test-flutter lint build-dashboard run-api run-mcp syncro-suite run-desktop up down k8s-dev

PY := services/control-plane/.venv/bin/python
PYTEST := services/control-plane/.venv/bin/pytest
RUFF := services/control-plane/.venv/bin/ruff
MYPY := services/control-plane/.venv/bin/mypy
AEGIS := services/control-plane/.venv/bin/aegis
SYNCRO := services/control-plane/.venv/bin/syncro

setup:
	cd services/control-plane && uv venv .venv && uv pip install --python .venv/bin/python -e ".[dev]"
	cd extensions/ts-policy-webhook && npm install
	cd apps/dashboard && npm install

test: test-py test-go test-ts test-java

test-py:
	cd services/control-plane && .venv/bin/pytest -v

test-go:
	cd extensions/go-drift-scanner && go test -v ./... && go vet ./...

test-ts:
	cd extensions/ts-policy-webhook && npm run build && npm test

test-java:
	cd extensions/java-audit-bridge && mkdir -p target/classes && javac -d target/classes src/main/java/io/aegisops/audit/*.java && java -cp target/classes io.aegisops.audit.AuditBridgeApplication --self-test

test-flutter:
	cd apps/syncro-desktop && flutter pub get && flutter analyze --fatal-infos && flutter test

lint:
	cd services/control-plane && .venv/bin/ruff check src tests && .venv/bin/mypy src
	cd extensions/go-drift-scanner && go vet ./...

build-dashboard:
	cd apps/dashboard && npm run build

run-api:
	$(AEGIS) server --host 127.0.0.1 --port 8080

run-mcp:
	$(AEGIS) mcp serve --transport stdio

syncro-suite:
	$(SYNCRO) syncro suite

run-desktop:
	cd apps/syncro-desktop && ([ -d linux ] || flutter create . --platforms=linux,macos,windows) && flutter pub get && flutter run -d linux --dart-define=SYNCRO_API_URL=http://127.0.0.1:8080

up:
	docker compose up --build

down:
	docker compose down -v

k8s-dev:
	kubectl apply -k deploy/k8s/overlays/dev
