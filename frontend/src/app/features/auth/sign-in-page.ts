/**
 * The sign-in screen.
 *
 * ═══════════════════════════════════════════════════════════════════════
 * WHAT IS REAL HERE AND WHAT IS NOT
 * ═══════════════════════════════════════════════════════════════════════
 * More is real than "stubbed" suggests, and the distinction matters:
 *
 * **Genuinely working.** The credentials go to the backend. The password is
 * checked against an Argon2id hash. The email address is found through a keyed
 * fingerprint, never by comparing addresses. Failures are rate limited to five
 * attempts per fifteen minutes, and every failure returns the same message
 * whether or not the account exists — so this form cannot be used to discover
 * who is registered.
 *
 * **Not real.** The session it produces. The token is unsigned and the backend
 * believes whoever presents it. There is no expiry and no revocation.
 *
 * That is why the backend refuses to start in production while authentication
 * is in this state, and why this screen says so out loud.
 */

import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';

import { SessionStore } from '../../core/state/session.store';
import { Banner } from '../../shared/ui/banner';
import { StubNotice } from '../../shared/ui/stub-notice';

@Component({
    selector: 'app-sign-in-page',
    changeDetection: ChangeDetectionStrategy.OnPush,
    imports: [FormsModule, RouterLink, Banner, StubNotice],
    styleUrl: './auth-layout.scss',
    template: `
        <div class="auth">
            <header class="auth__header">
                <h1>Sign in</h1>
                <p class="muted">Pick up where your last campaign left off.</p>
            </header>

            <div class="auth__notice">
                <app-stub-notice
                    detail="Signing in does not yet create a real, protected session — the token
                  handed out is a placeholder that is not verified."
                    whatIsReal="Your password is genuinely checked against an Argon2id hash, your
                      email address is looked up without ever being readable, and sign-in
                      attempts are rate limited."
                />
            </div>

            @if (error(); as message) {
                <div class="auth__notice">
                    <app-banner kind="danger">
                        <p style="margin: 0">{{ message }}</p>
                    </app-banner>
                </div>
            }

            <form class="card auth__card" (ngSubmit)="submit()">
                <label class="field">
                    <span class="field__label">Email or username</span>
                    <input
                        class="input"
                        name="identifier"
                        autocomplete="username"
                        required
                        [ngModel]="identifier()"
                        (ngModelChange)="identifier.set($event)"
                    />
                </label>

                <label class="field">
                    <span class="field__label">Password</span>
                    <input
                        class="input"
                        type="password"
                        name="password"
                        autocomplete="current-password"
                        required
                        [ngModel]="password()"
                        (ngModelChange)="password.set($event)"
                    />
                    <span class="field__hint">
                        <a routerLink="/forgot-password">Forgotten your password?</a>
                    </span>
                </label>

                <button type="submit" class="btn btn--primary btn--block" [disabled]="loading()">
                    {{ loading() ? 'Signing in…' : 'Sign in' }}
                </button>
            </form>

            <p class="auth__footer">
                No account yet? <a routerLink="/sign-up">Create one</a>
                <br />
                <a routerLink="/play">Or carry on in demo mode</a>
            </p>
        </div>
    `
})
export class SignInPage {
    private readonly session = inject(SessionStore);
    private readonly router = inject(Router);

    /** The email address or username being entered. */
    readonly identifier = signal('');

    /** The password being entered. Never logged and never stored. */
    readonly password = signal('');

    /** True while the request is in flight. */
    readonly loading = this.session.loading;

    /** The current failure message, or `null`. */
    readonly error = this.session.error;

    /**
     * Submit the form.
     *
     * @returns Nothing. On success the player is taken to the play screen.
     */
    async submit(): Promise<void> {
        const success = await this.session.login({
            identifier: this.identifier(),
            password: this.password()
        });
        if (success) {
            // Cleared immediately on success so the password does not sit in memory
            // any longer than it has to.
            this.password.set('');
            await this.router.navigate(['/play']);
        }
    }
}
