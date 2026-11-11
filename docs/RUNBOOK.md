# Runbook

For whoever keeps the SignalNova website running. First-time setup is in [DEPLOYMENT.md](DEPLOYMENT.md); making changes in [DEVELOPMENT.md](DEVELOPMENT.md).

Paths below are the production layout on the LivingLab server: code in `/home/ubuntu/signalnova-website`, virtualenv in `venv/`, logs in `logs/`. Run `manage.py` commands with the virtualenv active:

```bash
ssh -i ~/.ssh/binckhaven-key.pem ubuntu@<elastic-ip>
cd ~/signalnova-website && source venv/bin/activate
```

## 1. Quick reference

| What | Where |
|---|---|
| Website · health | `https://<domain>/` · `/health` |
| Server | EC2 `binckhaven-server` (shared with LivingLab) |
| Service | `signalnova-web`, uvicorn on `127.0.0.1:8001` |
| Database | RDS `binckhaven-db`, database `signalnova`, user `signalnova` |
| Configuration | `~/signalnova-website/.env`; template in [`.env.example`](../.env.example) |
| Whitepaper | `~/signalnova-website/private/whitepaper.pdf` (not in Git) |
| Log | `logs/web.log`; `logs/purge.log` for the nightly clean-up |
| E-mail | Brevo (sending), Cloudflare Email Routing (`privacy@`, `hello@`) |

## 2. Commands

```bash
systemctl status signalnova-web
sudo systemctl restart signalnova-web           # after .env or code changes
tail -n 100 logs/web.log
grep -E "ERROR|WARNING" logs/web.log | tail -20
curl -s 127.0.0.1:8001/health
```

`/health` fields: `database` (`ok`/`error`), `mail` (`smtp`, or `console` if `SMTP_HOST` is empty, meaning **no e-mail goes out**), `whitepaper` (`ok`/`missing`).

## 3. Weekly check (5 minutes)

1. `/health` is all `ok` and `mail` is `smtp`.
2. `python3 manage.py stats`. `mail_errors_7d` should be 0.
3. `grep ERROR logs/web.log | tail`: nothing new.
4. Brevo dashboard: no bounces piling up, nothing blocked.

## 4. Problems

### 4.1 Visitors say the code does not arrive

