-- =====================================================================
-- Migration 0002 — Stored procedures
-- =====================================================================
--
-- WHAT A STORED PROCEDURE IS
-- A named block of SQL that lives inside the database and is called by name,
-- like a function. Two reasons they are used here:
--
--   1. Operations that need several statements to stay consistent (check a
--      counter, then increment it) happen in one round trip instead of three,
--      which matters when the application is on Fly.io and the database is in
--      AWS — every trip between them costs real milliseconds.
--   2. The application can be granted permission to CALL these procedures
--      while being denied broad UPDATE and DELETE rights on the tables. The
--      procedure becomes the only door.
--
-- THE HARD RULE OBEYED BY EVERY PROCEDURE BELOW
-- No procedure accepts, returns, or compares plaintext personal data. The
-- database never holds an encryption key, so it *cannot* work with personal
-- data even if asked. Procedures deal only in:
--   - opaque random identifiers (user_id, campaign_id, analytics_id)
--   - digests (bucket_hmac, email_bidx)
--   - ciphertext, which they move around without ever looking inside
--   - numbers, timestamps, and fixed enumerated values
--
-- ABOUT "DELIMITER"
-- A procedure body contains semicolons, but a semicolon is also how you end a
-- statement. DELIMITER temporarily changes the end-of-statement marker to $$
-- so the whole procedure arrives as one unit. It is a client instruction, not
-- SQL. The migration runner in scripts/migrate.py understands it.
-- =====================================================================

DELIMITER $$

-- ---------------------------------------------------------------------
-- sp_rate_limit_hit
--
-- The whole abuse-prevention path in one call, using only digests.
-- Increments the counter for a bucket and reports whether the caller is over
-- the limit. Demonstrates the claim in ADR-007: rate limiting requires zero
-- plaintext and zero decryption.
--
-- p_bucket_hmac  HMAC of an IP address or username. Not reversible.
-- p_scope        which limit ('login', 'chat', ...).
-- p_window_secs  length of the counting window in seconds.
-- p_limit        how many hits are allowed in that window.
--
-- Returns one row: allowed (1/0), hit_count, retry_after_secs.
-- ---------------------------------------------------------------------
DROP PROCEDURE IF EXISTS sp_rate_limit_hit$$
CREATE PROCEDURE sp_rate_limit_hit(
  IN p_bucket_hmac BINARY(32),
  IN p_scope       VARCHAR(32),
  IN p_window_secs INT,
  IN p_limit       INT
)
BEGIN
  DECLARE v_window_start DATETIME(6);
  DECLARE v_count INT DEFAULT 0;

  -- Round "now" down to the start of the current window so that everyone
  -- sharing a window shares a counter row.
  SET v_window_start = FROM_UNIXTIME(
    FLOOR(UNIX_TIMESTAMP(UTC_TIMESTAMP(6)) / p_window_secs) * p_window_secs
  );

  INSERT INTO rate_limit_counters (bucket_hmac, scope, window_start, hit_count)
  VALUES (p_bucket_hmac, p_scope, v_window_start, 1)
  ON DUPLICATE KEY UPDATE hit_count = hit_count + 1;

  SELECT hit_count INTO v_count
  FROM rate_limit_counters
  WHERE bucket_hmac = p_bucket_hmac
    AND scope = p_scope
    AND window_start = v_window_start;

  SELECT
    (v_count <= p_limit) AS allowed,
    v_count              AS hit_count,
    GREATEST(0, TIMESTAMPDIFF(SECOND, UTC_TIMESTAMP(6),
              DATE_ADD(v_window_start, INTERVAL p_window_secs SECOND))) AS retry_after_secs;
END$$

