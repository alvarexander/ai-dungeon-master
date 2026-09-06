/**
 * Reads the Dungeon Master's narration aloud.
 *
 * WHY THE BROWSER RATHER THAN A SERVICE
 *
 * Every browser has a built-in speech synthesiser — the same one that powers
 * screen readers. Using it means:
 *
 * - **No cost.** No API, no per-character billing, nothing to meter.
 * - **Nothing leaves the machine.** The text is spoken locally. It has already
 *   been to Google to be generated, but reading it aloud adds no new
 *   disclosure.
 * - **No latency.** It starts speaking immediately rather than waiting for an
 *   audio file to be generated and downloaded.
 *
 * The trade is voice quality, which varies by operating system. macOS and iOS
 * have genuinely good voices; Windows is decent; Linux varies. A paid service
 * would sound better, and would cost money and send the text somewhere else.
 *
 * THE SYMMETRY WORTH NOTICING
 *
 * Speech *in* is transcribed on our own server, because a recording of
 * somebody's voice is sensitive. Speech *out* happens in the browser, because
 * it is only the Dungeon Master's own words. The sensitive direction gets the
 * careful treatment; the harmless one gets the free option.
 *
 * TWO BROWSER QUIRKS THIS FILE WORKS AROUND
 *
 * 1. **The voice list loads asynchronously.** Asking for voices immediately
 *    after page load returns an empty array in Chrome. `voiceschanged` fires
 *    later, which is why `ready` exists.
 * 2. **Chrome stops speaking after about fifteen seconds.** A long passage is
 *    silently cut off mid-sentence. The fix is to split the text into
 *    sentences and queue them separately, which is what `speak` does — and it
 *    reads better anyway, because the synthesiser handles sentence-length
 *    input more naturally.
 */

import { Injectable, computed, signal } from '@angular/core';

/**
 * Voices that sound obviously synthetic, and should never be chosen for us.
 *
 * macOS ships a set of novelty voices from the 1980s — Zarvox, Trinoids,
 * Bubbles and friends. They are still in the list every browser reports, and
 * some of them sort early alphabetically, so without this the automatic choice
 * can land on something that sounds like a broken robot reading a fantasy
 * novel. `Albert`, `Fred` and `Ralph` are the old default voices and are
 * noticeably worse than anything modern.
 */
const NOVELTY_VOICES = new Set([
    'Albert',
    'Bad News',
    'Bahh',
    'Bells',
    'Boing',
    'Bubbles',
    'Cellos',
    'Deranged',
    'Fred',
    'Good News',
    'Jester',
    'Junior',
    'Kathy',
    'Organ',
    'Princess',
    'Ralph',
    'Superstar',
    'Trinoids',
    'Whisper',
    'Wobble',
    'Zarvox',
    'Grandma',
    'Grandpa',
    'Eddy',
    'Flo',
    'Reed',
    'Rocko',
    'Sandy',
    'Shelley',
    'Bruce',
    'Agnes',
    'Vicki',
    'Victoria',
    'Alex'
]);

/**
 * Score a voice on how natural it is likely to sound.
 *
 * WHY THIS IS SCORED RATHER THAN A FIXED LIST
 *
 * A fixed list of preferred names fails on any machine that does not have
 * them, and every operating system ships a different set — this browser
 * reports 180 voices, another will report six. Scoring works everywhere: it
 * expresses what makes a voice good and lets each machine's best option win.
 *
 * The signals, in order of how much they matter:
 *
 * - **"Premium" and "Enhanced"** are Apple's labels for the large downloaded
 *   voices. They are dramatically better than the compact defaults, and are
 *   the single biggest improvement available.
 * - **"Natural" and "Neural"** are the equivalent labels from Microsoft.
 * - **Not a local service** means the browser synthesises it server-side —
 *   Chrome's "Google UK English" voices, which are noticeably smoother than
 *   the built-in compact ones.
 * - **English** because the Dungeon Master writes in English, and a voice for
 *   another language mispronounces almost everything.
 *
 * @param voice The voice to score.
 * @returns A number; higher is better. Novelty voices score below zero so they
 *   are never chosen automatically, though a user may still pick one.
 */
