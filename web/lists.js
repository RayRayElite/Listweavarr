// SPDX-License-Identifier: AGPL-3.0-only
let listReturnTab = 'mine';
/* Saved-list catalogue and explicit local/source editing. */
let listEditor = null,
  listEditorSearch = [],
  releaseMonitor = null;
function listCover(entry) {
  return entry.poster
    ? `<img src="${esc(entry.poster)}" alt="" loading="lazy">`
    : `<span class="list-cover-letter">${esc(entry.name.slice(0, 1))}</span><span class="list-cover-word">LISTWEAVARR / COLLECTION</span>`;
}
const listActionIcons = {
  edit: '<path d="m15 5 4 4M4 20l4-1L20 7a2.8 2.8 0 0 0-4-4L4 15z"/>',
  share:
    '<circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><path d="m9 10 6-4M9 14l6 4"/>',
  add: '<path d="M12 5v14M5 12h14"/>',
  delete: '<path d="m6 6 12 12M18 6 6 18"/>',
  refresh: '<path d="M20 7v5h-5M4 17v-5h5M6 6a8 8 0 0 1 13 2M18 18a8 8 0 0 1-13-2"/>',
};
function listActionButton(action, attribute, id, label) {
  return `<button type="button" class="list-icon-action${action === 'delete' ? ' list-icon-delete' : ''}" ${attribute}="${esc(id)}" title="${esc(label)}" aria-label="${esc(label)}"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">${listActionIcons[action]}</svg></button>`;
}
function catalogueSort(rows, order) {
  return [...rows].sort((a, b) => {
    if (order === 'count_desc')
      return (
        (b.count ?? b.items?.length ?? 0) - (a.count ?? a.items?.length ?? 0) ||
        a.name.localeCompare(b.name)
      );
    if (order === 'updated_desc')
      return (
        (b.updated_at || b.version || 0) - (a.updated_at || a.version || 0) ||
        a.name.localeCompare(b.name)
      );
    return (
      a.name.localeCompare(b.name, undefined, { numeric: true, sensitivity: 'base' }) *
      (order === 'title_desc' ? -1 : 1)
    );
  });
}
function drawOfficialCatalogue() {
  if (!$('official-items')) return;
  const order =
    $('official-list-sort').value ||
    localStorage.getItem('reelcheck-official-lists-sort') ||
    'title_asc';
  $('official-items').innerHTML =
    catalogueSort(officialCatalogue, order)
      .filter(
        (row) =>
          !document.getElementById('official-list-search')?.value ||
          ((row.name || '') + ' ' + (row.description || ''))
            .toLowerCase()
            .includes(document.getElementById('official-list-search').value.toLowerCase())
      )
      .map((row) => {
        const saved = state.lists.find((entry) => entry.official_id === row.id),
          entry = saved?.official_authoring ? saved : row;
        return `<article class="saved-list-card"><button class="saved-list-cover" data-official-open="${esc(row.id)}" aria-label="Open ${esc(entry.name)}">${listCover(entry)}</button><div><span class="eyebrow">OFFICIAL COLLECTION / V${esc(row.version)}${saved ? ' · ' + (saved.official_authoring ? 'Authoring original' : 'Personal copy saved') : ''}</span><h2><button class="title-link" data-official-open="${esc(row.id)}">${esc(entry.name)}</button></h2><p class="muted">${row.count} entries${entry.description ? ' &middot; ' + esc(entry.description) : ''}</p><div class="saved-list-actions">${saved?.official_authoring ? listActionButton('edit', 'data-edit-list', saved.id, 'Edit list & poster') + listActionButton('share', 'data-share-list', saved.id, 'Share list') + listActionButton('add', 'data-add-entries', saved.id, 'Add entries') + listActionButton('delete', 'data-delete-list', saved.id, 'Delete working copy') : listActionButton('add', 'data-official-open', row.id, saved ? 'Open my copy' : 'Add to My Lists')}</div></div></article>`;
      })
      .join('') ||
    '<div class="empty"><h2>No official collections match.</h2><button class="secondary" data-clear-catalogue="official-list-search">Clear search</button></div>';
}
for (const [id, key] of [
  ['saved-list-sort', 'my'],
  ['official-list-sort', 'official'],
]) {
  $(id).value = localStorage.getItem('reelcheck-' + key + '-lists-sort') || 'title_asc';
  $(id).onchange = () => {
    localStorage.setItem('reelcheck-' + key + '-lists-sort', $(id).value);
    id === 'saved-list-sort' ? drawListCatalogue() : drawOfficialCatalogue();
  };
}
$('official-items').addEventListener('click', (e) => {
  const edit = e.target.closest('[data-edit-list]'),
    share = e.target.closest('[data-share-list]'),
    add = e.target.closest('[data-add-entries]'),
    remove = e.target.closest('[data-delete-list]');
  if (edit) task(edit, () => editSavedList(edit.dataset.editList));
  if (share) openListShare(share.dataset.shareList);
  if (add) openListBuilder('', '', add.dataset.addEntries);
  if (remove) task(remove, () => openListDelete(remove.dataset.deleteList));
});
function drawListCatalogue() {
  if (!$('saved-list-grid')) return;
  $('saved-list-grid').innerHTML =
    catalogueSort(
      state.lists.filter(
        (row) =>
          !row.official_authoring &&
          (!document.getElementById('my-list-search')?.value ||
            ((row.name || '') + ' ' + (row.description || ''))
              .toLowerCase()
              .includes(document.getElementById('my-list-search').value.toLowerCase()))
      ),
      $('saved-list-sort').value || localStorage.getItem('reelcheck-my-lists-sort') || 'title_asc'
    )
      .map(
        (entry) =>
          `<article class="saved-list-card"><button class="saved-list-cover" data-open-list="${esc(entry.id)}" aria-label="Open ${esc(entry.name)}">${listCover(entry)}</button><div><span class="eyebrow">${entry.source ? 'LINKED SOURCE' : 'LOCAL COLLECTION'}</span><h2><button class="title-link" data-open-list="${esc(entry.id)}">${esc(entry.name)}</button></h2><p class="muted">${entry.items.length} entries${entry.description ? ' · ' + esc(entry.description.slice(0, 140)) : ''}</p><div class="saved-list-actions" role="group" aria-label="List actions">${listActionButton('edit', 'data-edit-list', entry.id, 'Edit list & poster')}${listActionButton('share', 'data-share-list', entry.id, 'Share list')}${listActionButton('add', 'data-add-entries', entry.id, 'Add entries')}${listActionButton('delete', 'data-delete-list', entry.id, 'Delete list')}${entry.source ? listActionButton('refresh', 'data-refresh-saved', entry.id, 'Refresh source') : ''}</div></div></article>`
      )
      .join('') ||
    (state.lists.some((row) => !row.official_authoring)
      ? '<div class="empty"><h2>No collections match.</h2><button class="secondary" data-clear-catalogue="my-list-search">Clear search</button></div>'
      : '<div class="empty"><h2>Your collections start here.</h2><p>Create a list or import a watch order from a supported source.</p></div>');
  const entry = current();
  $('list-publish-official').textContent = entry?.official_id
    ? 'Publish official update'
    : 'Publish as Official List';
  $('list-link-status').textContent = entry
    ? entry.official_authoring
      ? 'Official collection · authoring copy'
      : entry.source
        ? 'Linked source · refresh keeps your name, description and poster'
        : 'Local collection · edit freely'
    : '';
}
function showListCatalogue() {
  $('lists-mine').hidden = false;
  $('lists-official').hidden = true;
  $('breadcrumb').textContent = 'LISTS / MY LISTS';
  drawListCatalogue();
  $('list-catalogue').hidden = false;
  $('list-detail').hidden = true;
}
function openSavedList(id) {
  if (!state.lists.some((r) => r.id === id)) return;
  if ($('list-detail').hidden) listReturnTab = listsTab === 'official' ? 'official' : 'mine';
  active = id;
  localStorage.setItem('reelcheck-active-list', id);
  selected.clear();
  render();
  settingsView(false);
  selectListsTab(listReturnTab);
  $('lists-mine').hidden = true;
  $('lists-official').hidden = true;
  $('list-catalogue').hidden = true;
  $('list-detail').hidden = false;
  $('breadcrumb').textContent =
    (listReturnTab === 'official' ? 'OFFICIAL LISTS / ' : 'MY LISTS / ') + current().name;
  $('list-back').textContent =
    listReturnTab === 'official' ? 'Back to Official Lists' : 'Back to My Lists';
  drawListCatalogue();
}
const selectListsBeforeCatalogue = selectListsTab;
selectListsTab = function (name) {
  $('list-detail').hidden = true;
  selectListsBeforeCatalogue(name);
  if (name === 'mine') showListCatalogue();
};
// Rebind to use the catalogue-aware tab handler.
bindTabKeys('data-lists-tab', selectListsTab);
const replaceBeforeCatalogue = replaceList;
replaceList = function (entry) {
  const origin = listsTab;
  replaceBeforeCatalogue(entry);
  if (origin === 'official' && entry.official_id) selectListsTab('official');
  openSavedList(entry.id);
};
const renderBeforeCatalogue = render;
render = function () {
  renderBeforeCatalogue();
  if (!$('workspace').hidden && !$('list-catalogue').hidden) drawListCatalogue();
  if (officialLoaded && !$('workspace').hidden && !$('lists-official').hidden)
    drawOfficialCatalogue();
};
$('library-nav').onclick = () => {
  settingsView(false);
  selectListsTab('mine');
};
$('list-back').onclick = () => {
  if (listReturnTab === 'official') {
    $('list-detail').hidden = true;
    selectListsTab('official');
  } else showListCatalogue();
};
$('saved-list-grid').onclick = (e) => {
  const open = e.target.closest('[data-open-list]'),
    edit = e.target.closest('[data-edit-list]');
  if (open) openSavedList(open.dataset.openList);
  if (edit) task(edit, () => editSavedList(edit.dataset.editList));
};
$('list-create').onclick = (e) => task(e.target, () => editSavedList());
$('catalogue-import').onclick = () => $('import-open').click();
$('list-manage').onclick = (e) => task(e.target, () => editSavedList(active));
$('list-add-entries').onclick = () => openListBuilder('', '', active);
$('list-delete').onclick = (e) => task(e.target, () => openListDelete(active));
let deletingList = null;
async function openListDelete(id) {
  const data = await api('lists/revision', { list_id: id });
  deletingList = { id, revision: data.revision };
  $('list-delete-summary').textContent = `${data.entry.name} / ${data.entry.items.length} entries`;
  $('list-delete-status').textContent = '';
  $('list-delete-dialog').showModal();
}
$('list-delete-confirm').onclick = (e) =>
  task(e.target, async () => {
    if (!deletingList) return;
    const result = await api('lists/delete', {
      list_id: deletingList.id,
      revision: deletingList.revision,
      confirmed: true,
    });
    state.lists = state.lists.filter((row) => row.id !== result.deleted_id);
    if (active === result.deleted_id) {
      active = state.lists[0]?.id || '';
      selected.clear();
      if (active) localStorage.setItem('reelcheck-active-list', active);
      else localStorage.removeItem('reelcheck-active-list');
    }
    render();
    $('list-delete-dialog').close();
    deletingList = null;
    showListCatalogue();
    toast('Saved list deleted.');
  });
