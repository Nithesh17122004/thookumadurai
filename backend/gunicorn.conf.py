# Gunicorn Configuration — Thooku Madurai Backend
bind = "0.0.0.0:8000"
workers = 4                  # 2 × CPU cores + 1 (Render Starter: 2 vCPU)
worker_class = "gevent"     # Async for high concurrency
worker_connections = 1000
timeout = 120
keepalive = 5
max_requests = 1000
max_requests_jitter = 100
preload_app = True
loglevel = "info"
accesslog = "-"
errorlog = "-"
