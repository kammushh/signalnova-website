# Deployment guide

One-time setup that puts the SignalNova website live on your own domain, on the **existing LivingLab server**. Work through it top to bottom; each part ends with a check, so do not move on until the check passes. Everyday changes after go-live are in [DEVELOPMENT.md](DEVELOPMENT.md); running it is in [RUNBOOK.md](RUNBOOK.md).

Throughout, **`<domain>`** is your domain (for example `signalnova.com`). Other values in `<angle brackets>` are specific to your environment. Put them in the password manager, never in this repository.

```
                                    EC2 binckhaven-server
visitor ─► Cloudflare (<domain>) ══ tunnel "binckhaven" ══► cloudflared ─┬─► 127.0.0.1:8000  binckhaven-api   (LivingLab, unchanged)
                                                                         └─► 127.0.0.1:8001  signalnova-web ─┬─► RDS: database signalnova
                                                                                                             └─► SMTP (Brevo) ─► visitor
```

## Time plan

| Part | What | Time | Where |
|---|---|---|---|
| 0 | Gather what you need | 15 min | — |
| 1 | **Move the domain's DNS to Cloudflare (do this first: it can take hours to go live)** | 20 min + waiting | Registrar, Cloudflare |
| 2 | GitHub repository | 10 min | Laptop |
| 3 | Run it locally once | 20 min | Laptop |
| 4 | Database | 10 min | Server |
| 5 | Code, configuration, whitepaper, service | 30 min | Server |
| 6 | Hostname on the tunnel | 15 min | Cloudflare |
| 7 | E-mail (sending and receiving) | 45 min | Brevo, Cloudflare |
| 8 | Fill in the legal text | 20 min | Laptop |
| 9 | Go-live test | 15 min | Phone and laptop |

Total: about half a day, plus DNS waiting time. Do part 1 on Saturday morning, then parts 2–5 while it propagates.

## 0. Before you start

