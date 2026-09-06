/**
 * The password reset screen.
 *
 * FULLY STUBBED — nothing here reaches the backend, because password reset
 * requires sending email, which Phase 1 does not do.
 *
 * WHY THE MESSAGE IS DELIBERATELY VAGUE
 * Look at the confirmation below: it says a link has been sent "if that
 * address has an account". That wording is not evasiveness, it is the design.
 *
 * A reset form that says "no account with that email" is a tool for checking
 * whether someone is registered — try an address, read the answer. Repeat with
 * a list. For an application where the whole point is that email addresses are
 * unreadable even to someone holding the database, leaking them through the
 * front door would be absurd.
 *
 * So the response is identical either way, and always will be.
 */

import { ChangeDetectionStrategy, Component, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';

import { Banner } from '../../shared/ui/banner';
import { StubNotice } from '../../shared/ui/stub-notice';

@Component({
  selector: 'app-forgot-password-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, RouterLink, Banner, StubNotice],
  styleUrl: './auth-layout.scss',
  template: `
    <div class="auth">
      <header class="auth__header">
        <h1>Reset your password</h1>
        <p class="muted">We will send you a link to choose a new one.</p>
      </header>

      <div class="auth__notice">
        <app-stub-notice
          detail="This screen sends nothing. Password reset needs email delivery, which is
                  not built yet, so the form below only demonstrates the flow."
        />
      </div>

      @if (submitted()) {
        <div class="auth__notice">
          <app-banner kind="success" title="Check your email">
            <p style="margin: 0">
              If that address has an account, a reset link is on its way. The link expires
              in one hour.
            </p>
            <p class="small muted" style="margin: 8px 0 0">
              That wording is deliberate: the same message appears whether or not an account
              exists, so this form cannot be used to find out who is registered.
            </p>
          </app-banner>
        </div>
      } @else {
        <form class="card auth__card" (ngSubmit)="submit()">
          <label class="field">
            <span class="field__label">Email</span>
            <input
              class="input"
              type="email"
              name="email"
              autocomplete="email"
              required
              [ngModel]="email()"
              (ngModelChange)="email.set($event)"
            />
          </label>
          <button type="submit" class="btn btn--primary btn--block" [disabled]="!email().includes('@')">
            Send reset link
          </button>
        </form>
      }

      <p class="auth__footer">
        <a routerLink="/sign-in">Back to sign in</a>
      </p>
    </div>
  `,
})
export class ForgotPasswordPage {
  /** The email address being entered. */
  readonly email = signal('');

  /** True once the form has been submitted. */
  readonly submitted = signal(false);

  /**
   * Pretend to send a reset link.
   *
   * @returns Nothing. Shows the confirmation without contacting the backend.
   */
  submit(): void {
    this.submitted.set(true);
  }
}
