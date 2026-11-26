.PHONY: up down logs test lint format migrate makemigration seed shell

up:
	docker compose up --build

down:
	docker compose down -v

logs:
	docker compose logs -f

test:
	pytest

lint:
	ruff check .

format:
	ruff check . --fix

migrate:
	alembic upgrade head

makemigration:
	alembic revision --autogenerate -m "$(m)"

seed:
	python scripts/seed_dev.py

shell:
	docker compose exec app bash
