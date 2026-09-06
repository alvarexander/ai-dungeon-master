/**
 * The account screen: profile, activity, and deletion.
 *
 * THE ACTIVITY LOG IS NOT DECORATION
 * The design commits to telling people when their data is read. If support
 * ever decrypts someone's records, an entry appears in the list below saying
 * so, together with the reason that was given. This screen is where that
 * promise is kept, which is why it exists even though Phase 1 has almost
 * nothing to put in it yet.
 */

import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import { ApiClient } from '../../core/api/api.client';
import { AccountDeletionResponse, ActivityEntry } from '../../core/api/api.types';
import { SessionStore } from '../../core/state/session.store';
import { Banner } from '../../shared/ui/banner';
import { StubNotice } from '../../shared/ui/stub-notice';

@Component({
  selector: 'app-account-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, RouterLink, Banner, StubNotice],
  template: `
    <div class="page page--narrow">
      <header class="page__header">
        <h1>Account</h1>
      </header>

      @if (user(); as profile) {
        <section class="card">
          <h2>Your details</h2>
          <dl class="details">
            <dt>Display name</dt>
            <dd>{{ profile.display_name }}</dd>

            <dt>Username</dt>
            <dd>
              {{ profile.username }}
              <span class="small muted">stored as ordinary readable text</span>
            </dd>

            <dt>Email</dt>
            <dd>
              {{ profile.email }}
              <span class="small muted">
                encrypted at rest — decrypted only to show you this line
              </span>
            </dd>

            <dt>Account identifier</dt>
            <dd>
              <code class="mono">{{ profile.user_id }}</code>
              <span class="small muted">
                A random value that reveals nothing about you. Safe to quote in a bug report.
              </span>
            </dd>
          </dl>
        </section>
      }

      <section class="card">
        <h2>Account activity</h2>
        <p class="small muted">
          Everything that has happened to your account, including any occasion on which
          support has decrypted your data, and the reason they gave. If we look, you are
          told.
        </p>

        @if (activity().length === 0) {
          <p class="muted">Nothing to show yet.</p>
        } @else {
          <ul class="activity">
            @for (entry of activity(); track entry.occurred_at) {
              <li>
                <strong>{{ label(entry.event_type) }}</strong>
                <span class="small muted">{{ entry.occurred_at }}</span>
                @if (entry.detail) {
                  <p class="small" style="margin: 4px 0 0">{{ entry.detail }}</p>
                }
              </li>
            }
          </ul>
        }
      </section>

      <section class="card danger-zone">
        <h2>Delete your account</h2>

        <app-banner kind="danger" title="This cannot be undone by anyone, including us">
          <p style="margin: 0 0 8px">
            Deleting your account destroys the encryption key that protects your data. At
            that moment everything you have written becomes permanently unreadable — in the
            live system, and in every backup, including backups nobody can reach into and
            edit.
          </p>
          <p style="margin: 0" class="small">
            This is called crypto-shredding. The data is not gone through and erased; the
            only key that can read it is destroyed, which achieves the same thing everywhere
            at once and cannot be reversed.
          </p>
        </app-banner>

        @if (deletionResult(); as result) {
          <app-banner kind="success" title="Your account has been deleted">
            <p style="margin: 0">{{ result.detail }}</p>
          </app-banner>
        } @else {
          <label class="field" style="margin-top: var(--space-4)">
            <span class="field__label">Type your username to confirm</span>
            <input
              class="input"
              [placeholder]="user()?.username ?? ''"
              [ngModel]="confirmName()"
              (ngModelChange)="confirmName.set($event)"
              name="confirmName"
            />
          </label>

          <label class="toggle">
            <input
              type="checkbox"
              [checked]="understood()"
              (change)="understood.set(!understood())"
            />
            <span class="small">
              I understand this is permanent, and that not even the people running this
              service can recover my campaigns afterwards.
            </span>
          </label>

          @if (deleteError(); as message) {
            <app-banner kind="danger"><p style="margin: 0">{{ message }}</p></app-banner>
          }

          <button
            type="button"
            class="btn btn--danger"
            [disabled]="!canDelete()"
            (click)="deleteAccount()"
          >
            {{ deleting() ? 'Deleting…' : 'Permanently delete my account' }}
          </button>
        }
      </section>

      <section class="card">
        <h2>Password and email</h2>
        <app-stub-notice
          detail="Changing your password or email address is not implemented yet. Both need
                  email delivery to confirm the change, which Phase 1 does not have."
        />
      </section>

      <p><a routerLink="/privacy">What happens to your data</a></p>
    </div>
  `,
  styles: [
    `
      .page--narrow {
        max-width: 680px;
      }
      section {
        margin-bottom: var(--space-4);
      }
      .details {
        display: grid;
        grid-template-columns: max-content 1fr;
        gap: var(--space-2) var(--space-4);
        margin: 0;
      }
      .details dt {
        color: var(--ink-muted);
        font-size: 0.9rem;
      }
      .details dd {
        margin: 0;
        min-width: 0;
        overflow-wrap: anywhere;
      }
      .details dd span {
        display: block;
      }
      .activity {
        list-style: none;
        padding: 0;
        margin: 0;
      }
      .activity li {
        padding: var(--space-3) 0;
        border-top: 1px solid var(--border);
      }
      .activity li:first-child {
        border-top: none;
      }
      .activity strong {
        margin-right: var(--space-2);
      }
      .danger-zone {
        border-color: var(--danger);
      }
      .toggle {
        display: flex;
        gap: var(--space-3);
        align-items: flex-start;
        margin-bottom: var(--space-4);
        cursor: pointer;
      }
      .toggle input {
        margin-top: 3px;
      }
    `,
  ],
})
export class AccountPage {
  private readonly api = inject(ApiClient);
  private readonly session = inject(SessionStore);

