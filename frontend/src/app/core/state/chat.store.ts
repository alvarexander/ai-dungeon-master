/**
 * The conversation with the Dungeon Master, held as signals.
 *
 * WHAT THIS OWNS
 * The list of messages on screen, whether a reply is being waited for, and any
 * error. Components read these signals and re-render themselves; none of them
 * calls the backend directly.
 *
 * THE OPTIMISTIC MESSAGE
 * When the player sends something, their message appears immediately, before
 * the backend has confirmed anything. The alternative — waiting for the round
 * trip — makes the interface feel broken, because a Dungeon Master takes two
 * to six seconds to think and the player would stare at an empty box for all
 * of it. If the request fails, the optimistic message is removed and the text
 * is handed back so nothing they typed is lost.
 */

import { Injectable, computed, inject, signal } from '@angular/core';
import { Subject, defaultIfEmpty, firstValueFrom, takeUntil } from 'rxjs';

import { ApiClient } from '../api/api.client';
import { ChatTurnRequest, ChatTurnResponse, InputMode, TokenUsage, TranscriptMessage } from '../api/api.types';

/** One line in the conversation, as the interface needs it. */
export interface ChatLine {
    id: string;
    role: 'player' | 'dungeon_master' | 'system';
    content: string;
    inputMode: InputMode;
    /** True while the backend has not yet confirmed this message. */
    pending: boolean;
    createdAt: string;
}

@Injectable({ providedIn: 'root' })
export class ChatStore {
    private readonly api = inject(ApiClient);

    private readonly _lines = signal<ChatLine[]>([]);
    private readonly _sessionId = signal<string | null>(null);
    private readonly _campaignId = signal<string | null>(null);
    private readonly _waiting = signal(false);
    private readonly _error = signal<string | null>(null);
    private readonly _correlationId = signal<string | null>(null);
    private readonly _lastUsage = signal<TokenUsage | null>(null);
    private readonly _lastScrubbed = signal(false);

    /**
     * Emits when the player asks to stop waiting for a reply.
     *
     * Piping the request through `takeUntil` on this means unsubscribing, and
     * unsubscribing genuinely aborts the underlying network request rather than
     * merely ignoring its result. The server stops being waited on, and the
     * browser frees the connection.
     */
    private readonly _cancel = new Subject<void>();

    /** Every line currently on screen, oldest first. */
    readonly lines = this._lines.asReadonly();

    /** True while waiting for the Dungeon Master to reply. */
    readonly waiting = this._waiting.asReadonly();

    /** The current failure message, or `null`. */
    readonly error = this._error.asReadonly();

    /** The identifier to quote when reporting the current failure. */
    readonly correlationId = this._correlationId.asReadonly();

    /** What the most recent turn cost, so the AI allowance is visible. */
    readonly lastUsage = this._lastUsage.asReadonly();

    /** True if the last message had personal-looking text removed before sending. */
    readonly lastScrubbed = this._lastScrubbed.asReadonly();

    /** The play session in progress, if any. */
    readonly sessionId = this._sessionId.asReadonly();

    /** True before the first message, so the interface can show a welcome. */
    readonly isEmpty = computed(() => this._lines().length === 0);

    /**
     * Point the conversation at a campaign, clearing anything on screen.
     *
     * @param campaignId Which campaign, or `null` for the most recent.
     */
    setCampaign(campaignId: string | null): void {
        this._campaignId.set(campaignId);
        this._sessionId.set(null);
        this._lines.set([]);
        this._error.set(null);
    }

    /**
     * Load an existing conversation from the backend.
     *
     * @param sessionId Which play session to read.
     * @returns Nothing.
     */
    async loadSession(sessionId: string): Promise<void> {
        try {
            const messages = await firstValueFrom(
                this.api.get<TranscriptMessage[]>(`/api/v1/chat/sessions/${sessionId}/messages`, {
                    limit: 200
                })
            );
            this._sessionId.set(sessionId);
            this._lines.set(
                messages.map((message) => ({
                    id: message.message_id,
                    role: message.role,
                    content: message.content,
                    inputMode: message.input_mode,
                    pending: false,
                    createdAt: message.created_at
                }))
            );
        } catch (error) {
            this.recordFailure(error);
        }
    }

