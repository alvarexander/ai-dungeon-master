/**
 * The campaign list.
 *
 * A DETAIL THAT SHOWS THE PRIVACY DESIGN IN EVERYDAY USE
 * The sort control below offers "most recent" and "by title". Only the first
 * can be done by the database: campaign titles are encrypted, so the database
 * cannot read them, let alone put them in order. Sorting by title happens in
 * the browser, after this list has been decrypted — which is also why the
 * list is fetched in pages rather than all at once.
 *
 * It is a small cost, and it is the shape of every cost this design imposes:
 * anything that requires reading personal data has to happen where the keys
 * are, which is never the database.
 */

import { TitleCasePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import { CampaignStore } from '../../core/state/campaign.store';
import { Banner } from '../../shared/ui/banner';

@Component({
  selector: 'app-campaign-list-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, Banner, TitleCasePipe],
  template: `
    <div class="page">
      <header class="page__header row row--wrap">
        <div>
          <h1>Campaigns</h1>
          <p class="page__lead">Each campaign is a separate story with its own characters.</p>
        </div>
        <span class="spacer"></span>
        <a routerLink="/campaigns/new" class="btn btn--primary">New campaign</a>
      </header>

      @if (error(); as message) {
        <app-banner kind="danger"><p style="margin: 0">{{ message }}</p></app-banner>
      }

      @if (loading()) {
        <p class="muted">Loading…</p>
      } @else if (isEmpty()) {
        <div class="card empty">
          <h2>No campaigns yet</h2>
          <p class="muted">
            A campaign holds one ongoing story — its premise, its characters, and everything
            that has happened so far. You can also just start playing and one will be created
            for you.
          </p>
          <div class="row">
            <a routerLink="/campaigns/new" class="btn btn--primary">Create a campaign</a>
            <a routerLink="/play" class="btn">Just start playing</a>
          </div>
        </div>
      } @else {
        <div class="row row--wrap sort-row">
          <span class="small muted">Sort by</span>
          <button
            type="button"
            class="btn btn--ghost btn--sm"
            [class.is-selected]="sortBy() === 'recent'"
            (click)="store.setSort('recent')"
          >
            Most recent
          </button>
          <button
            type="button"
            class="btn btn--ghost btn--sm"
            [class.is-selected]="sortBy() === 'title'"
            (click)="store.setSort('title')"
          >
            Title
          </button>
          <span class="small muted sort-note">
            Sorting by title happens in your browser — the server cannot read encrypted titles.
          </span>
        </div>

        <div class="grid">
          @for (campaign of campaigns(); track campaign.campaign_id) {
            <article class="card campaign">
              <h2 class="campaign__title">{{ campaign.title }}</h2>
              <p class="small muted campaign__meta">
                {{ campaign.tone | titlecase }} · {{ campaign.ruleset === 'dnd5e' ? 'D&D 5e' : 'Freeform' }}
                · {{ campaign.character_count }}
                {{ campaign.character_count === 1 ? 'character' : 'characters' }}
              </p>
              <div class="row row--wrap campaign__actions">
                <a [routerLink]="['/play']" class="btn btn--primary btn--sm">Play</a>
                <a [routerLink]="['/campaigns', campaign.campaign_id, 'characters']" class="btn btn--sm">
                  Characters
                </a>
                <span class="spacer"></span>
                <button
                  type="button"
                  class="btn btn--ghost btn--sm btn--danger"
                  (click)="confirmDelete(campaign.campaign_id)"
                >
                  {{ pendingDelete() === campaign.campaign_id ? 'Really delete?' : 'Delete' }}
                </button>
              </div>
            </article>
          }
        </div>
      }
    </div>
  `,
  styles: [
    `
      .empty { text-align: center; max-width: 560px; margin: 0 auto; }
      .empty .row { justify-content: center; }
      .sort-row { margin-bottom: var(--space-4); }
      .sort-note { flex-basis: 100%; }
      .is-selected { color: var(--accent-strong); background: var(--surface-raised); }
      .campaign__title { font-family: var(--font-narrative); }
      .campaign__meta { margin-bottom: var(--space-4); }
      .campaign__actions { margin-top: auto; }
      .campaign { display: flex; flex-direction: column; }
    `,
  ],
})
export class CampaignListPage {
  readonly store = inject(CampaignStore);

  /** The campaigns, in the chosen order. */
  readonly campaigns = this.store.sortedCampaigns;
  readonly loading = this.store.loading;
  readonly error = this.store.error;
  readonly isEmpty = this.store.isEmpty;
  readonly sortBy = this.store.sortBy;

  /**
   * Which campaign is one click away from being deleted.
   *
   * A two-step confirmation rather than a dialogue box. Deleting a campaign
   * destroys a story somebody has spent hours in, so a single misplaced click
   * should not be enough — but a modal for every delete is heavy-handed.
   */
  readonly pendingDelete = signal<string | null>(null);

  constructor() {
    void this.store.load();
  }

  /**
   * Delete a campaign, asking once first.
   *
   * @param campaignId Which campaign.
   * @returns Nothing.
   */
  async confirmDelete(campaignId: string): Promise<void> {
    if (this.pendingDelete() !== campaignId) {
      this.pendingDelete.set(campaignId);
      // The confirmation lapses, so a stray "Really delete?" left on screen
      // does not become a trap the next time someone glances at the page.
      setTimeout(() => {
        if (this.pendingDelete() === campaignId) {
          this.pendingDelete.set(null);
        }
      }, 5000);
      return;
    }
    this.pendingDelete.set(null);
    await this.store.remove(campaignId);
  }
}
