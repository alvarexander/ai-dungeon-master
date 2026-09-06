/**
 * Tests for the dice rules.
 *
 * Dice are the one part of a game people will insist is rigged, so the rules
 * are pinned down rather than assumed: advantage really does take the higher
 * of two, the modifier is applied once, and every face is reachable.
 */

import { describe, expect, it } from 'vitest';

import { DIE_SIDES, DieType, describeRoll, roll, rollOne } from './dice';

describe('rollOne', () => {
    it('always lands within the die', () => {
        for (const sides of [4, 6, 8, 10, 12, 20, 100]) {
            for (let i = 0; i < 200; i++) {
                const value = rollOne(sides);
                expect(value).toBeGreaterThanOrEqual(1);
                expect(value).toBeLessThanOrEqual(sides);
                expect(Number.isInteger(value)).toBe(true);
            }
        }
    });

    it('can reach every face of a d20', () => {
        // A die that never rolls a 20 is a broken die, and this is the cheapest
        // way to notice an off-by-one in the modulo.
        const seen = new Set<number>();
        for (let i = 0; i < 4000; i++) {
            seen.add(rollOne(20));
        }
        expect(seen.size).toBe(20);
        expect(seen.has(1)).toBe(true);
        expect(seen.has(20)).toBe(true);
    });
});

describe('roll', () => {
    it('adds the modifier once, not once per die', () => {
        const result = roll('d6', { count: 3, modifier: 5 });
        const sum = result.rolls.reduce((a, b) => a + b, 0);
        expect(result.rolls).toHaveLength(3);
        expect(result.total).toBe(sum + 5);
    });

    it('handles a negative modifier', () => {
        const result = roll('d20', { modifier: -3 });
        expect(result.total).toBe(result.rolls[0] - 3);
    });

    it('takes the higher of two with advantage, and keeps the other', () => {
        for (let i = 0; i < 200; i++) {
            const result = roll('d20', { mode: 'advantage' });
            expect(result.rolls).toHaveLength(1);
            expect(result.discarded).toHaveLength(1);
            expect(result.rolls[0]).toBeGreaterThanOrEqual(result.discarded[0]);
        }
    });

    it('takes the lower of two with disadvantage', () => {
        for (let i = 0; i < 200; i++) {
            const result = roll('d20', { mode: 'disadvantage' });
            expect(result.rolls[0]).toBeLessThanOrEqual(result.discarded[0]);
        }
    });

    it('ignores advantage on dice where the rules do not define it', () => {
        // There is no such thing as rolling damage with advantage.
        const result = roll('d6', { mode: 'advantage' });
        expect(result.mode).toBe('normal');
        expect(result.discarded).toHaveLength(0);
    });

    it('marks a natural 20 and a natural 1 only on a single d20', () => {
        let sawCritical = false;
        let sawFumble = false;
        for (let i = 0; i < 3000; i++) {
            const result = roll('d20');
            if (result.rolls[0] === 20) {
                expect(result.critical).toBe(true);
                sawCritical = true;
            }
            if (result.rolls[0] === 1) {
                expect(result.fumble).toBe(true);
                sawFumble = true;
            }
        }
        expect(sawCritical && sawFumble).toBe(true);

        // Eight d6 for a fireball is not a critical hit, whatever comes up.
        for (let i = 0; i < 100; i++) {
            expect(roll('d6', { count: 8 }).critical).toBe(false);
        }
    });

    it('keeps the number of dice within sensible bounds', () => {
        expect(roll('d6', { count: 0 }).rolls).toHaveLength(1);
        expect(roll('d6', { count: 999 }).rolls).toHaveLength(20);
    });

    it('rolls every kind of die', () => {
        for (const die of Object.keys(DIE_SIDES) as DieType[]) {
            const result = roll(die);
            expect(result.rolls[0]).toBeLessThanOrEqual(DIE_SIDES[die]);
        }
    });
});

describe('describeRoll', () => {
    it('reads like something a player would say', () => {
        const described = describeRoll({
            die: 'd20',
            count: 1,
            rolls: [17],
            discarded: [],
            mode: 'normal',
            modifier: 3,
            total: 20,
            critical: false,
            fumble: false
        });
        expect(described).toBe('I roll d20+3 and get 20 (rolled 17).');
    });

    it('mentions advantage and the discarded die', () => {
        const described = describeRoll({
            die: 'd20',
            count: 1,
            rolls: [18],
            discarded: [4],
            mode: 'advantage',
            modifier: 0,
            total: 18,
            critical: false,
            fumble: false
        });
        expect(described).toContain('with advantage');
        expect(described).toContain('discarded 4');
    });

    it('calls out a natural 20', () => {
        const described = describeRoll({
            die: 'd20',
            count: 1,
            rolls: [20],
            discarded: [],
            mode: 'normal',
            modifier: 0,
            total: 20,
            critical: true,
            fumble: false
        });
        expect(described).toContain('A natural 20.');
    });
});
