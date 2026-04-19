.PHONY: test-integration run

run:
	source .venv/bin/activate && uvicorn main:app --host 127.0.0.1 --port 8000 --reload

test-integration:
	source .venv/bin/activate && python -m unittest discover -s tests -p 'test_*.py' -v
