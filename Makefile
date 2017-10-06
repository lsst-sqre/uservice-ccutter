.PHONY: help server worker flower run

help:
	@echo "Run these commands in separate shells:"
	@echo "  make redis  (start a Redis Docker container)"
	@echo "  make server (start the Flask app)"
	@echo "  make worker (start a Celery worker)"
	@echo "  make flower (start the Flower task monitor)"
	@echo "  run         (send a test request)"

redis:
	docker run --rm --name redis-dev -p 6379:6379 redis

server:
	source "./test.credentials.sh"; DEBUG=1 FLASK_APP=uservice_ccutter:flask_app flask run

worker:
	source "./test.credentials.sh"; celery -A uservice_ccutter.celery_app -E -l DEBUG worker

flower:
	celery -A uservice_ccutter.celery_app flower

run:
	source "./test.credentials.sh"; ./test.sh
