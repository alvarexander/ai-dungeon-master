/**
 * User settings.
 *
 * Every setting here is an enumerated value or a switch. None of it is
 * personal data, which is why the backend stores all of it in readable form
 * and can load this page without touching an encryption key at all. It is a
 * useful contrast with campaign titles, which cannot even be sorted without
 * being decrypted first.
 */

import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { RouterLink } from '@angular/router';

import { UserSettings } from '../../core/api/api.types';
import { SettingsStore } from '../../core/state/settings.store';
import { Banner } from '../../shared/ui/banner';

@Component({
  selector: 'app-settings-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, Banner],
  template: `
    <div class="page page--narrow">
      <header class="page__header">
        <h1>Settings</h1>
        <p class="page__lead">Changes save themselves as you make them.</p>
      </header>

      @if (error(); as message) {
        <app-banner kind="danger"><p style="margin: 0">{{ message }}</p></app-banner>
      }
      @if (recentlySaved()) {
        <app-banner kind="success"><p style="margin: 0">Saved.</p></app-banner>
      }

      <section class="card">
        <h2>The Dungeon Master</h2>

        <label class="field">
          <span class="field__label">How much narration</span>
          <select
            class="select"
            [value]="settings().narration_length"
            (change)="set({ narration_length: value($event) })"
          >
            <option value="brief">Brief — one short paragraph a turn</option>
            <option value="standard">Standard — two or three paragraphs</option>
            <option value="rich">Rich — more description and sensory detail</option>
          </select>
        </label>

        <label class="field">
          <span class="field__label">Content</span>
          <select
            class="select"
            [value]="settings().content_filter"
            (change)="set({ content_filter: value($event) })"
          >
            <option value="family">Suitable for all ages</option>
            <option value="standard">As a published adventure</option>
            <option value="mature">Adult themes and moral complexity</option>
          </select>
          <span class="field__hint">
            Steers what the Dungeon Master will describe. It is an instruction, not a
            guarantee — the model has its own safety limits on top of this.
          </span>
        </label>

        <label class="toggle">
          <input
            type="checkbox"
            [checked]="settings().dice_rolls_visible"
            (change)="set({ dice_rolls_visible: checked($event) })"
          />
          <span>
            <strong>Show dice rolls</strong>
            <span class="small muted">
              Off keeps the results behind the screen, as a human Dungeon Master might.
            </span>
          </span>
        </label>
      </section>

      <section class="card">
        <h2>Voice</h2>

        <label class="toggle">
          <input
            type="checkbox"
            [checked]="settings().voice_input_enabled"
            (change)="set({ voice_input_enabled: checked($event) })"
          />
          <span>
            <strong>Voice input</strong>
            <span class="small muted">
              Shows the microphone button. Recordings are transcribed on our own server and
              are never sent to Google or anyone else.
            </span>
          </span>
        </label>

        <label class="toggle">
          <input
            type="checkbox"
            [checked]="settings().voice_autosend"
            [disabled]="!settings().voice_input_enabled"
            (change)="set({ voice_autosend: checked($event) })"
          />
          <span>
            <strong>Send as soon as I stop speaking</strong>
            <span class="small muted">
              Off lets you read the transcription and correct it first.
            </span>
          </span>
        </label>
      </section>

      <section class="card">
        <h2>Appearance</h2>

        <label class="field">
          <span class="field__label">Theme</span>
          <select class="select" [value]="settings().theme" (change)="set({ theme: value($event) })">
            <option value="dark">Dark</option>
            <option value="light">Light</option>
            <option value="system">Match my system</option>
          </select>
        </label>

        <label class="toggle">
          <input
            type="checkbox"
            [checked]="settings().reduce_motion"
            (change)="set({ reduce_motion: checked($event) })"
          />
          <span>
            <strong>Reduce motion</strong>
            <span class="small muted">
              Removes animation. This is switched on automatically if your operating system
              already asks for it.
            </span>
          </span>
        </label>
      </section>

      <section class="card">
        <h2>Privacy</h2>

        <label class="toggle">
          <input
            type="checkbox"
            [checked]="settings().analytics_opt_in"
            (change)="set({ analytics_opt_in: checked($event) })"
          />
          <span>
            <strong>Contribute anonymous usage counts</strong>
            <span class="small muted">
              Counts of things like sessions started and turns taken. Recorded against a
              random identifier unrelated to your account, with no free text — there is
              physically no field in the analytics database that could hold anything you
              typed.
            </span>
          </span>
        </label>

        <p class="small muted" style="margin-bottom: 0">
          For the full picture of what is stored and what leaves this server, see
          <a routerLink="/privacy">Your data</a>.
        </p>
      </section>
    </div>
  `,
  styles: [
    `
      .page--narrow {
        max-width: 640px;
      }
      section {
        margin-bottom: var(--space-4);
      }
      .toggle {
        display: flex;
        gap: var(--space-3);
        align-items: flex-start;
        padding: var(--space-3) 0;
        cursor: pointer;
        border-top: 1px solid var(--border);
      }
      .toggle:first-of-type {
        border-top: none;
      }
      .toggle input {
        margin-top: 5px;
        flex-shrink: 0;
      }
      .toggle span span {
        display: block;
      }
    `,
  ],
})
export class SettingsPage {
  private readonly store = inject(SettingsStore);

  readonly settings = this.store.settings;
  readonly error = this.store.error;
  readonly recentlySaved = this.store.recentlySaved;

  /**
   * Save a change.
   *
   * @param changes The fields to change. Everything else is left alone.
   */
  set(changes: Partial<UserSettings>): void {
    void this.store.update(changes);
  }

  /**
   * Read the value from a dropdown's change event.
   *
   * @param event The change event.
   * @returns The selected value.
   */
  value(event: Event): never {
    return (event.target as HTMLSelectElement).value as never;
  }

  /**
   * Read the state from a checkbox's change event.
   *
   * @param event The change event.
   * @returns Whether the box is now ticked.
   */
  checked(event: Event): boolean {
    return (event.target as HTMLInputElement).checked;
  }
}