-- ---------------------------------------------------------------------
-- sp_rate_limit_prune
-- Housekeeping. Deletes counter rows whose window has long passed.
-- ---------------------------------------------------------------------
DROP PROCEDURE IF EXISTS sp_rate_limit_prune$$
CREATE PROCEDURE sp_rate_limit_prune(IN p_older_than_hours INT)
BEGIN
  DELETE FROM rate_limit_counters
  WHERE window_start < DATE_SUB(UTC_TIMESTAMP(6), INTERVAL p_older_than_hours HOUR)
  LIMIT 10000;
END$$

-- ---------------------------------------------------------------------
-- sp_user_find_by_email_bidx
--
-- The login lookup. Takes a fingerprint, returns ciphertext and the wrapped
-- key. The database has matched an email address without ever seeing one.
-- ---------------------------------------------------------------------
DROP PROCEDURE IF EXISTS sp_user_find_by_email_bidx$$
CREATE PROCEDURE sp_user_find_by_email_bidx(IN p_email_bidx BINARY(32))
BEGIN
  SELECT user_id, username, display_name, email_ct, password_hash,
         dek_wrapped, dek_key_version, kms_key_arn, status,
         failed_login_count, email_verified, created_at
  FROM users
  WHERE email_bidx = p_email_bidx
    AND status <> 'shredded'
  LIMIT 1;
END$$

-- ---------------------------------------------------------------------
-- sp_user_find_by_username
-- Same idea for the username, which is plaintext by explicit classification.
-- ---------------------------------------------------------------------
DROP PROCEDURE IF EXISTS sp_user_find_by_username$$
CREATE PROCEDURE sp_user_find_by_username(IN p_username VARCHAR(32))
BEGIN
  SELECT user_id, username, display_name, email_ct, password_hash,
         dek_wrapped, dek_key_version, kms_key_arn, status,
         failed_login_count, email_verified, created_at
  FROM users
  WHERE username = p_username
    AND status <> 'shredded'
  LIMIT 1;
END$$

-- ---------------------------------------------------------------------
-- sp_user_crypto_shred
--
-- Account deletion, and the clearest demonstration of the design.
--
-- Look at what this procedure does NOT do: it never touches campaigns,
-- characters, messages, or transcripts. It destroys the wrapped key and stops.
-- Every encrypted byte belonging to this user — in this database, in last
-- night snapshot, in a backup from March, in a copy an attacker already
-- stole — becomes permanently undecryptable at the moment this runs.
--
-- It also deletes the analytics mapping row, which severs the person from
-- their event history. The events remain and keep counting toward totals, but
-- nothing on earth can attribute them to anyone again.
-- ---------------------------------------------------------------------
DROP PROCEDURE IF EXISTS sp_user_crypto_shred$$
CREATE PROCEDURE sp_user_crypto_shred(IN p_user_id BINARY(16))
BEGIN
  DECLARE EXIT HANDLER FOR SQLEXCEPTION
  BEGIN
    ROLLBACK;
    RESIGNAL;
  END;

  START TRANSACTION;

    -- 1. Destroy the key. This is the deletion. Everything else is tidying.
    UPDATE users
       SET dek_wrapped = NULL,
           status      = 'shredded',
           shredded_at = UTC_TIMESTAMP(6)
     WHERE user_id = p_user_id;

    -- 2. Sever the link to analytics. Irreversible on purpose.
    DELETE FROM user_analytics_map WHERE user_id = p_user_id;

    -- 3. Revoke any live logins.
    UPDATE user_sessions
       SET revoked_at = UTC_TIMESTAMP(6)
     WHERE user_id = p_user_id AND revoked_at IS NULL;

    -- 4. Drop opt-in debug captures immediately rather than waiting 48 hours.
    DELETE FROM debug_captures WHERE user_id = p_user_id;

    -- 5. Record the completion. The detail column stays NULL because there is
    --    no longer a key to encrypt anything with.
    INSERT INTO account_activity_log (user_id, event_type, detail_ct)
    VALUES (p_user_id, 'deletion_completed', NULL);

  COMMIT;

  SELECT p_user_id AS user_id, 'shredded' AS status, UTC_TIMESTAMP(6) AS shredded_at;
