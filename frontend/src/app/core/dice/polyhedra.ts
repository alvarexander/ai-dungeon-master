/**
 * The geometry of real dice, computed rather than guessed.
 *
 * WHY THIS FILE EXISTS
 *
 * A d20 that is not an icosahedron is not a d20. Players know these shapes by
 * sight — the twenty-sided die is the emblem of the whole hobby — and a stand-in
 * shape reads as wrong immediately, even to someone who could not say what is
 * wrong with it.
 *
 * So every die here is its actual solid, with its actual number of faces, and
 * every face carries its number the way a real die does:
 *
 * | Die  | Solid                    | Faces | Shape of a face |
 * | ---- | ------------------------ | ----- | --------------- |
 * | d4   | tetrahedron              | 4     | triangle        |
 * | d6   | cube                     | 6     | square          |
 * | d8   | octahedron               | 8     | triangle        |
 * | d10  | pentagonal trapezohedron | 10    | kite            |
 * | d12  | dodecahedron             | 12    | pentagon        |
 * | d20  | icosahedron              | 20    | triangle        |
 * | d100 | pentagonal trapezohedron | 10    | kite            |
 *
 * A "solid" here just means a three-dimensional shape with flat sides. The
 * names are the traditional Greek ones and mean what they say: a dodecahedron
 * is a twelve-sided shape, an icosahedron a twenty-sided one.
 *
 * ONLY THE CORNERS ARE WRITTEN DOWN
 *
 * Everything else — which corners form a face, which way each face points, what
 * shape it is, where its number goes — is worked out from the corners.
 *
 * The alternative is to type out a table of twenty triples for an icosahedron
 * and twelve five-tuples for a dodecahedron, where one transposed digit
 * produces a shape that is subtly wrong in a way nobody can debug by looking at
 * it. This file originally took an even shorter cut — reusing one solid's
 * corners as another's face directions, which is true of *some* pairs of solids
 * in *some* orientations and was quietly false here. The tests caught it. The
 * corners are now the single source of truth, because they are the one thing
 * that can be checked against a reference by eye.
 *
 * HOW ONE FACE IS PLACED
 *
 * Each face is an ordinary HTML element. It starts flat, in the middle of the
 * screen, facing the viewer. Two turns and a push put it where it belongs:
 *
 *   rotateY(yaw) rotateX(pitch) translateZ(distance)
 *
 * - **yaw** turns it left or right and **pitch** tilts it up or down, until it
 *   faces the same direction the real face does. That direction is called the
 *   face's *normal* — think of an arrow sticking straight out of it.
 * - **translateZ** then pushes it outwards from the centre until it sits on the
 *   surface of the solid.
 *
 * There is deliberately no third rotation. Each face's outline is cut from its
 * real corners with `clip-path`, so its orientation is already part of its
 * shape. That is what makes neighbouring faces meet cleanly, and it is the only
 * way to draw a d10 at all — a d10's faces are kites, which no amount of
 * rotating a regular polygon will produce.
 */

import { DieType } from './dice';

/** A point in space, or a direction. */
export interface Vec3 {
    x: number;
    /** Positive is **downwards**, matching the way the browser measures. */
    y: number;
    z: number;
}

/** Everything needed to draw one face. */
export interface FacePlacement {
    /** Turn left or right, in degrees. */
    yaw: number;

    /** Tilt up or down, in degrees. */
    pitch: number;

    /**
     * How far out from the centre to push the face, as a fraction of the die's
     * radius. It is turned into pixels in the stylesheet, so the same numbers
     * work at any size.
     */
    distance: number;

    /** How wide the face's element must be, as a fraction of the die's radius. */
    size: number;

    /** The `clip-path` polygon that cuts the element down to the real face. */
    clipPath: string;

    /** Where the number sits within the face, as a percentage of the element. */
    labelX: number;

    /** Where the number sits within the face, as a percentage of the element. */
    labelY: number;

    /** Which face this is, counting from one. */
    value: number;

    /** The number printed on this face, as it should be read. */
    label: string;
}

/**
 * The golden ratio, roughly 1.618.
 *
 * It appears in the corners of the icosahedron and the dodecahedron the way pi
 * appears in circles — not decoration, just what the arithmetic of a
 * twenty-sided shape happens to produce.
 */
const PHI = (1 + Math.sqrt(5)) / 2;

/** How close two numbers must be to count as equal, given these come from square roots. */
const EPSILON = 1e-9;

const vec = (x: number, y: number, z: number): Vec3 => ({ x, y, z });
const dot = (a: Vec3, b: Vec3): number => a.x * b.x + a.y * b.y + a.z * b.z;
const sub = (a: Vec3, b: Vec3): Vec3 => vec(a.x - b.x, a.y - b.y, a.z - b.z);
const magnitude = (a: Vec3): number => Math.sqrt(dot(a, a));

