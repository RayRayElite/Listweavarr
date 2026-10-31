/* SPDX-License-Identifier: AGPL-3.0-only */
(function (root) {
  'use strict';
  function targets(document) {
    return {
      content: document.querySelector(
        '[class*="SettingsPage-content-"], [class*="PageContent-pageContentScroller-"]'
      ),
      sidebar: document.querySelector('[class*="SettingsSidebar-sidebarContent-"]'),
    };
  }
  function mount(api, state) {
    const dialog = document.createElement('dialog');
    dialog.setAttribute('aria-label', 'Playlist companion settings');
    dialog.style.cssText =
      'background:#202020;color:#eee;border:1px solid #555;border-radius:10px;padding:24px;width:540px;max-width:90vw;max-height:85vh;overflow:auto;font:14px system-ui;line-height:1.5';
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
    progressLabel.append(
      progress,
      'Sync playlist progress and chosen posters between paired devices'
    );
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
    portrait.onchange = () =>
      localStorage.setItem('playlist-companion:portrait', String(portrait.checked));
    const placementLabel = document.createElement('label');
    placementLabel.textContent = 'Continue Playlists position';
    const placement = document.createElement('select');
    placement.setAttribute('aria-label', 'Continue Playlists position');
    for (const [value, title] of [
      ['after-continue', 'Below Continue Watching'],
      ['top', 'Top of Home'],
      ['after-row', 'After row number...'],
      ['bottom', 'Bottom of Home'],
    ]) {
      const option = document.createElement('option');
      option.value = value;
      option.textContent = title;
      placement.append(option);
    }
    const current = root.ListweavarrPlaylistHome.rowPreference(localStorage);
    placement.value = current.mode;
    placement.style.cssText =
      'display:block;background:#333;color:#eee;padding:9px;width:100%;margin:8px 0';
    const rowLabel = document.createElement('label');
    rowLabel.textContent = 'Row number (starting at 1)';
    const row = document.createElement('input');
    row.type = 'number';
    row.min = '1';
    row.max = '100';
    row.step = '1';
    row.value = String(current.index);
    row.style.cssText = 'display:block;width:90px;padding:8px;background:#333;color:#eee';
    rowLabel.append(row);
    rowLabel.hidden = placement.value !== 'after-row';
    const positionStatus = document.createElement('p');
    positionStatus.setAttribute('role', 'status');
    function savePosition() {
      rowLabel.hidden = placement.value !== 'after-row';
      const index = Number(row.value);
      if (!Number.isInteger(index) || index < 1 || index > 100) {
        positionStatus.textContent = 'Choose a row number from 1 to 100.';
        return;
      }
      localStorage.setItem(
        'playlist-companion:home-position',
        JSON.stringify({ mode: placement.value, index })
      );
      root.dispatchEvent(new Event('listweavarr-playlist-settings'));
      positionStatus.textContent =
        'Saved on this client. If fewer rows exist, the playlist row follows the last available row.';
    }
    placement.onchange = row.onchange = savePosition;
    placementLabel.append(placement);
    const positionNote = document.createElement('p');
    positionNote.textContent =
      'Placement is saved separately on each client. Plex can load more Home rows as you scroll; the companion follows the chosen position.';
    const appearance = document.createElement('section');
    appearance.append(label, placementLabel, rowLabel, positionNote, positionStatus);
    const connection = document.createElement('section');
    connection.append(note, input, progressLabel, progressNote, status, actions);
    const recovery = document.createElement('section');
    const safetyNote = document.createElement('p');
    safetyNote.textContent =
      'Press Ctrl + Alt + Shift + L anywhere in Plex to turn the companion off or back on. Plex reloads; bookmarks, posters and pairing are kept. The shortcut loads before the integration.';
    const versionNote = document.createElement('p');
    versionNote.textContent = state.verifiedBuild
      ? 'This Plex build has been verified.'
      : 'This Plex version has not been verified. Features use compatibility checks rather than blocking by version number.';
    const disable = document.createElement('button');
    disable.textContent = 'Pause companion and reload Plex';
    disable.type = 'button';
    disable.onclick = () => root.__listweavarrCompanionSafety?.toggle();
    const launcherNote = document.createElement('p');
    launcherNote.textContent =
      'If the shortcut is unavailable, close Plex and run Start Plex without Companion.cmd from the Windows companion package. For Web, you can also disable the extension in Chrome.';
    recovery.append(versionNote, safetyNote, disable, launcherNote);
    const panels = [appearance, connection, recovery],
      tabs = document.createElement('div');
    tabs.setAttribute('role', 'tablist');
    tabs.setAttribute('aria-label', 'Companion settings sections');
    tabs.style.cssText = 'display:flex;gap:8px;margin:16px 0;flex-wrap:wrap';
    const tabButtons = [];
    function selectTab(index) {
      panels.forEach((panel, number) => {
        panel.hidden = number !== index;
        tabButtons[number].setAttribute('aria-selected', String(number === index));
        tabButtons[number].tabIndex = number === index ? 0 : -1;
      });
    }
    ['Appearance', 'Connection & sync', 'Recovery'].forEach((title, index) => {
      const tab = document.createElement('button');
      tab.type = 'button';
      tab.textContent = title;
      tab.setAttribute('role', 'tab');
      tab.id = 'lw-companion-tab-' + index;
      panels[index].id = 'lw-companion-panel-' + index;
      panels[index].setAttribute('role', 'tabpanel');
      panels[index].setAttribute('aria-labelledby', tab.id);
      tab.setAttribute('aria-controls', panels[index].id);
      tab.style.cssText =
        'background:#333;color:#eee;border:1px solid #666;padding:8px 12px;cursor:pointer';
      tab.onclick = () => selectTab(index);
      tab.onkeydown = (event) => {
        let next = index;
        if (event.key === 'ArrowRight') next = (index + 1) % 3;
        else if (event.key === 'ArrowLeft') next = (index + 2) % 3;
        else return;
        event.preventDefault();
        selectTab(next);
        tabButtons[next].focus();
      };
      tabButtons.push(tab);
      tabs.append(tab);
    });
    const close = document.createElement('button');
    close.textContent = 'Done';
    close.type = 'button';
    close.onclick = () => dialog.close();
    close.style.cssText =
      'margin-top:18px;padding:9px 16px;background:#333;color:#eee;border:1px solid #666;cursor:pointer';
    selectTab(0);
    dialog.append(heading, tabs, ...panels, close);
    document.body.append(dialog);
    state.openSettings = () => {
      if (!dialog.open) dialog.showModal();
    };
    // Make the same dashboard discoverable in Plex Settings, without replacing
    // native routes or changing their controls. Home's gear remains a shortcut.
    const entry = document.createElement('section');
    entry.style.cssText =
      'padding:18px;margin:16px 0;border:1px solid #555;border-radius:8px;background:#252525;color:#eee';
    const entryTitle = document.createElement('h3');
    entryTitle.textContent = 'Playlist companion';
    const entryNote = document.createElement('p');
    entryNote.textContent = 'Home layout, posters, syncing and recovery.';
    const open = document.createElement('button');
    open.textContent = 'Open companion settings';
    open.type = 'button';
    open.onclick = () => state.openSettings();
    entry.append(entryTitle, entryNote, open);
    const navigation = document.createElement('div');
    navigation.className = 'lw-companion-settings-nav';
    const navigationHeading = document.createElement('div');
    navigationHeading.textContent = 'Listweavarr';
    navigationHeading.style.cssText =
      'padding:18px 24px 8px;font-weight:600;font-size:13px;color:#999';
    const navigationButton = document.createElement('button');
    navigationButton.type = 'button';
    navigationButton.textContent = 'Playlist companion';
    navigationButton.style.cssText =
      'display:block;width:100%;text-align:left;padding:9px 42px;background:transparent;border:0;color:#ddd;cursor:pointer;font:inherit';
    navigationButton.onclick = () => state.openSettings();
    navigationButton.onmouseenter = () => {
      navigationButton.style.color = '#e5a00d';
    };
    navigationButton.onmouseleave = () => {
      navigationButton.style.color = '#ddd';
    };
    navigation.append(navigationHeading, navigationButton);
    let timer;
    function attach() {
      if (!/\/settings(?:[/?]|$)/.test(location.hash)) {
        entry.remove();
        navigation.remove();
        return;
      }
      const { content: container, sidebar } = targets(document);
      if (sidebar && navigation.parentElement !== sidebar)
        sidebar.insertBefore(
          navigation,
          sidebar.querySelector('[class*="ServerSettingsServerMenuButton-button-"]')
        );
      if (container && entry.parentElement !== container) {
        const header = container.querySelector('[class*="SettingsPageHeader-header-"]');
        container.insertBefore(entry, header?.nextSibling || container.firstChild);
      }
    }
    const schedule = () => {
      if (!timer)
        timer = setTimeout(() => {
          timer = null;
          attach();
        }, 100);
    };
    const observer = new MutationObserver(schedule);
    observer.observe(document.getElementById('plex') || document.body, {
      childList: true,
      subtree: true,
    });
    root.addEventListener('hashchange', schedule);
    attach();
    return () => {
      clearTimeout(timer);
      observer.disconnect();
      root.removeEventListener('hashchange', schedule);
      entry.remove();
      navigation.remove();
      dialog.remove();
    };
  }
  root.ListweavarrPlaylistSettings = { mount, targets };
})(globalThis);
