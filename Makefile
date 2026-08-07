.PHONY: up up-prod down logs ps test test-int backup dev-backend dev-frontend

## Запустить всё (одна кнопка)
up:
	@test -f .env || (cp .env.example .env && echo "Создан .env из .env.example — проверьте APP_PASSWORD и SECRET_KEY")
	docker compose up -d --build
	@echo "shaprivezu: http://localhost:3000"

## Прод: то же + Caddy с HTTPS (домен и loopback-порты задаются в .env)
up-prod:
	docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

down:
	docker compose down

logs:
	docker compose logs -f --tail=100

ps:
	docker compose ps

## Unit-тесты (без БД)
test:
	cd backend && uv run pytest tests/unit -q

## Integration-тесты (поднимает временный Postgres на 5433)
test-int:
	docker compose -f docker-compose.test.yml up -d --wait
	cd backend && TEST_DATABASE_URL=postgresql://crm:crm@localhost:5433/crm_test uv run pytest tests/integration -q; \
	status=$$?; cd .. && docker compose -f docker-compose.test.yml down -v; exit $$status

## Бэкап БД в ./backups (для крона: 0 4 * * * cd <репо> && make backup)
backup:
	mkdir -p backups
	docker compose exec -T postgres pg_dump -U crm crm > backups/crm-$$(date +%Y%m%d-%H%M%S).sql
	@ls -lh backups | tail -3

dev-backend:
	cd backend && uv run uvicorn crm.main:app --reload --port 8000

dev-frontend:
	cd frontend && npm run dev
