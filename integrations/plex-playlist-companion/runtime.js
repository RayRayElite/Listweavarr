/* SPDX-License-Identifier: AGPL-3.0-only */
/* Bootstrap probe only: does not intercept Plex or change layout/playback. */
(function () {
  'use strict';
  if (globalThis.__listweavarrPlaylistCompanion) return;
  const core = globalThis.ListweavarrPlaylistCore;
  if (!core) return;
  let storageAvailable = false;
  try {
    const key = 'playlist-companion:storage-probe';
    localStorage.setItem(key, '1');
    storageAvailable = localStorage.getItem(key) === '1';
    localStorage.removeItem(key);
  } catch {
    /* Offline persistence must be reported unavailable, not assumed. */
  }
  const state = Object.freeze({
    version: '0.1.0-probe',
    storageAvailable,
    platform: location.protocol === 'file:' ? 'desktop' : 'web',
    automaticTracking: false,
    resumeAdapter: false,
    posterLayout: false,
  });
  globalThis.__listweavarrPlaylistCompanion = state;
  console.info('[Listweavarr Playlist Companion] bootstrap ' + JSON.stringify(state));
})();