function scoreVoice(voice: SpeechSynthesisVoice): number {
    const name = voice.name;
    // Everything before the first bracket. Voices arrive with all sorts of
    // suffixes — "Eddy (English (United Kingdom))", "Ava (Premium)",
    // "Daniel (Enhanced)" — and the part that identifies the voice is the bit in
    // front. Matching on the whole string misses the novelty voices entirely,
    // which is how "Grandma" ends up narrating a dungeon.
    const base = name.split('(')[0].trim();

    if (NOVELTY_VOICES.has(base)) {
        return -100;
    }

    let score = 0;
    if (/premium/i.test(name)) score += 100;
    else if (/enhanced/i.test(name)) score += 80;
    else if (/natural|neural/i.test(name)) score += 80;
    if (/siri/i.test(name)) score += 60;
    if (!voice.localService) score += 40;
    if (voice.lang.startsWith('en')) score += 30;
    // A British voice suits a game set in a pseudo-medieval Britain. A gentle
    // nudge, not a requirement.
    if (voice.lang.startsWith('en-GB')) score += 10;
    if (voice.default) score += 5;

    return score;
}

/**
 * Remove markup the Dungeon Master sometimes emits, before it is read aloud.
 *
 * Models produce `*emphasis*` and occasional markdown headings. A synthesiser
 * reads an asterisk as the word "asterisk", or stumbles over it — which is
 * jarring in the middle of a description. Stripping them costs nothing and
 * removes the most common way the narration sounds wrong.
 *
 * @param text The narration as written.
 * @returns The same words, without the punctuation that should not be spoken.
 */