/**
 * The direction at right angles to two others.
 *
 * Given two edges of a face, this points straight out of that face, which is
 * how each face's direction is found.
 *
 * @param a The first vector.
 * @param b The second vector.
 * @returns A vector perpendicular to both.
 */
function cross(a: Vec3, b: Vec3): Vec3 {
    return vec(a.y * b.z - a.z * b.y, a.z * b.x - a.x * b.z, a.x * b.y - a.y * b.x);
}

/**
 * Scale a vector until its length is one, keeping its direction.
 *
 * @param a The vector.
 * @returns The same direction, length one.
 */
function normalise(a: Vec3): Vec3 {
    const length = magnitude(a) || 1;
    return vec(a.x / length, a.y / length, a.z / length);
}

/**
 * Every combination of plus and minus for three magnitudes.
 *
 * The corners of these solids are all sign variations of two or three numbers,
 * so generating them beats typing eight or twelve lines of nearly identical
 * coordinates and hoping none of them has a wrong minus sign.
 *
 * @param values One magnitude per axis.
 * @returns Every distinct signed combination. A zero has only one sign, so it
 *   does not produce a duplicate point.
 */
function signs(values: [number, number, number]): Vec3[] {
    const out: Vec3[] = [];
    for (const sx of values[0] === 0 ? [1] : [1, -1]) {
        for (const sy of values[1] === 0 ? [1] : [1, -1]) {
            for (const sz of values[2] === 0 ? [1] : [1, -1]) {
                out.push(vec(values[0] * sx, values[1] * sy, values[2] * sz));
            }
        }
    }
    return out;
}

/**
 * All three ways of rotating a coordinate triple, with every sign.
 *
 * `(0, 1, φ)` this way also produces `(1, φ, 0)` and `(φ, 0, 1)`, which between
 * them are the twelve corners of an icosahedron.
 *
 * @param values The triple.
 * @returns Every signed rotation of it.
 */
function cyclic(values: [number, number, number]): Vec3[] {
    const [a, b, c] = values;
    return [...signs([a, b, c]), ...signs([b, c, a]), ...signs([c, a, b])];
}

/**
 * The corners of a pentagonal trapezohedron — the real shape of a ten-sided die.
 *
 * Two sharp points, and between them two rings of five corners offset from one
 * another by half a step. That offset is what makes the faces kites rather than
 * triangles, and why the edge running around a d10 zig-zags instead of lying
 * flat.
 *
 * The height of the points is not a matter of taste. For the four corners of a
 * kite to lie in one plane — which they must, or it is not a flat face — the
 * points have to sit at `(1 + cos 36°) / (1 − cos 36°)` times the height of the
 * rings, which is about nine and a half. Any other value gives a die with
 * creased sides.
 *
 * That leaves one free choice: how high the rings are, which sets how tall the
 * die is against how wide. A manufactured d10 is roughly a tenth taller than it
 * is wide — around 22mm tall and 20mm across — so the ring height is picked to
 * match. Too tall and the faces narrow into slivers with the numbers piled on
 * top of one another; too flat and it stops looking like a d10 at all.
 *
 * @returns The twelve corners.
 */
function trapezohedronCorners(): Vec3[] {
    // Gives points at 1.1 against a ring radius of 1: a die 2.2 tall and 2 wide.
    const ringHeight = 0.1161;
    const pointHeight = (ringHeight * (1 + Math.cos(Math.PI / 5))) / (1 - Math.cos(Math.PI / 5));

    const corners: Vec3[] = [vec(0, pointHeight, 0), vec(0, -pointHeight, 0)];
    for (let i = 0; i < 5; i++) {
        const upper = (i / 5) * Math.PI * 2;
        const lower = upper + Math.PI / 5;
        corners.push(vec(Math.cos(upper), ringHeight, Math.sin(upper)));
        corners.push(vec(Math.cos(lower), -ringHeight, Math.sin(lower)));
    }
    return corners;
}

/**
 * The corners of each die.
 *
 * This is the entire description of the shapes. Everything else in this file is
 * derived from these numbers.
 */
const CORNERS: Record<DieType, Vec3[]> = {
    d4: [vec(1, 1, 1), vec(1, -1, -1), vec(-1, 1, -1), vec(-1, -1, 1)],
    d6: signs([1, 1, 1]),
    d8: cyclic([0, 0, 1]),
    d10: trapezohedronCorners(),
    d12: [...signs([1, 1, 1]), ...cyclic([0, 1 / PHI, PHI])],
    d20: cyclic([0, 1, PHI]),
    // Percentile dice are a ten-sided die read in tens.
    d100: trapezohedronCorners()
};

