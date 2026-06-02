import os

# Only 1 worker for 512MB RAM (Render free tier)
workers = 1
worker_class = "sync"
threads = 1

bind = f"0.0.0.0:{os.environ.get('PORT', '5000')}"

timeout = 120
max_requests = 200
max_requests_jitter = 50

accesslog = "-"
errorlog = "-"
loglevel = "info"

limit_request_line = 4094
limit_request_fields = 100
limit_request_field_size = 8190

proc_name = "shikshya_lms"
