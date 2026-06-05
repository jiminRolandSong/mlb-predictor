web: uvicorn app.main:app --host 0.0.0.0 --port $PORT
worker: celery -A app.core.celery_app.celery worker --loglevel=info --concurrency=2
beat: celery -A app.core.celery_app.celery beat --loglevel=info
