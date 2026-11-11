-- SignalNova website — database schema.
-- Idempotent: safe to re-run at any time (CREATE ... IF NOT EXISTS only).
--
--   psql -h <host> -U <user> -d signalnova -f init_db.sql

-- One row per e-mail address that ever asked for the whitepaper.
-- verified_at is set the first time the address proves it is real.
CREATE TABLE IF NOT EXISTS leads (
    id                BIGSERIAL PRIMARY KEY,
    email             TEXT        NOT NULL UNIQUE,      -- stored lower-case
    name              TEXT        NOT NULL,             -- latest name given
    consent_text      TEXT        NOT NULL,             -- exact wording the person agreed to
    consent_at        TIMESTAMPTZ NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    verified_at       TIMESTAMPTZ,
    first_ip          INET,
    last_ip           INET,
    user_agent        TEXT,
    download_count    INTEGER     NOT NULL DEFAULT 0,
    last_download_at  TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS leads_created_idx  ON leads (created_at);
CREATE INDEX IF NOT EXISTS leads_verified_idx ON leads (verified_at);

-- One row per code e-mailed. Only an HMAC of the code is stored.
-- Also the source for rate limiting (per address, per IP, per day).
CREATE TABLE IF NOT EXISTS verification_codes (
    id          BIGSERIAL PRIMARY KEY,
    lead_id     BIGINT      NOT NULL REFERENCES leads (id) ON DELETE CASCADE,
    code_hash   TEXT        NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at  TIMESTAMPTZ NOT NULL,
    attempts    INTEGER     NOT NULL DEFAULT 0,
    used_at     TIMESTAMPTZ,
    ip          INET,
    mail_error  TEXT                                   -- set when the SMTP send failed
);
CREATE INDEX IF NOT EXISTS vc_lead_idx    ON verification_codes (lead_id, created_at DESC);
CREATE INDEX IF NOT EXISTS vc_ip_idx      ON verification_codes (ip, created_at);
CREATE INDEX IF NOT EXISTS vc_created_idx ON verification_codes (created_at);

-- Download links handed out after a successful verification.
-- Only a SHA-256 of the token is stored; the token itself is in the link.
CREATE TABLE IF NOT EXISTS download_tokens (
    token_hash  TEXT        PRIMARY KEY,
    lead_id     BIGINT      NOT NULL REFERENCES leads (id) ON DELETE CASCADE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at  TIMESTAMPTZ NOT NULL,
    uses        INTEGER     NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS dt_lead_idx ON download_tokens (lead_id);

-- Every successful download.
CREATE TABLE IF NOT EXISTS downloads (
    id          BIGSERIAL PRIMARY KEY,
    lead_id     BIGINT      NOT NULL REFERENCES leads (id) ON DELETE CASCADE,
    at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    ip          INET,
    user_agent  TEXT
);
CREATE INDEX IF NOT EXISTS downloads_lead_idx ON downloads (lead_id, at);