async function refreshSavedList(id) {
  const entry = state.lists.find((row) => row.id === id);
  if (!entry?.source)
    throw Error('This is a local list. Use Add entries or Edit list to update it.');
  $('import-dialog').showModal();
  const result = await api('import/start', { list_id: id });
  await pollImport(result.job_id);
}
$('saved-list-grid').addEventListener('click', (e) => {
  const add = e.target.closest('[data-add-entries]'),
    remove = e.target.closest('[data-delete-list]'),
    refresh = e.target.closest('[data-refresh-saved]');
  if (add) openListBuilder('', '', add.dataset.addEntries);
  if (remove) task(remove, () => openListDelete(remove.dataset.deleteList));
  if (refresh) task(refresh, () => refreshSavedList(refresh.dataset.refreshSaved));
});

function editorMembershipChanged() {
  return (
    JSON.stringify(listEditor.items.map((r) => r.id || r._new)) !==
    JSON.stringify((listEditor.original?.items || []).map((r) => r.id))
  );
}
function drawEditorItems() {
  if (!listEditor) return;
  $('list-editor-count').textContent = `(${listEditor.items.length})`;
  $('list-editor-items').innerHTML = listEditor.items
    .map(
      (row, index) =>
        `<div class="list-edit-row"><span><b>${esc(row.title)}</b><small>${esc(row.type)}${row.year ? ' · ' + esc(row.year) : ''}${row.season != null ? ' · S' + esc(row.season) : ''}${row.episode != null ? ' E' + esc(row.episode) : ''}</small></span><button class="secondary" type="button" data-list-move="${index}" data-direction="-1" aria-label="Move ${esc(row.title)} up" ${index === 0 ? 'disabled' : ''}>↑</button><button class="secondary" type="button" data-list-move="${index}" data-direction="1" aria-label="Move ${esc(row.title)} down" ${index === listEditor.items.length - 1 ? 'disabled' : ''}>↓</button><button class="text-action" type="button" data-list-remove="${index}" aria-label="Remove ${esc(row.title)}">Remove</button></div>`
    )
    .join('');
  updateEditorLink();
}
function updateEditorLink() {
  const original = listEditor?.original,
    changed = editorMembershipChanged(),
    linked = $('list-edit-mode').value === 'linked';
  $('list-source-field').hidden = !linked;
  $('list-detach-warning').hidden = !(original?.source && (changed || !linked));
  $('list-source-help').textContent = original?.source
    ? changed
      ? 'Entry changes will convert this collection to local. Confirm below before saving.'
      : 'Rename, description and poster edits keep this source link. Refresh source checks for updates.'
    : linked
      ? 'The source will be imported in its own order. Manual entries below will be replaced by the source list.'
      : 'A local collection never refreshes from an external list.';
}
async function editSavedList(id) {
  let original = id ? state.lists.find((r) => r.id === id) : null;
  let revision = '';
  if (original) {
    const fresh = await api('lists/revision', { list_id: id });
    revision = fresh.revision;
    original = fresh.entry;
  }
  listEditor = {
    original,
    revision,
    items: (original?.items || []).map((r) => ({ ...r })),
    playlist_poster: original?.playlist_poster || '',
    poster: original?.poster || '',
  };
  $('list-edit-name').value = original?.name || '';
  $('list-edit-description').value = original?.description || '';
  $('list-edit-mode').value = original?.source ? 'linked' : 'local';
  $('list-edit-source').value = original?.source || '';
  $('list-edit-source').readOnly = Boolean(original?.source);
  $('list-editor-heading').textContent = original ? 'Edit collection' : 'Create collection';
  $('list-confirm-detach').checked = false;
  $('list-add-results').innerHTML = '';
  $('list-editor-status').textContent = '';
  $('list-add-season-end').value = '';
  $('list-add-season-end').hidden = $('list-add-scope').value !== 'season';
  $('list-edit-poster').value = '';
  $('list-edit-playlist-poster').value = '';
  updateEditorPoster();
  drawEditorItems();
  $('list-editor').showModal();
}
function updateEditorPoster() {
  $('list-playlist-poster-preview').hidden = !listEditor.playlist_poster;
  $('list-playlist-poster-preview').src = listEditor.playlist_poster || '';
  $('list-poster-preview').hidden = !listEditor.poster;
  $('list-poster-preview').src = listEditor.poster || '';
}
$('list-edit-mode').onchange = updateEditorLink;
$('list-editor-items').onclick = (e) => {
  const remove = e.target.closest('[data-list-remove]'),
    move = e.target.closest('[data-list-move]');
  if (remove) listEditor.items.splice(Number(remove.dataset.listRemove), 1);
  if (move) {
    const from = Number(move.dataset.listMove),
      to = from + Number(move.dataset.direction);
    if (to >= 0 && to < listEditor.items.length)
      [listEditor.items[from], listEditor.items[to]] = [
        listEditor.items[to],
        listEditor.items[from],
      ];
  }
  drawEditorItems();
};
async function findListEditorTitle(button, direct = false) {
  return task(button, async () => {
    const data = await api('lists/search', {
      [direct ? 'tmdb_input' : 'query']: $('list-add-query').value,
      type: $('list-add-type').value,
    });
    listEditorSearch = data.items;
    $('list-add-results').innerHTML =
      data.items.map((r, i) => mediaCandidateMarkup(r, i, 'data-list-add')).join('') ||
      '<p class="muted">No matches.</p>';
  });
}
$('list-add-search').onclick = (e) => findListEditorTitle(e.target);
$('list-add-tmdb').onclick = (e) => findListEditorTitle(e.target, true);
$('list-add-scope').onchange = () => {
  $('list-add-season-end').hidden = $('list-add-scope').value !== 'season';
};
$('list-add-results').onclick = (e) => {
  const button = e.target.closest('[data-list-add]');
  if (!button) return;
  const found = listEditorSearch[Number(button.dataset.listAdd)],
    row = { ...found, _new: crypto.randomUUID() },
    direct = found.direct_scope;
  delete row.direct_scope;
  const scope = direct?.season != null ? direct.type : $('list-add-scope').value;
  if (row.type === 'show' && scope !== 'show') {
    const season = direct?.season ?? $('list-add-season').value,
      episode = direct?.episode ?? $('list-add-episode').value;
    if (season === '' || (scope === 'episode' && !episode)) {
      toast('Choose the season and episode numbers before adding.');
      return;
    }
    row.type = scope;
    row.show_tmdb = row.tmdb;
    row.show_title = row.title;
    delete row.tmdb;
    row.season = season;
    if (row.type === 'episode') row.episode = episode;
    if (scope === 'season') {
      const last = direct?.season != null ? season : $('list-add-season-end').value || season;
      if (
        !/^\d{1,3}$/.test(String(season)) ||
        !/^\d{1,3}$/.test(String(last)) ||
        Number(last) < Number(season) ||
        Number(last) - Number(season) >= 100
      ) {
        toast('Choose a valid first and last season, up to 100 seasons.');
        return;
      }
      for (let number = Number(season); number <= Number(last); number++)
        listEditor.items.push({ ...row, season: String(number), _new: crypto.randomUUID() });
      drawEditorItems();
      return;
    }
  }
  listEditor.items.push(row);
  drawEditorItems();
};
$('list-clear-poster').onclick = () => {
  listEditor.poster = '';
  updateEditorPoster();
};
$('list-generate-poster').onclick = () => {
  const canvas = document.createElement('canvas');
  canvas.width = 600;
  canvas.height = 900;
  const ctx = canvas.getContext('2d'),
    gradient = ctx.createLinearGradient(0, 0, 600, 900);
  gradient.addColorStop(0, '#384c30');
  gradient.addColorStop(1, '#111b17');
  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, 600, 900);
  ctx.strokeStyle = '#d5f084';
  ctx.lineWidth = 3;
  ctx.strokeRect(35, 35, 530, 830);
  ctx.fillStyle = '#d5f084';
  ctx.font = '18px Segoe UI';
  ctx.fillText('R E E L C H E C K', 65, 100);
  ctx.fillStyle = '#e8ebdf';
  ctx.font = '48px Georgia';
  const words = ($('list-edit-name').value || 'My collection').split(/\s+/);
  let line = '',
    y = 360;
  for (const word of words) {
    if (ctx.measureText(line + ' ' + word).width > 465 && line) {
      ctx.fillText(line, 65, y);
      y += 62;
      line = word;
    } else line += (line ? ' ' : '') + word;
  }
  ctx.fillText(line, 65, y);
  ctx.font = '18px Segoe UI';
  ctx.fillStyle = '#a9b99d';
  ctx.fillText('A PERSONAL COLLECTION', 65, 800);
  listEditor.poster = canvas.toDataURL('image/jpeg', 0.9);
  updateEditorPoster();
};
$('list-edit-poster').onchange = (e) =>
  task(e.target, async () => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type) || file.size > 10_000_000)
      throw Error('Choose a PNG, JPEG or WebP under 10 MB.');
    const image = await createImageBitmap(file);
    try {
      const canvas = document.createElement('canvas'),
        scale = Math.min(1, 1200 / image.width, 1800 / image.height);
      canvas.width = Math.round(image.width * scale);
      canvas.height = Math.round(image.height * scale);
      canvas.getContext('2d').drawImage(image, 0, 0, canvas.width, canvas.height);
      listEditor.poster = canvas.toDataURL('image/jpeg', 0.85);
      updateEditorPoster();
    } finally {
      image.close();
    }
  });
