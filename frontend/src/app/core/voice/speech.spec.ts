/**
 * Tests for the narration volume.
 *
 * These exist because of a real bug. The first version of `readStoredVolume`
 * did `Number(localStorage.getItem(key))` and then checked the result was
 * between 0 and 1 — which looks careful and is wrong, because `Number(null)`
 * is 0 rather than NaN. Nothing stored therefore read as "turned all the way
 * down", and the Dungeon Master was silent for every user who had never
 * touched the slider. Silence is a hard failure to notice: nothing errors, and
 * the feature simply appears not to exist.
 */

import { beforeEach, describe, expect, it } from 'vitest';

import { SpeechService } from './speech';

const KEY = 'dm.volume';

describe('narration volume', () => {
    beforeEach(() => {
        localStorage.removeItem(KEY);
    });

    it('starts at full volume when nothing has been stored', () => {
        // The regression. A new user must be able to hear the narration.
        expect(new SpeechService().volume()).toBe(1);
        expect(new SpeechService().muted()).toBe(false);
    });

    it('remembers a volume that was set', () => {
        localStorage.setItem(KEY, '0.4');
        expect(new SpeechService().volume()).toBe(0.4);
    });

    it('honours a stored zero, which is a real choice rather than an absent one', () => {
        localStorage.setItem(KEY, '0');
        const speech = new SpeechService();
        expect(speech.volume()).toBe(0);
        expect(speech.muted()).toBe(true);
    });

    it('falls back to full volume rather than trusting nonsense', () => {
        for (const rubbish of ['', 'loud', '11', '-1', 'NaN']) {
            localStorage.setItem(KEY, rubbish);
            expect(new SpeechService().volume(), rubbish).toBe(1);
        }
    });

    it('brings an out-of-range value into range instead of rejecting it', () => {
        const speech = new SpeechService();

        speech.setVolume(5);
        expect(speech.volume()).toBe(1);

        speech.setVolume(-3);
        expect(speech.volume()).toBe(0);

        speech.setVolume(Number.NaN);
        expect(speech.volume()).toBe(1);
    });

    it('writes the choice down so it survives a reload', () => {
        new SpeechService().setVolume(0.65);
        expect(localStorage.getItem(KEY)).toBe('0.65');
        expect(new SpeechService().volume()).toBe(0.65);
    });
});
