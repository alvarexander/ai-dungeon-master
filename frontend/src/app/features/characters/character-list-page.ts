/** The characters belonging to one campaign. */

import { ChangeDetectionStrategy, Component, effect, inject, input } from '@angular/core';
import { RouterLink } from '@angular/router';

import { CampaignStore } from '../../core/state/campaign.store';
import { Banner } from '../../shared/ui/banner';

@Component({
    selector: 'app-character-list-page',
    changeDetection: ChangeDetectionStrategy.OnPush,
    imports: [RouterLink, Banner],
    template: `
        <div class="page">
            <header class="page__header row row--wrap">
                <div>
                    <h1>Characters</h1>
                    <p class="page__lead">Everyone adventuring in this campaign.</p>
                </div>
                <span class="spacer"></span>
                <a [routerLink]="['/campaigns', campaignId(), 'characters', 'new']" class="btn btn--primary">
                    New character
                </a>
            </header>

            @if (error(); as message) {
                <app-banner kind="danger"
                    ><p style="margin: 0">{{ message }}</p></app-banner
                >
            }

            @if (loading()) {
                <p class="muted">Loading…</p>
            } @else if (characters().length === 0) {
                <div class="card">
                    <h2>No characters yet</h2>
                    <p class="muted">
                        You can play without one — the Dungeon Master will help you work out who you are as you go. Or
                        make one now if you already know.
                    </p>
                    <a [routerLink]="['/campaigns', campaignId(), 'characters', 'new']" class="btn btn--primary">
                        Create a character
                    </a>
                </div>
            } @else {
                <div class="grid">
                    @for (character of characters(); track character.character_id) {
                        <a class="card character" [routerLink]="['/characters', character.character_id]">
                            <h2 class="character__name">{{ character.name }}</h2>
                            <p class="small muted">
                                Level {{ character.level }}
                                @if (character.ancestry) {
                                    {{ character.ancestry }}
                                }
                                {{ character.character_class }}
                            </p>
                            <p class="small">
                                <strong>{{ character.hit_points_current }}</strong>
                                <span class="muted"> / {{ character.hit_points_max }} hit points</span>
                            </p>
                        </a>
                    }
                </div>
            }

            <p style="margin-top: var(--space-5)">
                <a routerLink="/campaigns">Back to campaigns</a>
            </p>
        </div>
    `,
    styles: [
        `
            .character {
                text-decoration: none;
                color: inherit;
                display: block;
            }
            .character:hover {
                border-color: var(--accent);
            }
            .character__name {
                font-family: var(--font-narrative);
                margin-bottom: var(--space-1);
            }
        `
    ]
})
export class CharacterListPage {
    private readonly store = inject(CampaignStore);

    /** Which campaign, taken from the address. */
    readonly campaignId = input.required<string>();

    readonly characters = this.store.characters;
    readonly loading = this.store.loading;
    readonly error = this.store.error;

    constructor() {
        // Reloads whenever the address changes, so navigating between campaigns
        // shows the right characters rather than the previous campaign's.
        effect(() => {
            void this.store.loadCharacters(this.campaignId());
        });
    }
}