$('list-editor-form').onsubmit = (e) => {
  e.preventDefault();
  task(e.submitter, async () => {
    const linked = $('list-edit-mode').value === 'linked',
      original = listEditor.original;
    if (linked && !original?.source) {
      if (editorMembershipChanged() && listEditor.items.length)
        throw Error('Remove the local entries before linking; the source supplies the entries.');
      const url = $('list-edit-source').value.trim();
      if (!url) throw Error('Enter the source URL.');
      const result = await api('import/start', {
        url,
        name: $('list-edit-name').value,
        list_id: original?.id,
      });
      $('list-editor').close();
      $('import-dialog').showModal();
      await pollImport(result.id || result.job_id);
      const imported = current();
      const revision = (await api('lists/revision', { list_id: imported.id })).revision;
      const saved = await api('lists/edit', {
        list_id: imported.id,
        revision,
        name: imported.name,
        description: $('list-edit-description').value,
        poster: listEditor.poster,
        playlist_poster: listEditor.playlist_poster || '',
        items: imported.items.map((r) => ({ id: r.id })),
      });
      replaceList(saved.entry);
      return;
    }
    const result = await api('lists/edit', {
      list_id: original?.id,
      revision: listEditor.revision,
      name: $('list-edit-name').value,
      description: $('list-edit-description').value,
      poster: listEditor.poster,
      playlist_poster: listEditor.playlist_poster || '',
      items: listEditor.items,
      detach: !linked,
      confirm_detach: $('list-confirm-detach').checked,
    });
    replaceList(result.entry);
    $('list-editor').close();
    toast('Collection saved.');
  }).catch(() => {});
};
let readyBeforeCollections = window.onListweavarrReady,
  collectionsStarted = false;
