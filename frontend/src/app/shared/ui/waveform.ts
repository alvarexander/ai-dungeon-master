/**
 * A live waveform, showing what the microphone is picking up.
 *
 * WHY THIS IS NOT DECORATION
 *
 * A recording indicator that does not move gives no clue whether the
 * microphone is actually hearing anything. People speak into a muted device,
 * or one where the browser picked the wrong input, and only find out when
 * nothing arrives — after they have said their piece.
 *
 * Bars that move with your voice answer "is this working?" instantly, without
 * anybody having to explain it.
 *
 * The bars are plain elements rather than a canvas. There are only twenty-eight
 * of them, updated on animation frames the browser is drawing anyway, so the
 * cost is negligible and the result inherits the theme's colours for free.
 */

import { ChangeDetectionStrategy, Component, input } from '@angular/core';

@Component({
    selector: 'app-waveform',
    changeDetection: ChangeDetectionStrategy.OnPush,
    template: `
        <div
            class="wave"
            [class.wave--idle]="!active()"
            role="img"
            [attr.aria-label]="active() ? 'Microphone level' : 'Microphone idle'"
        >
            @for (level of levels(); track $index) {
                <span class="wave__bar" [style.height.%]="level * 100"></span>
            }
        </div>
    `,
    styles: [
        `
            .wave {
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 2px;
                height: 32px;
                flex: 1;
                min-width: 0;
            }
            .wave__bar {
                flex: 1;
                min-width: 2px;
                max-width: 4px;
                min-height: 2px;
                border-radius: 2px;
                background: var(--accent-strong);
                /* Short enough to feel immediate, long enough that the bars glide
           rather than flicker between frames. */
                transition: height 80ms linear;
            }
            .wave--idle .wave__bar {
                background: var(--border-strong);
            }

            /* Motion here conveys information, so it is not removed entirely for
         reduced-motion users — but the easing is dropped so nothing glides. */
            @media (prefers-reduced-motion: reduce) {
                .wave__bar {
                    transition: none;
                }
            }
        `
    ]
})
export class Waveform {
    /** Bar heights, each 0 to 1, from `VoiceRecorder.levels`. */
    readonly levels = input.required<number[]>();

    /** Whether the microphone is live. Drives the colour. */
    readonly active = input<boolean>(false);
}
