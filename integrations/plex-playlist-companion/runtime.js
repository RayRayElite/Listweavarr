/* SPDX-License-Identifier: AGPL-3.0-only */
/* Original companion controls and a narrowly versioned desktop integration. */
(function () {
  'use strict';
  if (globalThis.__listweavarrCompanionSafety?.disabled()) return;
  if (globalThis.__listweavarrPlaylistCompanion) return;
  const core = globalThis.ListweavarrPlaylistCore;
  if (!core) return;
  const state = {
    version: '0.4.0-development',
    platform: location.protocol === 'file:' ? 'desktop' : 'web',
    automaticTracking: false,
    resumeAdapter: false,
    posterLayout: false,
    api: null,
  };
  globalThis.__listweavarrPlaylistCompanion = state;
  const supported = () =>
    Array.from(document.scripts).some((script) =>
      (globalThis.ListweavarrPlaylistBuilds || []).some((build) => script.src.endsWith('/' + build))
    );
  let require;
  const chunks = globalThis.webpackChunkplex_web_client;
  if (!chunks || !globalThis.ListweavarrPlexAdapter) return;
  chunks.push([
    ['listweavarr-companion-' + Date.now()],
    {},
    (value) => {
      require = value;
    },
  ]);
  let attempts = 0;
  const initialize = setInterval(() => {
    try {
      state.verifiedBuild = supported();
      if (!require?.m?.[3467] || !require(3467).XU('appStore')) throw new Error('Waiting for Plex');
      const api = globalThis.ListweavarrPlexAdapter.create(require, localStorage, core);
      clearInterval(initialize);
      state.api = api;
      state.progressSync = core.createSync(localStorage, api);
      const syncProgress = () =>
        state.progressSync.sync().catch((error) => {
          state.syncError = error.message;
        });
      syncProgress();
      const progressTimer = setInterval(syncProgress, 10000);
      addEventListener('online', syncProgress);
      addEventListener(
        'pagehide',
        () => {
          clearInterval(progressTimer);
          removeEventListener('online', syncProgress);
        },
        { once: true }
      );
      state.automaticTracking = api.nativeTracking;
      state.resumeAdapter = true;
      state.posterLayout = !!globalThis.__listweavarrPlaylistLayout?.installed;
      console.info('[Listweavarr Playlist Companion] ' + state.platform + ' player adapter ready');
      mount(api);
      const artwork = globalThis.ListweavarrPlaylistArtwork;
      const stopArtwork = artwork?.mount(api);
      const stopSettings = globalThis.ListweavarrPlaylistSettings?.mount(api, state);
      artwork?.sync(api).catch(() => {});
      const artworkTimer = setInterval(() => artwork?.sync(api).catch(() => {}), 300000);
      const stopHome = globalThis.ListweavarrPlaylistHome?.mount(api, core, localStorage);
      addEventListener(
        'pagehide',
        () => {
          stopHome?.();
          stopSettings?.();
          stopArtwork?.();
          artwork?.close();
          clearInterval(artworkTimer);
          api.dispose();
        },
        { once: true }
      );
    } catch {
      if (++attempts >= 60) {
        clearInterval(initialize);
        console.warn(
          '[Listweavarr Playlist Companion] Player adapter unavailable; Plex left unchanged'
        );
      }
    }
  }, 500);
  function mount(api) {
    const host = document.createElement('div');
    host.style.cssText =
      'position:fixed;right:20px;bottom:100px;z-index:100000;font:14px system-ui;color:#eee';
    const toggle = document.createElement('button');
    toggle.textContent = 'Playlist diagnostics';
    toggle.hidden = true;
    toggle.style.cssText =
      'display:none;background:#282828;color:#eee;border:1px solid #777;border-radius:6px;padding:10px 14px;cursor:pointer';
    toggle.setAttribute('aria-expanded', 'false');
    const panel = document.createElement('section');
    panel.hidden = true;
    panel.setAttribute('aria-label', 'Playlist companion');
    panel.style.cssText =
      'background:#202020;border:1px solid #666;border-radius:8px;padding:18px;width:340px;max-width:80vw;box-shadow:0 8px 36px #000b;margin-bottom:8px';
    const heading = document.createElement('h2');
    heading.textContent = 'Continue a playlist';
    heading.style.cssText = 'font-size:20px;margin:0 0 12px';
    const note = document.createElement('p');
    note.textContent =
      'Development diagnostics · normal Plex playlist Play tracks automatically. Bookmarks stay on this device.';
    note.style.cssText = 'font-size:12px;color:#bbb;line-height:1.5';
    const select = document.createElement('select');
    select.setAttribute('aria-label', 'Video playlist');
    select.style.cssText =
      'width:100%;background:#333;color:white;padding:9px;margin:10px 0;border:1px solid #777';
    const info = document.createElement('p');
    info.style.cssText = 'line-height:1.5;overflow-wrap:anywhere';
    const status = document.createElement('p');
    status.setAttribute('role', 'status');
    status.style.cssText = 'font-size:12px;color:#ccc;line-height:1.5';
    const controls = document.createElement('div');
    controls.style.cssText = 'display:flex;gap:8px;flex-wrap:wrap';
    const buttons = [];
    let rows = [];
    function selected() {
      return rows[Number(select.value)];
    }
    function showSelection() {
      const row = selected();
      const saved = row && core.load(localStorage, row);
      info.textContent = saved
        ? `${saved.showTitle ? saved.showTitle + ' · ' : ''}${saved.itemTitle || 'Saved entry'} · ${Math.floor(saved.offsetMs / 60000)}:${String(Math.floor(saved.offsetMs / 1000) % 60).padStart(2, '0')}`
        : 'No bookmark yet. Start this playlist to remember your position.';
      buttons[1].disabled = !saved;
    }
    async function action(callback) {
      status.textContent = 'Working…';
      buttons.forEach((button) => {
        button.disabled = true;
      });
      try {
        await callback();
      } catch (error) {
        status.textContent =
          error?.message ||
          'Plex did not complete the request. Check the server connection and retry.';
        console.warn('[Listweavarr Playlist Companion] action failed: ' + status.textContent);
      } finally {
        buttons.forEach((button) => {
          button.disabled = false;
        });
        showSelection();
      }
    }
    function button(title, callback) {
      const element = document.createElement('button');
      element.textContent = title;
      element.style.cssText =
        'background:#e5a00d;color:#111;border:0;border-radius:4px;padding:9px 12px;cursor:pointer';
      element.onclick = () => action(callback);
      buttons.push(element);
      controls.append(element);
    }
    button('Start', async () => {
      const row = selected();
      if (!row) throw new Error('Choose a playlist');
      const result = await api.start(row, false);
      status.textContent = `Starting ${result.title}. Progress will be saved while this playlist plays.`;
    });
    button('Resume', async () => {
      const row = selected();
      if (!row) throw new Error('Choose a playlist');
      const result = await api.start(row, true);
      status.textContent = `Resuming ${result.title}. Next: ${result.nextTitle || 'end of playlist'}.`;
    });
    button('Pause & save', () => {
      const saved = api.pause();
      status.textContent = saved
        ? 'Playback paused; latest observed position saved.'
        : 'Playback paused. No valid timestamp has been observed yet; wait for the item to finish loading before resuming.';
    });
    button('Refresh', refresh);
    async function refresh() {
      status.textContent = 'Loading video playlists…';
      rows = await api.playlists();
      select.replaceChildren();
      rows.forEach((row, index) => {
        const option = document.createElement('option');
        option.value = String(index);
        option.textContent = `${row.title} (${row.count})`;
        select.append(option);
      });
      status.textContent = rows.length
        ? 'Choose a playlist.'
        : 'No ordinary video playlists found on connected servers.';
      showSelection();
    }
    select.onchange = showSelection;
    api.onProgress((message) => {
      status.textContent = message;
    });
    state.showDiagnostics = () => {
      toggle.hidden = false;
      toggle.style.display = '';
      panel.hidden = false;
      toggle.setAttribute('aria-expanded', 'true');
      action(refresh);
    };
    toggle.onclick = () => {
      panel.hidden = !panel.hidden;
      toggle.setAttribute('aria-expanded', String(!panel.hidden));
      if (!panel.hidden) action(refresh);
      else {
        toggle.hidden = true;
        toggle.style.display = 'none';
      }
    };
    panel.append(heading, note, select, info, controls, status);
    host.append(panel, toggle);
    document.body.append(host);
  }
})();
