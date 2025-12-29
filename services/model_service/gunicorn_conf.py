import os

from prometheus_client import multiprocess


def child_exit(server, worker):
    multiprocess.mark_process_dead(worker.pid)


bind = "0.0.0.0:8000"
worker_class = "uvicorn.workers.UvicornWorker"
workers = os.getenv("WEB_CONCURRENCY", "2")
timeout = os.getenv("GUNICORN_TIMEOUT", "30")
graceful_timeout = 10
keepalive = 5
