/**
 * The application shell: the navigation and layout that surrounds every screen.
 *
 * Angular renders whichever screen matches the current address into the
 * `<router-outlet>` below. Everything outside that outlet — the header, the
 * navigation, the demo-mode banner — is here, so it is written once rather
 * than repeated on every page.
 */

import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

import { APP_CONFIG } from './core/app-config';
import { SessionStore } from './core/state/session.store';
import { SettingsStore } from './core/state/settings.store';

@Component({
  selector: 'app-root',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterOutlet, RouterLink, RouterLinkActive],
  templateUrl: './app.html',
  styleUrl: './app.scss',
})
export class App {
  private readonly session = inject(SessionStore);
  private readonly settings = inject(SettingsStore);
  private readonly config = inject(APP_CONFIG);

  /** Whether the navigation is open on a narrow screen. */
  readonly menuOpen = signal(false);

  /** The name to greet the user by. */
  readonly displayName = this.session.displayName;

  /** True when authentication is stubbed, which drives the demo banner. */
  readonly isStub = this.session.isStub;

  /** True when this build is not pointed at production. */
  readonly isLocal = computed(() => this.config.environment !== 'production');

  constructor() {
    // Three things have to happen before the interface is usable, and they are
    // independent of each other, so they run together rather than in sequence.
    //
    // `primeXsrfToken` is first among equals: without a token, every save in
    // the application would fail. Doing it at startup means the very first
    // thing a user tries already works.
    void Promise.all([
      this.session.primeXsrfToken(),
      this.session.loadCurrentUser(),
      this.settings.load(),
    ]);
  }

  /**
   * Open or close the navigation on a narrow screen.
   *
   * @returns Nothing.
   */
  toggleMenu(): void {
    this.menuOpen.update((open) => !open);
  }

  /**
   * Close the navigation.
   *
   * Called after following a link, so the menu does not stay open on top of
   * the page the user just asked for.
   *
   * @returns Nothing.
   */
  closeMenu(): void {
    this.menuOpen.set(false);
  }

  /**
   * Sign out and return to the sign-in screen.
   *
   * @returns Nothing.
   */
  async signOut(): Promise<void> {
    await this.session.logout();
    this.closeMenu();
    window.location.assign('/sign-in');
  }
}
