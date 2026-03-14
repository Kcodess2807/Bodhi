.PHONY: run cli dev

run:
	uvicorn src.api.app:app --reload --host 0.0.0.0 --port 8000 --reload-exclude client

cli:
	python -m src.main

dev:
	cd client && npm run dev
