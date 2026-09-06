/**
 * A polyhedral die that tumbles in three dimensions and lands on its number.
 *
 * HOW THE 3D IS DONE, AND WHY THERE IS NO 3D LIBRARY
 *
 * The die is built from ordinary HTML elements — one per face — placed in space
 * with CSS `transform-style: preserve-3d`. The browser handles the perspective,
 * the rotation and working out which faces are in front. There is no canvas, no
 * WebGL and no library.
 *
 * A 3D library would draw a slightly nicer die. It would also add several
 * hundred kilobytes to a page whose entire bundle is under a hundred, for
 * something that is on screen for a second and a half. That is the wrong trade
 * for this project. What it would *not* buy is correctness — the shapes here
 * are the real solids, computed in `polyhedra.ts`, not approximations.
 *
 * WHERE THE SHAPES COME FROM
 *
 * All of it — how many faces, which way each one points, what shape it is,
 * where its number sits — is worked out in `core/dice/polyhedra.ts` from the
 * corners of the solid. This file only turns those numbers into styles.
 *
 * WHY THE FACES ARE SHADED HERE AND NOT THERE
 *
 * Shading is a matter of taste; geometry is not. `polyhedra.ts` says where a
 * face is, and this component decides how light it looks. Facets that are all
 * the same colour make a d20 read as a flat blob, so each face is tinted by how
 * much it faces an imaginary light above and to the left. That is what makes
 * the shape legible while it is spinning.
 *
 * THE RESULT IS DECIDED BEFORE THE ANIMATION STARTS
 *
 * The tumble is theatre. `dice.ts` produced the number the instant the button
 * was pressed; this component only makes the wait feel like something, and then
 * turns the die so that number is facing you when it stops. That separation is
 * what lets the animation be tuned freely, and what keeps the rules testable
 * without a browser.
 */

import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

import { DieType } from '../../core/dice/dice';
import { FacePlacement, faceIndexFor, facesOf, restingAngles } from '../../core/dice/polyhedra';

/** One face, ready to be handed straight to the template as styles. */
interface DrawnFace {
    transform: string;
    clipPath: string;
    sizePx: number;
    fontPx: number;
    labelX: number;
    labelY: number;
    label: string;
    shade: number;
    /** True for the face that is showing when the die stops. */
    winning: boolean;
    /** True for a 6 or a 9, which are underlined on real dice so they can be told apart. */
    underlined: boolean;
}

/**
 * Which way the imaginary light comes from: above, in front, and a little to
 * the left. `y` is negative because the browser counts downwards.
 */
const LIGHT = { x: -0.35, y: -0.8, z: 0.5 };
const LIGHT_LENGTH = Math.hypot(LIGHT.x, LIGHT.y, LIGHT.z);

/** How one kind of die behaves when it is thrown. */
interface Motion {
    /** How long the throw lasts, in milliseconds. */
    ms: number;

    /** How far it turns end over end, in degrees. Always a whole number of turns. */
    turnX: number;

    /** How far it spins about its upright axis, in degrees. Always a whole number of turns. */
    turnY: number;

    /** How high it bounces, as a fraction of the die's size. */
    bounce: number;
}

/**
 * How each die moves when it is thrown.
 *
 * Dice do not all behave the same way, and using one animation for all of them
 * is the reason a d4 and a d20 previously looked identical in flight. The
 * differences are the ones you would see on a table:
 *
 * - A **d4** is blunt and heavy for its size. It does not roll — it tips from
 *   one corner to the next and stops almost at once, with a hard bounce.
 * - A **d6** tumbles squarely over its edges. Fewer, more deliberate turns.
 * - A **d8** and a **d10** spin about their points, so most of their motion is
 *   around the upright axis rather than end over end. A d10 in particular
 *   spins far more than it tumbles.
 * - A **d12** is close to round and rolls smoothly.
 * - A **d20** is the closest thing to a ball in the set. It travels the
 *   longest, spins the most and barely bounces at all.
 *
 * The turns are whole multiples of 360 degrees on purpose: the animation
 * starts exactly that far back from where the die will finish, so it lands on
 * its final face with no jump between the throw ending and the die settling.
 */
