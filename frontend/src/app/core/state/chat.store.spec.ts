/**
 * Tests for the conversation state.
 *
 * The behaviour that matters most here is what happens when a send fails.
 * Losing what somebody typed because of a network blip is the kind of small
 * cruelty that makes people stop using software, so it is pinned down by a
 * test rather than left to good intentions.
 */

import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { of, throwError } from 'rxjs';

import { ApiClient } from '../api/api.client';
import { ChatStore } from './chat.store';

/** A stand-in for the HTTP layer, so no test touches the network. */
class FakeApiClient {
    post = vi.fn();
    get = vi.fn();
}

describe('ChatStore', () => {
    let store: ChatStore;
    let api: FakeApiClient;

    beforeEach(() => {
        api = new FakeApiClient();
        TestBed.configureTestingModule({
            providers: [ChatStore, { provide: ApiClient, useValue: api }]
        });
        store = TestBed.inject(ChatStore);
    });

    it('starts empty', () => {
        expect(store.isEmpty()).toBe(true);
        expect(store.lines()).toEqual([]);
    });

    it('shows both the player message and the reply after a successful turn', async () => {
        api.post.mockReturnValue(
            of({
                session_id: 'session-1',
                message_id: 'message-1',
                reply: 'The door gives with a groan.',
                turn: 1,
                usage: {
                    tokens_in: 10,
                    tokens_out: 20,
                    model_id: 'gemini-3.5-flash',
                    latency_ms: 900
                },
                scrubbed: false
            })
        );

        const returned = await store.send('I open the door.');

        expect(returned).toBeNull();
        expect(store.lines().map((line) => line.role)).toEqual(['player', 'dungeon_master']);
        expect(store.lines()[1].content).toBe('The door gives with a groan.');
        expect(store.sessionId()).toBe('session-1');
    });

    it('hands the text back when the send fails, rather than losing it', async () => {
        api.post.mockReturnValue(
            throwError(() => ({
                failure: { message: 'Too many requests.', correlationId: 'abc-123' }
            }))
        );

        const returned = await store.send('I open the door.');

        // The text comes back so the interface can restore it to the input box.
        expect(returned).toBe('I open the door.');
        // And the optimistic message is removed, so the conversation does not show
        // a message that was never actually sent.
        expect(store.lines()).toEqual([]);
        expect(store.error()).toBe('Too many requests.');
    });

    it('keeps the correlation identifier so the user can quote it', async () => {
        api.post.mockReturnValue(throwError(() => ({ failure: { message: 'It broke.', correlationId: 'abc-123' } })));

        await store.send('I open the door.');

        expect(store.correlationId()).toBe('abc-123');
    });

    it('ignores an empty message', async () => {
        const returned = await store.send('   ');

        expect(returned).toBeNull();
        expect(api.post).not.toHaveBeenCalled();
    });

    it('reports when the outbound prompt was scrubbed', async () => {
        api.post.mockReturnValue(
            of({
                session_id: 's',
                message_id: 'm',
                reply: 'ok',
                turn: 1,
                usage: { tokens_in: 1, tokens_out: 1, model_id: 'gemini-3.5-flash', latency_ms: 1 },
                scrubbed: true
            })
        );

        await store.send('Write to me at someone@example.com');

        // Surfaced rather than silent: the player is told that something was
        // removed before their words were sent to Google.
        expect(store.lastScrubbed()).toBe(true);
    });

    it('clears the conversation when the campaign changes', async () => {
        api.post.mockReturnValue(
            of({
                session_id: 's',
                message_id: 'm',
                reply: 'ok',
                turn: 1,
                usage: { tokens_in: 1, tokens_out: 1, model_id: 'x', latency_ms: 1 },
                scrubbed: false
            })
        );
        await store.send('hello');
        expect(store.lines().length).toBe(2);

        store.setCampaign('another-campaign');

        expect(store.lines()).toEqual([]);
        expect(store.sessionId()).toBeNull();
    });
});
