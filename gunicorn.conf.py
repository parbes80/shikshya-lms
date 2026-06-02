# ==============================================================================
# Shikshya LMS - Gunicorn Production Configuration
# ==============================================================================
import multiprocessing

import os

# Network sockets binding (Render sets $PORT, fallback 5000 for Docker Compose)
bind = f"0.0.0.0:{os.environ.get('PORT', '5000')}"

# Performance tuning
# Formula: (2 x num_cores) + 1
workers = multiprocessing.cpu_count() * 2 + 1
threads = 2

# Worker process classes
worker_class = "gthread"

# Connection timeout (seconds)
# Higher timeout is recommended for slower network file uploads
timeout = 120

# Logging parameters
accesslog = "-"  # Log access records to stdout
errorlog = "-"   # Log errors to stderr
loglevel = "info"

# Security and system resource management
limit_request_line = 4094
limit_request_fields = 100
limit_request_field_size = 8190

# Process naming
proc_name = "shikshya_lms"
