/**
 * The registration screen.
 *
 * WHAT IS REAL HERE
 * Almost all of it. Submitting this form creates an account in which the
 * password is hashed with Argon2id and the email address is encrypted with a
 * key minted for that account alone — the same key whose destruction later
 * constitutes deletion. Only the session that follows is a placeholder.
 *
 * A DETAIL WORTH NOTICING
 * The failure message for "that email is taken" is identical to the one for
 * "that username is taken". Being more specific would turn this form into a
 * way of checking which email addresses have accounts, which is exactly the
 * disclosure the encrypted email column exists to prevent.
 */

import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';

import { SessionStore } from '../../core/state/session.store';
import { Banner } from '../../shared/ui/banner';
import { StubNotice } from '../../shared/ui/stub-notice';

/** The shortest password accepted. Matches the backend, which enforces it. */
const MIN_PASSWORD_LENGTH = 12;

@Component({
    selector: 'app-sign-up-page',
    changeDetection: ChangeDetectionStrategy.OnPush,
    imports: [FormsModule, RouterLink, Banner, StubNotice],
    styleUrl: './auth-layout.scss',
    template: `
        <div class="auth">
            <header class="auth__header">
                <h1>Create an account</h1>
                <p class="muted">So your campaigns are waiting when you come back.</p>
            </header>

            <div class="auth__notice">
                <app-stub-notice
                    detail="The session created after registering is a placeholder, and account data
                  is held in memory only — it is lost when the server restarts."
                    whatIsReal="Your password is hashed with Argon2id and never stored. Your email is
                      encrypted with a key belonging only to you."
                />
            </div>

            @if (error(); as message) {
                <div class="auth__notice">
                    <app-banner kind="danger"
                        ><p style="margin: 0">{{ message }}</p></app-banner
                    >
                </div>
            }

            <form class="card auth__card" (ngSubmit)="submit()">
                <label class="field">
                    <span class="field__label">Username</span>
                    <input
                        class="input"
                        name="username"
                        autocomplete="username"
                        required
                        [ngModel]="username()"
                        (ngModelChange)="username.set($event)"
                    />
                    <span class="field__hint">
                        Letters, numbers, hyphen and underscore. This is stored as ordinary readable text, so choose
                        something you are happy to be visible.
                    </span>
                </label>

                <label class="field">
                    <span class="field__label">Display name</span>
                    <input
                        class="input"
                        name="displayName"
                        autocomplete="nickname"
                        required
                        [ngModel]="displayName()"
                        (ngModelChange)="displayName.set($event)"
                    />
                </label>

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
                    <span class="field__hint">
                        Encrypted before it is stored. Even someone holding a complete copy of the database cannot read
                        it.
                    </span>
                </label>

                <label class="field">
                    <span class="field__label">Password</span>
                    <input
                        class="input"
                        type="password"
                        name="password"
                        autocomplete="new-password"
                        required
                        [attr.aria-invalid]="passwordTooShort()"
                        [ngModel]="password()"
                        (ngModelChange)="password.set($event)"
                    />
                    @if (passwordTooShort()) {
                        <span class="field__error">
                            At least {{ minLength }} characters. Length matters far more than punctuation — a phrase you
                            can remember beats a short jumble you cannot.
                        </span>
                    } @else {
                        <span class="field__hint">
                            At least {{ minLength }} characters. Hashed with Argon2id, which is deliberately slow and
                            memory-hungry so that a stolen database cannot be cracked at speed.
                        </span>
                    }
                </label>

                <button type="submit" class="btn btn--primary btn--block" [disabled]="!canSubmit()">
                    {{ loading() ? 'Creating your account…' : 'Create account' }}
                </button>
            </form>

            <p class="auth__footer">Already have an account? <a routerLink="/sign-in">Sign in</a></p>
        </div>
    `
})
export class SignUpPage {
    private readonly session = inject(SessionStore);
    private readonly router = inject(Router);

    /** The shortest acceptable password, shown in the hint text. */
    readonly minLength = MIN_PASSWORD_LENGTH;

    readonly username = signal('');
    readonly displayName = signal('');
    readonly email = signal('');
    readonly password = signal('');

    /** True while the request is in flight. */
    readonly loading = this.session.loading;

    /** The current failure message, or `null`. */
    readonly error = this.session.error;

    /** True when a password has been started but is still too short. */
    readonly passwordTooShort = computed(
        () => this.password().length > 0 && this.password().length < MIN_PASSWORD_LENGTH
    );

    /** True when every field is filled in acceptably. */
    readonly canSubmit = computed(
        () =>
            !this.loading() &&
            this.username().trim().length >= 3 &&
            this.displayName().trim().length > 0 &&
            this.email().includes('@') &&
            this.password().length >= MIN_PASSWORD_LENGTH
    );

    /**
     * Submit the form.
     *
     * @returns Nothing. On success the player is taken to the play screen.
     */
    async submit(): Promise<void> {
        const success = await this.session.register({
            username: this.username().trim(),
            display_name: this.displayName().trim(),
            email: this.email().trim(),
            password: this.password()
        });
        if (success) {
            this.password.set('');
            await this.router.navigate(['/play']);
        }
    }
}
