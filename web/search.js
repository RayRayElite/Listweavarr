// SPDX-License-Identifier: AGPL-3.0-only
/* Local-first grouped search. Navigation is separate from request confirmation. */
let globalSearchSequence = 0,
  globalSearchTimer = null,
  globalSearchAbort = null;
let globalSearchLocal = null,
  globalSearchRemote = null,
  globalSearchPage = 1,
  globalSearchProviderPage = 1;
function searchBadgeMarkup(row) {
  const badges = [];
  if (row.in_plex) badges.push('In Plex (cached)');
  else if (row.parent_in_plex) badges.push('Parent show in Plex');
  else if (!row.library_known) badges.push('Library not checked');
  else if (!row.parent_in_plex) badges.push('No exact Plex match');
  if (row.request_status)
    badges.push('Request: ' + (REQUEST_LABELS[row.request_status] || row.request_status));
  if (row.tracked) badges.push('Release tracked');
  if (row.ignored) badges.push('Ignored');
  return badges.length
    ? `<div class="search-badges">${badges.map((badge) => `<span>${esc(badge)}</span>`).join('')}</div>`
    : '';
}
function searchMediaHref(row) {
  const item = row.item;
  if (
    ((item.type === 'movie' || item.type === 'show') && item.tmdb) ||
    (item.type === 'episode' && item.show_tmdb)
  )
    return mediaRoute(item);
  if (row.lists?.length)
    return (
      '#/lists/view/' +
      encodeURIComponent(row.lists[0].list_id) +
      '?item=' +
      encodeURIComponent(row.lists[0].item_id)
    );
  return row.plex_href || '';
}
function searchTitleCard(row) {
  const item = row.item,
    href = searchMediaHref(row),
    title = item.show_title ? item.show_title + ' / ' + item.title : item.title;
  const label =
    item.type === 'movie'
      ? 'Movie'
      : item.type === 'show'
        ? 'TV show'
        : item.type === 'season'
          ? 'Season ' + item.season
          : 'S' + item.season + ' / E' + item.episode;
  const external = href.startsWith('https:');
  const artwork = item.poster
    ? `<img src="${esc(item.poster)}" alt="" loading="lazy" referrerpolicy="no-referrer">`
    : `<span>${esc(title.charAt(0))}</span>`;
  return `<article class="search-title-card">${href ? `<a class="search-poster" href="${esc(href)}" ${external ? 'target="_blank" rel="noopener noreferrer"' : ''} aria-label="Details for ${esc(title)}">${artwork}</a>` : `<div class="search-poster">${artwork}</div>`}<strong>${href ? `<a href="${esc(href)}" ${external ? 'target="_blank" rel="noopener noreferrer"' : ''}>${esc(title)}</a>` : esc(title)}</strong><p class="muted">${esc(label)}${item.year ? ' / ' + esc(item.year) : ''}</p>${searchBadgeMarkup(row)}${row.lists?.length ? `<p class="search-origin">In ${row.lists.length} saved list${row.lists.length === 1 ? '' : 's'}</p>` : ''}</article>`;
}
function searchListsMarkup(lists) {
  return lists
    .map(
      (row) =>
        `<a class="search-list-card" href="${row.kind === 'official' ? '#/lists/official?find=' + encodeURIComponent(row.name) : '#/lists/view/' + encodeURIComponent(row.id) + (row.official_authoring ? '?origin=official' : '')}">${row.poster ? `<img src="${esc(row.poster)}" alt="" loading="lazy">` : '<span class="search-list-fallback" aria-hidden="true">&#9776;</span>'}<span><strong>${esc(row.name)}</strong><small>${row.kind === 'official' || row.official_authoring ? 'Official list' : 'Saved list'} / ${row.count} entries</small></span></a>`
    )
    .join('');
}
function drawGlobalSearch() {
  const local = globalSearchLocal;
  $('global-search-local').innerHTML = local
    ? `${local.lists.length ? `<section class="search-group"><h3>Lists <span>${local.lists_total}</span></h3><div class="search-list-results">${searchListsMarkup(local.lists)}</div></section>` : ''}${local.titles.length ? `<section class="search-group"><h3>Your library &amp; saved entries <span>${local.titles_total}</span></h3><div class="search-poster-row">${local.titles.map(searchTitleCard).join('')}</div></section>` : ''}<p class="footnote">${esc(local.library_note)}</p>${local.has_more ? '<button class="secondary" data-search-more="local">More workspace matches</button>' : ''}${!local.lists.length && !local.titles.length ? '<p class="muted">No workspace matches for this search.</p>' : ''}`
    : '';
  const remote = globalSearchRemote;
  $('global-search-remote').innerHTML = remote
    ? `${remote.items.length ? `<section class="search-group"><h3>TMDB titles</h3><div class="search-poster-row">${remote.items.map(searchTitleCard).join('')}</div></section>` : ''}${remote.people.length ? `<section class="search-group"><h3>People</h3><div class="search-poster-row">${remote.people.map((person) => `<article class="search-title-card"><a class="search-poster" href="#/projects/person/${encodeURIComponent(person.id)}" aria-label="Projects for ${esc(person.name)}">${person.poster ? `<img src="${esc(person.poster)}" alt="" loading="lazy" referrerpolicy="no-referrer">` : `<span>${esc(person.name.charAt(0))}</span>`}</a><strong><a href="#/projects/person/${encodeURIComponent(person.id)}">${esc(person.name)}</a></strong><p class="muted">${esc(person.department || 'Credits')}</p></article>`).join('')}</div></section>` : ''}<p class="footnote">${esc(remote.note || '')}</p>${remote.has_more ? '<button class="secondary" data-search-more="provider">More provider matches</button>' : ''}${!remote.items.length && !remote.people.length ? '<p class="muted">No provider matches on this page.</p>' : ''}`
    : '';
}
async function runGlobalSearch(allowShort = false) {
  clearTimeout(globalSearchTimer);
  globalSearchAbort?.abort();
  const query = $('global-search-query').value.trim(),
    seq = ++globalSearchSequence;
  globalSearchLocal = null;
  globalSearchRemote = null;
  globalSearchPage = 1;
  globalSearchProviderPage = 1;
  drawGlobalSearch();
  if (query.length < 2 && !(allowShort === true && query.length === 1)) {
    $('global-search-status').textContent =
      'Enter at least two characters, or press Search for a one-character title.';
    return;
  }
  const controller = typeof AbortController === 'function' ? new AbortController() : null;
  globalSearchAbort = controller;
  const body = { query, include_ignored: $('global-search-ignored').checked };
  $('global-search-status').textContent = 'Searching workspace...';
  let localWarning = '';
  const local = api('search/local', body, true, controller?.signal)
    .then((result) => {
      if (seq !== globalSearchSequence) return;
      globalSearchLocal = result;
      localWarning = (result.warnings || []).join(' ');
      drawGlobalSearch();
    })
    .catch((error) => {
      if (seq === globalSearchSequence && error.name !== 'AbortError') {
        localWarning = error.message;
      }
    });
  const remote = $('global-search-provider').checked
    ? api('search/provider', body, true, controller?.signal)
        .then((result) => {
          if (seq !== globalSearchSequence) return;
          globalSearchRemote = result;
          drawGlobalSearch();
        })
        .catch((error) => {
          if (seq === globalSearchSequence && error.name !== 'AbortError') {
            $('global-search-remote').innerHTML =
              `<p class="muted">Provider search unavailable. ${esc(error.message)}</p>`;
          }
        })
    : Promise.resolve();
  await Promise.all([local, remote]);
  if (seq === globalSearchSequence)
    $('global-search-status').textContent =
      localWarning || 'Search complete. Open a title or list to continue.';
}
function scheduleGlobalSearch() {
  clearTimeout(globalSearchTimer);
  globalSearchAbort?.abort();
  ++globalSearchSequence;
  globalSearchTimer = setTimeout(runGlobalSearch, 400);
}
function openGlobalSearch(value) {
  if (typeof value === 'string') $('global-search-query').value = value;
  $('global-search-dialog').showModal();
  $('global-search-query').focus();
  if ($('global-search-query').value.trim().length >= 1) runGlobalSearch(true);
}
$('global-search-open').onclick = () => openGlobalSearch();
$('global-search-close').onclick = () => $('global-search-dialog').close();
$('global-search-dialog').addEventListener('close', () => {
  globalSearchAbort?.abort();
  clearTimeout(globalSearchTimer);
  ++globalSearchSequence;
});
$('global-search-query').oninput = scheduleGlobalSearch;
$('global-search-form').onsubmit = (event) => {
  event.preventDefault();
  runGlobalSearch(true);
};
$('global-search-provider').onchange = runGlobalSearch;
$('global-search-ignored').onchange = runGlobalSearch;
$('global-search-index').onclick = (event) =>
  task(event.target, async () => {
    const result = await api('search/index', {});
    $('global-search-status').textContent = result.count + ' library titles indexed.';
    if ($('global-search-query').value.trim().length >= 2) await runGlobalSearch();
  });
