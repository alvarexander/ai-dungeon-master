/**
 * User settings.
 *
 * Everything here except the voice is saved to the account, so it follows the
 * player between devices. The chosen voice is the exception and is kept in the
 * browser, because the available voices differ from machine to machine — see
 * `SpeechService.setVoice`.
 */

import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { RouterLink } from '@angular/router';

import { UserSettings } from '../../core/api/api.types';
import { SettingsStore } from '../../core/state/settings.store';
import { SpeechService } from '../../core/voice/speech';
import { Banner } from '../../shared/ui/banner';
import { Icon } from '../../shared/ui/icon';

@Component({
    selector: 'app-settings-page',
    changeDetection: ChangeDetectionStrategy.OnPush,
    imports: [RouterLink, Banner, Icon],
    template: `
        <div class="page page--narrow">
            <header class="page__header">
                <h1>Settings</h1>
                <p class="page__lead">Changes save themselves as you make them.</p>
            </header>

            @if (error(); as message) {
                <app-banner kind="danger"
                    ><p style="margin: 0">{{ message }}</p></app-banner
                >
            }
            @if (recentlySaved()) {
                <app-banner kind="success"><p style="margin: 0">Saved.</p></app-banner>
            }

            <section class="card">
                <h2>The Dungeon Master</h2>

                <label class="field">
                    <span class="field__label">How much narration</span>
                    <select
                        class="select"
                        [value]="settings().narration_length"
                        (change)="set({ narration_length: value($event) })"
                    >
                        <option value="brief">Brief — one short paragraph a turn</option>
                        <option value="standard">Standard — two or three paragraphs</option>
                        <option value="rich">Rich — more description and sensory detail</option>
                    </select>
                </label>

                <label class="field">
                    <span class="field__label">Content</span>
                    <select
                        class="select"
                        [value]="settings().content_filter"
                        (change)="set({ content_filter: value($event) })"
                    >
                        <option value="family">Suitable for all ages</option>
                        <option value="standard">As a published adventure</option>
                        <option value="mature">Adult themes and moral complexity</option>
                    </select>
                    <span class="field__hint">
                        Steers what the Dungeon Master will describe. It is an instruction, not a guarantee — the model
                        has its own safety limits on top of this.
                    </span>
                </label>

                <label class="toggle">
                    <input
                        type="checkbox"
                        [checked]="settings().dice_rolls_visible"
                        (change)="set({ dice_rolls_visible: checked($event) })"
                    />
                    <span>
                        <strong>Show dice rolls</strong>
                        <span class="small muted">
                            Off keeps the results behind the screen, as a human Dungeon Master might.
                        </span>
                    </span>
                </label>
            </section>

            <section class="card">
                <h2>Voice</h2>

                <label class="toggle">
                    <input
                        type="checkbox"
                        [checked]="settings().voice_input_enabled"
                        (change)="set({ voice_input_enabled: checked($event) })"
                    />
                    <span>
                        <strong>Voice input</strong>
                        <span class="small muted">
                            Shows the microphone button. Recordings are transcribed on our own server and are never sent
                            to Google or anyone else.
                        </span>
                    </span>
                </label>

                <label class="toggle">
                    <input
                        type="checkbox"
                        [checked]="settings().voice_autosend"
                        [disabled]="!settings().voice_input_enabled"
                        (change)="set({ voice_autosend: checked($event) })"
                    />
                    <span>
                        <strong>Send as soon as I stop speaking</strong>
                        <span class="small muted"> Off lets you read the transcription and correct it first. </span>
                    </span>
                </label>

                <label class="toggle">
                    <input
                        type="checkbox"
                        [checked]="settings().voice_output_enabled"
                        (change)="set({ voice_output_enabled: checked($event) })"
                    />
                    <span>
                        <strong>The Dungeon Master reads its narration aloud</strong>
                        <span class="small muted">
                            Uses the voice built into your browser, so nothing is sent anywhere to produce the audio.
                            Both this and voice input must be on for hands-free play.
                        </span>
                    </span>
                </label>
                @if (speech.isSupported() && settings().voice_output_enabled) {
                    <label class="field" style="margin-top: var(--space-3)">
                        <span class="field__label">Which voice</span>
                        <select class="select" [value]="speech.voiceName()" (change)="chooseVoice($event)">
                            <option value="">Best available on this device</option>
                            @for (voice of speech.rankedVoices(); track voice.name) {
                                <option [value]="voice.name">{{ voice.name }} ({{ voice.lang }})</option>
                            }
                        </select>
                        <span class="field__hint">
                            Voices differ between computers, so this one is remembered on this device rather than on
                            your account. The list is ordered best first — anything marked Premium, Enhanced or Natural
                            is a large downloaded voice and sounds noticeably better than the rest.
                        </span>
                    </label>

                    <label class="field volume">
                        <span class="field__label">
                            How loud
                            <span class="volume__readout mono">{{ volumePercent() }}%</span>
                        </span>
                        <div class="volume__row">
                            <app-icon [name]="speech.muted() ? 'volume_off' : 'volume_up'" [size]="18" />
                            <input
                                type="range"
                                class="range"
                                min="0"
                                max="100"
                                step="5"
                                [value]="volumePercent()"
                                (input)="chooseVolume($event)"
                                aria-label="Narration volume"
                            />
                        </div>
                        <span class="field__hint">
                            @if (speech.muted()) {
                                <strong>Turned all the way down.</strong> The Dungeon Master will not read anything
                                aloud, and hands-free play will not wait for it to finish. The replies still arrive as
                                text exactly as before.
                            } @else {
                                Remembered on this device rather than on your account, because headphones and laptop
                                speakers want very different settings.
                            }
                        </span>
                    </label>

                    <button
                        type="button"
                        class="btn btn--sm"
                        (click)="speech.preview()"
                        [disabled]="speech.muted()"
                        [title]="speech.muted() ? 'Turn the volume up to hear the voice' : ''"
                    >
                        <app-icon name="volume_up" [size]="16" />
                        Hear this voice
                    </button>

                    @if (!speech.hasHighQualityVoice()) {
                        <p class="small muted voice-tip">
                            <strong>Sounding robotic?</strong> Your computer only has its basic voices installed. The
                            large downloadable ones are dramatically better, and it is a one-time download.
                            <br />
                            <span class="muted">
                                On a Mac: System Settings → Accessibility → Spoken Content → System Voice → Manage
                                Voices, then pick anything marked Premium or Enhanced. On Windows: Settings → Time &amp;
                                Language → Speech → Manage voices. Reload this page afterwards and the new voice appears
                                in the list above.
                            </span>
                        </p>
                    }
                }
            </section>

            <section class="card">
                <h2>Appearance</h2>

                <label class="field">
                    <span class="field__label">Theme</span>
                    <select class="select" [value]="settings().theme" (change)="set({ theme: value($event) })">
                        <option value="dark">Dark</option>
                        <option value="light">Light</option>
                        <option value="system">Match my system</option>
                    </select>
                </label>

                <label class="toggle">
                    <input
                        type="checkbox"
                        [checked]="settings().reduce_motion"
                        (change)="set({ reduce_motion: checked($event) })"
                    />
                    <span>
                        <strong>Reduce motion</strong>
                        <span class="small muted">
                            Removes animation. This is switched on automatically if your operating system already asks
                            for it.
                        </span>
                    </span>
                </label>
            </section>

            <section class="card">
                <h2>Privacy</h2>

                <label class="toggle">
                    <input
                        type="checkbox"
                        [checked]="settings().analytics_opt_in"
                        (change)="set({ analytics_opt_in: checked($event) })"
                    />
                    <span>
                        <strong>Contribute anonymous usage counts</strong>
                        <span class="small muted">
                            Counts of things like sessions started and turns taken. Recorded against a random identifier
                            unrelated to your account, with no free text — there is physically no field in the analytics
                            database that could hold anything you typed.
                        </span>
                    </span>
                </label>

                <p class="small muted" style="margin-bottom: 0">
                    For the full picture of what is stored and what leaves this server, see
                    <a routerLink="/privacy">Your data</a>.
                </p>
            </section>
        </div>
    `,
    styles: [
        `
            .page--narrow {
                max-width: 640px;
            }
            section {
                margin-bottom: var(--space-4);
            }
            .toggle {
                display: flex;
                gap: var(--space-3);
                align-items: flex-start;
                padding: var(--space-3) 0;
                cursor: pointer;
                border-top: 1px solid var(--border);
            }
            .toggle:first-of-type {
                border-top: none;
            }
            .toggle input {
                margin-top: 5px;
                flex-shrink: 0;
            }
            .toggle span span {
                display: block;
            }
            .volume {
                margin-top: var(--space-3);
            }
            .volume__row {
                display: flex;
                align-items: center;
                gap: var(--space-3);
            }
            .volume__readout {
                float: right;
                color: var(--ink-muted);
                font-weight: 400;
            }
            .voice-tip {
                margin: var(--space-3) 0 0;
                padding: var(--space-3);
                border-left: 2px solid var(--accent);
                background: var(--surface-sunken);
                border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
            }
        `
    ]
})
export class SettingsPage {
    private readonly store = inject(SettingsStore);
    readonly speech = inject(SpeechService);