    /**
     * Send one message and wait for the Dungeon Master's reply.
     *
     * @param message What the player typed or said.
     * @param inputMode Whether it was typed or spoken.
     * @returns The text to restore to the input box if the send failed, or
     *   `null` on success. Returning the text rather than silently discarding it
     *   means a network failure never costs the player what they wrote.
     */
    async send(message: string, inputMode: InputMode = 'typed'): Promise<string | null> {
        const trimmed = message.trim();
        if (!trimmed || this._waiting()) {
            return null;
        }

        this._error.set(null);
        this._correlationId.set(null);
        this._waiting.set(true);

        // Show it immediately. The identifier is temporary and is replaced when
        // the backend confirms.
        const optimisticId = `pending-${Date.now()}`;
        this._lines.update((lines) => [
            ...lines,
            {
                id: optimisticId,
                role: 'player',
                content: trimmed,
                inputMode,
                pending: true,
                createdAt: new Date().toISOString()
            }
        ]);

        const request: ChatTurnRequest = {
            message: trimmed,
            session_id: this._sessionId(),
            campaign_id: this._campaignId(),
            input_mode: inputMode
        };

        try {
            const response = await firstValueFrom(
                this.api.post<ChatTurnResponse>('/api/v1/chat/turn', request).pipe(
                    takeUntil(this._cancel),
                    // `takeUntil` completes the stream without emitting when cancelled,
                    // and `firstValueFrom` treats that as an error. This turns it into a
                    // value we can recognise instead.
                    defaultIfEmpty(null)
                )
            );

            if (response === null) {
                // Cancelled. Drop the optimistic message and hand the text back so the
                // player can edit and resend rather than retyping it.
                this._lines.update((lines) => lines.filter((line) => line.id !== optimisticId));
                return trimmed;
            }

            this._sessionId.set(response.session_id);
            this._lastUsage.set(response.usage);
            this._lastScrubbed.set(response.scrubbed);

            this._lines.update((lines) => [
                ...lines.map((line) => (line.id === optimisticId ? { ...line, pending: false } : line)),
                {
                    id: response.message_id,
                    role: 'dungeon_master' as const,
                    content: response.reply,
                    inputMode: 'typed' as const,
                    pending: false,
                    createdAt: new Date().toISOString()
                }
            ]);
            return null;
        } catch (error) {
            // Remove the optimistic message and hand the text back, so nothing the
            // player wrote is lost to a failed request.
            this._lines.update((lines) => lines.filter((line) => line.id !== optimisticId));
            this.recordFailure(error);
            return trimmed;
        } finally {
            this._waiting.set(false);
        }
    }

    /**
     * Stop waiting for the Dungeon Master's reply.
     *
     * Aborts the request in flight. The turn never happened as far as the
     * conversation is concerned — but the AI call may already have been made and
     * paid for, since the server does not know we stopped listening.
     *
     * @returns Nothing.
     */
    cancel(): void {
        if (!this._waiting()) {
            return;
        }
        this._cancel.next();
        this._waiting.set(false);
    }

    /**
     * Clear the current error.
     */
    clearError(): void {
        this._error.set(null);
        this._correlationId.set(null);
    }

    /**
     * Record a failure, keeping the identifier the user will need to quote.
     *
     * @param error Whatever was thrown.
     */
    private recordFailure(error: unknown): void {
        const failure = (error as { failure?: { message?: string; correlationId?: string } })?.failure;
        this._error.set(failure?.message ?? 'Something went wrong. Please try again.');
        this._correlationId.set(failure?.correlationId ?? null);
    }
}
