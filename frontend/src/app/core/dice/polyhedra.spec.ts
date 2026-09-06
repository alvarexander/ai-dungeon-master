/**
 * Tests for the dice geometry.
 *
 * These shapes are the kind of thing that looks almost right when it is wrong,
 * so the properties that make a solid a solid are checked directly rather than
 * left to the eye: the right number of faces, the right number of corners on
 * each of them, every face the same size as its neighbours, and every face
 * actually lying flat.
 */

import { describe, expect, it } from 'vitest';

import { DIE_TYPES, DieType } from './dice';
import { FacePlacement, faceIndexFor, facesOf, restingAngles } from './polyhedra';

/** How many faces each die must have, and how many corners each face must have. */
const EXPECTED: Record<DieType, { faces: number; cornersPerFace: number }> = {
    d4: { faces: 4, cornersPerFace: 3 },
    d6: { faces: 6, cornersPerFace: 4 },
    d8: { faces: 8, cornersPerFace: 3 },
    d10: { faces: 10, cornersPerFace: 4 },
    d12: { faces: 12, cornersPerFace: 5 },
    d20: { faces: 20, cornersPerFace: 3 },
    d100: { faces: 10, cornersPerFace: 4 }
};

/**
 * Whether two faces point in exactly opposite directions.
 *
 * Comparing the turns rather than the numbers: a face at the back of the die
 * has been turned half a circle away from the one at the front, and tilted the
 * opposite way.
 *
 * @param a One face.
 * @param b The other.
 * @returns True when they are back to back.
 */
function isOpposite(a: FacePlacement, b: FacePlacement): boolean {
    return direction(a).x * direction(b).x + direction(a).y * direction(b).y + direction(a).z * direction(b).z < -0.999;
}

/**
 * Recover the direction a face points from the turns that placed it.
 *
 * @param face The face.
 * @returns The direction it points, length one.
 */
function direction(face: FacePlacement): { x: number; y: number; z: number } {
    const yaw = (face.yaw * Math.PI) / 180;
    const pitch = (face.pitch * Math.PI) / 180;
    return {
        x: Math.sin(yaw) * Math.cos(pitch),
        y: -Math.sin(pitch),
        z: Math.cos(yaw) * Math.cos(pitch)
    };
}

/**
 * Count the corners in a `clip-path: polygon(...)` value.
 *
 * @param clipPath The CSS value.
 * @returns How many points it has.
 */
function cornerCount(clipPath: string): number {
    return clipPath.replace('polygon(', '').replace(')', '').split(',').length;
}

describe('facesOf', () => {
    it('gives every die the number of faces its name promises', () => {
        // A d20 with nineteen faces is the whole reason this file exists.
        for (const die of DIE_TYPES) {
            expect(facesOf(die), die).toHaveLength(EXPECTED[die].faces);
        }
    });

    it('gives every face the right shape', () => {
        // Triangles for the d4, d8 and d20; squares for the d6; kites for the
        // d10; pentagons for the d12.
        for (const die of DIE_TYPES) {
            for (const face of facesOf(die)) {
                expect(cornerCount(face.clipPath), die).toBe(EXPECTED[die].cornersPerFace);
            }
        }
    });

    it('makes every face of a die the same size and the same distance out', () => {
        // Every face of these solids is congruent with every other. If the
        // derivation picked up a stray corner, one face comes out larger, and
        // this is what notices.
        for (const die of DIE_TYPES) {
            const faces = facesOf(die);
            for (const face of faces) {
                expect(face.size, die).toBeCloseTo(faces[0].size, 6);
                expect(face.distance, die).toBeCloseTo(faces[0].distance, 6);
            }
        }
    });

    it('keeps every face inside the die rather than floating off it', () => {
        for (const die of DIE_TYPES) {
            for (const face of facesOf(die)) {
                expect(face.distance, die).toBeGreaterThan(0);
                expect(face.distance, die).toBeLessThanOrEqual(1);
            }
        }
    });

    it('uses every number exactly once', () => {
        for (const die of DIE_TYPES) {
            const faces = facesOf(die);
            const used = [...faces.map((face) => face.value)].sort((a, b) => a - b);
            expect(used, die).toEqual(Array.from({ length: faces.length }, (_, i) => i + 1));
        }
    });

    it('puts opposite numbers on opposite faces, the way dice are made', () => {
        // On a real die the two numbers you cannot see at once add up to one
        // more than the number of sides — 1 opposite 6, 1 opposite 20. It keeps
        // the weight even, and a d20 with 19 beside 20 looks wrong to anyone
        // who has held one. A tetrahedron has no opposite faces and is exempt.
        for (const die of DIE_TYPES) {
            if (die === 'd4') {
                continue;
            }
            const faces = facesOf(die);
            for (const face of faces) {
                const opposite = faces.find((other) => isOpposite(face, other));
                expect(opposite, `${die} face ${face.value}`).toBeDefined();
                expect(face.value + opposite!.value, `${die} face ${face.value}`).toBe(faces.length + 1);
            }
        }
    });

    it('labels a d10 from zero and a percentile die in tens', () => {
        // Both are how the real dice are printed: a d10 has a 0 rather than a
        // 10, and a d100 shows 00 through 90.
        expect([...facesOf('d10').map((f) => f.label)].sort()).toEqual([
            '0',
            '1',
            '2',
            '3',
            '4',
            '5',
            '6',
            '7',
            '8',
            '9'
        ]);
        expect([...facesOf('d100').map((f) => f.label)].sort()).toEqual([
            '00',
            '10',
            '20',
            '30',
            '40',
            '50',
            '60',
            '70',
            '80',
            '90'
        ]);
    });

    it('puts the number in the middle of a regular face', () => {
        for (const face of facesOf('d6')) {
            expect(face.labelX).toBeCloseTo(50, 6);
            expect(face.labelY).toBeCloseTo(50, 6);
        }
    });

    it('shifts the number off centre on a kite, where the middle is not the middle', () => {
        // A kite is lopsided, so a number at 50/50 sits visibly high or low.
        const offset = facesOf('d10').some((face) => Math.abs(face.labelY - 50) > 1 || Math.abs(face.labelX - 50) > 1);
        expect(offset).toBe(true);
    });

    it('returns the identical list each time rather than recomputing it', () => {
        expect(facesOf('d20')).toBe(facesOf('d20'));
    });
});