const MOTION: Record<DieType, Motion> = {
    d4: { ms: 900, turnX: 720, turnY: 360, bounce: 0.34 },
    d6: { ms: 1000, turnX: 1080, turnY: 720, bounce: 0.3 },
    d8: { ms: 1060, turnX: 720, turnY: 1440, bounce: 0.3 },
    d10: { ms: 1120, turnX: 360, turnY: 1800, bounce: 0.24 },
    d12: { ms: 1160, turnX: 1080, turnY: 1080, bounce: 0.2 },
    d20: { ms: 1260, turnX: 1440, turnY: 1440, bounce: 0.16 },
    d100: { ms: 1120, turnX: 360, turnY: 1800, bounce: 0.24 }
};

/**
 * How long a given die stays in the air.
 *
 * The tray needs this to know when to stop showing the die as rolling, and it
 * has to be the same number the animation uses — so both read it from here
 * rather than each keeping their own copy.
 *
 * @param die Which die.
 * @returns The length of the throw, in milliseconds.
 */
export function tumbleDuration(die: DieType): number {
    return MOTION[die].ms;
}

@Component({
    selector: 'app-die-3d',
    changeDetection: ChangeDetectionStrategy.OnPush,
    template: `
        <div
            class="stage"
            [class.stage--rolling]="rolling()"
            [style.width.px]="radius() * 2.2"
            [style.height.px]="radius() * 2.2"
        >
            <!--
          Sits behind the die. It is a drawn halo rather than a CSS filter on
          the die, because a filter flattens 3D children and would collapse the
          whole polyhedron.
        -->
            <span
                class="halo"
                [class.halo--critical]="critical() && !rolling()"
                [class.halo--fumble]="fumble() && !rolling()"
                aria-hidden="true"
            ></span>

            <div
                class="die"
                [style.transform]="dieTransform()"
                [style.--rest-x]="cssVars().restX"
                [style.--rest-y]="cssVars().restY"
                [style.--turn-x]="cssVars().turnX"
                [style.--turn-y]="cssVars().turnY"
                [style.--bounce]="cssVars().bounce"
                [style.--tumble-ms]="cssVars().duration"
            >
                @for (face of faces(); track $index) {
                    <span
                        class="face"
                        [class.face--winning]="face.winning && !rolling()"
                        [style.--clip]="face.clipPath"
                        [style.--shade]="face.shade"
                        [style.width.px]="face.sizePx"
                        [style.height.px]="face.sizePx"
                        [style.transform]="face.transform"
                    >
                        <span
                            class="pip"
                            [class.pip--underlined]="face.underlined"
                            [style.left.%]="face.labelX"
                            [style.top.%]="face.labelY"
                            [style.font-size.px]="face.fontPx"
                            >{{ face.label }}</span
                        >
                    </span>
                }
            </div>
        </div>

        <!--
      The number is read out for screen readers rather than left to be
      inferred from a rotating shape, which no assistive technology can see.
    -->
        <span class="visually-hidden" aria-live="polite">
            @if (hasResult() && !rolling()) {
                Rolled {{ roll() }} on a {{ type() }}.
            }
        </span>
    `,
    styleUrl: './die-3d.scss'
})
export class Die3d {
    /** Which die this is. Decides the shape, the face count and the numbering. */
    readonly type = input.required<DieType>();

    /**
     * The number that came up **on the die itself**.
     *
     * Not the total. A d20 with a +3 modifier can total 23, and there is no
     * face 23 to land on — the die shows the 20 and the tray shows the total.
     */
    readonly roll = input<number>(1);

    /** True while the die is in the air. */
    readonly rolling = input<boolean>(false);

    /**
     * Whether anything has been rolled yet.
     *
     * Before the first roll the die sits at a pleasant angle showing whatever
     * faces happen to be forward, the way a die sitting on a table does. It
     * only turns deliberately once there is a result to show.
     */
    readonly hasResult = input<boolean>(false);

    /** True on a natural 20 — the die glows gold. */
    readonly critical = input<boolean>(false);

