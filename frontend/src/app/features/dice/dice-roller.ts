/**
 * The dice tray.
 *
 * WHY THIS IS WORTH BUILDING AT ALL
 *
 * The Dungeon Master calls for checks — "make a Dexterity (Stealth) check" —
 * and without dice the player either types a number they invented or asks the
 * AI to roll for them. Both are unsatisfying. Half the pleasure of the game is
 * that the dice decide, and that nobody, including the person running it,
 * knows what is about to happen.
 *
 * So the roll happens here, visibly, and the result is sent to the Dungeon
 * Master as a sentence it can react to. That is the difference between a dice
 * widget and a dice feature.
 *
 * ADVANTAGE AND DISADVANTAGE
 *
 * The fifth-edition rules' way of saying "this is easier than usual" or
 * "harder than usual": roll two d20 and take the better or the worse. Both
 * dice are shown, because seeing the 3 you dodged is most of the fun.
 *
 * They apply to a d20 only, so the toggle disappears for other dice rather
 * than sitting there doing nothing.
 *
 * WHAT OPENS IT
 *
 * Not this component. It draws the tray and nothing else; whoever uses it
 * supplies the button and calls `toggle`. The play screen puts that button in
 * the message bar, beside the microphone.
 *
 * It used to open itself, from a round button floating over the bottom-right
 * corner. That is exactly where a messaging application puts its send button,
 * and no amount of nudging it upwards survives a message box that grows as you
 * type — so the button moved into the bar and the floating one was removed
 * rather than left as a second way in.
 */

import { ChangeDetectionStrategy, Component, computed, output, signal } from '@angular/core';

import { DIE_TYPES, DieType, RollMode, RollResult, describeRoll, roll } from '../../core/dice/dice';
import { Icon } from '../../shared/ui/icon';
import { Die3d, tumbleDuration } from './die-3d';

@Component({
    selector: 'app-dice-roller',
    changeDetection: ChangeDetectionStrategy.OnPush,
    imports: [Icon, Die3d],
    templateUrl: './dice-roller.html',
    styleUrl: './dice-roller.scss'
})
export class DiceRoller {
    /**
     * Emitted when the player sends a roll to the Dungeon Master.
     *
     * Carries the sentence to send, so the chat page does not need to know
     * anything about dice.
     */
    readonly rolled = output<string>();

    /** Every die, for the picker. */
    readonly dieTypes = DIE_TYPES;

    /** Whether the tray is open. */
    readonly open = signal(false);

    /** Which die is selected. The d20 is the default because it is the one the rules ask for. */
    readonly die = signal<DieType>('d20');

    /** How many dice to roll at once. */
    readonly count = signal(1);

    /** What to add to the total. */
    readonly modifier = signal(0);

    /** Advantage, disadvantage, or neither. */
    readonly mode = signal<RollMode>('normal');

    /** True while the die is in the air. */
    readonly rolling = signal(false);

    /** The most recent result, or `null` before the first roll. */
    readonly result = signal<RollResult | null>(null);

    /** True when advantage and disadvantage apply to the chosen die. */
    readonly supportsAdvantage = computed(() => this.die() === 'd20');

    /** The roll written out, e.g. `2d6+3` — shown on the button so it is unambiguous. */
    readonly notation = computed(() => {
        const count = this.mode() === 'normal' && this.count() > 1 ? this.count() : '';
        const modifier = this.modifier() > 0 ? `+${this.modifier()}` : this.modifier() < 0 ? `${this.modifier()}` : '';
        return `${count}${this.die()}${modifier}`;
    });

    /**
     * The number the die itself should come to rest on.
     *
     * The die's own roll, not the total — a d20 with a +3 modifier can total
     * 23, and no d20 has a face 23. The total is shown beside the die instead.
     * When several dice are rolled at once the tray animates the first of them;
     * the rest are listed underneath.
     */
    readonly shownRoll = computed(() => this.result()?.rolls[0] ?? 1);

    /**
     * Open or close the tray.
     *
     * @returns Nothing.
     */
    toggle(): void {
        this.open.update((value) => !value);
    }

    /**
     * Close the tray.
     *
     * @returns Nothing.
     */
    close(): void {
        this.open.set(false);
    }

    /**
     * Choose which die to roll.
     *
     * @param die The die.
     * @returns Nothing.
     */
    chooseDie(die: DieType): void {
        if (die === this.die()) {
            return;
        }
        this.die.set(die);

        // The previous result belonged to the previous die. Keeping a 17 on
        // screen after switching to a d6 would be nonsense, and the die would
        // have to land on a face that does not exist.
        this.result.set(null);

        // Advantage is a d20 concept. Leaving it set while a d8 is selected
        // would show a state that does nothing, which is worse than clearing it.
        if (die !== 'd20') {
            this.mode.set('normal');
        }
    }

    /**
     * Change how many dice are rolled.
     *
     * @param delta How much to add, which may be negative.
     * @returns Nothing.
     */
    adjustCount(delta: number): void {
        this.count.update((value) => Math.max(1, Math.min(20, value + delta)));
    }

    /**
     * Change the modifier.
     *
     * @param delta How much to add, which may be negative.
     * @returns Nothing.
     */
    adjustModifier(delta: number): void {
        this.modifier.update((value) => Math.max(-20, Math.min(20, value + delta)));
    }

    /**
     * Turn advantage or disadvantage on, or back off.
     *
     * Pressing the one that is already active clears it, so the same button
     * both sets and unsets — there is no separate "normal" to hunt for.
     *
     * @param mode Which to toggle.
     * @returns Nothing.
     */
    toggleMode(mode: RollMode): void {
        this.mode.update((current) => (current === mode ? 'normal' : mode));
    }

    /**
     * Roll the dice.
     *
     * The result is decided immediately; the tumble that follows is
     * presentation. That ordering matters — deciding the number when the
     * animation ends would mean a slow device changed the odds.
     *
     * @returns Nothing.
     */
    rollDice(): void {
        if (this.rolling()) {
            return;
        }

        const outcome = roll(this.die(), {
            count: this.count(),
            modifier: this.modifier(),
            mode: this.mode()
        });

        this.rolling.set(true);
        this.result.set(outcome);

        // Each die stays in the air for a different length of time, because
        // each one moves differently. `tumbleDuration` is the single source
        // both this timer and the animation read from, so they cannot drift.
        setTimeout(() => this.rolling.set(false), tumbleDuration(this.die()));
    }

    /**
     * Absolute value, for showing a modifier as `− 2` rather than `+ -2`.
     *
     * @param value The number.
     * @returns Its magnitude.
     */
    abs(value: number): number {
        return Math.abs(value);
    }

    /**
     * Send the result to the Dungeon Master and close the tray.
     *
     * @returns Nothing.
     */
    tellTheDungeonMaster(): void {
        const outcome = this.result();
        if (!outcome || this.rolling()) {
            return;
        }
        this.rolled.emit(describeRoll(outcome));
        this.close();
    }
}
