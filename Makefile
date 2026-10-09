.PHONY: up down logs test test-backend build
up:
	docker compose up --build -d
down:
	docker compose down
logs:
	docker compose logs -f --tail=100
test: test-backend

test-backend:
	cd backend && python -m pytest -q
build:
	docker compose build
