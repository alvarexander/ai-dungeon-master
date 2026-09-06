/**
 * Creating a character.
 *
 * A CLEAR EXAMPLE OF THE DATA CLASSIFICATION
 * This one form contains fields on both sides of the privacy line:
 *
 * - **Name and backstory are encrypted.** They are free text, and players
 *   routinely use their own name or a friend's.
 * - **Class, level and ability scores are stored in plain, readable form.**
 *   "Level 4 rogue with 14 constitution" identifies nobody, and keeping it
 *   readable means the server can compute hit points without decrypting
 *   anything.
 *
 * That split is the whole design in miniature: encrypt what a person wrote,
 * leave readable what came from a fixed list.
 */

import { ChangeDetectionStrategy, Component, computed, inject, input, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';

import { AbilityScores, CharacterClass } from '../../core/api/api.types';
import { CampaignStore } from '../../core/state/campaign.store';
import { Banner } from '../../shared/ui/banner';

/** The twelve classes of fifth-edition Dungeons & Dragons. */
const CLASSES: ReadonlyArray<{ value: CharacterClass; label: string; blurb: string }> = [
  { value: 'barbarian', label: 'Barbarian', blurb: 'Rage, endurance, and hitting things very hard.' },
  { value: 'bard', label: 'Bard', blurb: 'Talk your way in, and inspire everyone once you are there.' },
  { value: 'cleric', label: 'Cleric', blurb: 'Healing, protection, and divine authority.' },
  { value: 'druid', label: 'Druid', blurb: 'Nature magic, and turning into animals.' },
  { value: 'fighter', label: 'Fighter', blurb: 'Straightforward, versatile, and very good at combat.' },
  { value: 'monk', label: 'Monk', blurb: 'Speed and unarmed skill over armour and weapons.' },
  { value: 'paladin', label: 'Paladin', blurb: 'An oath, heavy armour, and radiant force behind it.' },
  { value: 'ranger', label: 'Ranger', blurb: 'Tracking, wilderness survival, and precise shooting.' },
  { value: 'rogue', label: 'Rogue', blurb: 'Stealth, locks, traps, and finding the weak spot.' },
  { value: 'sorcerer', label: 'Sorcerer', blurb: 'Innate magic, forceful and a little unpredictable.' },
  { value: 'warlock', label: 'Warlock', blurb: 'Power borrowed from something with its own agenda.' },
  { value: 'wizard', label: 'Wizard', blurb: 'Studied magic, and the widest spell list in the game.' },
];

/** The six ability scores, with what each governs. */
const ABILITIES: ReadonlyArray<{ key: keyof AbilityScores; label: string; governs: string }> = [
  { key: 'strength', label: 'Strength', governs: 'Lifting, shoving, hitting with heavy weapons' },
  { key: 'dexterity', label: 'Dexterity', governs: 'Stealth, reflexes, accuracy with light weapons' },
  { key: 'constitution', label: 'Constitution', governs: 'Health and stamina' },
  { key: 'intelligence', label: 'Intelligence', governs: 'Recall, deduction, wizardry' },
  { key: 'wisdom', label: 'Wisdom', governs: 'Perception, insight, willpower' },
  { key: 'charisma', label: 'Charisma', governs: 'Persuasion, deception, force of personality' },
];

/**
 * The standard array from the fifth-edition rules.
 *
 * Offered as a starting point so that a new player is not asked to invent six
 * numbers before they have any idea what the numbers do.
 */
const STANDARD_ARRAY: AbilityScores = {
  strength: 15,
  dexterity: 14,
  constitution: 13,
  intelligence: 12,
  wisdom: 10,
  charisma: 8,
};

@Component({
  selector: 'app-character-create-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, RouterLink, Banner],
  template: `
    <div class="page page--narrow">
      <header class="page__header">
        <h1>Create a character</h1>
        <p class="page__lead">
          None of this is permanent — you can change any of it later, and the Dungeon Master
          will work with whatever you give it.
        </p>
      </header>

      @if (error(); as message) {
        <app-banner kind="danger"><p style="margin: 0">{{ message }}</p></app-banner>
      }

      <form class="card" (ngSubmit)="submit()">
        <label class="field">
          <span class="field__label">Name</span>
          <input
            class="input"
            name="name"
            required
            maxlength="64"
            placeholder="Wren Ashdown"
            [ngModel]="name()"
            (ngModelChange)="name.set($event)"
          />
          <span class="field__hint">
            Encrypted before storage. People often use a real name here, so it is treated
            as personal data whatever you put.
          </span>
        </label>

        <label class="field">
          <span class="field__label">Ancestry <span class="muted">(optional)</span></span>
          <input
            class="input"
            name="ancestry"
            maxlength="48"
            placeholder="Half-elf"
            [ngModel]="ancestry()"
            (ngModelChange)="ancestry.set($event)"
          />
        </label>

        <fieldset class="field class-set">
          <legend class="field__label">Class</legend>
          <div class="class-grid">
            @for (option of classes; track option.value) {
              <label class="class-card" [class.class-card--selected]="characterClass() === option.value">
                <input
                  type="radio"
                  name="class"
                  class="visually-hidden"
                  [checked]="characterClass() === option.value"
                  (change)="characterClass.set(option.value)"
                />
                <strong>{{ option.label }}</strong>
                <span class="small muted">{{ option.blurb }}</span>
              </label>
            }
          </div>
        </fieldset>

        <label class="field">
          <span class="field__label">Level</span>
          <input
            class="input"
            type="number"
            name="level"
            min="1"
            max="20"
            [ngModel]="level()"
            (ngModelChange)="level.set(+$event)"
          />
          <span class="field__hint">Stored as an ordinary number — it identifies nobody.</span>
        </label>

        <fieldset class="field">
          <legend class="field__label">Ability scores</legend>
          <p class="small muted" style="margin-top: 0">
            These start from the standard set in the rules. 10 is average for an adult;
            higher is better. If you are not sure, leave them alone.
          </p>
          @for (ability of abilities; track ability.key) {
            <div class="ability">
              <label [attr.for]="ability.key">
                <strong>{{ ability.label }}</strong>
                <span class="small muted">{{ ability.governs }}</span>
              </label>
              <input
                class="input ability__input"
                type="number"
                [id]="ability.key"
                [name]="ability.key"
                min="1"
                max="30"
                [ngModel]="abilityValue(ability.key)"
                (ngModelChange)="setAbility(ability.key, +$event)"
              />
            </div>
          }
          <button type="button" class="btn btn--ghost btn--sm" (click)="resetAbilities()">
            Reset to the standard set
          </button>
        </fieldset>

        <label class="field">
          <span class="field__label">Backstory <span class="muted">(optional)</span></span>
          <textarea
            class="textarea"
            name="backstory"
            rows="4"
            maxlength="4000"
            placeholder="Left the coast after a shipwreck she does not talk about."
            [ngModel]="backstory()"
            (ngModelChange)="backstory.set($event)"
          ></textarea>
          <span class="field__hint">Free text, so it is encrypted like the name.</span>
        </label>

        <div class="row">
          <button type="submit" class="btn btn--primary" [disabled]="!canSubmit()">
            {{ loading() ? 'Creating…' : 'Create character' }}
          </button>
          <a routerLink="/play" class="btn btn--ghost">Skip for now</a>
        </div>
      </form>
    </div>
  `,
  styles: [
    `
      .page--narrow { max-width: 680px; }
      .class-set { border: none; padding: 0; margin: 0 0 var(--space-4); }
      .class-grid { display: grid; gap: var(--space-2); grid-template-columns: repeat(auto-fill, minmax(190px, 1fr)); }
      .class-card {
        display: block;
        padding: var(--space-3);
        border: 1px solid var(--border);
        border-radius: var(--radius);
        cursor: pointer;
      }
      .class-card--selected { border-color: var(--accent); background: var(--surface-raised); }
      .class-card strong { display: block; margin-bottom: 2px; }
      .class-card:has(input:focus-visible) { outline: 2px solid var(--focus); outline-offset: 2px; }
      .ability { display: flex; align-items: center; gap: var(--space-3); margin-bottom: var(--space-2); }
      .ability label { flex: 1; }
      .ability label span { display: block; }
      .ability__input { width: 88px; }
    `,
  ],
})
export class CharacterCreatePage {
  private readonly store = inject(CampaignStore);
  private readonly router = inject(Router);

  /** Which campaign this character belongs to, taken from the address. */
  readonly campaignId = input.required<string>();

  readonly classes = CLASSES;
  readonly abilities = ABILITIES;

  readonly name = signal('');
  readonly ancestry = signal('');
  readonly characterClass = signal<CharacterClass>('fighter');
  readonly level = signal(1);
  readonly backstory = signal('');
  readonly scores = signal<AbilityScores>({ ...STANDARD_ARRAY });

  readonly loading = this.store.loading;
  readonly error = this.store.error;

  /** True when the form can be submitted. */
  readonly canSubmit = computed(() => this.name().trim().length > 0 && !this.loading());

  /**
   * Read one ability score.
   *
   * @param key Which ability.
   * @returns Its current value.
   */
  abilityValue(key: keyof AbilityScores): number {
    return this.scores()[key];
  }

  /**
   * Change one ability score, keeping it inside the rules' limits.
   *
   * @param key Which ability.
   * @param value The new value.
   * @returns Nothing.
   */
  setAbility(key: keyof AbilityScores, value: number): void {
    const clamped = Math.max(1, Math.min(30, Number.isFinite(value) ? value : 10));
    this.scores.update((scores) => ({ ...scores, [key]: clamped }));
  }

  /**
   * Put the ability scores back to the standard set.
   *
   * @returns Nothing.
   */
  resetAbilities(): void {
    this.scores.set({ ...STANDARD_ARRAY });
  }

  /**
   * Create the character and go to the play screen.
   *
   * @returns Nothing.
   */
  async submit(): Promise<void> {
    const created = await this.store.createCharacter(this.campaignId(), {
      name: this.name().trim(),
      character_class: this.characterClass(),
      level: this.level(),
      ancestry: this.ancestry().trim() || null,
      abilities: this.scores(),
      backstory: this.backstory().trim() || null,
    });
    if (created) {
      await this.router.navigate(['/play']);
    }
  }
}
