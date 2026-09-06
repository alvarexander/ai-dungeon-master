-- =====================================================================
-- Migration 0001 — Initial schema
-- =====================================================================
--
-- WHAT A MIGRATION IS
-- A database starts empty. A "migration" is a numbered file of instructions
-- that changes the database's structure — creating tables, adding columns.
-- They are applied in order, once each, and never edited after they have run
-- anywhere real. That way any copy of the database (your laptop, the server)
-- can be rebuilt from scratch by replaying the same files in the same order.
--
-- HOW TO READ THE COMMENT ON EVERY COLUMN
-- Each column carries a COMMENT declaring how its contents are protected.
-- There are exactly four classifications, and every column has one:
--
--   PLAINTEXT     Stored as-is and readable by anyone with database access.
--                 Only permitted for data that is NOT personal: opaque random
--                 identifiers, usernames, display names, counters, timestamps,
--                 and fixed enumerated values.
--
--   ENCRYPTED     Stored as ciphertext (AES-256-GCM) using a Data Encryption
--                 Key unique to one user. Unreadable without calling AWS KMS
--                 as the application role. This is where all personal data
--                 lives.
--
--   HASHED        Passed through a one-way function. Cannot be reversed at
--                 all, only compared against a fresh guess.
--
--   BLIND-INDEX   A keyed one-way fingerprint (HMAC-SHA256) that is stable, so
--                 it can be indexed and searched, but not reversible. The key
--                 is NOT in this database.
--
-- THE RULE THIS SCHEMA ENFORCES
-- In a full dump of this database, the only human-meaningful plaintext about a
-- person is their username and display name. Everything else identifying is
-- ciphertext or an irreversible digest.
--
-- CONVENTIONS
--   *_ct       column holds ciphertext
--   *_bidx     column holds a blind index fingerprint
--   *_hmac     column holds a keyed digest used for counting, not lookup
--   BINARY(16) a UUID stored compactly as 16 raw bytes rather than 36 characters
--   DATETIME(6) a timestamp with microseconds, ALWAYS stored in UTC
-- =====================================================================

SET NAMES utf8mb4;
SET time_zone = '+00:00';

-- ---------------------------------------------------------------------
-- schema_migrations — bookkeeping so the runner knows what has been applied
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS schema_migrations (
  version      VARCHAR(64)  NOT NULL COMMENT 'PLAINTEXT: migration file number, e.g. 0001',
  applied_at   DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT 'PLAINTEXT: when this migration ran, UTC',
  checksum     CHAR(64)     NOT NULL COMMENT 'PLAINTEXT: SHA-256 of the file, detects edits to already-applied migrations',
  PRIMARY KEY (version)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='Which migrations have been applied. Contains no user data.';

-- =====================================================================
-- IDENTITY PLANE
-- Tables that describe a person. Everything personal here is ciphertext.
-- =====================================================================

-- ---------------------------------------------------------------------
-- users — one row per account
--
-- Note what is deliberately absent: there is no plaintext email column, and
-- no index on any encrypted column. The only searchable representation of an
-- email address is the blind index, and its key lives in AWS Secrets Manager.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
  user_id            BINARY(16)    NOT NULL COMMENT 'PLAINTEXT: random UUIDv4. Opaque — reveals nothing about the person. Safe to log.',
  username           VARCHAR(32)   NOT NULL COMMENT 'PLAINTEXT: chosen handle. Explicitly classified as non-personal for this product.',
  display_name       VARCHAR(64)   NOT NULL COMMENT 'PLAINTEXT: shown in the interface. Explicitly classified as non-personal.',

  email_bidx         BINARY(32)    NOT NULL COMMENT 'BLIND-INDEX: HMAC-SHA256(secrets-manager key, lowercased trimmed email). Enables login lookup. Leaks equality only.',
  email_ct           VARBINARY(512) NOT NULL COMMENT 'ENCRYPTED: the email address itself, AES-256-GCM under this user DEK.',
  email_verified     TINYINT(1)    NOT NULL DEFAULT 0 COMMENT 'PLAINTEXT: boolean flag, carries no identifying information.',

  password_hash      VARCHAR(255)  NOT NULL COMMENT 'HASHED: Argon2id digest including its own salt and parameters. NEVER encrypted — see ADR-004.',

  phone_ct           VARBINARY(512) NULL COMMENT 'ENCRYPTED: phone number.',
  first_name_ct      VARBINARY(512) NULL COMMENT 'ENCRYPTED: given name.',
  last_name_ct       VARBINARY(512) NULL COMMENT 'ENCRYPTED: family name.',
  date_of_birth_ct   VARBINARY(128) NULL COMMENT 'ENCRYPTED: date of birth as an ISO-8601 string.',

  dek_wrapped        VARBINARY(1024) NULL COMMENT 'ENCRYPTED: this user Data Encryption Key, wrapped by AWS KMS. Deleting these bytes crypto-shreds the account (ADR-005). NULL means already shredded.',
  dek_key_version    INT UNSIGNED  NOT NULL DEFAULT 1 COMMENT 'PLAINTEXT: which KMS key generation wrapped the DEK. Lets keys rotate without re-encrypting every row at once.',
  kms_key_arn        VARCHAR(255)  NULL COMMENT 'PLAINTEXT: identifier of the KMS key that can unwrap the DEK. Not a secret — it names a key, it is not the key.',

  status             ENUM('active','suspended','shredded') NOT NULL DEFAULT 'active' COMMENT 'PLAINTEXT: account state, fixed set of values.',
  failed_login_count INT UNSIGNED  NOT NULL DEFAULT 0 COMMENT 'PLAINTEXT: counter for lockout. A number, not personal data.',
  created_at         DATETIME(6)   NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT 'PLAINTEXT: signup time, UTC. Also drives retention cohorts.',
  updated_at         DATETIME(6)   NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6) COMMENT 'PLAINTEXT: last modification, UTC.',
  shredded_at        DATETIME(6)   NULL COMMENT 'PLAINTEXT: when the DEK was destroyed, UTC. Proof of deletion for compliance.',

  PRIMARY KEY (user_id),
  UNIQUE KEY uq_users_username (username),
  UNIQUE KEY uq_users_email_bidx (email_bidx),
  KEY idx_users_created_at (created_at),
  KEY idx_users_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='Accounts. Only username and display_name are human-meaningful plaintext.';