END$$

-- ---------------------------------------------------------------------
-- sp_session_transcript_page
--
-- Fetches a page of a conversation. Returns ciphertext; the application
-- decrypts after it arrives. Ordering uses `seq`, a plain integer, so paging
-- never needs to look inside a message.
-- ---------------------------------------------------------------------
DROP PROCEDURE IF EXISTS sp_session_transcript_page$$
CREATE PROCEDURE sp_session_transcript_page(
  IN p_game_session_id BINARY(16),
  IN p_after_seq       INT,
  IN p_limit           INT
)
BEGIN
  SELECT message_id, seq, role, content_ct, input_mode,
         token_count, dek_key_version, created_at
  FROM messages
  WHERE game_session_id = p_game_session_id
    AND seq > p_after_seq
  ORDER BY seq ASC
  LIMIT p_limit;
END$$

-- ---------------------------------------------------------------------
-- sp_message_append
--
-- Appends one message and advances the turn counter atomically, so two
-- browser tabs cannot both claim sequence number 7.
-- p_content_ct arrives already encrypted by the application.
-- ---------------------------------------------------------------------
DROP PROCEDURE IF EXISTS sp_message_append$$
CREATE PROCEDURE sp_message_append(
  IN p_message_id      BINARY(16),
  IN p_game_session_id BINARY(16),
  IN p_user_id         BINARY(16),
  IN p_role            VARCHAR(16),
  IN p_content_ct      MEDIUMBLOB,
  IN p_input_mode      VARCHAR(8),
  IN p_token_count     INT,
  IN p_dek_key_version INT
)
BEGIN
  DECLARE v_seq INT DEFAULT 0;

  DECLARE EXIT HANDLER FOR SQLEXCEPTION
  BEGIN
    ROLLBACK;
    RESIGNAL;
  END;

  START TRANSACTION;

    SELECT COALESCE(MAX(seq), 0) + 1 INTO v_seq
    FROM messages
    WHERE game_session_id = p_game_session_id
    FOR UPDATE;

    INSERT INTO messages (message_id, game_session_id, user_id, seq, role,
                          content_ct, input_mode, token_count, dek_key_version)
    VALUES (p_message_id, p_game_session_id, p_user_id, v_seq, p_role,
            p_content_ct, p_input_mode, p_token_count, p_dek_key_version);

    UPDATE game_sessions
       SET turn_count = turn_count + IF(p_role = 'player', 1, 0)
     WHERE game_session_id = p_game_session_id;

  COMMIT;

  SELECT p_message_id AS message_id, v_seq AS seq;
END$$

-- ---------------------------------------------------------------------
-- sp_analytics_record
--
-- The analytics write path. Every parameter is an enumerated value, a number,
-- or a timestamp. There is no free-text parameter, so no free text can enter
-- the analytics plane through this door — and this door is the only one, as
-- the application role has no direct INSERT right on analytics_events.
--
-- MySQL rejects an out-of-range ENUM value in strict mode, so an unrecognised
-- event name fails the call loudly rather than being written as an empty
-- string. That is the "reject unknown fields at write time" requirement,
-- enforced by the database rather than trusted to the application.
-- ---------------------------------------------------------------------
DROP PROCEDURE IF EXISTS sp_analytics_record$$
CREATE PROCEDURE sp_analytics_record(
  IN p_analytics_id    BINARY(16),
  IN p_event_name      VARCHAR(32),
  IN p_country_code    CHAR(2),
  IN p_duration_bucket VARCHAR(8),
  IN p_turn_count      INT,
  IN p_feature         VARCHAR(24),
  IN p_error_category  VARCHAR(24),
  IN p_success         TINYINT
)
BEGIN
  INSERT INTO analytics_events
    (analytics_id, event_name, country_code, duration_bucket,
     turn_count, feature, error_category, success)
  VALUES
    (p_analytics_id, p_event_name, p_country_code, p_duration_bucket,
     p_turn_count, p_feature, p_error_category, p_success);
