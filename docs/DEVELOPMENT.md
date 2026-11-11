# Development

How to work on the site locally and get changes to production. It is the same workflow as LivingLab ([LivingLab DEVELOPMENT.md](../../binckhaven-living-lab/docs/DEVELOPMENT.md)), with one difference: you never copy production data to your laptop (§5).

## 1. The workflow in one picture

```
 change + test locally (§3, §4)  →  commit + push to GitHub
      →  SSH / VS Code Remote-SSH into EC2  →  cd ~/signalnova-website && git pull
      →  sudo systemctl restart signalnova-web  →  check /health and the site
```

- Production changes only through `git pull` (code) or `init_db.sql` (schema). Nothing is edited by hand on the server, except `.env` and the PDF.
- A SignalNova deploy restarts **only** `signalnova-web`. Never restart `binckhaven-api` for it, and the other way round.

## 2. One-time local setup

You need Python 3 and a local PostgreSQL. On the Mac:

```bash
brew install postgresql@18 && brew services start postgresql@18
echo 'export PATH="/opt/homebrew/opt/postgresql@18/bin:$PATH"' >> ~/.zshrc && source ~/.zshrc
```

Then:

```bash
cd ~/Sparvix/signalnova-website
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
#   DB_HOST=localhost  DB_NAME=signalnova  DB_USER=<your mac username>  DB_PASSWORD=
#   APP_SECRET → python3 -c "import secrets; print(secrets.token_urlsafe(48))"
#   SITE_URL=http://localhost:8001
#   SMTP_HOST=      ← empty: e-mails are printed in the terminal instead of sent

createdb signalnova
psql -d signalnova -f init_db.sql
cp ~/path/to/whitepaper.pdf private/whitepaper.pdf     # any PDF works for testing
```

## 3. Run it locally

```bash
source venv/bin/activate
python3 app.py           # http://localhost:8001, reloads on code changes
```

Always open the site through `http://localhost:8001`, not the HTML file from disk; the form calls the API on the same origin.

With `SMTP_HOST` empty, the code appears in the terminal:

```
WARNING signalnova.mail: SMTP_HOST not set — e-mail NOT sent (console mode)
To: you@example.com
Subject: 123456 is your SignalNova verification code
```

To test real e-mail locally, put the Brevo settings in your local `.env` and send only to your own addresses.

## 4. What to test before you push

| Change | Test |
|---|---|
| Text or layout | Page in all three themes (SignalNova, Light, Dark; the half-circle icon in the nav), desktop and a phone-width window (≤ 390 px), no horizontal scrolling |
| Form or `site.js` | Whole flow: wrong code → right code → download. "Use another e-mail" and "Send a new code" |
| Tuning range | Drag the window with mouse and finger (phone), tap the bar to jump, arrow keys on the focused window; the "Drag to tune" hint disappears after the first move |
| `app.py` / `mailer.py` | Whole flow, plus `/health`, plus an expired link (`/download/x`) |
| `init_db.sql` | Run it twice on your local database (it must be idempotent) |
| Anything | Browser console has no errors. A red CSP error means something inline or from another site; move it into `css/` or `js/` |

**Content-Security-Policy:** the pages allow scripts, styles and fonts from the site itself only. No inline `<script>`, no `style="…"` attributes, no Google Fonts or CDNs. That is deliberate (security, and no visitor data to third parties). The policy is in `app.py` (`CSP`).

**Cache busting:** when you change `css/site.css` or a file in `js/`, raise the `?v=` number on the links in `index.html`, `privacy.html` and `EXPIRED_PAGE` in `app.py`.

## 5. Data: never copy production to your laptop

Unlike LivingLab's sensor data, the database here is **personal data** (names, e-mail addresses, IPs). There is no sync script on purpose. Test with your own addresses on your local database. To look at production, use `manage.py` on the server ([RUNBOOK.md §5](RUNBOOK.md#5-the-leads)).

## 6. Deploy a change

```bash
# laptop
git add -A && git commit -m "…" && git push

# server
ssh -i ~/.ssh/binckhaven-key.pem ubuntu@<elastic-ip>
cd ~/signalnova-website && git pull
source venv/bin/activate
pip install -r requirements.txt                                        # only if requirements.txt changed
psql -h <rds-endpoint> -U signalnova -d signalnova -f init_db.sql      # only if init_db.sql changed
sudo systemctl restart signalnova-web
curl -s 127.0.0.1:8001/health
```

Then open `https://<domain>` and try the part you changed.

**Rolling back:** `git log --oneline -5`, then `git checkout <previous-commit> -- .` and restart, or `git revert <commit>` on your laptop and deploy again.

## 7. Where things are

| To change | Edit |
|---|---|
| Page text, sections | `index.html` |
| Colours, fonts, layout | `css/site.css`: one token block per theme at the top (SignalNova is the default `:root`, then `[data-theme="light"]` and `[data-theme="dark"]`). A new colour must be added to all three |
| Default theme | `js/theme.js` (also the browser bar colours, which `site.js` repeats in `BAR`) |
| Tuning range, form behaviour | `js/site.js` (market ranges in `markets`, keep them in sync with the ranges in `index.html`; window limits `LO`/`HI`) |
| E-mail wording and layout | `mailer.py` (`code_email`, `link_email`) |
| Limits, link validity | `.env` (see `.env.example`); no code change needed |
| Consent wording | `index.html` **and** `CONSENT_TEXT` in `app.py`; they must match, because the server stores the text as proof |
| Privacy notice | `privacy.html` |
| Logo | `img/logo.png` (light) and `img/logo-dark.png` (dark); icons `img/favicon.svg`, `img/icon-*.png` |