window.onListweavarrReady = () => {
  readyBeforeCollections?.();
  drawListCatalogue();
  if (!collectionsStarted) {
    collectionsStarted = true;
    traktOpen();
  }
};
// A saved list selected from Explore should open the actual collection, not the catalogue.
const savedResultsClick = $('trakt-list-results').onclick;
$('trakt-list-results').onclick = (e) => {
  const button = e.target.closest('[data-explore-saved]');
  if (button) openSavedList(button.dataset.exploreSaved);
  else savedResultsClick(e);
};
$('release-watch-items').addEventListener('click', (e) => {
  const button = e.target.closest('[data-release-monitor]');
  if (button)
    task(button, async () => {
      const row = state.release_watchlist.find((r) => r.id === button.dataset.releaseMonitor);
      if (!row) return;
      releaseMonitor = row;
      const service = row.type === 'show' ? 'sonarr' : 'radarr',
        options = (await api('options', { list_id: active, services: [service] }))[service];
      $('release-monitor-heading').textContent = 'Monitor ' + row.title + ' in ' + service;
      $('release-monitor-options').innerHTML =
        `${requestRouteMarkup(options, service, 'release-monitor')}<label>Quality profile<select id="release-monitor-profile">${options.profiles.map((p) => `<option value="${p.id}">${esc(p.name)}</option>`).join('')}</select></label><label>Destination<select id="release-monitor-root">${options.roots.map((r) => `<option value="${esc(r.path)}">${esc(r.path)}</option>`).join('')}</select></label>`;
      if (options.defaults?.profile) $('release-monitor-profile').value = options.defaults.profile;
      if (options.defaults?.root) $('release-monitor-root').value = options.defaults.root;
      $('release-monitor-status').textContent = '';
      $('release-monitor-submit').hidden = false;
      $('release-monitor-dialog').showModal();
    });
});
$('release-monitor-submit').onclick = (e) =>
  task(e.target, async () => {
    const result = await api('releases/monitor', {
      id: releaseMonitor.id,
      profile: $('release-monitor-profile').value,
      root: $('release-monitor-root').value,
      route: $('release-monitor-route')?.value || 'primary',
    });
    state.release_watchlist = result.items;
    renderReleaseWatchlist();
    $('release-monitor-status').textContent = result.message;
    $('release-monitor-submit').hidden = true;
    $('release-monitor-dialog').close();
    toast(result.message || 'Release monitoring enabled.');
  });