END$$

-- ---------------------------------------------------------------------
-- sp_analytics_rollup_day
--
-- Turns raw events into permanent counters. This runs nightly and is what
-- makes the 90-day raw retention survivable: the totals outlive the rows they
-- were computed from, and outlive any user who later deletes their account.
-- ---------------------------------------------------------------------
DROP PROCEDURE IF EXISTS sp_analytics_rollup_day$$
CREATE PROCEDURE sp_analytics_rollup_day(IN p_day DATE)
BEGIN
  -- Sessions started.
  INSERT INTO analytics_daily_aggregates (day, metric, dimension, value)
  SELECT p_day, 'sessions', '_all', COUNT(*)
    FROM analytics_events
   WHERE event_name = 'session_started' AND DATE(occurred_at) = p_day
  ON DUPLICATE KEY UPDATE value = VALUES(value), computed_at = UTC_TIMESTAMP(6);

  -- Distinct pseudonymous users active that day.
  INSERT INTO analytics_daily_aggregates (day, metric, dimension, value)
  SELECT p_day, 'active_users', '_all', COUNT(DISTINCT analytics_id)
    FROM analytics_events
   WHERE DATE(occurred_at) = p_day
  ON DUPLICATE KEY UPDATE value = VALUES(value), computed_at = UTC_TIMESTAMP(6);

  -- Turns taken, split by whether the player typed or spoke.
  INSERT INTO analytics_daily_aggregates (day, metric, dimension, value)
  SELECT p_day, 'turns', '_all', COUNT(*)
    FROM analytics_events
   WHERE event_name = 'turn_taken' AND DATE(occurred_at) = p_day
  ON DUPLICATE KEY UPDATE value = VALUES(value), computed_at = UTC_TIMESTAMP(6);

  INSERT INTO analytics_daily_aggregates (day, metric, dimension, value)
  SELECT p_day, 'voice_turns', '_all', COUNT(*)
    FROM analytics_events
   WHERE event_name = 'voice_input_used' AND DATE(occurred_at) = p_day
  ON DUPLICATE KEY UPDATE value = VALUES(value), computed_at = UTC_TIMESTAMP(6);

  -- Signups.
  INSERT INTO analytics_daily_aggregates (day, metric, dimension, value)
  SELECT p_day, 'signups', '_all', COUNT(*)
    FROM analytics_events
   WHERE event_name = 'signup_completed' AND DATE(occurred_at) = p_day
  ON DUPLICATE KEY UPDATE value = VALUES(value), computed_at = UTC_TIMESTAMP(6);

  -- Errors, broken down by category. The dimension can only ever hold one of
  -- the ENUM values from analytics_events, so it cannot become free text.
  INSERT INTO analytics_daily_aggregates (day, metric, dimension, value)
  SELECT p_day, 'errors', COALESCE(error_category, '_all'), COUNT(*)
    FROM analytics_events
   WHERE event_name = 'error_occurred' AND DATE(occurred_at) = p_day
   GROUP BY error_category
  ON DUPLICATE KEY UPDATE value = VALUES(value), computed_at = UTC_TIMESTAMP(6);

  -- Quota exhaustion, so you can see the Gemini free tier biting.
  INSERT INTO analytics_daily_aggregates (day, metric, dimension, value)
  SELECT p_day, 'quota_exhaustions', '_all', COUNT(*)
    FROM analytics_events
   WHERE event_name = 'quota_exhausted' AND DATE(occurred_at) = p_day
  ON DUPLICATE KEY UPDATE value = VALUES(value), computed_at = UTC_TIMESTAMP(6);

  SELECT p_day AS rolled_up_day, ROW_COUNT() AS rows_touched;
END$$