    /** True on a natural 1 — the die glows red. */
    readonly fumble = input<boolean>(false);

    /** How big the die is, measured from its centre to its furthest corner. */
    readonly radius = input<number>(44);

    /** Which face ends up facing the viewer. */
    private readonly winningFace = computed(() => faceIndexFor(this.type(), this.roll()));

    /** How this kind of die behaves when it is thrown. */
    readonly motion = computed(() => MOTION[this.type()]);

    /**
     * Where the die comes to rest.
     *
     * Before the first roll, an angle that shows several faces at once so the
     * shape reads as solid rather than as a flat badge. After a roll, whatever
     * turn brings the rolled number round to the front.
     */
    readonly rest = computed(() =>
        this.hasResult() ? restingAngles(this.type(), this.winningFace()) : { x: -20, y: 28 }
    );

    /**
     * How the whole die is turned.
     *
     * While the die is in the air this is overridden by the tumble animation,
     * which is written to finish at exactly this angle — so when the animation
     * comes off, nothing moves.
     */
    readonly dieTransform = computed(
        () => `rotateX(${this.rest().x.toFixed(3)}deg) rotateY(${this.rest().y.toFixed(3)}deg)`
    );

    /**
     * The numbers the tumble animation needs, as CSS values with their units.
     *
     * Custom properties hold plain text, so the units have to be part of the
     * value — Angular's `[style.width.px]` shorthand only applies to real CSS
     * properties, not to `--` ones.
     */
    readonly cssVars = computed(() => {
        const motion = this.motion();
        return {
            restX: `${this.rest().x.toFixed(3)}deg`,
            restY: `${this.rest().y.toFixed(3)}deg`,
            turnX: `${motion.turnX}deg`,
            turnY: `${motion.turnY}deg`,
            bounce: `${(this.radius() * motion.bounce).toFixed(1)}px`,
            duration: `${motion.ms}ms`
        };
    });

    /** Every face, converted from geometry into styles. */
    readonly faces = computed<DrawnFace[]>(() => {
        const radius = this.radius();
        const winning = this.winningFace();

        return facesOf(this.type()).map((face, index) => {
            const sizePx = face.size * radius;
            return {
                // `transform-origin` is the middle of the die, so each face is
                // turned to point the right way, pushed out to the surface, and
                // then shifted by half its own width to sit centred on it.
                transform:
                    `rotateY(${face.yaw.toFixed(3)}deg) rotateX(${face.pitch.toFixed(3)}deg) ` +
                    `translateZ(${(face.distance * radius).toFixed(2)}px) translate(-50%, -50%)`,
                clipPath: face.clipPath,
                sizePx,
                // Two digits need to be smaller to fit inside the same facet.
                fontPx: sizePx * (face.label.length > 1 ? 0.26 : 0.36),
                labelX: face.labelX,
                labelY: face.labelY,
                label: face.label,
                shade: shadeOf(face),
                winning: index === winning,
                // A 6 and a 9 are the same shape upside down, so real dice
                // underline them. Only on dice that have both.
                underlined: face.label === '6' || face.label === '9'
            };
        });
    });
}

/**
 * How brightly lit a face is, from its direction.
 *
 * A face turned towards the light is pale, one turned away is dark, and the
 * difference is what separates one facet from the next. Without it a
 * twenty-sided die is a grey circle.
 *
 * @param face The face.
 * @returns A number from about 0.45 to 1, for the stylesheet to mix colours by.
 */
function shadeOf(face: FacePlacement): number {
    const yaw = (face.yaw * Math.PI) / 180;
    const pitch = (face.pitch * Math.PI) / 180;
    const normal = {
        x: Math.sin(yaw) * Math.cos(pitch),
        y: -Math.sin(pitch),
        z: Math.cos(yaw) * Math.cos(pitch)
    };

    const lit = (normal.x * LIGHT.x + normal.y * LIGHT.y + normal.z * LIGHT.z) / LIGHT_LENGTH;
    return Number((0.45 + 0.55 * Math.max(0, lit)).toFixed(3));
}
