.PHONY: dev test test-api test-web lint migrate seed health docker-up docker-down clean

# Development
dev: docker-up
	@echo "Starting services..."
	cd apps/api && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload &
	cd apps/web && npm run dev &
	@echo "API: http://localhost:8000  |  Web: http://localhost:3000"

# Testing
test: test-api test-web

test-api:
	cd apps/api && python -m pytest -v

test-web:
	cd apps/web && npx vitest run

# Linting
lint:
	ruff check apps/api/
	cd apps/web && npx tsc --noEmit

# Database
migrate:
	cd packages/db && alembic upgrade head

seed:
	cd packages/db && python seed.py

# Health checks
health:
	@echo "Checking API health..."
	@curl -sf http://localhost:8000/health | python3 -m json.tool || echo "API: unavailable"
	@echo ""
	@echo "Checking Web health..."
	@curl -sf http://localhost:3000/api/health | python3 -m json.tool || echo "Web: unavailable"

# Docker
docker-up:
	docker compose -f docker-compose.dev.yml up -d

docker-down:
	docker compose -f docker-compose.dev.yml down

# Cleanup
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	rm -rf apps/web/.next apps/web/node_modules
