/**
 * User preferences, and the code that makes them take effect.
 *
 * A note on classification worth carrying in your head: every field here is an
 * enumerated value or a boolean. None of it is personal data, which is why the
 * backend stores all of it in plaintext and can read it back without touching
 * an encryption key. It is a useful contrast with the campaign titles two
 * files over, which cannot even be sorted without decrypting them first.
 */

import { Injectable, computed, effect, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { ApiClient } from '../api/api.client';
import { UserSettings } from '../api/api.types';

/** What the interface uses before the backend has answered. */
const DEFAULTS: UserSettings = {
  narration_length: 'standard',
  dice_rolls_visible: true,
  content_filter: 'standard',
  voice_input_enabled: true,
  voice_autosend: false,
  theme: 'dark',
  reduce_motion: false,
  analytics_opt_in: true,
};

@Injectable({ providedIn: 'root' })
export class SettingsStore {
  private readonly api = inject(ApiClient);

  private readonly _settings = signal<UserSettings>(DEFAULTS);
  private readonly _saving = signal(false);
  private readonly _error = signal<string | null>(null);
  private readonly _savedAt = signal<number | null>(null);

  /** The current preferences. */
  readonly settings = this._settings.asReadonly();

  /** True while a change is being saved. */
  readonly saving = this._saving.asReadonly();

  /** The current failure message, or `null`. */
  readonly error = this._error.asReadonly();

  /** True briefly after a successful save, to show a confirmation. */
  readonly recentlySaved = computed(() => {
    const at = this._savedAt();
    return at !== null && Date.now() - at < 3000;
  });

  constructor() {
    // An effect runs whenever the signals it reads change. This one keeps the
    // page's appearance in step with the stored preference, so nothing has to
    // remember to apply the theme after a change.
    effect(() => {
      const settings = this._settings();
      applyTheme(settings.theme);
      document.documentElement.dataset['reduceMotion'] = String(settings.reduce_motion);
    });
  }

  /**
   * Load the preferences from the backend.
   *
   * @returns Nothing. On failure the defaults stay in place, which is a
   *   perfectly usable state — losing your theme preference should not stop
   *   you playing.
   */
  async load(): Promise<void> {
    try {
      const settings = await firstValueFrom(this.api.get<UserSettings>('/api/v1/settings'));
      this._settings.set(settings);
    } catch {
      this._settings.set(DEFAULTS);
    }
  }

  /**
   * Change one or more preferences and save them.
   *
   * The change is applied on screen immediately and saved in the background.
   * Waiting for the round trip before a theme toggle takes effect makes the
   * interface feel sluggish for no benefit — and if the save fails, the error
   * says so and the previous values are restored.
   *
   * @param changes The fields to change.
   * @returns Nothing.
   */
  async update(changes: Partial<UserSettings>): Promise<void> {
    const previous = this._settings();
    this._settings.set({ ...previous, ...changes });
    this._saving.set(true);
    this._error.set(null);

    try {
      const saved = await firstValueFrom(
        this.api.patch<UserSettings>('/api/v1/settings', changes),
      );
      this._settings.set(saved);
      this._savedAt.set(Date.now());
    } catch (error) {
      this._settings.set(previous);
      const failure = (error as { failure?: { message?: string } })?.failure;
      this._error.set(failure?.message ?? 'Could not save that change.');
    } finally {
      this._saving.set(false);
    }
  }
}

/**
 * Apply a theme to the page.
 *
 * @param theme The chosen theme. `system` follows the operating system's own
 *   light or dark setting, which is what most people actually want — it means
 *   the application changes with everything else on their machine at dusk.
 */
function applyTheme(theme: UserSettings['theme']): void {
  const root = document.documentElement;
  if (theme === 'system') {
    const prefersDark = window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? true;
    root.dataset['theme'] = prefersDark ? 'dark' : 'light';
  } else {
    root.dataset['theme'] = theme;
  }
}