// Sharing never exports server credentials, availability or request state.
let sharingListId = null,
  sharedListDocument = null,
  sharedListFingerprint = null;
function openListShare(id) {
  const entry = state.lists.find((r) => r.id === id);
  if (!entry) return;
  sharingListId = id;
  $('list-share-heading').textContent = 'Share ' + entry.name;
  $('list-share-poster').checked = true;
  $('list-share-status').textContent = '';
  $('list-share-dialog').showModal();
}
$('list-share').onclick = () => openListShare(active);
$('saved-list-grid').addEventListener('click', (e) => {
  const button = e.target.closest('[data-share-list]');
  if (button) openListShare(button.dataset.shareList);
});
$('list-share-download').onclick = (e) =>
  task(e.target, async () => {
    const document = await api('lists/share/export', {
        list_id: sharingListId,
        include_poster: $('list-share-poster').checked,
      }),
      blob = new Blob([JSON.stringify(document, null, 2)], { type: 'application/json' }),
      url = URL.createObjectURL(blob),
      link = window.document.createElement('a');
    link.href = url;
    link.download =
      (document.list.name.replace(/[^a-z0-9_-]+/gi, '-').slice(0, 80) || 'collection') +
      '.reelcheck-list.json';
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    $('list-share-status').textContent =
      'Shared-list file downloaded. The recipient can use Lists / My Lists / Import shared list.';
  });
