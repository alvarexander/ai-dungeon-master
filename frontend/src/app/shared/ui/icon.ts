/**
 * Google Material Symbols, drawn inline as SVG.
 *
 * WHY THESE ARE INLINE RATHER THAN A FONT FROM GOOGLE
 *
 * The usual way to use Material icons is a stylesheet link to
 * `fonts.googleapis.com`. That works, and it has three costs this project would
 * rather not pay:
 *
 * 1. **It contacts Google on every page load**, from the user's browser, before
 *   they have done anything. That is a third-party request carrying their IP
 *   address, and it is the specific thing several European data protection
 *   rulings have taken issue with.
 * 2. **It blocks rendering.** Icons appear late, or as squares, on a slow
 *   connection.
 * 3. **It breaks offline**, including on a laptop with patchy wifi at a table.
 *
 * The paths below are the real Material Symbols outlines, embedded. Material
 * Symbols are published by Google under the Apache License 2.0, which permits
 * this. The result is the same icon set with no external request at all.
 *
 * To add one: find it at fonts.google.com/icons, copy the SVG path data from
 * the 24px outlined variant, and add an entry to `ICONS`.
 */

import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

/** Every icon this application uses. */
export type IconName =
    | 'mic'
    | 'mic_off'
    | 'send'
    | 'stop'
    | 'close'
    | 'volume_up'
    | 'volume_off'
    | 'graphic_eq'
    | 'forum'
    | 'replay'
    | 'pause'
    | 'casino'
    | 'add'
    | 'remove'
    | 'arrow_upward'
    | 'arrow_downward'
    | 'menu'
    | 'play_arrow'
    | 'auto_stories'
    | 'settings'
    | 'person'
    | 'shield';

/**
 * Path data for each icon, on a 24 by 24 grid.
 *
 * These are Material Symbols outlines, from fonts.google.com/icons, published
 * by Google under the Apache License 2.0.
 */