/** A flat side of a solid: which way it points, and how far out it sits. */
interface Plane {
    normal: Vec3;
    offset: number;
}

/**
 * Find every flat side of a solid, given only its corners.
 *
 * Take any three corners. They define a flat plane. That plane is a face of the
 * solid exactly when no corner sticks out past it — which is true of any shape
 * that bulges outwards rather than caving in, and all dice do.
 *
 * So: try every group of three corners, keep the planes that nothing pokes
 * through, and discard the duplicates. Twenty corners means about a thousand
 * groups to try, which a computer does instantly and which cannot be mistyped.
 *
 * @param corners The corners of the solid, centred on the origin.
 * @returns One plane per face, in no particular order.
 */
function facePlanes(corners: Vec3[]): Plane[] {
    const planes: Plane[] = [];

    for (let i = 0; i < corners.length; i++) {
        for (let j = i + 1; j < corners.length; j++) {
            for (let k = j + 1; k < corners.length; k++) {
                const perpendicular = cross(sub(corners[j], corners[i]), sub(corners[k], corners[i]));
                // Three corners in a straight line describe no plane at all.
                if (magnitude(perpendicular) < EPSILON) {
                    continue;
                }

                let normal = normalise(perpendicular);
                let offset = dot(corners[i], normal);

                // Point it away from the centre, so "outwards" is unambiguous.
                if (offset < 0) {
                    normal = vec(-normal.x, -normal.y, -normal.z);
                    offset = -offset;
                }
                // A plane through the middle cuts the solid in half; it is not a face.
                if (offset < EPSILON) {
                    continue;
                }
                // If any corner is outside this plane, the plane is inside the solid.
                if (corners.some((corner) => dot(corner, normal) > offset + EPSILON)) {
                    continue;
                }
                // The same face is found once per group of three of its corners.
                if (planes.some((plane) => dot(plane.normal, normal) > 1 - EPSILON)) {
                    continue;
                }

                planes.push({ normal, offset });
            }
        }
    }

    // A stable order — highest first, then around the die — so that the numbers
    // land in the same places every time rather than wherever the loop happened
    // to reach them.
    return planes.sort(
        (a, b) => a.normal.y - b.normal.y || Math.atan2(a.normal.x, a.normal.z) - Math.atan2(b.normal.x, b.normal.z)
    );
}

/**
 * Number the faces the way a real die is numbered.
 *
 * On a manufactured die, opposite faces add up to one more than the number of
 * sides: 1 is across from 6 on a d6, and across from 20 on a d20. It is done
 * that way so the weight is even, and it is visible — a d20 with 19 next to 20
 * looks wrong to anyone who has held one.
 *
 * A tetrahedron has no opposite faces, so its numbers simply run in order.
 *
 * @param planes The faces.
 * @returns The number on each face, matching the order of `planes`.
 */
function numberFaces(planes: Plane[]): number[] {
    const total = planes.length;
    const numbers = new Array<number>(total).fill(0);
    let next = 1;

    for (let i = 0; i < total; i++) {
        if (numbers[i] !== 0) {
            continue;
        }
        numbers[i] = next;

        const opposite = planes.findIndex((plane, j) => j !== i && dot(plane.normal, planes[i].normal) < -1 + 1e-6);
        if (opposite >= 0 && numbers[opposite] === 0) {
            numbers[opposite] = total + 1 - next;
        }
        next++;
    }

    return numbers;
}

/**
 * How a number should be printed on a given die.
 *
 * @param die Which die.
 * @param value Which face, counting from one.
 * @returns What to print. A d10 runs 0 to 9 rather than 1 to 10, and a
 *   percentile die shows 00, 10, 20 and so on — both the way real dice do.
 */
function labelFor(die: DieType, value: number): string {
    if (die === 'd10') {
        return `${value % 10}`;
    }
    if (die === 'd100') {
        const tens = value % 10;
        return tens === 0 ? '00' : `${tens * 10}`;
    }
    return `${value}`;
}

/**
 * Work out how to draw every face of a die.
 *
 * @param die Which die to build.
 * @returns One placement per face.
 */
