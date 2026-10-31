/* SPDX-License-Identifier: AGPL-3.0-only */
(function (root) {
  'use strict';
  function mount(api, state) {
    const dialog = document.createElement('dialog');
    dialog.setAttribute('aria-label', 'Playlist companion settings');
    dialog.style.cssText =
      'background:#202020;color:#eee;border:1px solid #555;border-radius:10px;padding:24px;width:480px;max-width:90vw;font:14px system-ui;line-height:1.5';
    const heading = document.createElement('h2');
    heading.textContent = 'Playlist companion';
    const label = document.createElement('label');
    const portrait = document.createElement('input');
    portrait.type = 'checkbox';
    portrait.checked = localStorage.getItem('playlist-companion:portrait') !== 'false';
    label.append(
      portrait,
      ' Portrait playlist cards (restart Plex or reload the tab after changing)'
    );
    const note = document.createElement('p');
    note.textContent =
      'Optional artwork pairing: in Listweavarr, open Settings → Connections → Playlist companion. Paste its artwork pairing below. Cached posters and resume work when Listweavarr is closed.';
    const input = document.createElement('textarea');
    input.setAttribute('aria-label', 'Listweavarr artwork pairing');
    input.placeholder = 'Paste artwork pairing';
    input.style.cssText =
      'box-sizing:border-box;width:100%;height:75px;background:#111;color:#eee;padding:10px;border:1px solid #777';
    const status = document.createElement('p');
    status.setAttribute('role', 'status');
    status.textContent = root.ListweavarrPlaylistArtwork.paired()
      ? 'Artwork pairing is saved on this device.'
      : 'No artwork pairing. Plex artwork and local poster choices remain available.';
    const actions = document.createElement('div');
    const progressLabel = document.createElement('label');
    progressLabel.style.cssText = 'display:flex;gap:8px;align-items:center;margin:16px 0';
    const progress = document.createElement('input');
    progress.type = 'checkbox';
    progress.checked = localStorage.getItem('playlist-companion:sync-enabled') === 'true';
    progressLabel.append(progress, 'Sync playlist progress between paired devices');
    const progressNote = document.createElement('p');
    progressNote.textContent =
      'Pair each client with the same Listweavarr server. Sync includes existing local bookmarks and runs every 10 seconds while Plex is open. Keep Listweavarr running for cross-device sync; offline resume still works.';
    progress.onchange = async () => {
      localStorage.setItem('playlist-companion:sync-enabled', String(progress.checked));
      if (progress.checked) {
        try {
          await state.progressSync.sync();
          status.textContent = 'Progress synced.';
        } catch (error) {
          status.textContent = error.message;
        }
      } else status.textContent = 'Progress sync disabled. Local and shared bookmarks were kept.';
    };
    actions.style.cssText = 'display:flex;gap:10px;flex-wrap:wrap';
    function button(name, action) {
      const value = document.createElement('button');
      value.textContent = name;
      value.type = 'button';
      value.style.cssText =
        'background:#333;color:#eee;border:1px solid #666;border-radius:4px;padding:9px 13px;cursor:pointer';
      value.onclick = action;
      actions.append(value);
      return value;
    }
    const sync = button('Connect / refresh artwork', async () => {
      sync.disabled = true;
      try {
        if (input.value.trim()) root.ListweavarrPlaylistArtwork.connect(input.value.trim());
        if (!root.ListweavarrPlaylistArtwork.paired())
          throw new Error('Paste an artwork pairing first.');
        input.value = '';
        const result = await root.ListweavarrPlaylistArtwork.sync(api, true);
        if (progress.checked) await state.progressSync.sync();
        status.textContent = `Artwork connected. ${result.updated} posters updated.`;
      } catch (error) {
        status.textContent =
          error.message || 'Artwork server unavailable. Cached posters were kept.';
      } finally {
        sync.disabled = false;
      }
    });
    button('Disconnect artwork', () => {
      root.ListweavarrPlaylistArtwork.disconnect();
      input.value = '';
      status.textContent = 'Disconnected. Cached posters were kept.';
    });
    button('Diagnostics', () => {
      dialog.close();
      state.showDiagnostics?.();
    });
    button('Done', () => dialog.close());
    portrait.onchange = () =>
      localStorage.setItem('playlist-companion:portrait', String(portrait.checked));
    dialog.append(heading, label, note, input, progressLabel, progressNote, status, actions);
    document.body.append(dialog);
    state.openSettings = () => {
      if (!dialog.open) dialog.showModal();
    };
    return () => dialog.remove();
  }
  root.ListweavarrPlaylistSettings = { mount };
})(globalThis);
