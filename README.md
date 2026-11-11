<p align="center"><img src="img/logo.png" alt="SignalNova" width="300"></p>
<h1 align="center">SignalNova website</h1>
<p align="center">One-page product site with a gated whitepaper: visitors confirm their e-mail address with a code, then download the PDF.</p>

---

## What it does

1. The visitor enters name, work e-mail and consent.
2. The server stores the request and e-mails a 6-digit code (valid 15 minutes, single use, 5 attempts).
3. With the right code the address is marked verified and the page shows a download button. The same link is e-mailed (valid 72 hours, max 10 downloads).
4. The PDF is never at a public URL. It is only served through a valid link, and every download is recorded.

## Same stack, same workflow as LivingLab

This site is built and run exactly like the LivingLab platform. If you know how to deploy a LivingLab change, you know how to deploy this one.

| | LivingLab | SignalNova website |
|---|---|---|
| Code | `binckhaven-living-lab` on GitHub | `signalnova-website` on GitHub (own repo) |
| Backend | FastAPI + uvicorn + psycopg2 | same |
| Front end | Plain HTML/CSS/JS, no build step | same |
| Server | EC2 `binckhaven-server` | **same machine**, own folder `~/signalnova-website` |
| Service | `binckhaven-api` on `127.0.0.1:8000` | `signalnova-web` on `127.0.0.1:8001` |
| Database | RDS `binckhaven-db`, database `binckhaven` | **same RDS instance**, own database and user `signalnova` |
| Web traffic | Cloudflare Tunnel `binckhaven` | **same tunnel**, extra public hostname for your domain |
| E-mail | SMTP (Gmail) | SMTP (Brevo or Gmail) |
| Config | `.env` + `.env.example` | same |
| Deploy | commit → push → SSH → `git pull` → restart | same, restart `signalnova-web` |

**Extra running cost: €0.** EC2, RDS and Cloudflare are already paid for or free. Only the domain itself costs money, and you already have it.

The two sites share a machine but nothing else: separate folders, services, ports, databases, database users, `.env` files and hostnames. Restarting or breaking one does not touch the other. What they do share: a server reboot or an RDS outage takes both down, and both draw on the same 2 GB of memory (the website uses about 60 MB).

## Documentation

| Document | Use it when |
|---|---|
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Putting the site live for the first time (the weekend plan) |
| [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) | Changing the site: local setup, testing, deploying an update |
| [docs/RUNBOOK.md](docs/RUNBOOK.md) | Running it: health checks, problems, the leads, privacy requests |

## Quick start (local)

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env               # set DB_* and APP_SECRET; leave SMTP_HOST empty
createdb signalnova && psql -d signalnova -f init_db.sql
cp ~/path/to/whitepaper.pdf private/whitepaper.pdf
python3 app.py                     # http://localhost:8001 (codes are printed in the terminal)
```

Details in [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md).

## Repository layout

```
app.py            FastAPI app: pages, /api/send-code, /api/verify-code, /download/{token}, /health
mailer.py         SMTP sending + e-mail templates (code, download link)
manage.py         stats / export / delete / purge
init_db.sql       database schema (idempotent, safe to re-run)
index.html        the website
privacy.html      privacy notice (fill in the placeholders before launch)
css/ js/ img/ fonts/
private/          the whitepaper PDF (git-ignored, copied to the server by hand)
deploy/           systemd unit
docs/             deployment, development, runbook
.env.example      every configuration variable
```