$('shared-list-open').onclick = () => {
  sharedListDocument = null;
  sharedListFingerprint = null;
  $('shared-list-file').value = '';
  $('shared-list-status').textContent = '';
  $('shared-list-preview').hidden = true;
  $('shared-list-accept').hidden = true;
  $('shared-list-dialog').showModal();
};
$('shared-list-file').onchange = (e) =>
  task(e.target, async () => {
    sharedListDocument = null;
    sharedListFingerprint = null;
    $('shared-list-preview').hidden = true;
    $('shared-list-accept').hidden = true;
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > 7_500_000) throw Error('Choose a shared-list file under 7.5 MB.');
    const document = JSON.parse(await file.text()),
      result = await api('lists/share/preview', { document });
    sharedListDocument = document;
    sharedListFingerprint = result.fingerprint;
    const summary = result.summary;
    $('shared-list-preview').innerHTML =
      `<div class="shared-list-identity">${summary.poster ? `<img src="${esc(summary.poster)}" alt="List poster">` : ''}<div><h3>${esc(summary.name)}</h3><p class="muted">${esc(summary.description || '')}</p><p>${summary.count} entries &middot; ${Object.entries(
        summary.types
      )
        .filter(([, count]) => count)
        .map(([kind, count]) => count + ' ' + kind)
        .join(
          ' / '
        )}</p>${summary.needs_matching ? `<p class="muted">${summary.needs_matching} entries need identifier matching.</p>` : ''}</div></div><ol>${summary.sample.map((row) => `<li>${esc(row.title)} <small>${esc(row.type)}${row.season != null ? ' S' + esc(row.season) : ''}${row.episode != null ? ' E' + esc(row.episode) : ''}</small></li>`).join('')}</ol>`;
    $('shared-list-preview').hidden = false;
    $('shared-list-accept').hidden = false;
    $('shared-list-status').textContent =
      'Preview ready. Importing creates a new local list with unchecked availability.';
  });
