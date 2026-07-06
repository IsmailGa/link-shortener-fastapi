import multiprocessing
import os

# Worker configuration
cores = multiprocessing.cpu_count()
web_concurrency = os.getenv("WEB_CONCURRENCY")
if web_concurrency and web_concurrency.strip():
    workers = int(web_concurrency)
else:
    workers = (2 * cores) + 1
worker_class = "uvicorn.workers.UvicornWorker"

# Binding
bind = os.getenv("BIND", "0.0.0.0:8000")

# Performance
preload_app = True
max_requests = 2000
max_requests_jitter = 200

# Timeouts
timeout = 60
graceful_timeout = 30
keepalive = 5

# Logging
accesslog = "-"
errorlog = "-"
loglevel = os.getenv("LOG_LEVEL", "info")
