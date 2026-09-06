/**
 * Creating a campaign.
 *
 * The two free-text fields here — title and premise — are encrypted before
 * storage, because they are things a person wrote and may contain anything.
 * The tone and ruleset are values from a fixed list, so they stay readable,
 * which is what allows a question like "how many campaigns use the horror
 * tone?" to be answered without decrypting anything at all.
 */

import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';

import { Tone } from '../../core/api/api.types';
import { CampaignStore } from '../../core/state/campaign.store';
import { Banner } from '../../shared/ui/banner';

/** The tones on offer, with a sentence explaining what each does to the game. */
const TONES: readonly { value: Tone; label: string; description: string }[] = [
    {
        value: 'heroic',
        label: 'Heroic',
        description: 'Courage is rewarded. The world is worth saving.'
    },
    {
        value: 'gritty',
        label: 'Gritty',
        description: 'Resources matter, wounds linger, few people are purely good.'
    },
    {
        value: 'comedic',
        label: 'Comedic',
        description: 'Absurd but consistent. Jokes come from the situation.'
    },
    {
        value: 'horror',
        label: 'Horror',
        description: 'More is withheld than shown. You feel watched before you see anything.'
    },
    {
        value: 'mystery',
        label: 'Mystery',
        description: 'Concrete clues to chase. Every scene offers something to notice.'
    }
];

@Component({
    selector: 'app-campaign-create-page',
    changeDetection: ChangeDetectionStrategy.OnPush,
    imports: [FormsModule, RouterLink, Banner],
    template: `
        <div class="page page--narrow">
            <header class="page__header">
                <h1>New campaign</h1>
                <p class="page__lead">A campaign is one ongoing story. You can change any of this later.</p>
            </header>

            @if (error(); as message) {
                <app-banner kind="danger"
                    ><p style="margin: 0">{{ message }}</p></app-banner
                >
            }

            <form class="card" (ngSubmit)="submit()">
                <label class="field">
                    <span class="field__label">Title</span>
                    <input
                        class="input"
                        name="title"
                        required
                        maxlength="120"
                        placeholder="The Hollow Beneath Redmoor"
                        [ngModel]="title()"
                        (ngModelChange)="title.set($event)"
                    />
                    <span class="field__hint">Encrypted before it is stored — it is text you wrote.</span>
                </label>

                <label class="field">
                    <span class="field__label">Opening premise <span class="muted">(optional)</span></span>
                    <textarea
                        class="textarea"
                        name="premise"
                        rows="4"
                        maxlength="2000"
                        placeholder="A mining village whose children have started sleepwalking towards the old shaft."
                        [ngModel]="premise()"
                        (ngModelChange)="premise.set($event)"
                    ></textarea>
                    <span class="field__hint">
                        Leave it blank and the Dungeon Master will invent something that fits the title.
                    </span>
                </label>

                <fieldset class="field tone-set">
                    <legend class="field__label">Tone</legend>
                    @for (option of tones; track option.value) {
                        <label class="tone" [class.tone--selected]="tone() === option.value">
                            <input
                                type="radio"
                                name="tone"
                                [value]="option.value"
                                [checked]="tone() === option.value"
                                (change)="tone.set(option.value)"
                            />
                            <span>
                                <strong>{{ option.label }}</strong>
                                <span class="small muted">{{ option.description }}</span>
                            </span>
                        </label>
                    }
                </fieldset>

                <div class="row">
                    <button type="submit" class="btn btn--primary" [disabled]="!canSubmit()">
                        {{ loading() ? 'Creating…' : 'Create campaign' }}
                    </button>
                    <a routerLink="/campaigns" class="btn btn--ghost">Cancel</a>
                </div>
            </form>
        </div>
    `,
    styles: [
        `
            .page--narrow {
                max-width: 640px;
            }
            .tone-set {
                border: none;
                padding: 0;
                margin: 0 0 var(--space-4);
            }
            .tone {
                display: flex;
                gap: var(--space-3);
                align-items: flex-start;
                padding: var(--space-3);
                border: 1px solid var(--border);
                border-radius: var(--radius);
                margin-bottom: var(--space-2);
                cursor: pointer;
            }
            .tone--selected {
                border-color: var(--accent);
                background: var(--surface-raised);
            }
            .tone span span {
                display: block;
            }
            .tone input {
                margin-top: 4px;
            }
        `
    ]
})
export class CampaignCreatePage {
    private readonly store = inject(CampaignStore);
    private readonly router = inject(Router);

    /** The tones on offer. */
    readonly tones = TONES;

    readonly title = signal('');
    readonly premise = signal('');
    readonly tone = signal<Tone>('heroic');

    readonly loading = this.store.loading;
    readonly error = this.store.error;

    /** True when the form can be submitted. */
    readonly canSubmit = computed(() => this.title().trim().length > 0 && !this.loading());

    /**
     * Create the campaign and go to the play screen.
     *
     * @returns Nothing.
     */
    async submit(): Promise<void> {
        const created = await this.store.create({
            title: this.title().trim(),
            premise: this.premise().trim() || null,
            ruleset: 'dnd5e',
            tone: this.tone()
        });
        if (created) {
            await this.router.navigate(['/campaigns', created.campaign_id, 'characters', 'new']);
        }
    }
}