function buildFaces(die: DieType): FacePlacement[] {
    const corners = CORNERS[die];
    const planes = facePlanes(corners);
    const numbers = numberFaces(planes);

    // Scale against the furthest corner, so every die comes out the same visual
    // size no matter how differently proportioned it is.
    const outerRadius = Math.max(...corners.map(magnitude));

    return planes.map((plane, index) => {
        const { normal, offset } = plane;
        const centre = vec(normal.x * offset, normal.y * offset, normal.z * offset);
        const onFace = corners.filter((corner) => Math.abs(dot(corner, normal) - offset) < 1e-6);

        const yaw = Math.atan2(normal.x, normal.z);
        const pitch = -Math.asin(Math.max(-1, Math.min(1, normal.y)));

        // Once the face has been turned by yaw and pitch, these are the
        // directions its own "right" and "down" point in. Measuring a corner
        // against them turns it from a point in space into a position on the
        // flat element, which is what `clip-path` needs.
        const cosYaw = Math.cos(yaw);
        const sinYaw = Math.sin(yaw);
        const cosPitch = Math.cos(pitch);
        const sinPitch = Math.sin(pitch);
        const faceRight = vec(cosYaw, 0, -sinYaw);
        const faceDown = vec(sinYaw * sinPitch, cosPitch, cosYaw * sinPitch);

        const flat = onFace
            .map((corner) => {
                const away = sub(corner, centre);
                return { x: dot(away, faceRight), y: dot(away, faceDown) };
            })
            // Put the corners in order around the edge. Unsorted points make
            // `clip-path` draw a bow tie instead of a face.
            .sort((a, b) => Math.atan2(a.y, a.x) - Math.atan2(b.y, b.x));

        const faceRadius = Math.max(...flat.map((point) => Math.hypot(point.x, point.y)));
        const polygon = flat
            .map((point) => {
                const x = 50 + (50 * point.x) / faceRadius;
                const y = 50 + (50 * point.y) / faceRadius;
                return `${x.toFixed(3)}% ${y.toFixed(3)}%`;
            })
            .join(', ');

        // The middle of a kite is not the middle of the box around it, so the
        // number goes at the average of the corners rather than at 50/50.
        const meanX = flat.reduce((total, point) => total + point.x, 0) / flat.length;
        const meanY = flat.reduce((total, point) => total + point.y, 0) / flat.length;

        return {
            yaw: (yaw * 180) / Math.PI,
            pitch: (pitch * 180) / Math.PI,
            distance: offset / outerRadius,
            size: (2 * faceRadius) / outerRadius,
            clipPath: `polygon(${polygon})`,
            labelX: 50 + (50 * meanX) / faceRadius,
            labelY: 50 + (50 * meanY) / faceRadius,
            value: numbers[index],
            label: labelFor(die, numbers[index])
        };
    });
}

/** Worked out once per die and kept, since the shape of an icosahedron is settled. */
const CACHE = new Map<DieType, FacePlacement[]>();

/**
 * The faces of a die, computed the first time and remembered after that.
 *
 * @param die Which die.
 * @returns Its faces.
 */
export function facesOf(die: DieType): FacePlacement[] {
    let faces = CACHE.get(die);
    if (!faces) {
        faces = buildFaces(die);
        CACHE.set(die, faces);
    }
    return faces;
}

/**
 * Which face should be facing the viewer for a given result.
 *
 * @param die Which die.
 * @param rolled The number that came up on the die itself — not the total,
 *   which may include a modifier and would point at a face that does not exist.
 * @returns The position of that face in the list from {@link facesOf}.
 */
export function faceIndexFor(die: DieType, rolled: number): number {
    const faces = facesOf(die);
    if (faces.length === 0) {
        return 0;
    }

    let wanted: number;
    if (die === 'd100') {
        // Percentile dice are read in tens: a 47 rests on the 40 face, and the
        // 00 face is the tenth one rather than a zeroth.
        const tens = Math.min(9, Math.max(0, Math.floor((rolled - 1) / 10)));
        wanted = tens === 0 ? 10 : tens;
    } else if (die === 'd10') {
        const digit = ((rolled % 10) + 10) % 10;
        wanted = digit === 0 ? 10 : digit;
    } else {
        wanted = Math.min(faces.length, Math.max(1, rolled));
    }

    const index = faces.findIndex((face) => face.value === wanted);
    return index >= 0 ? index : 0;
}

/**
 * How far to turn the die to bring one face round to look at the viewer.
 *
 * Undoing a face's own yaw and pitch, in the opposite order, points it back at
 * the camera. That is what lets the die settle showing the number it actually
 * rolled, the way a real die comes to rest — rather than stopping in a random
 * position with the answer printed somewhere on the back.
 *
 * The two angles are returned separately rather than as a finished transform
 * because the tumble animation needs to do arithmetic on them: it starts a
 * whole number of turns away from this position and ends exactly on it, so
 * there is no jump between the animation finishing and the die settling.
 *
 * @param die Which die.
 * @param faceIndex Which face should end up facing forwards.
 * @returns The two turns, in degrees.
 */
export function restingAngles(die: DieType, faceIndex: number): { x: number; y: number } {
    const faces = facesOf(die);
    const face = faces[Math.min(faces.length - 1, Math.max(0, faceIndex))];
    if (!face) {
        return { x: 0, y: 0 };
    }
    return { x: -face.pitch, y: -face.yaw };
}