    readonly settings = this.store.settings;
    readonly error = this.store.error;
    readonly recentlySaved = this.store.recentlySaved;

    /**
     * Save a change.
     *
     * @param changes The fields to change. Everything else is left alone.
     */
    set(changes: Partial<UserSettings>): void {
        void this.store.update(changes);
    }

    /**
     * Set how loud the narration is.
     *
     * @param event The input event from the volume slider.
     * @returns Nothing.
     */
    chooseVolume(event: Event): void {
        this.speech.setVolume(Number((event.target as HTMLInputElement).value) / 100);
    }

    /**
     * The volume as a whole percentage, for the slider and its readout.
     *
     * The slider works in percent because "70%" means something to a reader and
     * "0.7" does not; the service stores the fraction the browser's speech API
     * actually wants.
     *
     * @returns A number from 0 to 100.
     */
    readonly volumePercent = computed(() => Math.round(this.speech.volume() * 100));

    /**
     * Choose which voice to use.
     *
     * @param event The change event from the select.
     * @returns Nothing.
     */
    chooseVoice(event: Event): void {
        this.speech.setVoice((event.target as HTMLSelectElement).value);
    }

    /**
     * Read the value from a dropdown's change event.
     *
     * @param event The change event.
     * @returns The selected value.
     */
    value(event: Event): never {
        return (event.target as HTMLSelectElement).value as never;
    }

    /**
     * Read the state from a checkbox's change event.
     *
     * @param event The change event.
     * @returns Whether the box is now ticked.
     */
    checked(event: Event): boolean {
        return (event.target as HTMLInputElement).checked;
    }
}
