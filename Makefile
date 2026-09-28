# 开发命令入口：所有依赖安装、构建和检查均交由 Docker 执行。
# Prefer the plugin; support standalone Compose installations automatically.
COMPOSE ?= $(shell if docker compose version >/dev/null 2>&1; then printf 'docker compose'; else printf 'docker-compose'; fi)
.PHONY: setup build up check collect logs stop test db-shell

setup:
	@test -f .env || cp .env.example .env
	@chmod 600 .env

build:
	$(COMPOSE) build migrate web

up:
	$(COMPOSE) up -d --build postgres migrate api web collector

check:
	$(COMPOSE) run --rm migrate trading check

collect:
	$(COMPOSE) up -d --build --force-recreate collector

logs:
	$(COMPOSE) logs -f collector

stop:
	$(COMPOSE) down

test:
	$(COMPOSE) --profile test run --build --rm tests

db-shell:
	$(COMPOSE) exec postgres sh -c 'psql -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"'

# The production frontend build includes lint, format and TypeScript checks.
.PHONY: frontend-check backend-check quality
frontend-check:
	$(COMPOSE) build web

backend-check: test

quality: frontend-check backend-check
