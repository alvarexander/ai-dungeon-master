/**
 * The application mark: a twenty-sided die.
 *
 * WHY A D20
 *
 * It is the emblem of the whole hobby. The fifth edition rules ask for it by
 * default — every check, every attack, every saving throw is a d20 — and it is
 * the shape a player recognises before reading a word of the page.
 *
 * WHY IT IS DRAWN HERE RATHER THAN LOADED AS AN IMAGE
 *
 * Same reasoning as the icons in `icon.ts`: an inline drawing costs no network
 * request, cannot arrive late or fail on a patchy connection, and scales to any
 * size without a second file. The mark is small enough that inlining it is
 * cheaper than fetching it would be.
 *
 * WHY IT CARRIES NO NUMBER
 *
 * A real d20 has numbers on its faces, and the obvious thing is to put a "20"
 * on the front one. At the size this appears — beside the wordmark in the
 * header, and sixteen pixels across in a browser tab — that number would be a
 * smudge, and drawing real text would mean depending on a font that may not be
 * installed. The faceted outline is recognisable at every size and needs
 * nothing.
 *
 * WHERE THE SHAPE COMES FROM
 *
 * Not drawn by eye. Seen straight down one of its faces, an icosahedron's
 * outline is a perfect regular hexagon divided into ten triangles, and these
 * are those ten triangles — computed from the corners of the solid by the same
 * arithmetic as `core/dice/polyhedra.ts`, which is also what draws the dice in
 * the tray. The two are the same shape because they are the same maths.
 *
 * The facets are tinted by how squarely each faces a light above and to the
 * left. That shading is the only reason a flat drawing reads as a solid object.
 *
 * `public/favicon.svg` is this same mark with a dark rounded background behind
 * it, so it holds together on a pale browser tab. If one changes, change both.
 */

import { ChangeDetectionStrategy, Component, input } from '@angular/core';

@Component({
    selector: 'app-logo',
    changeDetection: ChangeDetectionStrategy.OnPush,
    template: `
        <svg
            [attr.width]="size()"
            [attr.height]="size()"
            viewBox="0 0 128 128"
            [attr.aria-hidden]="label() ? null : true"
            [attr.role]="label() ? 'img' : null"
            [attr.aria-label]="label() || null"
        >
            @if (label()) {
                <title>{{ label() }}</title>
            }

            <g stroke="#3a2a0e" stroke-width="1.4" stroke-linejoin="round">
                <polygon points="39.38,78.21 88.62,78.21 64.00,35.57" fill="#f5cc78" />
                <polygon points="64.00,110.00 88.62,78.21 39.38,78.21" fill="#6b4a17" />
                <polygon points="39.38,78.21 64.00,35.57 24.16,41.00" fill="#e0b455" />
                <polygon points="88.62,78.21 103.84,41.00 64.00,35.57" fill="#b8862f" />
                <polygon points="64.00,110.00 39.38,78.21 24.16,87.00" fill="#6b4a17" />
                <polygon points="24.16,87.00 39.38,78.21 24.16,41.00" fill="#b8862f" />
                <polygon points="64.00,110.00 103.84,87.00 88.62,78.21" fill="#5c3f13" />
                <polygon points="24.16,41.00 64.00,35.57 64.00,18.00" fill="#f0c164" />
                <polygon points="88.62,78.21 103.84,87.00 103.84,41.00" fill="#5c3f13" />
                <polygon points="64.00,35.57 103.84,41.00 64.00,18.00" fill="#d9a441" />
            </g>

            <!-- Drawn last so the outline stays crisp over the facets. -->
            <polygon
                points="64,18 103.84,41 103.84,87 64,110 24.16,87 24.16,41"
                fill="none"
                stroke="#f5cc78"
                stroke-width="2.6"
                stroke-linejoin="round"
            />
        </svg>
    `,
    styles: [
        `
            :host {
                display: inline-flex;
            }
            svg {
                display: block;
            }
        `
    ]
})
export class Logo {
    /** Width and height in pixels. The mark is square. */
    readonly size = input<number>(28);

    /**
     * A description for screen readers.
     *
     * Leave it empty where the mark sits beside the application's name, which
     * already says the same thing — a screen reader announcing the title twice
     * is worse than silence.
     */
    readonly label = input<string>('');
}