| You need | Where from |
|---|---|
| Login for the registrar where `<domain>` is registered | You |
| Cloudflare account (the one that already has `dream360.net`) | You |
| SSH access to the server: `ssh -i ~/.ssh/binckhaven-key.pem ubuntu@<elastic-ip>` from an allow-listed IP | LivingLab [Runbook §5](../../binckhaven-living-lab/docs/RUNBOOK.md) if your IP changed |
| RDS master credentials (the `DB_*` values in LivingLab's `.env` on the server) | Password manager |
| The whitepaper PDF | You |
| Company details for the privacy notice: registered address, KvK number, a privacy contact address | You |

## 1. Domain on Cloudflare

Skip this part if `<domain>` is already in your Cloudflare account and shows **Active**.

1. Cloudflare → **Add a domain** → `<domain>` → **Free** plan.
2. Cloudflare imports the existing DNS records. Compare them with the registrar's DNS page line by line. Keep anything for **e-mail** (`MX`, `TXT`) if you already receive mail on this domain. Delete any old `A`/`CNAME` record for `<domain>` and `www`; the tunnel creates its own in part 6.
3. At the registrar: turn **DNSSEC off**, then replace the nameservers with the two Cloudflare shows.
4. Wait for Cloudflare's e-mail "<domain> is now active", usually 10 minutes to a few hours.
5. Then: **SSL/TLS → Overview → Full**, and **SSL/TLS → Edge Certificates → Always Use HTTPS: on**. You can turn DNSSEC back on from Cloudflare (DNS → Settings) and add the DS record at the registrar.

**Check:** the domain shows **Active** in Cloudflare.

## 2. GitHub repository

On your laptop:

```bash
cd ~/Sparvix/signalnova-website
git add -A && git status        # private/ must show only .gitkeep; no .env
git commit -m "SignalNova website"
```

On GitHub create a **private** repository `signalnova-website` (no README, no .gitignore), then:

```bash
git remote add origin git@github.com:kammushh/signalnova-website.git
git push -u origin main
```

**Check:** the repository on GitHub has no `.env` and no PDF.

## 3. Run it locally once

Follow [DEVELOPMENT.md §2–3](DEVELOPMENT.md#2-one-time-local-setup). Go through the whole flow in the browser with the code from the terminal.

**Check:** you can download the PDF locally.

## 4. Database

SSH into the server. Use the RDS endpoint and master user from LivingLab's `.env`:

```bash
ssh -i ~/.ssh/binckhaven-key.pem ubuntu@<elastic-ip>
grep -E '^DB_(HOST|USER)=' ~/binckhaven-living-lab/.env       # endpoint and master user
python3 -c "import secrets; print(secrets.token_urlsafe(24))" # → password for the new role; save it

psql -h <rds-endpoint> -U <master-user> -d postgres
```

```sql
CREATE ROLE signalnova LOGIN PASSWORD '<new password>';
CREATE DATABASE signalnova OWNER signalnova;
REVOKE CONNECT ON DATABASE signalnova FROM PUBLIC;
\q
```

The schema is created in part 5 once the code is on the server.

Why a separate role: the website's credentials cannot read LivingLab data, and the other way round. RDS automated backups already include the new database.

**Check:** `psql -h <rds-endpoint> -U signalnova -d signalnova -c "select 1"` works with the new password.

## 5. Code, configuration, whitepaper, service

### 5.1 Deploy key

The server's existing key is already a deploy key on the LivingLab repository, and GitHub allows a key on only one repository. Create a second one:

```bash
ssh-keygen -t ed25519 -C "signalnova-ec2-deploy" -f ~/.ssh/id_signalnova -N ""
cat >> ~/.ssh/config <<'EOF'

Host github-signalnova
  HostName github.com
  User git
  IdentityFile ~/.ssh/id_signalnova
  IdentitiesOnly yes
EOF
cat ~/.ssh/id_signalnova.pub
```

GitHub → `signalnova-website` → **Settings → Deploy keys → Add deploy key**, paste it, *Allow write access* **unchecked**.

### 5.2 Code

```bash
cd ~
git clone github-signalnova:kammushh/signalnova-website.git
cd signalnova-website
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
psql -h <rds-endpoint> -U signalnova -d signalnova -f init_db.sql
```

### 5.3 Configuration

```bash
cp .env.example .env && chmod 600 .env
python3 -c "import secrets; print(secrets.token_urlsafe(48))"     # → APP_SECRET
nano .env
```

| Variable | Value |
|---|---|
| `SITE_URL` | `https://<domain>` (no trailing slash) |
| `APP_SECRET` | the generated value |
| `DB_HOST` | RDS endpoint |
| `DB_NAME`, `DB_USER` | `signalnova` |
| `DB_PASSWORD` | the password from part 4 |
| `SMTP_HOST` | **leave empty for now**; part 7 fills in the `SMTP_*` settings |

### 5.4 Whitepaper

From your **laptop**:

```bash
scp -i ~/.ssh/binckhaven-key.pem whitepaper.pdf ubuntu@<elastic-ip>:~/signalnova-website/private/whitepaper.pdf
```

The PDF is not in Git. Keep the master copy somewhere safe (it is not in any backup on the server side).

### 5.5 Service

```bash
cd ~/signalnova-website
sudo cp deploy/signalnova-web.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now signalnova-web
systemctl status signalnova-web
curl -s 127.0.0.1:8001/health
```

Expected: `{"status":"ok","database":"ok","mail":"console","whitepaper":"ok"}`. `mail` changes to `smtp` after part 7.

Add the log to LivingLab's logrotate file so it does not grow forever:

```bash
sudo nano /etc/logrotate.d/binckhaven
# change the first line to cover both folders:
# /home/ubuntu/binckhaven-living-lab/logs/*.log /home/ubuntu/signalnova-website/logs/*.log {
sudo logrotate -d /etc/logrotate.d/binckhaven     # dry run, no errors
```

Daily clean-up of old codes and unverified addresses (`crontab -e`):

```
15 3 * * * cd /home/ubuntu/signalnova-website && venv/bin/python manage.py purge >> logs/purge.log 2>&1
```

**Check:** `/health` as above, and LivingLab still answers: `curl -s 127.0.0.1:8000/health`.

## 6. Hostname on the tunnel

Use the existing tunnel `binckhaven`. Nothing changes on the server.

1. Cloudflare → **Zero Trust → Networks → Tunnels → binckhaven → Public hostname → Add a public hostname**:
   subdomain *empty*, domain `<domain>`, path *empty*, type `HTTP`, URL `localhost:8001`.
2. Add a second one for `www`: subdomain `www`, domain `<domain>`, `HTTP`, `localhost:8001`.
3. Send `www` to the bare domain: Cloudflare → `<domain>` → **Rules → Redirect Rules → Create rule** → *Redirect from WWW to root* template (301, keep the path).
4. **Caching → Cache Rules → Create rule:** hostname equals `<domain>` → **Bypass cache**, the same as LivingLab. Without it Cloudflare may serve old CSS/JS after a deploy.
5. If **Bot Fight Mode** is on for this domain, leave it on. The form works with it.

**Check:** `https://<domain>/health` shows the JSON from part 5, `https://www.<domain>` lands on `https://<domain>`, and the page loads on your phone over mobile data.

## 7. E-mail

With your own domain the best free set-up is:

- **Sending** the codes and links through **Brevo** (free: 300 e-mails a day, from `no-reply@<domain>`). Mail from your own domain with DKIM lands in spam far less often than Gmail.
- **Receiving** at `privacy@<domain>` and `hello@<domain>` through **Cloudflare Email Routing** (free), forwarded to your own inbox. The privacy notice needs a working contact address, and people will reply to the e-mails.

Prefer Gmail? Use the Gmail block in `.env.example` instead of 7.2; it works, but mail comes from a `@gmail.com` address.

### 7.1 Receiving: Cloudflare Email Routing

1. Cloudflare → `<domain>` → **Email → Email Routing → Get started**.
2. Add destination address: your own inbox. Confirm the e-mail Cloudflare sends.
3. Custom addresses: `privacy@<domain>` → your inbox, `hello@<domain>` → your inbox.
4. Let Cloudflare add its `MX` and `TXT` (SPF) records.

### 7.2 Sending: Brevo

1. Sign up at brevo.com (free plan).
2. **Senders, Domains & Dedicated IPs → Domains → Add a domain** → `<domain>`. Brevo shows DNS records (a `brevo-code` TXT, DKIM records, and DMARC). Add each one in Cloudflare → DNS exactly as shown, with **proxy off** (grey cloud) for any CNAME.
3. **SPF: one record only.** Email Routing already created `v=spf1 include:_spf.mx.cloudflare.net ~all`. Do not add a second SPF record; edit that one to:
   ```
   v=spf1 include:_spf.mx.cloudflare.net include:spf.brevo.com ~all
   ```
4. If Brevo did not ask for DMARC, add it yourself: TXT `_dmarc` → `v=DMARC1; p=none; rua=mailto:privacy@<domain>`.
5. Back in Brevo, click **Authenticate**. All records should go green (can take an hour).
6. **Senders → Add a sender**: `SignalNova`, `no-reply@<domain>`.
7. **SMTP & API → SMTP → Generate a new SMTP key**. Note the login shown there (it is not your account e-mail).

On the server, in `~/signalnova-website/.env`:

```
SMTP_HOST=smtp-relay.brevo.com
SMTP_PORT=587
SMTP_SECURITY=starttls
SMTP_USER=<Brevo SMTP login>
SMTP_PASSWORD=<Brevo SMTP key>
SMTP_FROM="SignalNova <no-reply@<domain>>"
SMTP_REPLY_TO=hello@<domain>
MAIL_DAILY_LIMIT=140
```

`MAIL_DAILY_LIMIT=140` keeps a verified request (2 e-mails) safely under Brevo's 300/day.

```bash
sudo systemctl restart signalnova-web
curl -s 127.0.0.1:8001/health            # "mail":"smtp"
```

**Check:** request the whitepaper on `https://<domain>` with a Gmail and an Outlook address. Both codes arrive in the **inbox** (not spam). In Gmail, *Show original* says `SPF: PASS`, `DKIM: PASS`, `DMARC: PASS`.

## 8. Legal text

Before anyone outside sees the site, on your laptop:

1. `privacy.html`: replace every highlighted `[placeholder]`: date, registered address, KvK number, `privacy@<domain>`, retention period, and the mail provider (Brevo).
2. `index.html` footer: add address/KvK/contact where the `TODO` comment is, if you want them on the page.
3. Have someone check the privacy text if you can. It is a reasonable template, not legal advice.
4. Commit, push, and deploy as in [DEVELOPMENT.md §6](DEVELOPMENT.md#6-deploy-a-change).

## 9. Go-live test

On your phone, over mobile data:

1. `https://<domain>` loads, light and dark mode both look right.
2. Request the whitepaper. Enter one wrong code ("4 attempts left"), then the right one.
3. The PDF downloads and opens. The e-mail with the link arrives and the link works.
4. `https://<domain>/download/anything` shows "This link has expired."

On the server:

```bash
cd ~/signalnova-website && source venv/bin/activate
python3 manage.py stats          # 1 verified, ≥1 download
python3 manage.py delete --email <your test address>    # clean up your test
```

Then: a calendar reminder to check `manage.py stats` and the logs once a week for the first month ([RUNBOOK.md §3](RUNBOOK.md#3-weekly-check-5-minutes)).

## Changing the domain later

1. Add the new domain to Cloudflare (part 1) and its hostnames to the tunnel (part 6).
2. Update `SITE_URL`, verify the new domain in Brevo (7.2), update `SMTP_FROM`, restart.
3. Keep the old hostname for at least 72 hours (`DOWNLOAD_LINK_HOURS`) with a redirect rule to the new one, because links already e-mailed point at it.
