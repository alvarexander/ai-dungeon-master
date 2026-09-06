/**
 * Campaigns and characters, held as signals.
 *
 * A note on ordering that reflects the privacy design: campaigns arrive from
 * the backend ordered by when they were last played, because their titles are
 * encrypted and the database genuinely cannot sort by them. Sorting by name
 * happens here, in the browser, after decryption — which is also why the list
 * is paged rather than unbounded.
 */

import { Injectable, computed, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { ApiClient } from '../api/api.client';
import {
  Acknowledgement,
  CampaignCreateRequest,
  CampaignDetail,
  CampaignSummary,
  CharacterCreateRequest,
  CharacterDetail,
  Page,
} from '../api/api.types';

@Injectable({ providedIn: 'root' })
export class CampaignStore {
  private readonly api = inject(ApiClient);

  private readonly _campaigns = signal<CampaignSummary[]>([]);
  private readonly _characters = signal<CharacterDetail[]>([]);
  private readonly _loading = signal(false);
  private readonly _error = signal<string | null>(null);
  private readonly _sortBy = signal<'recent' | 'title'>('recent');

  /** Every campaign belonging to the signed-in user. */
  readonly campaigns = this._campaigns.asReadonly();

  /** Characters in the campaign most recently loaded. */
  readonly characters = this._characters.asReadonly();

  /** True while a request is in flight. */
  readonly loading = this._loading.asReadonly();

  /** The current failure message, or `null`. */
  readonly error = this._error.asReadonly();

  /** How the list is currently ordered. */
  readonly sortBy = this._sortBy.asReadonly();

  /**
   * The campaigns in display order.
   *
   * Sorting by title happens here rather than in the database, because titles
   * are encrypted and the database cannot read them. This is a small, concrete
   * example of what the privacy design costs day to day.
   */
  readonly sortedCampaigns = computed(() => {
    const list = [...this._campaigns()];
    if (this._sortBy() === 'title') {
      return list.sort((a, b) => a.title.localeCompare(b.title));
    }
    return list.sort((a, b) => b.updated_at.localeCompare(a.updated_at));
  });

  /** True when the user has no campaigns yet. */
  readonly isEmpty = computed(() => !this._loading() && this._campaigns().length === 0);

  /**
   * Change the list ordering.
   *
   * @param sortBy Either most recently played, or alphabetical by title.
   */
  setSort(sortBy: 'recent' | 'title'): void {
    this._sortBy.set(sortBy);
  }

  /**
   * Load the user's campaigns.
   *
   * @returns Nothing.
   */
  async load(): Promise<void> {
    this._loading.set(true);
    this._error.set(null);
    try {
      const page = await firstValueFrom(
        this.api.get<Page<CampaignSummary>>('/api/v1/campaigns', { limit: 100 }),
      );
      this._campaigns.set(page.items);
    } catch (error) {
      this._error.set(messageFrom(error));
    } finally {
      this._loading.set(false);
    }
  }

  /**
   * Create a campaign.
   *
   * @param request The campaign details.
   * @returns The created campaign, or `null` if it failed.
   */
  async create(request: CampaignCreateRequest): Promise<CampaignDetail | null> {
    this._loading.set(true);
    this._error.set(null);
    try {
      const created = await firstValueFrom(
        this.api.post<CampaignDetail>('/api/v1/campaigns', request),
      );
      await this.load();
      return created;
    } catch (error) {
      this._error.set(messageFrom(error));
      return null;
    } finally {
      this._loading.set(false);
    }
  }

  /**
   * Fetch one campaign in full.
   *
   * @param campaignId Which campaign.
   * @returns The campaign, or `null` if it could not be read.
   */
  async get(campaignId: string): Promise<CampaignDetail | null> {
    try {
      return await firstValueFrom(
        this.api.get<CampaignDetail>(`/api/v1/campaigns/${campaignId}`),
      );
    } catch (error) {
      this._error.set(messageFrom(error));
      return null;
    }
  }

  /**
   * Delete a campaign and everything in it.
   *
   * @param campaignId Which campaign.
   * @returns True if it was deleted.
   */
  async remove(campaignId: string): Promise<boolean> {
    try {
      await firstValueFrom(this.api.delete<Acknowledgement>(`/api/v1/campaigns/${campaignId}`));
      await this.load();
      return true;
    } catch (error) {
      this._error.set(messageFrom(error));
      return false;
    }
  }

  /**
   * Load the characters in one campaign.
   *
   * @param campaignId Which campaign.
   * @returns Nothing.
   */
  async loadCharacters(campaignId: string): Promise<void> {
    this._loading.set(true);
    try {
      const characters = await firstValueFrom(
        this.api.get<CharacterDetail[]>(`/api/v1/campaigns/${campaignId}/characters`),
      );
      this._characters.set(characters);
    } catch (error) {
      this._error.set(messageFrom(error));
    } finally {
      this._loading.set(false);
    }
  }

  /**
   * Create a character in a campaign.
   *
   * @param campaignId Which campaign.
   * @param request The character's details.
   * @returns The created character, or `null` if it failed.
   */
  async createCharacter(
    campaignId: string,
    request: CharacterCreateRequest,
  ): Promise<CharacterDetail | null> {
    this._loading.set(true);
    this._error.set(null);
    try {
      const created = await firstValueFrom(
        this.api.post<CharacterDetail>(`/api/v1/campaigns/${campaignId}/characters`, request),
      );
      await this.loadCharacters(campaignId);
      return created;
    } catch (error) {
      this._error.set(messageFrom(error));
      return null;
    } finally {
      this._loading.set(false);
    }
  }

  /**
   * Change a character.
   *
   * @param characterId Which character.
   * @param changes The fields to change.
   * @returns The updated character, or `null` if it failed.
   */
  async updateCharacter(
    characterId: string,
    changes: Partial<CharacterCreateRequest> & { hit_points_current?: number },
  ): Promise<CharacterDetail | null> {
    try {
      const updated = await firstValueFrom(
        this.api.patch<CharacterDetail>(`/api/v1/characters/${characterId}`, changes),
      );
      this._characters.update((list) =>
        list.map((character) =>
          character.character_id === characterId ? updated : character,
        ),
      );
      return updated;
    } catch (error) {
      this._error.set(messageFrom(error));
      return null;
    }
  }

  /**
   * Clear the current error message.
   */
  clearError(): void {
    this._error.set(null);
  }
}

/**
 * Extract a displayable message from a thrown error.
 *
 * @param error Whatever was thrown.
 * @returns A message safe to show the user.
 */
function messageFrom(error: unknown): string {
  const failure = (error as { failure?: { message?: string } })?.failure;
  return failure?.message ?? 'Something went wrong. Please try again.';
}
