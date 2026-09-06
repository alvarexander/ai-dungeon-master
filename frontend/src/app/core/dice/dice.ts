/**
 * Rolling dice.
 *
 * WHY THIS IS A SEPARATE FILE FROM THE ANIMATION
 *
 * Rolling is arithmetic and rules; the tumbling die is presentation. Keeping
 * them apart means the rules can be tested properly — a roll with advantage
 * really does take the higher of two, a modifier really is applied once — and
 * none of those tests need a browser or a running animation.
 *
 * It also means the animation can be as slow or as fast as looks good without
 * changing what was rolled. The result is decided the moment the button is
 * pressed; the tumble is theatre.
 */

/** The dice a fifth-edition player actually uses. */
export type DieType = 'd4' | 'd6' | 'd8' | 'd10' | 'd12' | 'd20' | 'd100';

/** How many sides each die has. */
export const DIE_SIDES: Record<DieType, number> = {
    d4: 4,
    d6: 6,
    d8: 8,
    d10: 10,
    d12: 12,
    d20: 20,
    d100: 100
};

/** Every die, in the order they are shown in the picker. */
export const DIE_TYPES: readonly DieType[] = ['d4', 'd6', 'd8', 'd10', 'd12', 'd20', 'd100'];

/**
 * How a d20 is rolled.
 *
 * Advantage and disadvantage are the fifth-edition rules' way of saying "this
 * is easier than usual" or "this is harder than usual": roll two dice and take
 * the better or the worse. They apply to a single d20 only — there is no such
 * thing as rolling damage with advantage.
 */
export type RollMode = 'normal' | 'advantage' | 'disadvantage';

/** Everything one roll produced. */
export interface RollResult {
    /** Which die was rolled. */
    die: DieType;

    /** How many of them. */
    count: number;

    /** Every number that counted, in the order they were rolled. */
    rolls: number[];

    /**
     * The rolls that did not count.
     *
     * With advantage or disadvantage two dice are rolled and one is discarded.
     * Keeping the discarded one lets the interface show both, which is what
     * makes the mechanic feel fair rather than arbitrary.
     */
    discarded: number[];

    /** Advantage, disadvantage, or neither. */
    mode: RollMode;

    /** The number added to or taken from the total. */
    modifier: number;

    /** The final answer: the kept dice plus the modifier. */
    total: number;

    /**
     * True when a single d20 came up 20.
     *
     * A natural 20 is an automatic success on an attack, and traditionally
     * something the whole table reacts to — so the interface marks it.
     */
    critical: boolean;

    /** True when a single d20 came up 1. An automatic miss, and a story beat. */
    fumble: boolean;
}

/**
 * Produce one random number from 1 to `sides`.
 *
 * Uses `crypto.getRandomValues` rather than `Math.random` where it exists —
 * not because a dice roll needs cryptographic security, but because dice are
 * the one thing in a game people will swear feels rigged. The stronger source
 * costs nothing and removes the argument.
 *
 * The modulo is rejection-sampled, so every face is exactly equally likely
 * rather than the low faces being very slightly favoured.
 *
 * @param sides How many faces the die has.
 * @returns A number from 1 to `sides` inclusive.
 */
export function rollOne(sides: number): number {
    if (typeof crypto !== 'undefined' && typeof crypto.getRandomValues === 'function') {
        const limit = Math.floor(0xffffffff / sides) * sides;
        const buffer = new Uint32Array(1);
        let value: number;
        do {
            crypto.getRandomValues(buffer);
            value = buffer[0];
            // Reject the tail that would make low numbers marginally more
            // likely. On a d20 this loops about once in fifty million times.
        } while (value >= limit);
        return (value % sides) + 1;
    }
    return Math.floor(Math.random() * sides) + 1;
}

/**
 * Roll dice and work out the result.
 *
 * @param die Which die to roll.
 * @param options.count How many, from 1 to 20. Ignored for advantage and
 *   disadvantage, which are defined as exactly two dice.
 * @param options.modifier Added to the total. May be negative.
 * @param options.mode Advantage, disadvantage, or neither. Only meaningful for
 *   a d20; the rules do not define it for anything else, so it is ignored.
 * @returns Everything about the roll, including the dice that were discarded.
 */
export function roll(die: DieType, options: { count?: number; modifier?: number; mode?: RollMode } = {}): RollResult {
    const sides = DIE_SIDES[die];
    const modifier = options.modifier ?? 0;
    const mode = die === 'd20' ? (options.mode ?? 'normal') : 'normal';

    if (mode !== 'normal') {
        const first = rollOne(sides);
        const second = rollOne(sides);
        const kept = mode === 'advantage' ? Math.max(first, second) : Math.min(first, second);
        const dropped = kept === first ? second : first;

        return {
            die,
            count: 1,
            rolls: [kept],
            discarded: [dropped],
            mode,
            modifier,
            total: kept + modifier,
            critical: kept === 20,
            fumble: kept === 1
        };
    }

    const count = Math.max(1, Math.min(20, options.count ?? 1));
    const rolls = Array.from({ length: count }, () => rollOne(sides));
    const sum = rolls.reduce((running, value) => running + value, 0);

    return {
        die,
        count,
        rolls,
        discarded: [],
        mode: 'normal',
        modifier,
        total: sum + modifier,
        // A critical only means anything on a single d20. Rolling eight d6 for
        // fireball damage and seeing a 20 in the total is not a critical hit.
        critical: die === 'd20' && count === 1 && rolls[0] === 20,
        fumble: die === 'd20' && count === 1 && rolls[0] === 1
    };
}

/**
 * Describe a roll the way a player would say it aloud.
 *
 * Used for the message sent to the Dungeon Master, so the narration can react
 * to what actually happened rather than to a bare number.
 *
 * @param result The roll to describe.
 * @returns Something like `I roll 2d6+3 and get 11 (rolled 4, 4).`
 */
export function describeRoll(result: RollResult): string {
    const notation = `${result.count > 1 ? result.count : ''}${result.die}`;
    const modifier = result.modifier > 0 ? `+${result.modifier}` : result.modifier < 0 ? `${result.modifier}` : '';

    const parts: string[] = [`I roll ${notation}${modifier}`];

    if (result.mode !== 'normal') {
        parts.push(`with ${result.mode}`);
    }

    parts.push(`and get ${result.total}`);

    const detail: string[] = [];
    if (result.rolls.length > 1 || result.modifier !== 0 || result.discarded.length > 0) {
        detail.push(`rolled ${result.rolls.join(', ')}`);
    }
    if (result.discarded.length > 0) {
        detail.push(`discarded ${result.discarded.join(', ')}`);
    }

    let sentence = parts.join(' ');
    if (detail.length > 0) {
        sentence += ` (${detail.join('; ')})`;
    }
    sentence += '.';

    if (result.critical) {
        sentence += ' A natural 20.';
    } else if (result.fumble) {
        sentence += ' A natural 1.';
    }

    return sentence;
}
