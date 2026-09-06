/**
 * Every screen in the application, and the address that reaches it.
 *
 * WHY EVERY SCREEN IS LOADED LAZILY
 *
 * `loadComponent` means the code for a screen is downloaded the first time
 * someone visits it, rather than all of it arriving up front. For a first page
 * load that is the difference between downloading the chat screen and
 * downloading the chat screen plus the character sheet plus the settings plus
 * every authentication page.
 *
 * A RULE ABOUT THESE ADDRESSES
 *
 * **No personal data appears in any URL.** Only opaque identifiers — random
 * values that mean nothing on their own. This is not a style preference: URLs
 * are recorded in browser history, in server access logs, and in the
 * `Referer` header sent to any site the user clicks through to. All of those
 * sit outside the encryption boundary, so anything in a URL is effectively
 * public.
 */

import { Routes } from '@angular/router';

export const routes: Routes = [
    {
        path: '',
        pathMatch: 'full',
        redirectTo: 'play'
    },
    {
        path: 'play',
        title: 'Play — AI Dungeon Master',
        loadComponent: () => import('./features/chat/chat-page').then((m) => m.ChatPage)
    },
    {
        path: 'play/:sessionId',
        title: 'Play — AI Dungeon Master',
        loadComponent: () => import('./features/chat/chat-page').then((m) => m.ChatPage)
    },
    {
        path: 'campaigns',
        title: 'Campaigns — AI Dungeon Master',
        loadComponent: () => import('./features/campaigns/campaign-list-page').then((m) => m.CampaignListPage)
    },
    {
        path: 'campaigns/new',
        title: 'New campaign — AI Dungeon Master',
        loadComponent: () => import('./features/campaigns/campaign-create-page').then((m) => m.CampaignCreatePage)
    },
    {
        path: 'campaigns/:campaignId/characters',
        title: 'Characters — AI Dungeon Master',
        loadComponent: () => import('./features/characters/character-list-page').then((m) => m.CharacterListPage)
    },
    {
        path: 'campaigns/:campaignId/characters/new',
        title: 'New character — AI Dungeon Master',
        loadComponent: () => import('./features/characters/character-create-page').then((m) => m.CharacterCreatePage)
    },
    {
        path: 'characters/:characterId',
        title: 'Character sheet — AI Dungeon Master',
        loadComponent: () => import('./features/characters/character-sheet-page').then((m) => m.CharacterSheetPage)
    },
    {
        path: 'settings',
        title: 'Settings — AI Dungeon Master',
        loadComponent: () => import('./features/settings/settings-page').then((m) => m.SettingsPage)
    },
    {
        path: 'account',
        title: 'Account — AI Dungeon Master',
        loadComponent: () => import('./features/account/account-page').then((m) => m.AccountPage)
    },
    {
        path: 'privacy',
        title: 'Your data — AI Dungeon Master',
        loadComponent: () => import('./features/account/privacy-page').then((m) => m.PrivacyPage)
    },

    // --- Authentication. Fully designed, deliberately not fully implemented. ---
    {
        path: 'sign-in',
        title: 'Sign in — AI Dungeon Master',
        loadComponent: () => import('./features/auth/sign-in-page').then((m) => m.SignInPage)
    },
    {
        path: 'sign-up',
        title: 'Create an account — AI Dungeon Master',
        loadComponent: () => import('./features/auth/sign-up-page').then((m) => m.SignUpPage)
    },
    {
        path: 'forgot-password',
        title: 'Reset your password — AI Dungeon Master',
        loadComponent: () => import('./features/auth/forgot-password-page').then((m) => m.ForgotPasswordPage)
    },

    {
        path: '**',
        title: 'Not found — AI Dungeon Master',
        loadComponent: () => import('./features/shell/not-found-page').then((m) => m.NotFoundPage)
    }
];