const ICONS: Record<IconName, string> = {
    mic:
        'M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3zm5-3c0 ' +
        '2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z',
    mic_off:
        'M19 11h-1.7c0 .74-.16 1.43-.43 2.05l1.23 1.23c.56-.98.9-2.09.9-3.28zm-4.02.17c0-.06.02-.11' +
        '.02-.17V5c0-1.66-1.34-3-3-3S9 3.34 9 5v.18l5.98 5.99zM4.27 3L3 4.27l6.01 6.01V11c0 1.66 ' +
        '1.33 3 2.99 3 .22 0 .44-.03.65-.08l1.66 1.66c-.71.33-1.5.52-2.31.52-2.76 0-5.3-2.1-5.3-5.1' +
        'H5c0 3.41 2.72 6.23 6 6.72V21h2v-3.28c.91-.13 1.77-.45 2.54-.9L19.73 21 21 19.73 4.27 3z',
    send: 'M2.01 21L23 12 2.01 3 2 10l15 2-15 2z',
    stop: 'M6 6h12v12H6z',
    pause: 'M6 19h4V5H6v14zm8-14v14h4V5h-4z',
    close: 'M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 ' + '17.59 13.41 12z',
    volume_up:
        'M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02z' +
        'M14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-' +
        '7.86-7-8.77z',
    volume_off:
        'M16.5 12c0-1.77-1.02-3.29-2.5-4.03v2.21l2.45 2.45c.03-.2.05-.41.05-.63zm2.5 0c0 .94-.2 ' +
        '1.82-.54 2.64l1.51 1.51C20.63 14.91 21 13.5 21 12c0-4.28-2.99-7.86-7-8.77v2.06c2.89.86 5 ' +
        '3.54 5 6.71zM4.27 3L3 4.27 7.73 9H3v6h4l5 5v-6.73l4.25 4.25c-.67.52-1.42.93-2.25 1.18v2.06' +
        'c1.38-.31 2.63-.95 3.69-1.81L19.73 21 21 19.73l-9-9L4.27 3zM12 4L9.91 6.09 12 8.18V4z',
    graphic_eq: 'M7 18h2V6H7v12zm4 4h2V2h-2v20zm-8-8h2v-4H3v4zm12 4h2V6h-2v12zm4-8v4h2v-4h-2z',
    forum:
        'M15 4v7H5.17L4 12.17V4h11m1-2H3c-.55 0-1 .45-1 1v14l4-4h10c.55 0 1-.45 1-1V3c0-.55-.45-1' +
        '-1-1zm5 4h-2v9H6v2c0 .55.45 1 1 1h11l4 4V7c0-.55-.45-1-1-1z',
    casino:
        'M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zM7.5 18c-.83 ' +
        '0-1.5-.67-1.5-1.5S6.67 15 7.5 15s1.5.67 1.5 1.5S8.33 18 7.5 18zm0-9C6.67 9 6 8.33 6 ' +
        '7.5S6.67 6 7.5 6 9 6.67 9 7.5 8.33 9 7.5 9zm4.5 4.5c-.83 0-1.5-.67-1.5-1.5s.67-1.5 ' +
        '1.5-1.5 1.5.67 1.5 1.5-.67 1.5-1.5 1.5zm4.5 4.5c-.83 0-1.5-.67-1.5-1.5s.67-1.5 1.5-1.5 ' +
        '1.5.67 1.5 1.5-.67 1.5-1.5 1.5zm0-9c-.83 0-1.5-.67-1.5-1.5S15.67 6 16.5 6s1.5.67 1.5 ' +
        '1.5S17.33 9 16.5 9z',
    add: 'M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z',
    remove: 'M19 13H5v-2h14v2z',
    arrow_upward: 'M4 12l1.41 1.41L11 7.83V20h2V7.83l5.58 5.59L20 12l-8-8-8 8z',
    arrow_downward: 'M20 12l-1.41-1.41L13 16.17V4h-2v12.17l-5.58-5.59L4 12l8 8 8-8z',
    replay:
        'M12 5V1L7 6l5 5V7c3.31 0 6 2.69 6 6s-2.69 6-6 6-6-2.69-6-6H4c0 4.42 3.58 8 8 8s8-3.58 8-8' + '-3.58-8-8-8z',
    menu: 'M3 18h18v-2H3v2zm0-5h18v-2H3v2zm0-7v2h18V6H3z',
    play_arrow: 'M8 5v14l11-7z',
    auto_stories:
        'M19 1l-5 5v11l5-4.5V1zM1 6v14.65c0 .25.25.5.5.5.1 0 .15-.05.25-.05C3.1 20.45 5.05 20 6.5 20' +
        'c1.95 0 4.05.4 5.5 1.5V6c-1.45-1.1-3.55-1.5-5.5-1.5S2.45 4.9 1 6zm22 13.5V6c-.6-.45-1.25-.75' +
        '-2-1v13.5c-1.1-.35-2.3-.5-3.5-.5-1.7 0-4.15.65-5.5 1.5v2c1.35-.85 3.8-1.5 5.5-1.5 1.65 0 ' +
        '3.35.3 4.75 1.05.1.05.15.05.25.05.25 0 .5-.25.5-.5z',
    settings:
        'M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58c.18-.14.23-.41.12-.61l-1.92' +
        '-3.32c-.12-.22-.37-.29-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54c-.04-.24-.24-.41' +
        '-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96c-.22-.08-.47 ' +
        '0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.09.63-.09.94s.02.64.07.94l-2.03 ' +
        '1.58c-.18.14-.23.41-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 ' +
        '2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96' +
        'c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6c-1.98 0-3.6-1.62' +
        '-3.6-3.6s1.62-3.6 3.6-3.6 3.6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z',
    person: 'M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z',
    shield: 'M12 1L3 5v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V5l-9-4z'
};

@Component({
    selector: 'app-icon',
    changeDetection: ChangeDetectionStrategy.OnPush,
    template: `
        <svg
            [attr.width]="size()"
            [attr.height]="size()"
            viewBox="0 0 24 24"
            fill="currentColor"
            [attr.aria-hidden]="label() ? null : true"
            [attr.role]="label() ? 'img' : null"
            [attr.aria-label]="label() || null"
        >
            @if (label()) {
                <title>{{ label() }}</title>
            }
            <path [attr.d]="path()" />
        </svg>
    `,
    styles: [
        `
            :host {
                display: inline-flex;
                align-items: center;
                justify-content: center;
            }
            svg {
                display: block;
            }
        `
    ]
})
export class Icon {
    /** Which icon to draw. */
    readonly name = input.required<IconName>();

    /** Width and height in pixels. Icons are square. */
    readonly size = input<number>(20);

    /**
     * A description for screen readers.
     *
     * Leave it empty when the icon sits next to text that already says the same
     * thing — a screen reader announcing "send send" is worse than silence. Set
     * it when the icon is the only label, as on an icon-only button.
     */
    readonly label = input<string>('');

    /**
     * The path data for the chosen icon.
     *
     * @returns The SVG path, or the microphone as a fallback so an unknown name
     *   shows something rather than an invisible gap.
     */
    readonly path = computed(() => ICONS[this.name()] ?? ICONS.mic);
}