-- ---------------------------------------------------------------------
-- user_analytics_map — the ONLY link between a person and their analytics
--
-- The analytics identifier is stored encrypted under the user own DEK. That
-- is not decoration: it means crypto-shredding severs the link automatically,
-- even if this row somehow survives in an old backup.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS user_analytics_map (
  user_id          BINARY(16)     NOT NULL COMMENT 'PLAINTEXT: opaque account identifier.',
  analytics_id_ct  VARBINARY(512) NOT NULL COMMENT 'ENCRYPTED: the random analytics UUID. Encrypted so that destroying the DEK orphans the analytics permanently.',
  created_at       DATETIME(6)    NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT 'PLAINTEXT: when the mapping was created, UTC.',
  PRIMARY KEY (user_id),
  CONSTRAINT fk_uam_user FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='Bridge between identity and analytics. Deleting a row here is irreversible by design.';

-- ---------------------------------------------------------------------
-- user_sessions — issued refresh tokens (Phase 2; schema defined now)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS user_sessions (
  session_id          BINARY(16)      NOT NULL COMMENT 'PLAINTEXT: opaque random identifier for this login session.',
  user_id             BINARY(16)      NOT NULL COMMENT 'PLAINTEXT: opaque account identifier.',
  refresh_token_hash  BINARY(32)      NOT NULL COMMENT 'HASHED: SHA-256 of the refresh token. Storing the hash means a database leak does not hand over working tokens.',
  ip_hmac             BINARY(32)      NOT NULL COMMENT 'HASHED: HMAC of the IP address with a salt that rotates daily and is never stored here. Lets us spot session hijacking without keeping addresses.',
  user_agent_ct       VARBINARY(1024) NULL COMMENT 'ENCRYPTED: browser identification string. Free text, therefore treated as personal data.',
  created_at          DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT 'PLAINTEXT: session start, UTC.',
  expires_at          DATETIME(6)     NOT NULL COMMENT 'PLAINTEXT: expiry, UTC.',
  revoked_at          DATETIME(6)     NULL COMMENT 'PLAINTEXT: when revoked, UTC. NULL means still valid.',
  PRIMARY KEY (session_id),
  KEY idx_sessions_user (user_id),
  UNIQUE KEY uq_sessions_token (refresh_token_hash),
  KEY idx_sessions_expiry (expires_at),
  CONSTRAINT fk_sessions_user FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='Active login sessions.';

-- ---------------------------------------------------------------------
-- account_activity_log — what the USER sees about their own account
--
-- This is where "support looked at your data on Tuesday" appears. If we are
-- going to read someone's records, they get told.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS account_activity_log (
  activity_id  BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT 'PLAINTEXT: row counter.',
  user_id      BINARY(16)      NOT NULL COMMENT 'PLAINTEXT: opaque account identifier.',
  event_type   ENUM('login','logout','password_changed','email_changed','support_access','data_exported','deletion_requested','deletion_completed') NOT NULL COMMENT 'PLAINTEXT: fixed set of values, no free text possible.',
  detail_ct    VARBINARY(2048) NULL COMMENT 'ENCRYPTED: any human-readable detail, e.g. the stated reason for a support access.',
  occurred_at  DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT 'PLAINTEXT: event time, UTC.',
  PRIMARY KEY (activity_id),
  KEY idx_activity_user_time (user_id, occurred_at),
  CONSTRAINT fk_activity_user FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='Per-user visible activity history, including support access disclosure.';

-- =====================================================================
-- GAME PLANE
-- Campaigns, characters and transcripts. Player free text is personal data
-- because players type their own and their friends real names into it.
-- =====================================================================

CREATE TABLE IF NOT EXISTS campaigns (
  campaign_id     BINARY(16)      NOT NULL COMMENT 'PLAINTEXT: opaque identifier.',
  user_id         BINARY(16)      NOT NULL COMMENT 'PLAINTEXT: owning account.',
  title_ct        VARBINARY(512)  NOT NULL COMMENT 'ENCRYPTED: campaign title. User free text.',
  premise_ct      VARBINARY(4096) NULL COMMENT 'ENCRYPTED: the opening premise the player wrote. User free text.',
  ruleset         ENUM('dnd5e','freeform') NOT NULL DEFAULT 'dnd5e' COMMENT 'PLAINTEXT: which rules the DM applies. Fixed set.',
  tone            ENUM('heroic','gritty','comedic','horror','mystery') NOT NULL DEFAULT 'heroic' COMMENT 'PLAINTEXT: narrative tone. Fixed set, useful for aggregate analytics.',
  status          ENUM('active','archived','deleted') NOT NULL DEFAULT 'active' COMMENT 'PLAINTEXT: fixed set.',
  dek_key_version INT UNSIGNED    NOT NULL DEFAULT 1 COMMENT 'PLAINTEXT: which key generation encrypted this row.',
  created_at      DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT 'PLAINTEXT: UTC.',
  updated_at      DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6) COMMENT 'PLAINTEXT: UTC.',
  PRIMARY KEY (campaign_id),
  KEY idx_campaigns_user (user_id, status, updated_at),
  CONSTRAINT fk_campaigns_user FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='A long-running story belonging to one account.';

CREATE TABLE IF NOT EXISTS characters (
  character_id    BINARY(16)      NOT NULL COMMENT 'PLAINTEXT: opaque identifier.',
  campaign_id     BINARY(16)      NOT NULL COMMENT 'PLAINTEXT: owning campaign.',
  user_id         BINARY(16)      NOT NULL COMMENT 'PLAINTEXT: owning account, denormalised so the DEK can be found without a join.',
  name_ct         VARBINARY(512)  NOT NULL COMMENT 'ENCRYPTED: character name. Players routinely use their own or a friend real name.',
  backstory_ct    MEDIUMBLOB      NULL COMMENT 'ENCRYPTED: free-text backstory.',
  sheet_ct        MEDIUMBLOB      NOT NULL COMMENT 'ENCRYPTED: the full character sheet as JSON — abilities, inventory, notes.',
  char_class      ENUM('barbarian','bard','cleric','druid','fighter','monk','paladin','ranger','rogue','sorcerer','warlock','wizard') NOT NULL COMMENT 'PLAINTEXT: fixed set. Not personal; kept readable so aggregate class popularity needs no decryption.',
  char_level      TINYINT UNSIGNED NOT NULL DEFAULT 1 COMMENT 'PLAINTEXT: a number 1-20. Not personal.',
  dek_key_version INT UNSIGNED    NOT NULL DEFAULT 1 COMMENT 'PLAINTEXT: key generation used.',
  created_at      DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT 'PLAINTEXT: UTC.',
  updated_at      DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6) COMMENT 'PLAINTEXT: UTC.',
  PRIMARY KEY (character_id),
  KEY idx_characters_campaign (campaign_id),
  KEY idx_characters_user (user_id),
  CONSTRAINT fk_characters_campaign FOREIGN KEY (campaign_id) REFERENCES campaigns(campaign_id) ON DELETE CASCADE,
  CONSTRAINT fk_characters_user FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='Player characters.';

CREATE TABLE IF NOT EXISTS game_sessions (
  game_session_id      BINARY(16)   NOT NULL COMMENT 'PLAINTEXT: opaque identifier for one sitting at the table.',
  campaign_id          BINARY(16)   NOT NULL COMMENT 'PLAINTEXT: owning campaign.',
  user_id              BINARY(16)   NOT NULL COMMENT 'PLAINTEXT: owning account, denormalised for key lookup.',
  started_at           DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT 'PLAINTEXT: UTC.',
  ended_at             DATETIME(6)  NULL COMMENT 'PLAINTEXT: UTC. NULL while play is in progress.',
  turn_count           INT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'PLAINTEXT: number of exchanges. A counter.',
  debug_capture        TINYINT(1)   NOT NULL DEFAULT 0 COMMENT 'PLAINTEXT: has the player opted in to storing prompt content for debugging?',
  debug_capture_until  DATETIME(6)  NULL COMMENT 'PLAINTEXT: when that opt-in expires, UTC. Always 48 hours or less.',
  PRIMARY KEY (game_session_id),
  KEY idx_gs_campaign (campaign_id, started_at),
  KEY idx_gs_user (user_id),
  CONSTRAINT fk_gs_campaign FOREIGN KEY (campaign_id) REFERENCES campaigns(campaign_id) ON DELETE CASCADE,
  CONSTRAINT fk_gs_user FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='One play session within a campaign.';

CREATE TABLE IF NOT EXISTS messages (
  message_id       BINARY(16)   NOT NULL COMMENT 'PLAINTEXT: opaque identifier.',
  game_session_id  BINARY(16)   NOT NULL COMMENT 'PLAINTEXT: owning play session.',
  user_id          BINARY(16)   NOT NULL COMMENT 'PLAINTEXT: owning account, denormalised for key lookup.',
  seq              INT UNSIGNED NOT NULL COMMENT 'PLAINTEXT: position in the conversation, 1, 2, 3...',
  role             ENUM('player','dungeon_master','system') NOT NULL COMMENT 'PLAINTEXT: who spoke. Fixed set.',
  content_ct       MEDIUMBLOB   NOT NULL COMMENT 'ENCRYPTED: the actual words. THIS IS PERSONAL DATA — players type real names and private details into it.',
  input_mode       ENUM('typed','voice') NOT NULL DEFAULT 'typed' COMMENT 'PLAINTEXT: how it was entered. Fixed set, feeds feature-usage analytics.',
  token_count      INT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'PLAINTEXT: length in model tokens. A number.',
  dek_key_version  INT UNSIGNED NOT NULL DEFAULT 1 COMMENT 'PLAINTEXT: key generation used.',
  created_at       DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT 'PLAINTEXT: UTC.',
  PRIMARY KEY (message_id),
  UNIQUE KEY uq_messages_session_seq (game_session_id, seq),
  KEY idx_messages_user (user_id),
  CONSTRAINT fk_messages_session FOREIGN KEY (game_session_id) REFERENCES game_sessions(game_session_id) ON DELETE CASCADE,
  CONSTRAINT fk_messages_user FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='The transcript. Every content row is ciphertext.';

-- =====================================================================
-- OBSERVABILITY PLANE (debug)
-- =====================================================================

-- ---------------------------------------------------------------------
-- gemini_calls — one row per request to the AI
--
-- Note the columns that DO NOT exist: there is no prompt column and no
-- response column. Content is never recorded here, by construction.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS gemini_calls (
  call_id               BINARY(16)   NOT NULL COMMENT 'PLAINTEXT: opaque identifier.',
  correlation_id        BINARY(16)   NOT NULL COMMENT 'PLAINTEXT: ties this call to the request that caused it and to every log line for that request.',
  game_session_id       BINARY(16)   NULL COMMENT 'PLAINTEXT: owning play session, if any.',
  model_id              VARCHAR(64)  NOT NULL COMMENT 'PLAINTEXT: e.g. gemini-3.5-flash.',
  latency_ms            INT UNSIGNED NOT NULL COMMENT 'PLAINTEXT: how long the call took.',
  tokens_in             INT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'PLAINTEXT: prompt size in tokens.',
  tokens_out            INT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'PLAINTEXT: response size in tokens.',
  finish_reason         ENUM('stop','max_tokens','safety','recitation','other','error') NOT NULL COMMENT 'PLAINTEXT: why generation stopped. Fixed set.',
  safety_blocked        TINYINT(1)   NOT NULL DEFAULT 0 COMMENT 'PLAINTEXT: did a safety filter fire?',
  error_code            VARCHAR(64)  NULL COMMENT 'PLAINTEXT: provider error code such as RESOURCE_EXHAUSTED. Never a message body.',
  retry_count           TINYINT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'PLAINTEXT: retries before success or failure.',
  estimated_cost_micros BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'PLAINTEXT: estimated cost in millionths of a US dollar. Zero on the free tier.',
  created_at            DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT 'PLAINTEXT: UTC.',
  PRIMARY KEY (call_id),
  KEY idx_calls_time (created_at),
  KEY idx_calls_correlation (correlation_id),
  KEY idx_calls_errors (finish_reason, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='Metadata about AI calls. Deliberately has no content columns.';

-- ---------------------------------------------------------------------
-- debug_captures — opt-in, encrypted, self-expiring prompt storage
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS debug_captures (
  capture_id   BINARY(16)  NOT NULL COMMENT 'PLAINTEXT: opaque identifier.',
  call_id      BINARY(16)  NOT NULL COMMENT 'PLAINTEXT: the AI call this captures.',
  user_id      BINARY(16)  NOT NULL COMMENT 'PLAINTEXT: owning account — needed to locate the decryption key.',
  prompt_ct    MEDIUMBLOB  NOT NULL COMMENT 'ENCRYPTED: the exact prompt sent, under the user DEK.',
  response_ct  MEDIUMBLOB  NULL COMMENT 'ENCRYPTED: the exact response received, under the user DEK.',
  expires_at   DATETIME(6) NOT NULL COMMENT 'PLAINTEXT: hard deletion deadline, UTC. Never more than 48 hours after creation.',
  created_at   DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT 'PLAINTEXT: UTC.',
  PRIMARY KEY (capture_id),
  KEY idx_captures_expiry (expires_at),
  KEY idx_captures_call (call_id),
  CONSTRAINT fk_captures_user FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='Opt-in prompt capture. Encrypted, 48-hour lifetime, readable only through the audited support flow.';

-- ---------------------------------------------------------------------
-- support_access_grants — immutable audit of every plaintext read
--
-- The reason text is encrypted under a SEPARATE audit key, not the user DEK.
-- If it used the user key, crypto-shredding an account would also erase the
-- record of who looked at it — destroying exactly the evidence an audit needs.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS support_access_grants (
  grant_id        BINARY(16)      NOT NULL COMMENT 'PLAINTEXT: opaque identifier.',
  operator_id     VARCHAR(128)    NOT NULL COMMENT 'PLAINTEXT: which staff identity requested access. Staff, not a customer.',
  target_user_id  BINARY(16)      NOT NULL COMMENT 'PLAINTEXT: whose data. Opaque identifier only.',
  reason_ct       VARBINARY(2048) NOT NULL COMMENT 'ENCRYPTED: the stated justification, under the dedicated AUDIT key so it survives crypto-shredding of the user.',
  scope           ENUM('profile','transcript','debug_capture') NOT NULL COMMENT 'PLAINTEXT: what was unlocked. Fixed set.',
  granted_at      DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT 'PLAINTEXT: UTC.',
  expires_at      DATETIME(6)     NOT NULL COMMENT 'PLAINTEXT: automatic expiry, UTC. Default one hour after granting.',
  revoked_at      DATETIME(6)     NULL COMMENT 'PLAINTEXT: early revocation, UTC.',
  PRIMARY KEY (grant_id),
  KEY idx_grants_target (target_user_id, granted_at),
  KEY idx_grants_operator (operator_id, granted_at),
  KEY idx_grants_expiry (expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='Append-only. The application role is granted INSERT and SELECT but never UPDATE or DELETE.';

-- =====================================================================
-- ABUSE PREVENTION PLANE
-- Every value here is a digest. Rate limiting runs with zero decryption.
-- =====================================================================

CREATE TABLE IF NOT EXISTS rate_limit_counters (
  bucket_hmac   BINARY(32)   NOT NULL COMMENT 'HASHED: HMAC of the IP address or username with a daily-rotating salt held only in memory and the secrets manager.',
  scope         ENUM('ip_global','login','register','chat','stt','password_reset') NOT NULL COMMENT 'PLAINTEXT: which limit this counts. Fixed set.',
  window_start  DATETIME(6)  NOT NULL COMMENT 'PLAINTEXT: start of the counting window, UTC.',
  hit_count     INT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'PLAINTEXT: requests so far in this window. A number.',
  PRIMARY KEY (bucket_hmac, scope, window_start),
  KEY idx_rl_window (window_start)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='Rate limit counters keyed by digest. Contains no readable identifier of any kind.';

-- =====================================================================
-- ANALYTICS PLANE
-- NOTE: there is deliberately NO foreign key from these tables to users.
-- The absence is the safety property — the database itself cannot join a
-- person to their analytics. There is also no free-text column anywhere.
-- =====================================================================

CREATE TABLE IF NOT EXISTS analytics_events (
  event_id        BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT 'PLAINTEXT: row counter.',
  analytics_id    BINARY(16)      NOT NULL COMMENT 'PLAINTEXT: pseudonymous identifier, mathematically unrelated to user_id. NOT a foreign key, on purpose.',
  event_name      ENUM('session_started','session_ended','turn_taken','voice_input_used','campaign_created','character_created','character_updated','settings_changed','error_occurred','quota_exhausted','signup_completed','login_succeeded') NOT NULL COMMENT 'PLAINTEXT: the allowlist. Adding an event means a migration, which is the point.',
  occurred_at     DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT 'PLAINTEXT: UTC.',
  country_code    CHAR(2)         NULL COMMENT 'PLAINTEXT: ISO country derived from the IP at request time, after which the address is discarded. Never city, never the address itself.',
  platform        ENUM('web') NOT NULL DEFAULT 'web' COMMENT 'PLAINTEXT: fixed set.',
  duration_bucket ENUM('lt_1m','1_5m','5_15m','15_30m','30_60m','gt_60m') NULL COMMENT 'PLAINTEXT: bucketed, never an exact duration, so it cannot act as a fingerprint.',
  turn_count      INT UNSIGNED    NULL COMMENT 'PLAINTEXT: a number.',
  feature         ENUM('voice_input','typed_input','character_sheet','campaign_list','dice_roller','settings') NULL COMMENT 'PLAINTEXT: fixed set.',
  error_category  ENUM('validation','rate_limited','upstream_ai','upstream_timeout','auth','internal') NULL COMMENT 'PLAINTEXT: fixed set. Categories only — never a message.',
  success         TINYINT(1)      NULL COMMENT 'PLAINTEXT: boolean.',
  PRIMARY KEY (event_id),
  KEY idx_ae_name_time (event_name, occurred_at),
  KEY idx_ae_analytics (analytics_id, occurred_at),
  KEY idx_ae_time (occurred_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='Raw pseudonymous events. 90-day retention. No free-text column exists here, so none can be smuggled in.';

CREATE TABLE IF NOT EXISTS analytics_daily_aggregates (
  day          DATE            NOT NULL COMMENT 'PLAINTEXT: the day being summarised, UTC.',
  metric       ENUM('sessions','active_users','turns','voice_turns','signups','errors','quota_exhaustions','avg_session_seconds') NOT NULL COMMENT 'PLAINTEXT: fixed set.',
  dimension    VARCHAR(32)     NOT NULL DEFAULT '_all' COMMENT 'PLAINTEXT: an enum value from elsewhere in the schema, or _all. Constrained by the stored procedure, never free text.',
  value        BIGINT          NOT NULL DEFAULT 0 COMMENT 'PLAINTEXT: the count.',
  computed_at  DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT 'PLAINTEXT: UTC.',
  PRIMARY KEY (day, metric, dimension)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='Rolled-up counters, kept indefinitely. Survives crypto-shredding — that is why they are computed daily rather than on demand.';

CREATE TABLE IF NOT EXISTS analytics_retention_cohorts (
  signup_week   DATE   NOT NULL COMMENT 'PLAINTEXT: Monday of the week the cohort signed up, UTC.',
  week_offset   TINYINT UNSIGNED NOT NULL COMMENT 'PLAINTEXT: weeks since signup — 0, 1, 2...',
  active_users  INT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'PLAINTEXT: how many of that cohort were active. A count.',
  computed_at   DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT 'PLAINTEXT: UTC.',
  PRIMARY KEY (signup_week, week_offset)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='Retention by signup cohort. Counts only — impossible to reconstruct an individual.';

INSERT INTO schema_migrations (version, checksum)
VALUES ('0001', 'set-by-migration-runner')
ON DUPLICATE KEY UPDATE applied_at = applied_at;
