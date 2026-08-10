# Deployment guide — 10.10.9.227 (Linux, systemd, nginx)

This guide deploys the Router Troubleshooting RAG app to an internal Linux
server reachable at `ssh abhishek@10.10.9.227`, keeps the FastAPI backend
running as a `systemd` service, builds the React/Vite frontend as static
files, and serves everything through a single `nginx` entry point on port 80.

> **Security note:** per the [README](README.md#current-limitations-and-production-guidance),
> this application has **no authentication** and must not be exposed to the
> public internet. `10.10.9.227` looks like an internal/private address —
> confirm the server's firewall only allows access from your internal
> network before going further (see [Step 8](#8-restrict-network-access)).

## Table of contents

1. [Prerequisites on the server](#1-prerequisites-on-the-server)
2. [Transfer the code](#2-transfer-the-code)
3. [Backend: Python environment](#3-backend-python-environment)
4. [Backend: configure .env](#4-backend-configure-env)
5. [Backend: systemd service](#5-backend-systemd-service)
6. [Frontend: production build](#6-frontend-production-build)
7. [nginx: single entry point](#7-nginx-single-entry-point)
8. [Restrict network access](#8-restrict-network-access)
9. [Verify the deployment](#9-verify-the-deployment)
10. [Redeploying updates](#10-redeploying-updates)
11. [Useful operational commands](#11-useful-operational-commands)

---

## 1. Prerequisites on the server

SSH in and install system dependencies:

```bash
ssh abhishek@10.10.9.227

sudo apt update
sudo apt install -y python3.11 python3.11-venv python3-pip git nginx

# Node.js 20.x (NodeSource)
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
```

Verify:

```bash
python3.11 --version   # 3.11.x or newer
node --version          # v20.x or newer
nginx -v
```

Decide where the app will live, e.g.:

```bash
sudo mkdir -p /opt/troubleshooter-guide
sudo chown "$USER":"$USER" /opt/troubleshooter-guide
```

## 2. Transfer the code

From your Windows machine, either `git clone` on the server (if the repo is
in a remote you both can reach) or `rsync`/`scp` the working tree over. The
`.env` file and `backend/data/` (SQLite + Chroma + uploads) are gitignored,
so a plain `git clone` will **not** bring your local API keys or existing
indexed documents — copy those separately if you want to carry them over.

**Option A — git clone on the server** (recommended if you have a remote):

```bash
# on the server
cd /opt/troubleshooter-guide
git clone <your-remote-url> .
```

**Option B — copy the working tree directly from Windows** (PowerShell, run
from the repo root; excludes local venv/build artifacts):

```powershell
rsync -avz --exclude '.venv' --exclude 'node_modules' --exclude 'frontend/dist' `
  --exclude '.git' --exclude '__pycache__' `
  . abhishek@10.10.9.227:/opt/troubleshooter-guide/
```

(If `rsync` isn't available on Windows, use `scp -r .\ abhishek@10.10.9.227:/opt/troubleshooter-guide/`
instead, then clean up excluded folders manually on the server.)

Carry over existing runtime data and secrets, if you want the server to start
with what you already have locally:

```powershell
scp .\.env abhishek@10.10.9.227:/opt/troubleshooter-guide/.env
scp -r .\backend\data abhishek@10.10.9.227:/opt/troubleshooter-guide/backend/data
```

> Your local `.env` currently points at your personal OpenRouter key and
> model. Decide whether the server should reuse that same key or use its own
> before copying it over — see [Step 4](#4-backend-configure-env).

## 3. Backend: Python environment

On the server, from `/opt/troubleshooter-guide`:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r backend/requirements.txt
```

Confirm the venv is active:

```bash
python -c "import sys; print(sys.executable)"
# should print /opt/troubleshooter-guide/.venv/bin/python
```

## 4. Backend: configure .env

If you didn't copy `.env` over in Step 2, create one now:

```bash
cp .env.example .env
nano .env
```

Set at minimum:

```dotenv
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=<your-key>
OPENROUTER_MODEL=<your-model-slug>

# Must be reachable from wherever the browser loads the UI:
FRONTEND_ORIGINS=http://10.10.9.227
```

`DATA_DIR=backend/data` is relative to the **process working directory**, so
the systemd service in the next step must set `WorkingDirectory` to the repo
root — never start uvicorn from inside `backend/`.

## 5. Backend: systemd service

Create `/etc/systemd/system/troubleshooter-backend.service`:

```ini
[Unit]
Description=Router Troubleshooter RAG - FastAPI backend
After=network.target

[Service]
Type=simple
User=abhishek
WorkingDirectory=/opt/troubleshooter-guide
Environment=PATH=/opt/troubleshooter-guide/.venv/bin
ExecStart=/opt/troubleshooter-guide/.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --app-dir backend
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
```

Notes:

- `--host 127.0.0.1` deliberately binds the backend to localhost only —
  nginx is the only thing that talks to it directly (Step 7).
- No `--reload` in production.

Enable and start it:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now troubleshooter-backend
sudo systemctl status troubleshooter-backend
```

Check the health endpoint locally on the server:

```bash
curl http://127.0.0.1:8000/api/health
```

## 6. Frontend: production build

Still on the server:

```bash
cd /opt/troubleshooter-guide/frontend
npm install
npm run build
```

This produces static files in `frontend/dist/`, which nginx will serve
directly (no Node process needs to stay running for the frontend).

## 7. nginx: single entry point

Create `/etc/nginx/sites-available/troubleshooter-guide`:

```nginx
server {
    listen 80;
    server_name 10.10.9.227;

    root /opt/troubleshooter-guide/frontend/dist;
    index index.html;

    # React SPA: let client-side routing handle unknown paths
    location / {
        try_files $uri $uri/ /index.html;
    }

    # Proxy API calls to the FastAPI backend
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # PDF uploads can be large; match MAX_UPLOAD_MB from .env
        client_max_body_size 30m;
    }
}
```

Enable the site and reload nginx:

```bash
sudo ln -s /etc/nginx/sites-available/troubleshooter-guide /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default   # optional: stop nginx's default page from responding
sudo nginx -t
sudo systemctl reload nginx
```

## 8. Restrict network access

This app has no login and must stay off the open internet. If the server
has a public interface as well as the internal one, lock nginx/UFW down to
your internal network/VPN range, e.g.:

```bash
sudo ufw allow from 10.10.9.0/24 to any port 80 proto tcp
sudo ufw enable
sudo ufw status
```

Adjust `10.10.9.0/24` to your actual internal subnet.

## 9. Verify the deployment

From your own machine (not the server):

```powershell
Invoke-RestMethod http://10.10.9.227/api/health
```

Expected:

```json
{
  "status": "ok",
  "database": true,
  "vector_store": true,
  "embedding_model": true,
  "llm_provider": "openrouter",
  "llm_configured": true,
  "llm_available": true
}
```

Then open `http://10.10.9.227` in a browser and confirm the chat UI loads,
you can upload a PDF, and you can ask a question.

## 10. Redeploying updates

After pulling/copying new code to `/opt/troubleshooter-guide`:

```bash
cd /opt/troubleshooter-guide

# backend changes
source .venv/bin/activate
pip install -r backend/requirements.txt
sudo systemctl restart troubleshooter-backend

# frontend changes
cd frontend
npm install
npm run build   # nginx serves the new dist/ immediately, no restart needed
```

## 11. Useful operational commands

```bash
# Backend logs (follow)
sudo journalctl -u troubleshooter-backend -f

# Backend status / restart / stop
sudo systemctl status troubleshooter-backend
sudo systemctl restart troubleshooter-backend
sudo systemctl stop troubleshooter-backend

# nginx logs
sudo tail -f /var/log/nginx/access.log /var/log/nginx/error.log

# Confirm nginx config is valid before reloading
sudo nginx -t
```

For application-level troubleshooting (Ollama/OpenRouter errors, stuck
enrichment jobs, `requires_ocr`, etc.), see the
[Troubleshooting section of the README](README.md#troubleshooting). 