-- ---------------------------------------------------------------------
-- sp_analytics_purge_raw
-- Enforces the 90-day raw retention limit. Aggregates are untouched.
-- ---------------------------------------------------------------------
DROP PROCEDURE IF EXISTS sp_analytics_purge_raw$$
CREATE PROCEDURE sp_analytics_purge_raw(IN p_retention_days INT)
BEGIN
  DELETE FROM analytics_events
  WHERE occurred_at < DATE_SUB(UTC_TIMESTAMP(6), INTERVAL p_retention_days DAY)
  LIMIT 50000;
  SELECT ROW_COUNT() AS deleted_rows;
END$$

-- ---------------------------------------------------------------------
-- sp_debug_captures_expire
-- Hard-deletes opt-in prompt captures past their 48-hour deadline.
-- ---------------------------------------------------------------------
DROP PROCEDURE IF EXISTS sp_debug_captures_expire$$
CREATE PROCEDURE sp_debug_captures_expire()
BEGIN
  DELETE FROM debug_captures WHERE expires_at < UTC_TIMESTAMP(6) LIMIT 10000;

  UPDATE game_sessions
     SET debug_capture = 0, debug_capture_until = NULL
   WHERE debug_capture = 1 AND debug_capture_until < UTC_TIMESTAMP(6);

  SELECT ROW_COUNT() AS sessions_cleared;
END$$

-- ---------------------------------------------------------------------
-- sp_support_grant_open
--
-- Opens a time-boxed permission for a staff member to decrypt one user
-- records, and — in the same transaction — writes the disclosure into that
-- user own visible activity log. The two cannot come apart: if the audit
-- write fails, the grant is not created.
--
-- p_reason_ct arrives already encrypted under the audit key.
-- ---------------------------------------------------------------------
DROP PROCEDURE IF EXISTS sp_support_grant_open$$
CREATE PROCEDURE sp_support_grant_open(
  IN p_grant_id       BINARY(16),
  IN p_operator_id    VARCHAR(128),
  IN p_target_user_id BINARY(16),
  IN p_reason_ct      VARBINARY(2048),
  IN p_scope          VARCHAR(24),
  IN p_ttl_seconds    INT,
  IN p_detail_ct      VARBINARY(2048)
)
BEGIN
  DECLARE EXIT HANDLER FOR SQLEXCEPTION
  BEGIN
    ROLLBACK;
    RESIGNAL;
  END;

  START TRANSACTION;

    INSERT INTO support_access_grants
      (grant_id, operator_id, target_user_id, reason_ct, scope, expires_at)
    VALUES
      (p_grant_id, p_operator_id, p_target_user_id, p_reason_ct, p_scope,
       DATE_ADD(UTC_TIMESTAMP(6), INTERVAL p_ttl_seconds SECOND));

    -- The user is told. This is not optional and not a separate call.
    INSERT INTO account_activity_log (user_id, event_type, detail_ct)
    VALUES (p_target_user_id, 'support_access', p_detail_ct);

  COMMIT;

  SELECT p_grant_id AS grant_id,
         DATE_ADD(UTC_TIMESTAMP(6), INTERVAL p_ttl_seconds SECOND) AS expires_at;
END$$

-- ---------------------------------------------------------------------
-- sp_support_grant_check
-- Confirms a grant is live before any decryption happens.
-- ---------------------------------------------------------------------
DROP PROCEDURE IF EXISTS sp_support_grant_check$$
CREATE PROCEDURE sp_support_grant_check(
  IN p_grant_id BINARY(16),
  IN p_operator_id VARCHAR(128)
)
BEGIN
  SELECT grant_id, target_user_id, scope, granted_at, expires_at,
         (revoked_at IS NULL AND expires_at > UTC_TIMESTAMP(6)) AS is_live
  FROM support_access_grants
  WHERE grant_id = p_grant_id AND operator_id = p_operator_id
  LIMIT 1;
END$$

DELIMITER ;

INSERT INTO schema_migrations (version, checksum)
VALUES ('0002', 'set-by-migration-runner')
ON DUPLICATE KEY UPDATE applied_at = applied_at;
