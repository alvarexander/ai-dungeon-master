/**
 * The play screen: the conversation with the Dungeon Master.
 *
 * THREE WAYS TO PLAY, AND WHY THERE ARE THREE
 *
 * **Typing.** Always available. Everything else degrades to this, and every
 * voice failure says so.
 *
 * **Push to talk.** Press the microphone, speak, press again. The waveform
 * shows what is being heard, so a muted device is obvious immediately rather
 * than after you have said your piece.
 *
 * **Conversational mode.** Hands-free. It listens, notices when you stop
 * talking, sends what you said, reads the reply aloud, and starts listening
 * again. This is the mode that makes it feel like a person running the game
 * rather than a text box — which is the point of the product.
 *
 * WHY THE LOOP HAS TO WAIT FOR THE SPEAKING TO FINISH
 *
 * In conversational mode the microphone must not reopen until the Dungeon
 * Master has stopped talking. Otherwise it hears the narration through the
 * speakers, transcribes it, and sends it back as though the player had said
 * it — the game starts talking to itself. That is why `speak` takes an `onEnd`
 * callback and the loop is driven from it rather than from a timer.
 */

import {
    ChangeDetectionStrategy,
    Component,
    ElementRef,
    computed,
    effect,
    inject,
    signal,
    viewChild
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';

import { ChatStore } from '../../core/state/chat.store';
import { SettingsStore } from '../../core/state/settings.store';
import { SpeechService } from '../../core/voice/speech';
import { VoiceRecorder } from '../../core/voice/voice-recorder';
import { DiceRoller } from '../dice/dice-roller';
import { Banner } from '../../shared/ui/banner';
import { Icon } from '../../shared/ui/icon';
import { Waveform } from '../../shared/ui/waveform';

@Component({
    selector: 'app-chat-page',
    changeDetection: ChangeDetectionStrategy.OnPush,
    imports: [FormsModule, RouterLink, Banner, Icon, Waveform, DiceRoller],
    templateUrl: './chat-page.html',
    styleUrl: './chat-page.scss'
})
export class ChatPage {
    private readonly chat = inject(ChatStore);
    private readonly settings = inject(SettingsStore);
    readonly voice = inject(VoiceRecorder);
    readonly speech = inject(SpeechService);

    /** The conversation on screen. */
    readonly lines = this.chat.lines;

    /** True while waiting for the Dungeon Master. */
    readonly waiting = this.chat.waiting;

    /** The current failure, or `null`. */
    readonly error = this.chat.error;

    /** The identifier to quote when reporting the current failure. */
    readonly correlationId = this.chat.correlationId;

    /** What the last turn cost. */
    readonly usage = this.chat.lastUsage;

    /** True if the last message had personal-looking text removed before sending. */
    readonly scrubbed = this.chat.lastScrubbed;

    /** True before the first message. */
    readonly isEmpty = this.chat.isEmpty;

    /** What the player is currently typing. */
    readonly draft = signal('');

    /** True when hands-free conversation is running. */
    readonly conversational = signal(false);

    /** Which message is being read aloud, if any. */
    readonly speakingId = signal<string | null>(null);

    /** True when the send button should be usable. */
    readonly canSend = computed(() => this.draft().trim().length > 0 && !this.waiting());

    /** True when voice input is available and switched on. */
    readonly voiceAvailable = computed(() => this.settings.settings().voice_input_enabled && this.voice.isSupported());

    /** True when the Dungeon Master can read its narration aloud. */
    readonly speechAvailable = computed(
        () => this.settings.settings().voice_output_enabled && this.speech.isSupported()
    );

    /** True when hands-free mode can be offered at all. */
    readonly conversationalAvailable = computed(() => this.voiceAvailable() && this.speechAvailable());

    /** How long the current recording has run, as a readable time. */
    readonly recordingTime = computed(() => {
        const seconds = Math.floor(this.voice.elapsedMs() / 1000);
        return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
    });

    /**
     * What the interface is doing, as one value.
     *
     * Collapsing four booleans into one state removes a class of bug where two
     * of them are true at once and the screen shows two contradictory things.
     */
    readonly phase = computed<'idle' | 'listening' | 'transcribing' | 'thinking' | 'speaking'>(() => {
        if (this.voice.isRecording() || this.voice.isRequesting()) return 'listening';
        if (this.voice.isTranscribing()) return 'transcribing';
        if (this.waiting()) return 'thinking';
        if (this.speech.speaking()) return 'speaking';
        return 'idle';
    });

    private readonly transcriptEnd = viewChild<ElementRef<HTMLDivElement>>('transcriptEnd');

    constructor() {
        // Keep the newest message in view. Without this a reply arrives below the
        // fold and the player thinks nothing happened.
        effect(() => {
            this.lines();
            this.phase();
            queueMicrotask(() => {
                this.transcriptEnd()?.nativeElement.scrollIntoView({
                    behavior: this.settings.settings().reduce_motion ? 'auto' : 'smooth',
                    block: 'end'
                });
            });
        });
    }

    /**
     * Send whatever is in the input box.
     *
     * @param inputMode Whether this came from typing or from speech.
     * @returns Nothing.
     */
    async send(inputMode: 'typed' | 'voice' = 'typed'): Promise<void> {
        const message = this.draft();
        if (!message.trim() || this.waiting()) {
            return;
        }
        this.draft.set('');
        // Stop any narration still playing. Being talked over by the previous
        // paragraph while sending the next message is disorienting.
        this.speech.stop();

        const returned = await this.chat.send(message, inputMode);
        if (returned !== null) {
            // The send failed, so the text comes back rather than being lost.
            this.draft.set(returned);
            this.conversational.set(false);
            return;
        }

        const reply = this.lines().at(-1);
        if (reply?.role === 'dungeon_master' && this.speechAvailable()) {
            this.readAloud(reply.id, reply.content, this.conversational());
        }
    }

    /**
     * Grow the message box as the text wraps, and shrink it again.
     *
     * A single-line pill that silently scrolls hides what somebody has written,
     * and a permanently three-line box wastes the screen when almost every
     * message is one line. Growing to fit is what messaging applications do,
     * and it is the only reason this needs JavaScript at all — CSS still has no
     * way to size a `textarea` to its content.
     *
     * Reset to `auto` first, or the box can only ever get taller: `scrollHeight`
     * of an element already tall enough is just its current height.
     *
     * @param event The input event from the message box.
     * @returns Nothing.
     */
    autoGrow(event: Event): void {
        const box = event.target as HTMLTextAreaElement;
        box.style.height = 'auto';
        box.style.height = `${box.scrollHeight}px`;
        // Past one line the pill's ends should square off into a rounded
        // rectangle. A class is cheaper than measuring in the stylesheet.
        box.classList.toggle('is-tall', box.scrollHeight > 34);
    }

    /**
     * Handle a key press in the message box.
     *
     * Enter sends; Shift+Enter starts a new line — the convention every chat
     * application uses, and one people try without being told.
     *
     * @param event The keyboard event.
     * @returns Nothing.
     */
    onKeydown(event: KeyboardEvent): void {
        if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            void this.send('typed');
        }
    }

    /**
     * Start or stop push-to-talk recording.
     *
     * @returns Nothing.
     */
    async toggleRecording(): Promise<void> {
        if (this.voice.isRecording()) {
            const transcript = await this.voice.stopAndTranscribe();
            if (transcript) {
                // Appended rather than replacing, so a player can dictate and then
                // correct or add to it by typing before sending.
                this.draft.update((current) => (current ? `${current} ${transcript}` : transcript));
                if (this.settings.settings().voice_autosend) {
                    await this.send('voice');
                }
            }
            return;
        }

        this.speech.stop();
        await this.voice.start();
    }

    /**
     * Turn hands-free conversation on or off.
     *
     * @returns Nothing.
     */
    /**
     * Turn the Dungeon Master's narration on or off from the play screen.
     *
     * The same setting as the one in Settings, deliberately — this is a
     * shortcut to it, not a second switch that could disagree with it. Somebody
     * who wants to read rather than listen usually decides that mid-scene, and
     * making them leave the game to act on it is the kind of friction that ends
     * with the sound left on and the tab closed.
     *
     * Silencing it also ends hands-free play, which has nothing to wait for
     * once the narration has stopped.
     *
     * @returns Nothing.
     */
    toggleNarration(): void {
        const wanted = !this.speechAvailable();

        if (!wanted) {
            this.speech.stop();
            this.speakingId.set(null);
            this.conversational.set(false);
        }

        void this.settings.update({ voice_output_enabled: wanted });
    }

    async toggleConversational(): Promise<void> {
        if (this.conversational()) {
            this.conversational.set(false);
            this.voice.cancel();
            this.speech.stop();
            return;
        }

        this.conversational.set(true);
        await this.listenHandsFree();
    }

    /**
     * Listen until the player stops speaking, then send what they said.
     *
     * The loop continues in `send`, which reads the reply aloud and calls back
     * here when it has finished — see the note at the top of this file about why
     * it must wait rather than reopening the microphone on a timer.
     *
     * @returns Nothing.
     */
    private async listenHandsFree(): Promise<void> {
        if (!this.conversational()) {
            return;
        }

        await this.voice.start({
            onSilence: () => {
                void (async () => {
                    const transcript = await this.voice.stopAndTranscribe();
                    if (!this.conversational()) {
                        return;
                    }
                    if (!transcript?.trim()) {
                        // Heard nothing usable — a cough, a door. Listen again rather than
                        // sending an empty turn and wasting an AI call.
                        await this.listenHandsFree();
                        return;
                    }
                    this.draft.set(transcript);
                    await this.send('voice');
                })();
            }
        });

        // Starting failed — most often permission was refused. Leave hands-free
        // mode rather than sitting in a state that cannot progress.
        if (this.voice.state() === 'error') {
            this.conversational.set(false);
        }
    }

    /**
     * Read one message aloud.
     *
     * @param id Which message, so the interface can show which is speaking.
     * @param text The narration.
     * @param thenListen Whether to start listening again afterwards.
     * @returns Nothing.
     */
    readAloud(id: string, text: string, thenListen = false): void {
        this.speakingId.set(id);
        this.speech.speak(text, {
            onEnd: () => {
                this.speakingId.set(null);
                if (thenListen && this.conversational()) {
                    void this.listenHandsFree();
                }
            }
        });
    }

    /**
     * Stop reading aloud.
     *
     * @returns Nothing.
     */
    stopSpeaking(): void {
        this.speech.stop();
        this.speakingId.set(null);
    }

    /**
     * Stop whatever is happening: waiting for a reply, or reading aloud.
     *
     * One button rather than two, because from the player's point of view there
     * is one thing to interrupt. Which of the two is running is the interface's
     * problem, not theirs.
     *
     * Also leaves hands-free mode, since the point of pressing stop is to take
     * back control — having the microphone reopen a second later would be the
     * opposite of that. The text of the cancelled message is returned to the
     * input box by `ChatStore.send`, so nothing typed is lost.
     *
     * @returns Nothing.
     */
    stopEverything(): void {
        this.conversational.set(false);
        this.speech.stop();
        this.speakingId.set(null);
        this.chat.cancel();
    }

    /**
     * Abandon the current recording without sending it.
     *
     * @returns Nothing.
     */
    cancelRecording(): void {
        this.voice.cancel();
        this.conversational.set(false);
    }

    /**
     * Dismiss the current error message.
     *
     * @returns Nothing.
     */
    dismissError(): void {
        this.chat.clearError();
        this.voice.clearError();
    }

    /**
     * Send a dice result to the Dungeon Master.
     *
     * Sent immediately rather than dropped into the input box. The player has
     * already decided to roll and pressed a button that says "tell the Dungeon
     * Master"; asking them to press Send as well would be a step for no reason.
     *
     * @param description The roll, written as a sentence.
     * @returns Nothing.
     */
    async sendRoll(description: string): Promise<void> {
        this.draft.set(description);
        await this.send('typed');
    }

    /**
     * Fill the input box with a suggestion from the empty state.
     *
     * @param text The suggested opening line.
     * @returns Nothing.
     */
    useSuggestion(text: string): void {
        this.draft.set(text);
    }
}
