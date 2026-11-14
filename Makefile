.PHONY: up down logs single test dev reset
up:      ## full stack (Postgres + API + UI) at http://localhost:3000
	docker compose up --build -d
down:
	docker compose down
logs:
	docker compose logs -f
single:  ## the single-container image used for free hosting, at http://localhost:8080
	docker build -t aml-copilot . && docker run --rm -p 8080:8080 -v aml-data:/data aml-copilot
test:
	cd backend && python -m pytest -q
dev:     ## no Docker
	./setup.sh --local
reset:   ## wipe the DB volume and rebuild demo data
	docker compose down -v && docker compose up --build -d