| Check | Meaning / fix |
|---|---|
| `/health` says `"mail":"console"` | `SMTP_HOST` is empty in `.env`. Fill in the Brevo settings, restart |
| `manage.py stats` shows `mail_errors_7d` > 0 | `grep "sending code" logs/web.log \| tail` shows the SMTP error. Authentication error → SMTP key revoked: new key in Brevo → `SMTP_PASSWORD` → restart |
| No errors, mail sent | It is in spam or delayed. Check Brevo → Transactional → Logs for that address (delivered / bounced / blocked). In Brevo, Domains must show the domain authenticated |
| Lands in spam | Check the SPF/DKIM/DMARC records ([DEPLOYMENT §7.2](DEPLOYMENT.md#72-sending-brevo)). Exactly **one** SPF record |
| Visitor sees "We are receiving a lot of requests" | The daily cap (`MAIL_DAILY_LIMIT`) is reached. Usually a bot: see 4.4. If it is real interest, raise the cap (and the Brevo plan) |

To find one visitor's attempts:

```bash
psql -h <rds-endpoint> -U signalnova -d signalnova -c "
SELECT vc.created_at, vc.mail_error, vc.attempts, vc.used_at
FROM verification_codes vc JOIN leads l ON l.id = vc.lead_id
WHERE l.email = 'someone@example.com' ORDER BY vc.created_at DESC;"
```

### 4.2 Site unreachable or Cloudflare error page

| Symptom | Fix |
|---|---|
| **502 Bad Gateway** | Service down: `systemctl status signalnova-web`, `tail logs/web.log`, restart |
| Error **1033** / tunnel error | `cloudflared` down; this also affects LivingLab. `sudo systemctl restart cloudflared`; see LivingLab Runbook §4.6 |
| Service will not start: `APP_SECRET missing` | Set it in `.env` (at least 32 characters) |
| `/health` `"database":"error"` | RDS unreachable or wrong `DB_*`. Test: `psql -h <rds-endpoint> -U signalnova -d signalnova -c "select 1"`. If LivingLab is also down, it is RDS itself |
| Old CSS/JS after a deploy | The Cloudflare cache-bypass rule is missing; or bump `?v=` ([DEVELOPMENT §4](DEVELOPMENT.md#4-what-to-test-before-you-push)) |

### 4.3 Download link says "expired" for a valid visitor

Links work for 72 hours and 10 downloads (`DOWNLOAD_LINK_HOURS`, `DOWNLOAD_LINK_MAX_USES`). The visitor requests the whitepaper again with the same address and gets a new link.

If **every** download fails with "temporarily unavailable" (503): `/health` shows `"whitepaper":"missing"`. Copy the PDF back (§6).

### 4.4 A bot is hammering the form

The limits already stop it from sending much mail (10 codes per IP per hour, 200 per day). To see it:

```bash
psql -h <rds-endpoint> -U signalnova -d signalnova -c "
SELECT ip, count(*) FROM verification_codes
WHERE created_at > now() - interval '24 hours' GROUP BY ip ORDER BY 2 DESC LIMIT 10;"
```

Block persistent IPs in Cloudflare → `<domain>` → **Security → WAF → Custom rules** (field *IP Source Address*, action *Block*), or add a rule *URI Path equals /api/send-code* → **Managed Challenge** for a while.

## 5. The leads

```bash
python3 manage.py stats                        # totals
python3 manage.py export > leads.csv           # verified leads, CSV
python3 manage.py export --all > leads.csv     # including addresses that never verified
```

Copy the CSV to your laptop and delete it from the server afterwards; it is personal data:

```bash
scp -i ~/.ssh/binckhaven-key.pem ubuntu@<elastic-ip>:~/signalnova-website/leads.csv .
ssh -i ~/.ssh/binckhaven-key.pem ubuntu@<elastic-ip> rm ~/signalnova-website/leads.csv
```

### Privacy requests (GDPR)

Requests arrive at `privacy@<domain>`. Answer within one month.

| Request | Do |
|---|---|
| "What do you have on me?" | `psql … -c "SELECT * FROM leads WHERE email = '…'"` and send the person the result |
| "Delete me" / consent withdrawn | `python3 manage.py delete --email …`. Removes the address, codes, links and download history. Also delete them from any CSV you exported or CRM you imported into |
| "Correct my name" | `psql … -c "UPDATE leads SET name = '…' WHERE email = '…'"` |

`manage.py purge` runs nightly from cron: it deletes codes and links older than 7 days, and addresses that never verified after 30 days (`UNVERIFIED_RETENTION_DAYS`). Check `logs/purge.log` once in a while.

## 6. Routine changes

| Change | How |
|---|---|
| **New version of the whitepaper** | From the laptop: `scp … whitepaper.pdf ubuntu@<elastic-ip>:~/signalnova-website/private/whitepaper.pdf`. No restart needed. Links already sent serve the new file |
| Different download file name | `WHITEPAPER_FILENAME` in `.env`, restart |
| Limits, link validity | `.env` (see `.env.example`), restart |
| Code or text changes | [DEVELOPMENT §6](DEVELOPMENT.md#6-deploy-a-change) |
| Change the domain | [DEPLOYMENT, "Changing the domain later"](DEPLOYMENT.md#changing-the-domain-later) |

## 7. Rotate secrets

| Secret | How | Side effect |
|---|---|---|
| `APP_SECRET` | New value in `.env`, restart | Codes sent in the last 15 minutes stop working; visitors ask for a new one. Download links keep working |
| `DB_PASSWORD` | `ALTER ROLE signalnova PASSWORD '…';` as the master user, then `.env`, restart | None |
| Brevo SMTP key | Generate a new one in Brevo, `.env`, restart, delete the old key | None |
| Deploy key | New key (DEPLOYMENT §5.1), replace it on GitHub | None |

## 8. Backup and restore

- **Database:** covered by RDS automated backups together with LivingLab. A point-in-time restore creates a new instance; dump the `signalnova` database from it with `pg_dump` and restore that into the live instance.
- **Whitepaper:** keep the master copy outside the server. To restore, copy it back (§6).
- **Configuration:** keep the `.env` values in the password manager. With those and GitHub, a rebuild is DEPLOYMENT parts 4–6.
