# Shikshya LMS — Production Deployment Guide

Two deployment options:

- **A) Docker Compose** (simpler, uses PostgreSQL in container)
- **B) VPS (Manual)** (Nginx + Gunicorn + PostgreSQL directly on host)

---

## A) Docker Compose (Recommended)

### Prerequisites
- Server with Docker Engine v20+ and Docker Compose v2+
- A domain name (e.g., `shikshya.example.com`) pointed to your server IP

### Step 1 — Install Docker

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y apt-transport-https ca-certificates curl software-properties-common
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

### Step 2 — Upload Code & Create .env

```bash
sudo mkdir -p /var/www/shikshya
sudo chown -R $USER:$USER /var/www/shikshya
cd /var/www/shikshya

# Upload your code here (git clone, scp, or rsync)
# git clone <your-repo-url> .

# Create .env file
cat > .env << 'EOF'
SECRET_KEY=$(openssl rand -hex 32)
DB_PASSWORD=choose-a-strong-password
SITE_URL=https://shikshya.example.com

# Optional: SMTP for password reset emails
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=true
MAIL_USERNAME=you@gmail.com
MAIL_PASSWORD=your-app-password
MAIL_DEFAULT_SENDER=Shikshya <you@gmail.com>

# Optional: Redis for rate limiting (remove if not using)
# RATELIMIT_STORAGE_URL=redis://redis:6379/0
EOF
```

### Step 3 — Launch

```bash
docker compose up -d --build
```

### Step 4 — Seed Database

```bash
docker compose exec web python seed.py
```

Your app is now live at `http://<server-ip>`.

### Step 5 — SSL with Let's Encrypt

```bash
docker compose down
sudo apt install -y certbot
sudo certbot certonly --standalone -d shikshya.example.com --email admin@example.com --agree-tos --no-eff-email

# Update nginx.conf — swap listen 80 to the SSL server block (see section below)
# Then restart:
docker compose up -d
```

**nginx.conf SSL block** — replace the `server` block with:

```nginx
server {
    listen 80;
    server_name shikshya.example.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name shikshya.example.com;

    ssl_certificate /etc/letsencrypt/live/shikshya.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/shikshya.example.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers on;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 1d;

    client_max_body_size 100M;

    location /static/ {
        alias /usr/share/nginx/html/static/;
        expires 30d;
        add_header Cache-Control "public, no-transform";
        access_log off;
    }

    location /uploads/ {
        alias /usr/share/nginx/html/uploads/;
        expires 7d;
        access_log off;
    }

    location / {
        proxy_pass http://web:5000;
        proxy_redirect off;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
        proxy_connect_timeout 120s;

        add_header X-Frame-Options "SAMEORIGIN" always;
        add_header X-Content-Type-Options "nosniff" always;
        add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    }
}
```

---

## B) VPS — Manual (Nginx + Gunicorn + PostgreSQL)

### Step 1 — System Dependencies

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3-pip python3-venv nginx supervisor postgresql postgresql-contrib libpq-dev
```

### Step 2 — PostgreSQL Setup

```bash
sudo -u postgres psql -c "CREATE USER shikshya WITH PASSWORD 'your_strong_password';"
sudo -u postgres psql -c "CREATE DATABASE shikshya OWNER shikshya;"
sudo -u postgres psql -c "GRANT ALL ON DATABASE shikshya TO shikshya;"
```

### Step 3 — Upload & Configure App

```bash
sudo mkdir -p /var/www/shikshya
sudo chown -R $USER:$USER /var/www/shikshya
cd /var/www/shikshya

# Upload code here (git clone / scp / rsync)

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install gunicorn psycopg2-binary

# Create .env
cat > .env << 'EOF'
SECRET_KEY=$(openssl rand -hex 32)
DATABASE_URL=postgresql://shikshya:your_strong_password@localhost:5432/shikshya
SESSION_COOKIE_SECURE=True
FLASK_ENV=production
SITE_URL=https://shikshya.example.com

# SMTP
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=true
MAIL_USERNAME=you@gmail.com
MAIL_PASSWORD=your-app-password
MAIL_DEFAULT_SENDER=Shikshya <you@gmail.com>
EOF

# Seed database
python seed.py
```

### Step 4 — Gunicorn via Supervisor

```bash
sudo nano /etc/supervisor/conf.d/shikshya.conf
```

Paste:

```ini
[program:shikshya]
command=/var/www/shikshya/venv/bin/gunicorn -w 4 -b 127.0.0.1:8000 --access-logfile - --error-logfile - app:create_app()
directory=/var/www/shikshya
user=www-data
autostart=true
autorestart=true
stderr_logfile=/var/log/shikshya/err.log
stdout_logfile=/var/log/shikshya/out.log
environment=PATH="/var/www/shikshya/venv/bin"
```

```bash
sudo mkdir -p /var/log/shikshya
sudo supervisorctl reread && sudo supervisorctl update
sudo supervisorctl start shikshya
```

### Step 5 — Nginx Reverse Proxy

```bash
sudo nano /etc/nginx/sites-available/shikshya
```

Paste:

```nginx
server {
    listen 80;
    server_name shikshya.example.com;

    client_max_body_size 50M;

    location /static/ {
        alias /var/www/shikshya/static/;
        expires 30d;
    }

    location /uploads/ {
        alias /var/www/shikshya/static/uploads/;
        expires 7d;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/shikshya /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

### Step 6 — SSL with Certbot

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d shikshya.example.com --non-interactive --agree-tos -m admin@example.com
```

---

## Management Commands

| Action | Docker | Manual VPS |
|--------|--------|------------|
| View logs | `docker compose logs -f` | `sudo supervisorctl tail -f shikshya` |
| Restart app | `docker compose restart web` | `sudo supervisorctl restart shikshya` |
| Rebuild | `docker compose up -d --build` | `sudo supervisorctl restart shikshya` |
| Enter shell | `docker compose exec web bash` | `source venv/bin/activate` |
| Backup DB | N/A (PostgreSQL data in `pgdata` volume) | `pg_dump -U shikshya shikshya > backup.sql` |

## SMTP Setup (Gmail)

1. Enable 2-Factor Authentication on your Google account
2. Go to https://myaccount.google.com/apppasswords
3. Generate an App Password for "Mail"
4. Set `MAIL_USERNAME` to your full Gmail address
5. Set `MAIL_PASSWORD` to the 16-character App Password

---

## Files Changed for Production

| File | Change |
|------|--------|
| `config.py` | Added `MAIL_*`, `SITE_URL`, `SITE_NAME` settings; PostgreSQL SSL mode |
| `routes/auth.py` | Replaced `print()` with real SMTP email sending via `utils/mail.py` |
| `utils/mail.py` | **New** — SMTP email sender with HTML template support |
| `templates/emails/password_reset.html` | **New** — branded HTML email template |
| `.env.example` | Full production env vars with all options documented |
| `requirements.txt` | Added `gunicorn`, `psycopg2-binary` |
| `docker-compose.yml` | Added PostgreSQL service; env vars for mail, site URL, rate limit |
| `nginx.conf` | Added `/uploads/` location block for uploaded files |
| `Dockerfile` | Added missing upload directories |
