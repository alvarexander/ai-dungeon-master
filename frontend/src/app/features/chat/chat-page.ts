/**
 * The play screen: where the conversation with the Dungeon Master happens.
 *
 * This is the one part of Phase 1 that is fully real. A message goes to the
 * backend, the backend asks Google Gemini, and the narration comes back.
 *
 * WHAT THIS SCREEN IS RESPONSIBLE FOR
 * Displaying the conversation, taking input by typing or by voice, and
 * reporting failures in a way the player can act on. It holds no state of its
 * own — the conversation lives in `ChatStore`, so navigating away and back
 * does not lose it.
 */

import { ChangeDetectionStrategy, Component, ElementRef, computed, effect, inject, signal, viewChild } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';

import { ChatStore } from '../../core/state/chat.store';
import { SettingsStore } from '../../core/state/settings.store';
import { VoiceRecorder } from '../../core/voice/voice-recorder';
import { Banner } from '../../shared/ui/banner';

@Component({
  selector: 'app-chat-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, RouterLink, Banner],
  templateUrl: './chat-page.html',
  styleUrl: './chat-page.scss',
})
export class ChatPage {
  private readonly chat = inject(ChatStore);
  private readonly settings = inject(SettingsStore);
  readonly voice = inject(VoiceRecorder);

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

  /** True when the send button should be usable. */
  readonly canSend = computed(() => this.draft().trim().length > 0 && !this.waiting());

  /** True when voice input is available and switched on. */
  readonly voiceAvailable = computed(
    () => this.settings.settings().voice_input_enabled && this.voice.isSupported(),
  );

  /** How long the current recording has run, as a readable time. */
  readonly recordingTime = computed(() => {
    const seconds = Math.floor(this.voice.elapsedMs() / 1000);
    return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
  });

  private readonly transcriptEnd = viewChild<ElementRef<HTMLDivElement>>('transcriptEnd');

  constructor() {
    // Keep the newest message in view. Without this, a reply arrives below the
    // fold and the player thinks nothing happened.
    effect(() => {
      this.lines();
      this.waiting();
      queueMicrotask(() => {
        this.transcriptEnd()?.nativeElement.scrollIntoView({
          behavior: this.settings.settings().reduce_motion ? 'auto' : 'smooth',
          block: 'end',
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

    const returned = await this.chat.send(message, inputMode);
    if (returned !== null) {
      // The send failed, so the text comes back rather than being lost. Losing
      // what somebody wrote because of a network blip is unforgivable.
      this.draft.set(returned);
    }
  }

  /**
   * Handle a key press in the message box.
   *
   * Enter sends; Shift+Enter starts a new line. This is the convention every
   * chat application uses, and people will try it without being told.
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
   * Start or stop recording, depending on what is happening now.
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
    } else {
      await this.voice.start();
    }
  }

  /**
   * Abandon the current recording without transcribing it.
   *
   * @returns Nothing.
   */
  cancelRecording(): void {
    this.voice.cancel();
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
   * Fill the input box with a suggestion from the empty state.
   *
   * @param text The suggested opening line.
   * @returns Nothing.
   */
  useSuggestion(text: string): void {
    this.draft.set(text);
  }
}
