/**
 * One character's sheet, with editing.
 *
 * The whole sheet arrives from the backend as a single encrypted blob and is
 * decrypted for this one response. Changes are saved back the same way. The
 * class and level travel separately in readable form, which is what lets the
 * server recompute hit points when constitution or level changes without
 * needing to open the rest of the sheet.
 */

import { ChangeDetectionStrategy, Component, computed, effect, inject, input, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import { ApiClient } from '../../core/api/api.client';
import { AbilityScores, CharacterDetail } from '../../core/api/api.types';
import { CampaignStore } from '../../core/state/campaign.store';
import { Banner } from '../../shared/ui/banner';

/** The six ability scores, in the order the rules present them. */
const ABILITY_KEYS: readonly (keyof AbilityScores)[] = [
    'strength',
    'dexterity',
    'constitution',
    'intelligence',
    'wisdom',
    'charisma'
];

@Component({
    selector: 'app-character-sheet-page',
    changeDetection: ChangeDetectionStrategy.OnPush,
    imports: [FormsModule, RouterLink, Banner],
    template: `
        <div class="page page--narrow">
            @if (character(); as sheet) {
                <header class="page__header">
                    <h1 class="sheet__name">{{ sheet.name }}</h1>
                    <p class="page__lead">
                        Level {{ sheet.level }}
                        @if (sheet.ancestry) {
                            {{ sheet.ancestry }}
                        }
                        {{ sheet.character_class }}
                    </p>
                </header>

                @if (saved()) {
                    <app-banner kind="success"><p style="margin: 0">Saved.</p></app-banner>
                }
                @if (error(); as message) {
                    <app-banner kind="danger"
                        ><p style="margin: 0">{{ message }}</p></app-banner
                    >
                }

                <section class="card">
                    <h2>Hit points</h2>
                    <div class="row">
                        <input
                            class="input hp-input"
                            type="number"
                            min="0"
                            [max]="sheet.hit_points_max"
                            [ngModel]="hitPoints()"
                            (ngModelChange)="hitPoints.set(+$event)"
                            aria-label="Current hit points"
                        />
                        <span class="muted">of {{ sheet.hit_points_max }}</span>
                        <span class="spacer"></span>
                        <button type="button" class="btn btn--sm" (click)="adjustHp(-1)">−1</button>
                        <button type="button" class="btn btn--sm" (click)="adjustHp(1)">+1</button>
                        <button type="button" class="btn btn--primary btn--sm" (click)="saveHitPoints()">Save</button>
                    </div>
                    <div class="hp-bar" [attr.aria-hidden]="true">
                        <span [style.width.%]="hpPercent()"></span>
                    </div>
                </section>

                <section class="card">
                    <h2>Abilities</h2>
                    <div class="ability-grid">
                        @for (key of abilityKeys; track key) {
                            <div class="ability-box">
                                <span class="ability-box__label">{{ key.slice(0, 3) }}</span>
                                <span class="ability-box__score">{{ sheet.abilities[key] }}</span>
                                <span class="ability-box__mod">{{ modifier(sheet.abilities[key]) }}</span>
                            </div>
                        }
                    </div>
                    <p class="small muted" style="margin-bottom: 0">
                        The number underneath is the modifier — what gets added to a dice roll. 10 is average and gives
                        nothing; every two points above or below shifts it by one.
                    </p>
                </section>

                @if (sheet.backstory) {
                    <section class="card">
                        <h2>Backstory</h2>
                        <p class="narrative">{{ sheet.backstory }}</p>
                        <p class="small muted" style="margin-bottom: 0">
                            Stored encrypted. Nobody with database access can read this.
                        </p>
                    </section>
                }

                <p>
                    <a [routerLink]="['/campaigns', sheet.campaign_id, 'characters']">Back to characters</a>
                </p>
            } @else if (loading()) {
                <p class="muted">Loading…</p>
            } @else {
                <app-banner kind="danger" title="Not found">
                    <p style="margin: 0">
                        That character could not be found. It may have been deleted, or it may belong to a different
                        account.
                    </p>
                </app-banner>
            }
        </div>
    `,
    styles: [
        `
            .page--narrow {
                max-width: 680px;
            }
            .page--narrow section {
                margin-bottom: var(--space-4);
            }
            .sheet__name {
                font-family: var(--font-narrative);
                font-size: 2rem;
            }
            .hp-input {
                width: 100px;
            }
            .hp-bar {
                margin-top: var(--space-3);
                height: 8px;
                border-radius: 999px;
                background: var(--surface-sunken);
                overflow: hidden;
            }
            .hp-bar span {
                display: block;
                height: 100%;
                background: var(--success);
                transition: width var(--transition);
            }
            .ability-grid {
                display: grid;
                gap: var(--space-3);
                grid-template-columns: repeat(auto-fit, minmax(84px, 1fr));
                margin-bottom: var(--space-4);
            }
            .ability-box {
                display: flex;
                flex-direction: column;
                align-items: center;
                padding: var(--space-3);
                border: 1px solid var(--border);
                border-radius: var(--radius);
                background: var(--surface-sunken);
            }
            .ability-box__label {
                font-size: 0.7rem;
                text-transform: uppercase;
                letter-spacing: 0.08em;
                color: var(--ink-faint);
            }
            .ability-box__score {
                font-size: 1.5rem;
                font-weight: 600;
            }
            .ability-box__mod {
                font-size: 0.85rem;
                color: var(--accent-strong);
            }
            .narrative {
                font-family: var(--font-narrative);
                line-height: 1.75;
            }
        `
    ]
})
export class CharacterSheetPage {
    private readonly api = inject(ApiClient);
    private readonly store = inject(CampaignStore);

    /** Which character, taken from the address. */
    readonly characterId = input.required<string>();

    readonly abilityKeys = ABILITY_KEYS;

    /** The loaded sheet, or `null` while loading or if it was not found. */
    readonly character = signal<CharacterDetail | null>(null);
    readonly loading = signal(true);
    readonly error = signal<string | null>(null);
    readonly saved = signal(false);

    /** The hit points shown in the editable box. */
    readonly hitPoints = signal(0);

    /** How full the health bar should be, as a percentage. */
    readonly hpPercent = computed(() => {
        const sheet = this.character();
        if (!sheet || sheet.hit_points_max === 0) {
            return 0;
        }
        return Math.max(0, Math.min(100, (this.hitPoints() / sheet.hit_points_max) * 100));
    });

    constructor() {
        effect(() => {
            void this.load(this.characterId());
        });
    }

    /**
     * Format an ability modifier the way a character sheet does.
     *
     * @param score The ability score.
     * @returns The modifier with an explicit sign, e.g. `+3` or `−1`.
     */
    modifier(score: number): string {
        const value = Math.floor((score - 10) / 2);
        return value >= 0 ? `+${value}` : `−${Math.abs(value)}`;
    }

    /**
     * Change hit points by a small amount, staying within the sheet's limits.
     *
     * @param delta How much to add, which may be negative.
     * @returns Nothing.
     */
    adjustHp(delta: number): void {
        const max = this.character()?.hit_points_max ?? 0;
        this.hitPoints.update((current) => Math.max(0, Math.min(max, current + delta)));
    }

    /**
     * Save the current hit points.
     *
     * @returns Nothing.
     */
    async saveHitPoints(): Promise<void> {
        const updated = await this.store.updateCharacter(this.characterId(), {
            hit_points_current: this.hitPoints()
        });
        if (updated) {
            this.character.set(updated);
            this.saved.set(true);
            setTimeout(() => this.saved.set(false), 2500);
        } else {
            this.error.set(this.store.error());
        }
    }

    /**
     * Fetch the sheet.
     *
     * @param characterId Which character.
     * @returns Nothing.
     */
    private async load(characterId: string): Promise<void> {
        this.loading.set(true);
        this.error.set(null);
        try {
            const sheet = await firstValueFrom(this.api.get<CharacterDetail>(`/api/v1/characters/${characterId}`));
            this.character.set(sheet);
            this.hitPoints.set(sheet.hit_points_current);
        } catch {
            this.character.set(null);
        } finally {
            this.loading.set(false);
        }
    }
}
