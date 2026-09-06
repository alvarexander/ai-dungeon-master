/**
 * Who is signed in, held as signals.
 *
 * WHAT A SIGNAL IS
 *
 * A value that knows who is reading it. When it changes, everything that reads
 * it updates automatically — no event listeners, no manual refreshing, no
 * wondering whether the screen matches the data. Angular calls the readable
 * form a `Signal` and the writable form a `WritableSignal`.
 *
 * The pattern used throughout this application: keep the writable signal
 * private, and expose a read-only view. That way a component can display the
 * current user but cannot quietly reassign it — every change goes through a
 * method here, which is the only place that has to be got right.
 *
 * ═══════════════════════════════════════════════════════════════════════
 * PHASE 1 — WHAT IS REAL AND WHAT IS NOT
 * ═══════════════════════════════════════════════════════════════════════
 * Registration and password checking genuinely work: the backend hashes with
 * Argon2id and encrypts the email address.
 *
 * The **session** is stubbed. The token is an unsigned string, and the backend
 * believes whoever presents it. On top of that, a request with no token at all
 * is treated as the demo account, which is what lets you explore the interface
 * without signing in.
 *
 * The token is kept in `localStorage`, which is not where a real one should
 * live: anything stored there is readable by any script on the page, so a
 * cross-site scripting flaw would hand over the session. Phase 2 replaces it
 * with a signed token in a cookie the browser will not let scripts read at
 * all. Recorded here rather than in a ticket, because the next person to look
 * at this file is the one who needs to know.
 */

