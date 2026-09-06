/**
 * Marks a screen whose behaviour is designed but not yet implemented.
 *
 * WHY THIS EXISTS AT ALL
 * Several screens in this application look finished and are not. The sign-in
 * form validates properly and looks exactly like a working one, but the
 * session it creates is a placeholder that the backend does not verify.
 *
 * A mock that cannot be told apart from working software is a trap — for a
 * user who assumes their account is protected, and for whoever picks this up
 * later and assumes it is done. So every stubbed screen says so, on the screen,
 * in plain language, with a note about what specifically is not real.
 */

import { ChangeDetectionStrategy, Component, input } from '@angular/core';

import { Banner } from './banner';

@Component({
  selector: 'app-stub-notice',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Banner],
  template: `
    <app-banner kind="warning" title="This screen is a preview">
      <p style="margin: 0">{{ detail() }}</p>
      @if (whatIsReal()) {
        <p style="margin: 8px 0 0" class="small">
          <strong>What genuinely works:</strong> {{ whatIsReal() }}
        </p>
      }
    </app-banner>
  `,
})
export class StubNotice {
  /** What is not implemented, stated plainly. */
  readonly detail = input.required<string>();

  /**
   * What on this screen is genuinely working.
   *
   * Included because "this is a preview" on its own is misleading in the other
   * direction — on most of these screens a good deal is real, and it is worth
   * saying which parts.
   */
  readonly whatIsReal = input<string>('');
}
