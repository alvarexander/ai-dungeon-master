/** Shown when an address does not match any screen. */

import { ChangeDetectionStrategy, Component } from '@angular/core';
import { RouterLink } from '@angular/router';

@Component({
  selector: 'app-not-found-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink],
  template: `
    <div class="page" style="text-align: center; padding-top: var(--space-8)">
      <h1 style="font-family: var(--font-narrative); font-size: 2rem">
        The passage ends in bare rock.
      </h1>
      <p class="page__lead" style="margin-inline: auto">
        There is nothing at this address. It may have been a typing slip, or something that
        used to be here has moved.
      </p>
      <p>
        <a routerLink="/play" class="btn btn--primary">Back to the game</a>
      </p>
      <p class="small muted" style="margin-top: var(--space-6)">
        If you reached this by refreshing the page on a live deployment, the web server may
        need a rewrite rule — see the Hostinger section of the deployment guide.
      </p>
    </div>
  `,
})
export class NotFoundPage {}