describe('faceIndexFor', () => {
    it('lands on the face showing the number that was rolled', () => {
        // The whole point of the resting position: roll a 17, see the 17.
        for (const die of DIE_TYPES) {
            if (die === 'd10' || die === 'd100') {
                continue;
            }
            const faces = facesOf(die);
            for (let value = 1; value <= faces.length; value++) {
                expect(faces[faceIndexFor(die, value)].label, `${die} rolled ${value}`).toBe(`${value}`);
            }
        }
    });

    it('reads a d10 the way a d10 is read, with 10 shown as zero', () => {
        const faces = facesOf('d10');
        expect(faces[faceIndexFor('d10', 7)].label).toBe('7');
        expect(faces[faceIndexFor('d10', 10)].label).toBe('0');
    });

    it('rests a percentile die on its tens digit', () => {
        const faces = facesOf('d100');
        expect(faces[faceIndexFor('d100', 47)].label).toBe('40');
        expect(faces[faceIndexFor('d100', 100)].label).toBe('90');
        expect(faces[faceIndexFor('d100', 1)].label).toBe('00');
    });

    it('stays on a real face if given a number the die does not have', () => {
        // The total can exceed the die once a modifier is added, and asking for
        // face 23 of a d20 must not produce an empty die.
        for (const die of DIE_TYPES) {
            const index = faceIndexFor(die, 999);
            expect(index).toBeGreaterThanOrEqual(0);
            expect(index).toBeLessThan(facesOf(die).length);
        }
    });
});

describe('restingAngles', () => {
    it('cancels out the face it is bringing forward', () => {
        // Turning by the opposite of a face's own yaw and pitch is what points
        // it back at the viewer.
        const face = facesOf('d20')[0];
        expect(restingAngles('d20', 0)).toEqual({ x: -face.pitch, y: -face.yaw });
    });

    it('turns the rolled face towards the viewer, whatever was rolled', () => {
        // The property that matters: after resting, the winning face's normal
        // points at the camera. Undoing its own two turns is what achieves it.
        for (const die of DIE_TYPES) {
            const faces = facesOf(die);
            for (let i = 0; i < faces.length; i++) {
                const angles = restingAngles(die, i);
                expect(angles.x + faces[i].pitch, `${die} face ${i}`).toBeCloseTo(0, 6);
                expect(angles.y + faces[i].yaw, `${die} face ${i}`).toBeCloseTo(0, 6);
            }
        }
    });

    it('survives an index that does not exist', () => {
        expect(restingAngles('d6', 99)).toBeDefined();
    });
});
