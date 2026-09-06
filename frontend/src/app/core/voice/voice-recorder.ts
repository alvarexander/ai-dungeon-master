/**
 * Records the microphone, shows what it is hearing, and sends it to our server.
 *
 * ═══════════════════════════════════════════════════════════════════════
 * WHY THIS IS NOT THE BROWSER'S BUILT-IN SPEECH RECOGNITION
 * ═══════════════════════════════════════════════════════════════════════
 * Browsers have a `SpeechRecognition` API that would replace most of this file
 * with five lines. In Chrome it works by **streaming the raw microphone audio
 * to Google's servers**.
 *
 * That would send a recording of the user's voice — in their home, with
 * whoever else is audible in the room — to a third party. So instead the audio
 * is recorded here, uploaded to our own backend, transcribed by a model
 * running on that machine, and discarded.
 *
 * The transcribed *text* does go to Google as part of the prompt, because that
 * is the product. Text and audio are not equivalent: text can be reviewed and
 * scrubbed before it is sent, while a recording carries the speaker's identity
 * in its waveform whatever the words are.
 *
 * ═══════════════════════════════════════════════════════════════════════
 * THE LIVE WAVEFORM
 * ═══════════════════════════════════════════════════════════════════════
 * While recording, an `AnalyserNode` from the Web Audio API reports the
 * frequency content of the microphone many times a second. That drives the
 * bars in `<app-waveform>`.
 *
 * This is not decoration. A recording indicator that does not move gives no
 * clue whether the microphone is actually picking anything up — people end up
 * speaking into a muted device and only discovering it when nothing arrives.
 * Bars that move with your voice answer that instantly.
 *
 * ═══════════════════════════════════════════════════════════════════════
 * SILENCE DETECTION, FOR HANDS-FREE MODE
 * ═══════════════════════════════════════════════════════════════════════
 * The same analyser measures loudness. When the level stays below a threshold
 * for about a second and a half **after speech has been detected**, the
 * recording stops itself.
 *
 * That "after speech" condition matters: without it, recording would end
 * immediately every time, because there is always a moment of quiet before
 * somebody starts talking.
 *
 * ═══════════════════════════════════════════════════════════════════════
 * THE BROWSER PERMISSION FLOW
 * ═══════════════════════════════════════════════════════════════════════
 * 1. The page calls `getUserMedia`.
 * 2. **The browser** shows its own prompt. We cannot style it or pre-empt it.
 * 3. The user chooses Allow or Block.
 * 4. On Allow, recording starts and the browser shows a recording indicator.
 * 5. **On Block, the choice is remembered and asking again does nothing.** The
 *    prompt simply does not reappear — which is why `permissionDenied` is a
 *    separate signal, so the interface can explain that the browser's own
 *    settings must be changed. Without that explanation the button just looks
 *    broken.
 *
 * Browsers also only allow microphone access on a secure origin: HTTPS in
 * production, with `localhost` specially exempted for development.
 */

