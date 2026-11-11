"""
mailer.py — outgoing e-mail (verification code, download link).

Plain SMTP, so any provider works by changing .env only:
    Gmail             smtp.gmail.com:587  starttls  (app password, ~500 mails/day)
    Brevo (free tier) smtp-relay.brevo.com:587 starttls  (300 mails/day, own domain)

With SMTP_HOST empty the message is printed to the log instead of sent —
meant for local development only. /health reports which mode is active.
"""

import html
import logging
import os
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formatdate, make_msgid, parseaddr

from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger("signalnova.mail")

SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER)
SMTP_REPLY_TO = os.getenv("SMTP_REPLY_TO", "")
SMTP_SECURITY = os.getenv("SMTP_SECURITY", "starttls").strip().lower()
LOGO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "img", "logo.png")

INDIGO, INK, MUTED = "#3A3B8C", "#1D1D1F", "#6E6E73"


def mail_mode() -> str:
    return "smtp" if SMTP_HOST else "console"


def send_email(to: str, subject: str, text: str, html_body: str) -> None:
    """Send one message to one recipient. Raises on failure."""
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = SMTP_FROM or "SignalNova <no-reply@localhost>"
    msg["To"] = to
    if SMTP_REPLY_TO:
        msg["Reply-To"] = SMTP_REPLY_TO
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=parseaddr(SMTP_FROM)[1].split("@")[-1] or None)
    # Tells mail servers not to send out-of-office replies back to us.
    msg["Auto-Submitted"] = "auto-generated"
    msg["X-Auto-Response-Suppress"] = "All"
    msg.set_content(text)
    msg.add_alternative(html_body, subtype="html")
    # Inline logo (cid:logo): most mail apps block remote images by default.
    if "cid:logo" in html_body and os.path.exists(LOGO_PATH):
        with open(LOGO_PATH, "rb") as f:
            msg.get_payload()[1].add_related(f.read(), "image", "png", cid="<logo>",
                                             filename="signalnova.png")

    if not SMTP_HOST:
        log.warning("SMTP_HOST not set — e-mail NOT sent (console mode)\nTo: %s\nSubject: %s\n\n%s",
                    to, subject, text)
        return

    ctx = ssl.create_default_context()
    if SMTP_SECURITY == "ssl":
        server = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=ctx, timeout=30)
    else:
        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30)
    try:
        if SMTP_SECURITY == "starttls":
            server.starttls(context=ctx)
        if SMTP_USER:
            server.login(SMTP_USER, SMTP_PASSWORD)
        server.send_message(msg)
    finally:
        # Once send_message returned the mail is out; a failing QUIT must not raise.
        try:
            server.quit()
        except Exception:
            server.close()


# ── Layout ───────────────────────────────────────────────────────────────
# Table-based with inline styles: the only thing that renders the same in
# Outlook, Gmail and Apple Mail.

def _layout(preheader: str, inner: str) -> str:
    return f"""<!DOCTYPE html><html><body style="margin:0;padding:0;background:#F5F5F7;">
<span style="display:none;max-height:0;overflow:hidden;">{html.escape(preheader)}</span>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#F5F5F7;padding:32px 12px;">
<tr><td align="center">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:520px;background:#FFFFFF;border-radius:18px;">
<tr><td style="padding:28px 32px 8px;"><img src="cid:logo" width="180" alt="SignalNova" style="display:block;border:0;"></td></tr>
<tr><td style="padding:8px 32px 32px;font-family:-apple-system,BlinkMacSystemFont,Helvetica,Arial,sans-serif;font-size:16px;line-height:1.55;color:{INK};">{inner}</td></tr>
</table>
</td></tr></table></body></html>"""


def code_email(name: str, code: str, minutes: int) -> tuple:
    subject = f"{code} is your SignalNova verification code"
    text = (f"Hi {name},\n\nYour verification code is: {code}\n\n"
            f"Enter it on the SignalNova website to get the whitepaper. "
            f"The code expires in {minutes} minutes.\n\n"
            "If you did not ask for this, you can ignore this e-mail.\n\n— SignalNova")
    inner = f"""<p style="margin:0 0 14px;">Hi {html.escape(name)},</p>
<p style="margin:0 0 18px;">Enter this code on the SignalNova website to get the whitepaper:</p>
<p style="margin:0 0 18px;font-size:34px;font-weight:bold;letter-spacing:8px;color:{INDIGO};">{code}</p>
<p style="margin:0 0 14px;color:{MUTED};font-size:14px;">The code expires in {minutes} minutes.
If you did not ask for this, you can ignore this e-mail.</p>"""
    return subject, text, _layout(f"Your code is {code}", inner)


def link_email(name: str, url: str, hours: int) -> tuple:
    subject = "Your SignalNova whitepaper"
    text = (f"Hi {name},\n\nThank you for confirming your e-mail address. "
            f"Download the whitepaper here:\n\n{url}\n\n"
            f"The link works for {hours} hours.\n\n— SignalNova")
    inner = f"""<p style="margin:0 0 14px;">Hi {html.escape(name)},</p>
<p style="margin:0 0 22px;">Thank you for confirming your e-mail address. Your whitepaper is ready.</p>
<p style="margin:0 0 22px;"><a href="{html.escape(url)}" style="display:inline-block;background:{INDIGO};color:#FFFFFF;
text-decoration:none;font-weight:bold;padding:13px 24px;border-radius:999px;">Download the whitepaper (PDF)</a></p>
<p style="margin:0 0 14px;color:{MUTED};font-size:14px;">The link works for {hours} hours.
If the button does not work, copy this address into your browser:<br>
<span style="word-break:break-all;">{html.escape(url)}</span></p>"""
    return subject, text, _layout("Your whitepaper is ready to download", inner)
