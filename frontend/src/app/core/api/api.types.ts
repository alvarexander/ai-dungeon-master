/**
 * The shapes the backend sends and expects.
 *
 * WHY THESE ARE HAND-WRITTEN RATHER THAN GENERATED
 *
 * The backend publishes a machine-readable description of itself at
 * `/openapi.json`, and tools exist that turn it into TypeScript automatically.
 * That is worth doing once the API stops changing daily. For now these are
 * written by hand, because a generated file is one nobody reads — and these
 * types are where the privacy classification of each field is recorded, which
 * is exactly the thing a person needs to read before using it.
 *
 * The comments below are the important part. They say which fields hold
 * personal data, so nobody has to guess before deciding whether it is safe to
 * log, cache, or put in a URL.
 *
 * **When the backend's models change, these must change with them.** The
 * mismatch will not be caught by the compiler, because the boundary between
 * two programs is not type-checked. It will show up as `undefined` at runtime.
 */

/** A backend error, always in this shape. */
export interface ApiErrorBody {
  error: {
    /** Stable machine-readable code. Branch on this, not on the message. */
    code: string;
    /** Plain-language explanation, safe to show. Never contains personal data. */
    message: string;
    /** The identifier to quote when reporting the problem. */
    correlation_id: string;
    /** Present on validation failures: which fields were wrong, never their values. */
    fields?: Array<{ field: string; problem: string }>;
  };
}

/** One page of a list. */
export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

/** A simple confirmation. */
export interface Acknowledgement {
  ok: boolean;
  detail: string;
}

// ---------------------------------------------------------------------------
// Authentication
// ---------------------------------------------------------------------------

/** The signed-in account. */
export interface UserProfile {
  /** Opaque random identifier. Safe to log and to put in a bug report. */
  user_id: string;
  /** Plaintext by classification — explicitly not personal data here. */
  username: string;
  /** Plaintext by classification. */
  display_name: string;
  /** PERSONAL DATA. Encrypted at rest; decrypted only for this response. Never log it. */
  email: string;
  email_verified: boolean;
  created_at: string;
  /** True while authentication is stubbed. Drives the demo-mode banner. */
  is_stub: boolean;
}

export interface RegisterRequest {
  username: string;
  display_name: string;
  /** PERSONAL DATA. */
  email: string;
  /** Never logged, never stored in the browser, never put in a URL. */
  password: string;
}

export interface LoginRequest {
  /** PERSONAL DATA when it is an email address. */
  identifier: string;
  password: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: UserProfile;
  /** True while authentication is stubbed. */
  is_stub: boolean;
}

// ---------------------------------------------------------------------------
// The Dungeon Master conversation
// ---------------------------------------------------------------------------

export type InputMode = 'typed' | 'voice';
export type MessageRole = 'player' | 'dungeon_master' | 'system';

export interface ChatTurnRequest {
  /** PERSONAL DATA. Players type real names into this. */
  message: string;
  session_id?: string | null;
  campaign_id?: string | null;
  input_mode: InputMode;
}

/** What one turn cost, so the free allowance is visible rather than mysterious. */
export interface TokenUsage {
  tokens_in: number;
  tokens_out: number;
  model_id: string;
  latency_ms: number;
}

export interface ChatTurnResponse {
  session_id: string;
  message_id: string;
  /** PERSONAL DATA — it quotes back what the player said. */
  reply: string;
  turn: number;
  usage: TokenUsage;
  /** True if something personal-looking was removed before the prompt was sent to Google. */
  scrubbed: boolean;
}

export interface TranscriptMessage {
  message_id: string;
  seq: number;
  role: MessageRole;
  /** PERSONAL DATA. */
  content: string;
  input_mode: InputMode;
  created_at: string;
}

// ---------------------------------------------------------------------------
// Campaigns
// ---------------------------------------------------------------------------

export type Ruleset = 'dnd5e' | 'freeform';
export type Tone = 'heroic' | 'gritty' | 'comedic' | 'horror' | 'mystery';

export interface CampaignSummary {
  campaign_id: string;
  /** PERSONAL DATA — free text the player wrote. Encrypted at rest. */
  title: string;
  ruleset: Ruleset;
  tone: Tone;
  status: 'active' | 'archived';
  character_count: number;
  updated_at: string;
}

export interface CampaignDetail extends CampaignSummary {
  /** PERSONAL DATA. */
  premise: string | null;
  created_at: string;
}

export interface CampaignCreateRequest {
  title: string;
  premise?: string | null;
  ruleset: Ruleset;
  tone: Tone;
}

// ---------------------------------------------------------------------------
// Characters
// ---------------------------------------------------------------------------

export type CharacterClass =
  | 'barbarian' | 'bard' | 'cleric' | 'druid' | 'fighter' | 'monk'
  | 'paladin' | 'ranger' | 'rogue' | 'sorcerer' | 'warlock' | 'wizard';

export interface AbilityScores {
  strength: number;
  dexterity: number;
  constitution: number;
  intelligence: number;
  wisdom: number;
  charisma: number;
}

export interface CharacterDetail {
  character_id: string;
  campaign_id: string;
  /** PERSONAL DATA — players use their own or a friend's real name here. */
  name: string;
  character_class: CharacterClass;
  level: number;
  ancestry: string | null;
  abilities: AbilityScores;
  hit_points_current: number;
  hit_points_max: number;
  /** PERSONAL DATA. */
  backstory: string | null;
  created_at: string;
  updated_at: string;
}

export interface CharacterCreateRequest {
  name: string;
  character_class: CharacterClass;
  level: number;
  ancestry?: string | null;
  abilities: AbilityScores;
  backstory?: string | null;
}

// ---------------------------------------------------------------------------
// Settings and the account
// ---------------------------------------------------------------------------

/**
 * User preferences.
 *
 * Every field is an enumerated value or a boolean — no free text anywhere.
 * That is why settings are stored in plaintext and can be read without any
 * decryption at all.
 */
export interface UserSettings {
  narration_length: 'brief' | 'standard' | 'rich';
  dice_rolls_visible: boolean;
  content_filter: 'family' | 'standard' | 'mature';
  voice_input_enabled: boolean;
  voice_autosend: boolean;
  theme: 'dark' | 'light' | 'system';
  reduce_motion: boolean;
  analytics_opt_in: boolean;
}

export interface ActivityEntry {
  event_type:
    | 'login' | 'logout' | 'password_changed' | 'email_changed'
    | 'support_access' | 'data_exported' | 'deletion_requested';
  detail: string | null;
  occurred_at: string;
}

export interface AccountDeletionResponse {
  user_id: string;
  shredded_at: string;
  detail: string;
}

// ---------------------------------------------------------------------------
// Voice
// ---------------------------------------------------------------------------

export interface TranscriptionResponse {
  /** PERSONAL DATA. Never logged. */
  transcript: string;
  duration_seconds: number;
  language: string;
  model: string;
  /** Always true. The audio was transcribed on our server and sent nowhere. */
  processed_locally: boolean;
}

/** The backend's readiness report, used by the developer diagnostics panel. */
export interface ReadinessReport {
  status: string;
  app_env: string;
  encryption_provider: string;
  repository_backend: string;
  auth_mode: string;
  model_id: string;
  stt_enabled: boolean;
  gemini_key_configured: boolean;
  correlation_id: string;
  warnings: string[];
}