$('global-search-dialog').addEventListener('click', async (event) => {
  if (
    event.target.closest('a[href]') &&
    !event.ctrlKey &&
    !event.metaKey &&
    !event.shiftKey &&
    event.button === 0
  )
    $('global-search-dialog').close();
  const button = event.target.closest('[data-search-more]');
  if (!button) return;
  await task(button, async () => {
    const local = button.dataset.searchMore === 'local',
      seq = globalSearchSequence;
    const page = (local ? globalSearchPage : globalSearchProviderPage) + 1;
    const result = await api(
      'search/' + (local ? 'local' : 'provider'),
      {
        query: $('global-search-query').value.trim(),
        page,
        include_ignored: $('global-search-ignored').checked,
      },
      true,
      globalSearchAbort?.signal
    );
    if (seq !== globalSearchSequence) return;
    if (local) {
      globalSearchPage = page;
      globalSearchLocal = {
        ...result,
        titles: [...globalSearchLocal.titles, ...result.titles],
        lists: [...globalSearchLocal.lists, ...result.lists],
      };
    } else {
      globalSearchProviderPage = page;
      globalSearchRemote = {
        ...result,
        items: [...globalSearchRemote.items, ...result.items],
        people: [...globalSearchRemote.people, ...result.people],
      };
    }
    drawGlobalSearch();
  });
});
document.addEventListener?.('keydown', (event) => {
  if (!(event.ctrlKey || event.metaKey) || event.key.toLowerCase() !== 'k') return;
  event.preventDefault();
  if (document.querySelector('dialog[open]:not(#global-search-dialog)')) return;
  openGlobalSearch();
});
