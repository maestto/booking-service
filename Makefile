PYTHON ?= python3
PIP ?= $(PYTHON) -m pip
APP_MODULE ?= app.main:app
CELERY_APP ?= app.worker.celery_app.celery_app

.PHONY: help install dev worker migrate test lint docker-up docker-down docker-config docker-logs

help:
	@echo "Доступные команды:"
	@echo "  make install       Установить Python-зависимости"
	@echo "  make dev           Запустить FastAPI локально"
	@echo "  make worker        Запустить воркер Celery локально"
	@echo "  make migrate       Применить Alembic-миграции"
	@echo "  make test          Запустить тесты"
	@echo "  make lint          Запустить ruff-проверку"
	@echo "  make docker-up     Собрать и поднять Docker Compose стек"
	@echo "  make docker-down   Остановить Docker Compose стек"
	@echo "  make docker-config Проверить docker-compose.yml"
	@echo "  make docker-logs   Смотреть логи Docker Compose"

install:
	$(PIP) install -r requirements.txt

dev:
	uvicorn $(APP_MODULE) --reload

worker:
	celery -A $(CELERY_APP) worker --loglevel=info

migrate:
	alembic upgrade head

test:
	$(PYTHON) -m pytest

lint:
	$(PYTHON) -m ruff check app tests

docker-up:
	docker compose up --build

docker-down:
	docker compose down

docker-config:
	docker compose config

docker-logs:
	docker compose logs -f