$('shared-list-accept').onclick = (e) =>
  task(e.target, async () => {
    if (!sharedListDocument || !sharedListFingerprint) throw Error('Preview a shared list first.');
    const result = await api('lists/share/import', {
      document: sharedListDocument,
      fingerprint: sharedListFingerprint,
    });
    replaceList(result.entry);
    settingsView(false);
    $('shared-list-dialog').close();
    sharedListDocument = null;
    sharedListFingerprint = null;
    toast(
      'Shared list imported as a local copy. Compare with your Plex library to check availability.'
    );
  });

let officialPublication = null;
$('list-publish-official').onclick = (e) =>
  task(e.target, async () => {
    const result = await api('lists/revision', { list_id: active });
    officialPublication = { id: result.entry.id, revision: result.revision };
    $('official-publish-summary').textContent =
      `${result.entry.name} / ${result.entry.items.length} entries. ${result.entry.official_id ? 'Update its official version.' : 'Add a new Official List.'}`;
    $('official-publish-status').textContent = '';
    $('official-publish-dialog').showModal();
  });
$('official-publish-confirm').onclick = (e) =>
  task(e.target, async () => {
    if (!officialPublication) return;
    try {
      const result = await api('explore/official/publish', {
        list_id: officialPublication.id,
        revision: officialPublication.revision,
        confirmed: true,
      });
      $('official-publish-dialog').close();
      officialPublication = null;
      officialLoaded = false;
      replaceList(result.entry);
      await loadOfficialLists();
      selectListsTab('official');
      toast(
        `${result.report.name}: official version ${result.report.version}${result.report.changed ? ' published.' : ' is already up to date.'}`
      );
    } catch (error) {
      $('official-publish-status').textContent = error.message;
    }
  });

