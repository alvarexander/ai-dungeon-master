/**
 * A message box for information, warnings, errors and confirmations.
 *
 * WHY THIS IS ONE COMPONENT RATHER THAN STYLING REPEATED EVERYWHERE
 * Messages are where an interface either helps someone or abandons them, and
 * consistency matters more than it looks. Putting them in one component means
 * every message in the application gets the same accessibility treatment —
 * described below — instead of whichever screen happened to be written by
 * someone who remembered.
 */

import { ChangeDetectionStrategy, Component, input } from '@angular/core';

/** How prominent and how alarming a banner should be. */
export type BannerKind = 'info' | 'warning' | 'danger' | 'success';

@Component({
  selector: 'app-banner',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div
      class="banner banner--{{ kind() }}"
      [attr.role]="kind() === 'danger' ? 'alert' : 'status'"
      [attr.aria-live]="kind() === 'danger' ? 'assertive' : 'polite'"
    >
      <span class="banner__icon" aria-hidden="true">{{ icon() }}</span>
      <div class="banner__body">
        @if (title()) {
          <strong class="banner__title">{{ title() }}</strong>
        }
        <ng-content />
      </div>
    </div>
  `,
})
export class Banner {
  /** Which kind of message this is. Drives colour, icon and urgency. */
  readonly kind = input<BannerKind>('info');

  /** An optional bold heading above the message. */
  readonly title = input<string>('');

  /**
   * The symbol shown beside the message.
   *
   * Deliberately paired with colour rather than replacing it. Roughly one man
   * in twelve cannot reliably distinguish red from green, so colour alone
   * cannot be the only thing carrying meaning.
   *
   * @returns The symbol for this kind of banner.
   */
  icon(): string {
    switch (this.kind()) {
      case 'danger':
        return '⚠';
      case 'warning':
        return '⚑';
      case 'success':
        return '✓';
      default:
        return 'ℹ';
    }
  }
}