  readonly user = this.session.user;
  readonly activity = signal<ActivityEntry[]>([]);
  readonly confirmName = signal('');
  readonly understood = signal(false);
  readonly deleting = signal(false);
  readonly deleteError = signal<string | null>(null);
  readonly deletionResult = signal<AccountDeletionResponse | null>(null);

  /**
   * True only when the confirmation is complete.
   *
   * Both the typed username and the tickbox are required. This is deliberate
   * friction on an action that nobody — not the user, not us — can reverse.
   */
  readonly canDelete = computed(
    () =>
      !this.deleting() &&
      this.understood() &&
      this.confirmName().trim().length > 0 &&
      this.confirmName().trim() === this.user()?.username,
  );

  constructor() {
    void this.loadActivity();
  }

  /**
   * Turn a stored event type into something readable.
   *
   * @param type The event type from the backend.
   * @returns A human-readable label.
   */
  label(type: ActivityEntry['event_type']): string {
    const labels: Record<ActivityEntry['event_type'], string> = {
      login: 'Signed in',
      logout: 'Signed out',
      password_changed: 'Password changed',
      email_changed: 'Email changed',
      support_access: 'Support accessed your data',
      data_exported: 'Data exported',
      deletion_requested: 'Deletion requested',
    };
    return labels[type];
  }

  /**
   * Load the activity list.
   *
   * @returns Nothing. A failure leaves the list empty rather than showing an
   *   error, because an empty activity list is not a problem the user can act
   *   on.
   */
  private async loadActivity(): Promise<void> {
    try {
      const entries = await firstValueFrom(
        this.api.get<ActivityEntry[]>('/api/v1/account/activity'),
      );
      this.activity.set(entries);
    } catch {
      this.activity.set([]);
    }
  }

  /**
   * Delete the account by destroying its encryption key.
   *
   * @returns Nothing.
   */
  async deleteAccount(): Promise<void> {
    this.deleting.set(true);
    this.deleteError.set(null);
    try {
      const result = await firstValueFrom(
        this.api.post<AccountDeletionResponse>('/api/v1/account/delete', {
          confirm_username: this.confirmName().trim(),
          understood: true,
        }),
      );
      this.deletionResult.set(result);
      await this.session.logout();
    } catch (error) {
      const failure = (error as { failure?: { message?: string } })?.failure;
      this.deleteError.set(failure?.message ?? 'Could not delete the account.');
    } finally {
      this.deleting.set(false);
    }
  }
}