import { Injectable, computed, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { ApiClient } from '../api/api.client';
import { TranscriptionResponse } from '../api/api.types';

/** What the recorder is currently doing. */
export type RecorderState = 'idle' | 'requesting' | 'recording' | 'transcribing' | 'error';

/** How long a single recording may run before it stops itself. */
const MAX_RECORDING_MS = 120_000;

/** How many bars the waveform shows. */
const BAR_COUNT = 28;

/**
 * Below this average level, the microphone is considered quiet.
 *
 * Measured on the 0–255 scale the analyser reports. Chosen by trying it in a
 * normal room: low enough that background hum does not read as speech, high
 * enough that a quiet voice does.
 */
const SILENCE_THRESHOLD = 12;

/** How long the level must stay low before a hands-free recording stops. */
const SILENCE_DURATION_MS = 1500;

/** Ignore silence for this long at the start, so it does not stop instantly. */
const MIN_SPEECH_MS = 600;

@Injectable({ providedIn: 'root' })
export class VoiceRecorder {
    private readonly api = inject(ApiClient);

    private mediaRecorder: MediaRecorder | null = null;
    private stream: MediaStream | null = null;
    private chunks: Blob[] = [];
    private stopTimer: ReturnType<typeof setTimeout> | null = null;
    private elapsedTimer: ReturnType<typeof setInterval> | null = null;

    // Web Audio pieces, used only for the waveform and silence detection.
    private audioContext: AudioContext | null = null;
    private analyser: AnalyserNode | null = null;
    private frameHandle: number | null = null;
    private startedAt = 0;
    private quietSince: number | null = null;
    private heardSpeech = false;

    /** Called when a hands-free recording stops itself after silence. */
    private onSilence: (() => void) | null = null;

    private readonly _state = signal<RecorderState>('idle');
    private readonly _error = signal<string | null>(null);
    private readonly _permissionDenied = signal(false);
    private readonly _elapsedMs = signal(0);
    private readonly _levels = signal<number[]>(new Array(BAR_COUNT).fill(0));

    /** What the recorder is doing right now. */
    readonly state = this._state.asReadonly();

    /** The current failure message, or `null`. */
    readonly error = this._error.asReadonly();

    /**
     * True once the user has refused microphone access.
     *
     * Worth its own signal because the browser will not ask again — the
     * interface has to explain that its site settings must be changed.
     */
    readonly permissionDenied = this._permissionDenied.asReadonly();

    /** How long the current recording has been running, in milliseconds. */
    readonly elapsedMs = this._elapsedMs.asReadonly();

    /**
     * Bar heights for the waveform, each 0 to 1.
     *
     * Updated on every animation frame while recording, and reset to zero
     * otherwise.
     */
    readonly levels = this._levels.asReadonly();

    /** True while the microphone is live. */
    readonly isRecording = computed(() => this._state() === 'recording');

    /** True while the server is turning audio into text. */
    readonly isTranscribing = computed(() => this._state() === 'transcribing');

    /** True while the browser is asking for permission. */
    readonly isRequesting = computed(() => this._state() === 'requesting');

    /** True when this browser can record at all. */
    readonly isSupported = computed(
        () =>
            typeof navigator !== 'undefined' &&
            typeof navigator.mediaDevices?.getUserMedia === 'function' &&
            typeof MediaRecorder !== 'undefined'
    );

    /**
     * Ask for the microphone and start recording.
     *
     * @param options.onSilence Called when the recording stops itself because the
     *   speaker went quiet. Used by hands-free mode; omit it and the recording
     *   runs until stopped by hand.
     * @returns Nothing. Failures are recorded in `error` and `permissionDenied`
     *   rather than thrown, because every one of them is something the interface
     *   needs to explain rather than something a caller can handle.
     */
    async start(options: { onSilence?: () => void } = {}): Promise<void> {
        if (this._state() !== 'idle' && this._state() !== 'error') {
            return;
        }

        if (!this.isSupported()) {
            this._state.set('error');
            this._error.set(
                'This browser cannot record audio. Recent versions of Chrome, Edge, Firefox and ' +
                    'Safari all can. You can still type.'
            );
            return;
        }

        this.onSilence = options.onSilence ?? null;
        this._state.set('requesting');
        this._error.set(null);

        try {
            // This line is what triggers the browser's permission prompt.
            this.stream = await navigator.mediaDevices.getUserMedia({
                audio: {
                    // Tuned for speech in an ordinary room. These three make a
                    // noticeable difference to transcription accuracy.
                    echoCancellation: true,
                    noiseSuppression: true,
                    autoGainControl: true
                }
            });
        } catch (error) {
            this.handlePermissionFailure(error);
            return;
        }

        this.chunks = [];
        this.mediaRecorder = new MediaRecorder(this.stream, { mimeType: pickSupportedMimeType() });
        this.mediaRecorder.ondataavailable = (event) => {
            if (event.data.size > 0) {
                this.chunks.push(event.data);
            }
        };
        this.mediaRecorder.start();

        this._state.set('recording');
        this._elapsedMs.set(0);
        this.startedAt = Date.now();
        this.quietSince = null;
        this.heardSpeech = false;

        this.startAnalyser();

        this.elapsedTimer = setInterval(() => {
            this._elapsedMs.update((value) => value + 100);
        }, 100);

        // A safety stop. Without it, somebody who walks away leaves the microphone
        // live indefinitely and then uploads a file the server refuses.
        this.stopTimer = setTimeout(() => {
            if (this._state() === 'recording') {
                void this.stopAndTranscribe();
            }
        }, MAX_RECORDING_MS);
    }

    /**
     * Stop recording, upload the audio, and return the text.
     *
     * @returns The transcript, or `null` if anything failed.
     */
    async stopAndTranscribe(): Promise<string | null> {
        const recorder = this.mediaRecorder;
        if (!recorder || this._state() !== 'recording') {
            return null;
        }

        this.clearTimers();
        this.stopAnalyser();

        // `MediaRecorder` finishes asynchronously, so wait for its stop event
        // before assembling the audio — otherwise the last chunk is missing.
        const audio = await new Promise<Blob>((resolve) => {
            recorder.onstop = () => resolve(new Blob(this.chunks, { type: recorder.mimeType }));
            recorder.stop();
        });

        this.releaseMicrophone();
        this._state.set('transcribing');

        try {
            const formData = new FormData();
            formData.append('audio', audio, 'recording.webm');

            const response = await firstValueFrom(
                this.api.upload<TranscriptionResponse>('/api/v1/voice/transcribe', formData)
            );

            this._state.set('idle');
            return response.transcript;
        } catch (error) {
            this._state.set('error');
            this._error.set(messageFrom(error));
            return null;
        }
    }

    /**
     * Abandon the current recording without transcribing it.
     *
     * @returns Nothing.
     */
    cancel(): void {
        this.clearTimers();
        this.stopAnalyser();
        if (this.mediaRecorder && this._state() === 'recording') {
            this.mediaRecorder.onstop = null;
            this.mediaRecorder.stop();
        }
        this.chunks = [];
        this.releaseMicrophone();
        this._state.set('idle');
        this._elapsedMs.set(0);
    }

    /**
     * Clear the current error.
     *
     * @returns Nothing.
     */
    clearError(): void {
        this._error.set(null);
        if (this._state() === 'error') {
            this._state.set('idle');
        }
    }

    // -------------------------------------------------------------------
    // The live waveform and silence detection
    // -------------------------------------------------------------------

    /**
     * Begin analysing the microphone for the waveform and silence detection.
     *
     * Failure here is deliberately not fatal. If the Web Audio API is
     * unavailable the recording still works perfectly — the bars simply stay
     * flat. Losing a visual flourish should never cost somebody their recording.
     */
    private startAnalyser(): void {
        if (!this.stream) {
            return;
        }
        try {
            this.audioContext = new AudioContext();
            const source = this.audioContext.createMediaStreamSource(this.stream);
            this.analyser = this.audioContext.createAnalyser();
            // 256 samples gives 128 frequency bins — plenty for 28 bars, and cheap
            // enough to run every frame without warming the laptop.
            this.analyser.fftSize = 256;
            this.analyser.smoothingTimeConstant = 0.7;
            source.connect(this.analyser);
            this.tick();
        } catch {
            this.analyser = null;
        }
    }

    /**
     * Read the microphone once per animation frame and update the bars.
     *
     * Uses `requestAnimationFrame` rather than a timer so it runs in step with
     * the display and pauses automatically when the tab is in the background.
     */
    private tick = (): void => {
        const analyser = this.analyser;
        if (!analyser || this._state() !== 'recording') {
            return;
        }

        const spectrum = new Uint8Array(analyser.frequencyBinCount);
        analyser.getByteFrequencyData(spectrum);

        // Fold the bins down into the number of bars actually drawn, taking the
        // average of each group so a bar reflects its whole slice of the spectrum.
        const perBar = Math.floor(spectrum.length / BAR_COUNT) || 1;
        const bars: number[] = [];
        let total = 0;
        for (let i = 0; i < BAR_COUNT; i++) {
            let sum = 0;
            for (let j = 0; j < perBar; j++) {
                sum += spectrum[i * perBar + j] ?? 0;
            }
            const average = sum / perBar;
            total += average;
            // A floor of 0.06 keeps a visible resting line rather than the bars
            // disappearing completely between words.
            bars.push(Math.max(0.06, Math.min(1, average / 180)));
        }
        this._levels.set(bars);

        this.checkForSilence(total / BAR_COUNT);
        this.frameHandle = requestAnimationFrame(this.tick);
    };

    /**
     * Stop a hands-free recording once the speaker has gone quiet.
     *
     * @param level The current average loudness, on the analyser's 0–255 scale.
     */
    private checkForSilence(level: number): void {
        if (!this.onSilence) {
            return;
        }

        const elapsed = Date.now() - this.startedAt;
        if (level > SILENCE_THRESHOLD) {
            this.heardSpeech = true;
            this.quietSince = null;
            return;
        }

        // Do not stop before the speaker has actually said something. Without this
        // the recording would end during the pause before they begin.
        if (!this.heardSpeech || elapsed < MIN_SPEECH_MS) {
            return;
        }

        this.quietSince ??= Date.now();
        if (Date.now() - this.quietSince >= SILENCE_DURATION_MS) {
            const finish = this.onSilence;
            this.onSilence = null;
            finish?.();
        }
    }

    /** Stop the analysis loop and release the audio context. */
    private stopAnalyser(): void {
        if (this.frameHandle !== null) {
            cancelAnimationFrame(this.frameHandle);
            this.frameHandle = null;
        }
        this.analyser = null;
        void this.audioContext?.close().catch(() => undefined);
        this.audioContext = null;
        this._levels.set(new Array(BAR_COUNT).fill(0));
    }

    // -------------------------------------------------------------------
    // Failure handling and cleanup
    // -------------------------------------------------------------------

    /**
     * Turn a `getUserMedia` failure into something the user can act on.
     *
     * @param error Whatever the browser threw.
     */
    private handlePermissionFailure(error: unknown): void {
        this._state.set('error');
        const name = (error as { name?: string })?.name ?? '';

        if (name === 'NotAllowedError' || name === 'SecurityError') {
            this._permissionDenied.set(true);
            this._error.set(
                'Microphone access was blocked. The browser will not ask again, so this has to be ' +
                    'changed in its own settings: click the icon at the left of the address bar, set ' +
                    'the microphone to Allow, and reload the page.'
            );
            return;
        }

        if (name === 'NotFoundError' || name === 'DevicesNotFoundError') {
            this._error.set('No microphone was found. Check that one is connected.');
            return;
        }

        if (name === 'NotReadableError') {
            this._error.set(
                'The microphone is in use by another application. Close anything else that might ' +
                    'be using it, then try again.'
            );
            return;
        }

        this._error.set('Could not start recording. You can still type your message.');
    }

    /**
     * Switch the microphone off.
     *
     * Every track must be stopped explicitly. If they are not, the browser keeps
     * showing its recording indicator and **the microphone stays live** — both
     * alarming to the user and a genuine privacy failure, caused by forgetting
     * one line.
     */
    private releaseMicrophone(): void {
        this.stream?.getTracks().forEach((track) => track.stop());
        this.stream = null;
        this.mediaRecorder = null;
    }

    /** Cancel the running timers. */
    private clearTimers(): void {
        if (this.stopTimer) {
            clearTimeout(this.stopTimer);
            this.stopTimer = null;
        }
        if (this.elapsedTimer) {
            clearInterval(this.elapsedTimer);
            this.elapsedTimer = null;
        }
    }
}

/**
 * Choose an audio format this browser can actually produce.
 *
 * Browsers disagree: Chrome and Firefox produce WebM with Opus, Safari
 * produces MP4. Asking for one the browser cannot make throws. The
 * transcription model on the server reads all of them, so the first supported
 * option is fine.
 *
 * @returns A supported MIME type, or an empty string to let the browser pick.
 */
function pickSupportedMimeType(): string {
    const candidates = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg;codecs=opus'];
    return candidates.find((type) => MediaRecorder.isTypeSupported(type)) ?? '';
}

/**
 * Extract a displayable message from a thrown error.
 *
 * @param error Whatever was thrown.
 * @returns A message safe to show the user.
 */
function messageFrom(error: unknown): string {
    const failure = (error as { failure?: { message?: string } })?.failure;
    return failure?.message ?? 'Could not transcribe that recording. You can type instead.';
}
