/**
 * Records the microphone and sends the audio to our own server to transcribe.
 *
 * ═══════════════════════════════════════════════════════════════════════
 * WHY THIS IS NOT THE BROWSER'S BUILT-IN SPEECH RECOGNITION
 * ═══════════════════════════════════════════════════════════════════════
 * Browsers have a `SpeechRecognition` API that turns speech into text in about
 * five lines of code. It is not used here.
 *
 * In Chrome, that API works by **streaming the raw microphone audio to
 * Google's servers**. That would place a recording of the user's voice — in
 * their home, with whoever else is audible in the room — outside the boundary
 * this whole application exists to maintain. No amount of encrypting the
 * database afterwards makes up for having posted the audio elsewhere first.
 *
 * So this records audio in the browser, uploads it to our backend, and the
 * backend transcribes it locally with a model running on its own processor.
 * The audio reaches one server, ours, and is discarded once transcribed.
 *
 * The honest complication: the resulting *text* is then sent to Google as part
 * of the prompt, because that is the product. Text and audio are not
 * equivalent, though. Text can be scrubbed of names before it is sent,
 * inspected, and reasoned about. A voice recording cannot be scrubbed — it
 * carries the speaker's identity in its waveform whatever the words are.
 *
 * ═══════════════════════════════════════════════════════════════════════
 * THE BROWSER PERMISSION FLOW
 * ═══════════════════════════════════════════════════════════════════════
 * A browser will not let a page use the microphone without the user agreeing.
 * The sequence:
 *
 * 1. The page calls `getUserMedia`.
 * 2. The browser shows its own prompt — a bar near the address bar asking to
 *    use the microphone. We cannot style it, move it, or pre-empt it.
 * 3. The user chooses Allow or Block.
 * 4. If they allow, recording starts. The browser shows a recording indicator
 *    for as long as the microphone is live.
 * 5. If they block, the choice is remembered for that site, and asking again
 *    does nothing at all — the prompt simply does not reappear. This is the
 *    part that confuses people, so `permissionDenied` exists to explain that
 *    the browser's own settings must be changed.
 *
 * A further constraint: browsers only permit microphone access on a secure
 * origin. That means HTTPS in production, with `localhost` specially exempted
 * so local development works.
 */

import { Injectable, computed, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { ApiClient } from '../api/api.client';
import { TranscriptionResponse } from '../api/api.types';

/** What the recorder is currently doing. */
export type RecorderState = 'idle' | 'requesting' | 'recording' | 'transcribing' | 'error';

/** How long a single recording may run before it stops itself, in milliseconds. */
const MAX_RECORDING_MS = 120_000;

@Injectable({ providedIn: 'root' })
export class VoiceRecorder {
  private readonly api = inject(ApiClient);

  private mediaRecorder: MediaRecorder | null = null;
  private stream: MediaStream | null = null;
  private chunks: Blob[] = [];
  private stopTimer: ReturnType<typeof setTimeout> | null = null;

  private readonly _state = signal<RecorderState>('idle');
  private readonly _error = signal<string | null>(null);
  private readonly _permissionDenied = signal(false);
  private readonly _elapsedMs = signal(0);
  private elapsedTimer: ReturnType<typeof setInterval> | null = null;

  /** What the recorder is doing right now. */
  readonly state = this._state.asReadonly();

  /** The current failure message, or `null`. */
  readonly error = this._error.asReadonly();

  /**
   * True once the user has refused microphone access.
   *
   * Worth its own signal because the browser will not ask again — the
   * interface has to explain that the browser's own site settings must be
   * changed, or the button appears simply broken.
   */
  readonly permissionDenied = this._permissionDenied.asReadonly();

  /** How long the current recording has been running, in milliseconds. */
  readonly elapsedMs = this._elapsedMs.asReadonly();

  /** True while the microphone is live. */
  readonly isRecording = computed(() => this._state() === 'recording');

  /** True while the server is turning audio into text. */
  readonly isTranscribing = computed(() => this._state() === 'transcribing');

  /** True when this browser can record at all. */
  readonly isSupported = computed(
    () =>
      typeof navigator !== 'undefined' &&
      typeof navigator.mediaDevices?.getUserMedia === 'function' &&
      typeof MediaRecorder !== 'undefined',
  );

  /**
   * Ask for the microphone and start recording.
   *
   * @returns Nothing. Failures are recorded in `error` and `permissionDenied`
   *   rather than thrown, because every one of them is something the interface
   *   needs to explain rather than something a caller can handle.
   */
  async start(): Promise<void> {
    if (this._state() !== 'idle' && this._state() !== 'error') {
      return;
    }

    if (!this.isSupported()) {
      this._state.set('error');
      this._error.set(
        'This browser cannot record audio. Recent versions of Chrome, Edge, Firefox and ' +
          'Safari all can. You can still type.',
      );
      return;
    }

    this._state.set('requesting');
    this._error.set(null);

    try {
      // This line is what triggers the browser's permission prompt.
      this.stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          // Speech, not music. These three make a noticeable difference to
          // transcription accuracy in an ordinary room.
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
    } catch (error) {
      this.handlePermissionFailure(error);
      return;
    }

    this.chunks = [];
    this.mediaRecorder = new MediaRecorder(this.stream, {
      mimeType: pickSupportedMimeType(),
    });

    this.mediaRecorder.ondataavailable = (event) => {
      if (event.data.size > 0) {
        this.chunks.push(event.data);
      }
    };

    this.mediaRecorder.start();
    this._state.set('recording');
    this._elapsedMs.set(0);

    this.elapsedTimer = setInterval(() => {
      this._elapsedMs.update((value) => value + 100);
    }, 100);

    // A safety stop. Without it, a user who walks away leaves the microphone
    // live indefinitely and then uploads an enormous file the server refuses.
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
        this.api.upload<TranscriptionResponse>('/api/v1/voice/transcribe', formData),
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
   */
  clearError(): void {
    this._error.set(null);
    if (this._state() === 'error') {
      this._state.set('idle');
    }
  }

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
          'the microphone to Allow, and reload the page.',
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
          'be using it, then try again.',
      );
      return;
    }

    this._error.set('Could not start recording. You can still type your message.');
  }

  /**
   * Switch the microphone off.
   *
   * Every track must be stopped explicitly. If they are not, the browser keeps
   * showing its recording indicator and the microphone stays live — which is
   * both alarming to the user and a genuine privacy failure.
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
 * Browsers disagree about recording formats. Chrome and Firefox produce WebM
 * with the Opus codec; Safari produces MP4. Asking for one the browser cannot
 * make throws. The transcription model on the server reads all of these, so
 * the first supported option is fine.
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