function forSpeech(text: string): string {
    return (
        text
            .replace(/\*\*(.+?)\*\*/g, '$1')
            .replace(/\*(.+?)\*/g, '$1')
            .replace(/_(.+?)_/g, '$1')
            .replace(/`(.+?)`/g, '$1')
            .replace(/^#{1,6}\s+/gm, '')
            .replace(/[*_`#]/g, '')
            // An em dash is a pause in writing. Spoken, it is either ignored or read
            // aloud as a word depending on the engine; a comma gives the pause the
            // author intended.
            .replace(/\s*—\s*/g, ', ')
            .replace(/\s+/g, ' ')
            .trim()
    );
}

/** Where the chosen voice is remembered. Per device, deliberately. */
const VOICE_STORAGE_KEY = 'dm.voice';

/**
 * Read the remembered voice, tolerating browsers that forbid storage.
 *
 * @returns The stored voice name, or an empty string for the automatic choice.
 */
function readStoredVoice(): string {
    try {
        return localStorage.getItem(VOICE_STORAGE_KEY) ?? '';
    } catch {
        return '';
    }
}

@Injectable({ providedIn: 'root' })
export class SpeechService {
    private readonly _speaking = signal(false);
    private readonly _voices = signal<SpeechSynthesisVoice[]>([]);
    private readonly _voiceName = signal<string>(readStoredVoice());

    /** True while the Dungeon Master is talking. */
    readonly speaking = this._speaking.asReadonly();

    /** Every voice this browser offers. */
    readonly voices = this._voices.asReadonly();

    /** The chosen voice's name, or empty for the automatic choice. */
    readonly voiceName = this._voiceName.asReadonly();

    /** True when this browser can speak at all. */
    readonly isSupported = computed(() => typeof window !== 'undefined' && 'speechSynthesis' in window);

    constructor() {
        if (!this.isSupported()) {
            return;
        }
        this.loadVoices();
        // Chrome populates the list asynchronously and fires this when it does.
        window.speechSynthesis.addEventListener('voiceschanged', () => this.loadVoices());
    }

    /**
     * Read the browser's voice list into a signal.
     *
     * @returns Nothing.
     */
    private loadVoices(): void {
        this._voices.set(window.speechSynthesis.getVoices());
    }

    /**
     * Choose which voice to use.
     *
     * WHY THIS IS STORED IN THE BROWSER AND NOT ON THE SERVER
     *
     * Every other preference is saved to the account, so it follows you between
     * devices. This one deliberately is not, because **the available voices
     * differ from machine to machine.** Choosing "Ava (Premium)" on a Mac and
     * then signing in on a Windows laptop that has never heard of it would leave
     * the setting pointing at nothing.
     *
     * A device-specific preference belongs in device-specific storage.
     *
     * @param name The voice's name, or an empty string for the automatic choice.
     * @returns Nothing.
     */
    setVoice(name: string): void {
        this._voiceName.set(name);
        try {
            if (name) {
                localStorage.setItem(VOICE_STORAGE_KEY, name);
            } else {
                localStorage.removeItem(VOICE_STORAGE_KEY);
            }
        } catch {
            // Private browsing, or storage disabled. The choice then lasts for this
            // session only, which is a small loss rather than a failure.
        }
    }

    /**
     * Say a short line, so the listener can judge a voice before committing.
     *
     * @returns Nothing.
     */
    preview(): void {
        this.speak('The door gives with a groan of swollen wood. What do you do?');
    }

    /**
     * The English voices this browser offers, best first.
     *
     * Used to fill the picker in Settings. Sorted so the good ones are at the
     * top, because a list of 180 voices in alphabetical order is not a choice
     * anybody can usefully make.
     */
    readonly rankedVoices = computed(() =>
        this._voices()
            .filter((voice) => voice.lang.startsWith('en'))
            .map((voice) => ({ voice, score: scoreVoice(voice) }))
            .sort((a, b) => b.score - a.score)
            .map((entry) => entry.voice)
    );

    /**
     * True when a large, high-quality voice is installed.
     *
     * The compact voices every system ships are intelligible but obviously
     * synthetic. The downloadable ones — Apple calls them Premium and Enhanced,
     * Microsoft calls them Natural — are in a different class, and installing one
     * does more for how this sounds than any amount of tuning here.
     *
     * Surfaced so Settings can point that out, since somebody who finds the
     * voice robotic has a one-time fix available and no way to know it.
     */
    readonly hasHighQualityVoice = computed(() =>
        this._voices().some((voice) => /premium|enhanced|natural|neural/i.test(voice.name))
    );

    /**
     * Pick the voice to speak with.
     *
     * @returns The user's choice if they made one and it is still available,
     *   otherwise the highest-scoring voice on this machine, or `null` to let the
     *   browser decide.
     */
    private pickVoice(): SpeechSynthesisVoice | null {
        const available = this._voices();
        if (available.length === 0) {
            return null;
        }

        const chosen = this._voiceName();
        if (chosen) {
            const match = available.find((voice) => voice.name === chosen);
            if (match) {
                return match;
            }
        }

        return this.rankedVoices()[0] ?? available[0];
    }

    /**
     * Read a passage aloud.
     *
     * @param text What to say.
     * @param options.rate Speaking speed. 1 is normal; 0.95 suits narration,
     *   which benefits from being very slightly unhurried.
     * @param options.onEnd Called when the whole passage has finished. Used by
     *   hands-free mode to start listening again — and it must not fire until
     *   the last sentence is done, or the microphone would pick up the Dungeon
     *   Master's own voice.
     * @returns Nothing.
     */
    speak(text: string, options: { rate?: number; onEnd?: () => void } = {}): void {
        if (!this.isSupported() || !text.trim()) {
            options.onEnd?.();
            return;
        }

        this.stop();

        // Split into sentences. This works around Chrome cutting off long
        // utterances after roughly fifteen seconds, and produces more natural
        // phrasing than one enormous block — the synthesiser handles a sentence
        // better than a page.
        const sentences = forSpeech(text)
            .split(/(?<=[.!?…])\s+/)
            .map((part) => part.trim())
            .filter(Boolean);

        if (sentences.length === 0) {
            options.onEnd?.();
            return;
        }

        const voice = this.pickVoice();
        this._speaking.set(true);

        sentences.forEach((sentence, index) => {
            const utterance = new SpeechSynthesisUtterance(sentence);
            if (voice) {
                utterance.voice = voice;
                utterance.lang = voice.lang;
            }
            // Slightly slower than normal speech. Narration read at conversational
            // pace sounds rushed, and a storyteller naturally slows down.
            utterance.rate = options.rate ?? 0.92;
            // A fraction below default. Synthesised voices tend to sit high, which
            // is part of what reads as "robotic"; dropping it a little warms them up.
            utterance.pitch = 0.95;

            if (index === sentences.length - 1) {
                utterance.onend = () => {
                    this._speaking.set(false);
                    options.onEnd?.();
                };
                utterance.onerror = () => {
                    this._speaking.set(false);
                    options.onEnd?.();
                };
            }

            window.speechSynthesis.speak(utterance);
        });
    }

    /**
     * Stop speaking immediately.
     *
     * Called when the player sends another message, navigates away, or presses
     * the stop button. Nobody wants to be talked over by a paragraph they have
     * already moved past.
     *
     * @returns Nothing.
     */
    stop(): void {
        if (!this.isSupported()) {
            return;
        }
        window.speechSynthesis.cancel();
        this._speaking.set(false);
    }
}