import { Injectable, computed, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { ApiClient } from '../api/api.client';
import {
  LoginRequest,
  LoginResponse,
  RegisterRequest,
  UserProfile,
} from '../api/api.types';

/** Where the placeholder token is kept. See the warning above. */
const TOKEN_STORAGE_KEY = 'dm.stub_token';

@Injectable({ providedIn: 'root' })
export class SessionStore {
  private readonly api = inject(ApiClient);

  private readonly _user = signal<UserProfile | null>(null);
  private readonly _token = signal<string | null>(readStoredToken());
  private readonly _loading = signal(false);
  private readonly _error = signal<string | null>(null);

  /** The signed-in account, or `null` if nobody is. */
  readonly user = this._user.asReadonly();

  /** True while a sign-in or registration is in flight. */
  readonly loading = this._loading.asReadonly();

  /** The most recent failure message, or `null`. */
  readonly error = this._error.asReadonly();

  /** True when a token is held. */
  readonly isAuthenticated = computed(() => this._token() !== null);

  /**
   * True when authentication is not really implemented.
   *
   * Drives the demo-mode banner. The point is that a stubbed screen should
   * never be mistaken for a working one — by a user, or by whoever picks this
   * up in six months.
   */
  readonly isStub = computed(() => this._user()?.is_stub ?? true);

  /** The name to greet the user by, falling back sensibly. */
  readonly displayName = computed(() => this._user()?.display_name ?? 'Adventurer');

  /**
   * Get the token for the Authorization header.
   *
   * @returns The stored token, or `null`. When `null`, the backend treats the
   *   request as the demo account, which is how the interface works before
   *   anyone signs in.
   */
  token(): string | null {
    return this._token();
  }

  /**
   * Fetch a cross-site request forgery token before anything else happens.
   *
   * The backend also sets this as a cookie automatically. Calling it
   * explicitly at startup turns one specific misconfiguration — frontend and
   * backend on unrelated domains, so the browser refuses to let us read the
   * cookie — into a clear message now, rather than mysterious 403 responses
   * on the first thing the user tries to do.
   *
   * @returns Nothing. Failures are logged, not thrown: the application is
   *   still perfectly usable for reading, and the specific error on the first
   *   write is more informative than a blank screen at startup.
   */
  async primeXsrfToken(): Promise<void> {
    try {
      await firstValueFrom(this.api.get('/api/v1/auth/csrf'));
    } catch {
      console.warn(
        '[session] Could not obtain a cross-site request forgery token. Saving anything ' +
          'will fail until this is resolved. Check that the backend is running.',
      );
    }
  }

  /**
   * Load the current account from the backend.
   *
   * In Phase 1 this succeeds even with no token, returning the demo account —
   * which is exactly what makes the interface explorable straight away.
   *
   * @returns Nothing. A failure leaves the user signed out.
   */
  async loadCurrentUser(): Promise<void> {
    try {
      const profile = await firstValueFrom(this.api.get<UserProfile>('/api/v1/auth/me'));
      this._user.set(profile);
    } catch {
      this._user.set(null);
    }
  }

  /**
   * Sign in.
   *
   * @param request The submitted credentials.
   * @returns True if it succeeded.
   */
  async login(request: LoginRequest): Promise<boolean> {
    this._loading.set(true);
    this._error.set(null);
    try {
      const response = await firstValueFrom(
        this.api.post<LoginResponse>('/api/v1/auth/login', request),
      );
      this.acceptSession(response);
      return true;
    } catch (error) {
      // The backend deliberately returns the same message whether the account
      // exists or the password is wrong, so that the sign-in form cannot be
      // used to discover who is registered. It is passed through unchanged.
      this._error.set(messageFrom(error));
      return false;
    } finally {
      this._loading.set(false);
    }
  }

  /**
   * Create an account and sign in.
   *
   * @param request The registration details.
   * @returns True if it succeeded.
   */
  async register(request: RegisterRequest): Promise<boolean> {
    this._loading.set(true);
    this._error.set(null);
    try {
      const profile = await firstValueFrom(
        this.api.post<UserProfile>('/api/v1/auth/register', request),
      );
      this._user.set(profile);
      const signedIn = await this.login({
        identifier: request.email,
        password: request.password,
      });
      return signedIn;
    } catch (error) {
      this._error.set(messageFrom(error));
      return false;
    } finally {
      this._loading.set(false);
    }
  }

  /**
   * Sign out and forget the token.
   *
   * @returns Nothing.
   */
  async logout(): Promise<void> {
    try {
      await firstValueFrom(this.api.post('/api/v1/auth/logout', {}));
    } catch {
      // Signing out must always work from the user's point of view. If the
      // network call fails, the local session is cleared anyway — leaving
      // someone apparently signed in because a request failed would be worse
      // than the token outliving the click.
    }
    this._token.set(null);
    this._user.set(null);
    safeRemove(TOKEN_STORAGE_KEY);
  }

  /**
   * Clear the current error message.
   *
   * @returns Nothing.
   */
  clearError(): void {
    this._error.set(null);
  }

  /**
   * Record a successful sign-in.
   *
   * @param response What the backend returned.
   */
  private acceptSession(response: LoginResponse): void {
    this._token.set(response.access_token);
    this._user.set(response.user);
    safeWrite(TOKEN_STORAGE_KEY, response.access_token);
  }
}

/**
 * Read the stored token, tolerating browsers that forbid storage.
 *
 * Private browsing modes and some privacy settings make `localStorage` throw
 * rather than return nothing. An unguarded read there would stop the
 * application starting at all.
 *
 * @returns The stored token, or `null`.
 */
function readStoredToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_STORAGE_KEY);
  } catch {
    return null;
  }
}

/**
 * Write to storage, ignoring failures.
 *
 * @param key The storage key.
 * @param value The value to store.
 */
function safeWrite(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    // Storage unavailable. The session then lasts until the tab is closed,
    // which is a degraded experience rather than a broken one.
  }
}

/**
 * Remove from storage, ignoring failures.
 *
 * @param key The storage key.
 */
function safeRemove(key: string): void {
  try {
    localStorage.removeItem(key);
  } catch {
    // Nothing useful to do.
  }
}

/**
 * Extract a displayable message from a thrown error.
 *
 * @param error Whatever was thrown.
 * @returns A message safe to show the user.
 */
function messageFrom(error: unknown): string {
  const failure = (error as { failure?: { message?: string } })?.failure;
  return failure?.message ?? 'Something went wrong. Please try again.';
}