$('list-edit-playlist-poster').onchange = (e) =>
  task(e.target, async () => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type) || file.size > 10000000)
      throw Error('Choose a PNG, JPEG or WebP under 10 MB.');
    const image = await createImageBitmap(file);
    try {
      const canvas = document.createElement('canvas');
      canvas.width = canvas.height = 800;
      const side = Math.min(image.width, image.height);
      canvas
        .getContext('2d')
        .drawImage(
          image,
          (image.width - side) / 2,
          (image.height - side) / 2,
          side,
          side,
          0,
          0,
          800,
          800
        );
      listEditor.playlist_poster = canvas.toDataURL('image/jpeg', 0.85);
      updateEditorPoster();
    } finally {
      image.close();
    }
  });
$('list-clear-playlist-poster').onclick = () => {
  listEditor.playlist_poster = '';
  updateEditorPoster();
};
$('list-generate-playlist-poster').onclick = () => {
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = 800;
  const ctx = canvas.getContext('2d'),
    g = ctx.createLinearGradient(0, 0, 800, 800);
  g.addColorStop(0, '#254c66');
  g.addColorStop(1, '#101c30');
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, 800, 800);
  ctx.strokeStyle = '#6be0db';
  ctx.lineWidth = 3;
  ctx.strokeRect(40, 40, 720, 720);
  ctx.fillStyle = '#6be0db';
  ctx.font = '20px Segoe UI';
  ctx.fillText('LISTWEAVARR / PLAYLIST', 70, 110);
  ctx.fillStyle = '#f3f5f9';
  ctx.font = '48px Segoe UI';
  let line = '',
    y = 300;
  for (const word of ($('list-edit-name').value || 'My collection').split(/\s+/)) {
    if (ctx.measureText(line + ' ' + word).width > 650 && line) {
      ctx.fillText(line, 70, y);
      y += 62;
      line = word;
    } else line += (line ? ' ' : '') + word;
  }
  ctx.fillText(line, 70, y);
  listEditor.playlist_poster = canvas.toDataURL('image/jpeg', 0.9);
  updateEditorPoster();
};
