# Contributing
* Backend: `cd backend && pip install -r requirements.txt && python -m pytest -q` (SQLite by default; set `DATABASE_URL` for Postgres).
* Frontend: `cd frontend && npm install && npx tsc --noEmit && npm run build`.
* After changing `backend/app/models.py`, regenerate `sql/schema.sql`: `python backend/scripts/dump_schema.py`.
* Agents must stay deterministic and explainable; the LLM layer may only write narrative text.
* Add a test for every new permission or four-eyes rule.
