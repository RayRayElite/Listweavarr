// SPDX-License-Identifier: AGPL-3.0-only
/* Full Explore workspace. Saving picks uses the existing reviewed download workflow. */
let exploreHomeSequence = 0,
  exploreHomeLoaded = false,
  exploreListsSequence = 0,
  exploreListsLoaded = false;
const explorePicks = new Map();
function regionName(code) {
  try {
    return new Intl.DisplayNames(['en'], { type: 'region' }).of(code) || code;
  } catch {
    return code || 'Release region';
  }
}
function exploreFilters() {
  return {
    region: $('release-region').value || state.release_region || 'CA',
    type: $('explore-media').value || 'both',
    quality: $('explore-quality').value || '6.0',
    guilty: $('explore-cult').checked,
  };
}
function exploreCardDate(value) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value || '')) return '';
  const date = new Date(value + 'T12:00:00Z');
  return Number.isNaN(date.getTime())
    ? ''
    : date.toLocaleDateString(undefined, {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
        timeZone: 'UTC',
      });
}
function exploreTitleCard(row) {
  const chosen = explorePicks.has(row.key),
    canTrack = !row.in_library && (row.upcoming || row.availability?.status === 'theatrical');
  const tracking = (state.release_watchlist || []).some(
    (r) =>
      r.tmdb === String(row.tmdb) &&
      (r.type || 'movie') === row.type &&
      r.region === exploreFilters().region
  );
  const trackLabel = row.type === 'show' ? 'Track premiere' : 'Track home release';
  const date = row.upcoming
    ? exploreCardDate(row.release_date)
    : row.availability
      ? exploreCardDate(row.availability.home_date || row.availability.theatrical_date)
      : row.year || '';
  const reason = (row.reasons || []).slice(0, 6);
  const availability = row.in_library
    ? 'In Plex'
    : row.upcoming
      ? 'Upcoming'
      : row.availability?.status === 'home'
        ? row.availability.home_format || 'Available at home'
        : row.availability?.status === 'theatrical'
          ? 'Theatrical release'
          : '';
  return `<article class="related-card explore-card ${chosen ? 'is-picked' : ''}"><div class="explore-artwork"><button class="explore-poster" data-explore-title="${esc(row.tmdb)}" data-type="${esc(row.type)}" aria-label="Details for ${esc(row.title)}">${row.poster ? posterArt(row.poster, row) : `<span class="trakt-poster-placeholder">${esc(row.title.charAt(0))}</span>`}</button><label class="explore-pick" title="Select ${esc(row.title)} to save and compare"><input type="checkbox" data-explore-pick="${esc(row.key)}" aria-label="Select ${esc(row.title)} to save and compare" ${chosen ? 'checked' : ''}><span class="sr">Save this pick</span></label>${availability ? `<span class="explore-availability">${esc(availability)}</span>` : ''}</div><div class="explore-card-copy"><button class="title-link" data-explore-title="${esc(row.tmdb)}" data-type="${esc(row.type)}" title="${esc(row.title)}">${esc(row.title)}</button><div class="explore-card-meta"><span>${row.chart_rank ? '#' + Number(row.chart_rank) + ' / ' : ''}${row.type === 'show' ? 'TV' : 'Movie'}${date ? ' &middot; ' + esc(date) : ''}</span></div>${reason[0]?.startsWith('Because ') && !row.upcoming ? `<p class="explore-card-reason" title="${esc(reason[0])}">${esc(reason[0])}</p>` : ''}<div class="explore-card-footer"><span class="explore-rating">${row.upcoming && !preferredRating(row) ? '<span class="muted">Not yet rated</span>' : ratingWidget(row)}</span><details class="explore-card-menu"><summary aria-label="More options for ${esc(row.title)}" title="More options">&#8943;</summary><div class="explore-card-menu-content">${reason.length ? `<strong>Why this title?</strong><ul>${reason.map((value) => `<li>${esc(value)}</li>`).join('')}</ul>` : ''}${ignoreButton(row)}</div></details></div>${canTrack ? `<button class="release-track" data-track-release="${esc(row.tmdb)}" data-release-type="${esc(row.type)}" aria-label="${tracking ? 'Tracking release for' : trackLabel + ' for'} ${esc(row.title)}" title="${esc(trackLabel)}">${tracking ? '&#10003; Tracking release' : row.type === 'show' ? '+ Track premiere' : '+ Track release'}</button>` : ''}</div></article>`;
}

let exploreRows = [];
function exploreSelection() {
  const count = explorePicks.size;
  const pending = [...explorePicks.values()].filter(
    (row) => row.upcoming || row.availability?.status === 'theatrical'
  ).length;
  const available = count - pending;
  const destinations = [
    available ? available + ' to compare' : '',
    pending ? pending + ' to track' : '',
  ]
    .filter(Boolean)
    .join(' · ');
  $('explore-pick-count').textContent = count ? count + ' selected · ' + destinations : '';
  $('explore-save-picks').textContent =
    available && pending
      ? 'Save & track selected'
      : pending
        ? 'Track selected releases'
        : 'Save & compare selected';
  $('explore-save-picks').disabled = !count;
  $('explore-clear-picks').disabled = !count;
  const tray = $('explore-pick-count').closest?.('.explore-pick-bar');
  if (tray) tray.hidden = !count;
}

async function loadExploreHome(refresh = false) {
  if (exploreHomeLoaded && !refresh) return;
  const sequence = ++exploreHomeSequence,
    filters = exploreFilters();
  $('explore-home-status').textContent = 'Reading your library and finding better-rated picks…';
  $('explore-refresh').disabled = true;
  try {
    const data = await api('explore/home', { ...filters, refresh, defer_extra: true });
    if (sequence !== exploreHomeSequence) return;
    exploreHomeLoaded = true;
    exploreRows = data.rows.flatMap((r) => r.items);
    $('explore-personalization').textContent = data.library_connected
      ? `Inspired by ${Number(data.profile.count).toLocaleString()} library titles · ${Number(data.profile.watched).toLocaleString()} watched${data.profile.genres.length ? ' · ' + data.profile.genres.join(' / ') : ''}`
      : 'Connect Plex for personalized suggestions and library exclusions.';
    $('explore-quality-note').textContent = data.quality_note || '';
    window.refreshExploreHeading?.();
    $('explore-home-status').textContent = (data.warnings || []).join(' ');
    const rows = data.rows
      .filter((r) => r.items.length)
      .sort((a, b) => Number(/upcoming/i.test(a.id)) - Number(/upcoming/i.test(b.id)));
    $('explore-home-rows').innerHTML = rows.length
      ? rows
          .map(
            (row) =>
              `<section class="explore-shelf"><div class="section-heading"><div class="explore-shelf-heading"><h2><button class="shelf-title-link" data-explore-shelf="${esc(row.id)}">${esc(row.name)} <span aria-hidden="true">&#8594;</span></button></h2><span class="muted">${row.items.length} titles</span></div><details class="explore-shelf-about"><summary>About this row</summary><p class="explore-shelf-note">${esc(row.note)}${row.source_url ? ` <a href="${esc(row.source_url)}" target="_blank" rel="noopener noreferrer">Source</a>` : ''}</p></details></div><div class="related-preview explore-shelf-row" role="region" tabindex="0" aria-label="${esc(row.name)}">${row.items.map(exploreTitleCard).join('')}</div></section>`
          )
          .join('')
      : '<div class="empty"><h2>No new matches at this rating level.</h2><p>Try the other media type or a lower minimum rating. Connect Plex and TMDB under Connections if needed.</p></div>';
    exploreSelection();
    loadExploreExtras(sequence, refresh);
  } catch (e) {
    if (sequence === exploreHomeSequence) {
      exploreHomeLoaded = false;
      $('explore-home-status').textContent = e.message;
    }
  } finally {
    if (sequence === exploreHomeSequence) $('explore-refresh').disabled = false;
  }
}
const openExploreBeforeHome = traktOpen;
traktOpen = function () {
  openExploreBeforeHome();
  selectExploreTab(exploreTab);
};
$('trakt-nav').onclick = () => traktOpen();
$('explore-refresh').onclick = () => {
  closeExploreShelf();
  loadExploreHome(true);
};
for (const id of [
  'explore-media',
  'explore-quality',
  'explore-cult',
  'explore-indexers',
  'explore-downloads-missing',
])
  $(id).onchange = () => {
    closeExploreShelf();
    exploreHomeLoaded = false;
    loadExploreHome();
  };
$('explore-home-rows').onclick = (e) => {
  const shelf = e.target.closest('[data-explore-shelf]');
  if (shelf) {
    openExploreShelf(
      shelf.dataset.exploreShelf,
      shelf.textContent.replace(/\s*[^a-zA-Z0-9?]+$/, '').trim()
    );
    return;
  }
  const title = e.target.closest('[data-explore-title]');
  if (title) openExternalTitle(title.dataset.type, title.dataset.exploreTitle);
};
$('explore-home-rows').onchange = (e) => {
  const input = e.target.closest('[data-explore-pick]');
  if (!input) return;
  const row = exploreRows.find((r) => r.key === input.dataset.explorePick);
  if (!row) return;
  if (input.checked && explorePicks.size >= 100 && !explorePicks.has(row.key)) {
    input.checked = false;
    toast('Save up to 100 discoveries at a time.');
    return;
  }
  if (input.checked) explorePicks.set(row.key, row);
  else explorePicks.delete(row.key);
  input.closest?.('.explore-card')?.classList.toggle('is-picked', input.checked);
  exploreSelection();
};
$('explore-clear-picks').onclick = () => {
  explorePicks.clear();
  document.querySelectorAll('[data-explore-pick]').forEach((input) => {
    input.checked = false;
    input.closest?.('.explore-card')?.classList.remove('is-picked');
  });
  exploreSelection();
};
$('explore-save-picks').onclick = (e) =>
  task(e.target, async () => {
    if (!explorePicks.size) return;
    const result = await api('explore/route', {
      region: exploreFilters().region,
      items: [...explorePicks.values()].map((r) => ({ type: r.type, tmdb: r.tmdb })),
    });
    state.release_watchlist = result.items;
    explorePicks.clear();
    document.querySelectorAll('[data-explore-pick]').forEach((input) => {
      input.checked = false;
      input.closest?.('.explore-card')?.classList.remove('is-picked');
    });
    exploreSelection();
    renderReleaseWatchlist();
    if (result.entry) {
      replaceList(result.entry);
      settingsView(false);
    } else selectExploreTab('watchlist');
    toast(
      `${result.compared} titles saved for comparison; ${result.tracked} titles on your release watchlist.`
    );
  }).finally(exploreSelection);

function exploreListCards(lists) {
  return (
    lists
      .map(
        (l, index) =>
          `<article class="trakt-list-row"><span class="trakt-list-rank">${String(index + 1).padStart(2, '0')}</span><div class="trakt-list-copy"><span class="explore-provider">${esc(l.provider || 'Trakt')}</span><h3>${esc(l.name)}</h3><div class="trakt-list-meta"><span>${esc(l.owner || '')}</span><span>${esc(l.count ?? '—')} titles</span>${l.saved_id ? `<span>${Number(l.missing || 0)} missing / partial at last comparison</span>` : l.collection_id ? '<span>Movie collection</span>' : `<span>${Number(l.likes || 0).toLocaleString()} likes</span>`}</div><p class="trakt-list-description">${esc(traktDescription(l.description).slice(0, 180))}</p></div>${l.saved_id ? `<button class="secondary" data-explore-saved="${esc(l.saved_id)}">Open saved list &#8594;</button>` : l.collection_id ? `<button class="secondary" data-explore-collection="${esc(l.collection_id)}">Preview collection &#8594;</button>` : `<button class="secondary" data-trakt-preview="${esc(l.url)}">Preview list &#8594;</button>`}</article>`
      )
      .join('') ||
    '<p class="muted">No matching lists found. Try another source or paste a list URL below.</p>'
  );
}
async function exploreSearchLists() {
  if ($('trakt-query').value.trim()) $('trakt-list-mode').value = 'search';
  const sequence = ++exploreListsSequence;
  $('trakt-explore-status').textContent = 'Finding lists and collections…';
  const data = await api('explore/lists', {
    query: $('trakt-query').value,
    mode: $('trakt-list-mode').value,
    source: $('explore-list-source').value || 'all',
    page: traktPage,
  });
  if (sequence !== exploreListsSequence) return;
  $('trakt-list-results').innerHTML = exploreListCards(data.lists);
  $('trakt-page-prev').hidden = traktPage <= 1;
  $('trakt-page-next').hidden = !data.has_more;
  $('trakt-explore-status').textContent =
    `Page ${traktPage}${$('trakt-query').value.trim() ? ' - Results for ' + $('trakt-query').value.trim() : ''}. Trakt and TMDB are live results; Letterboxd, MDBList, IMDb and ChronoCanon results come from your saved lists. ${(data.warnings || []).join(' ')}`;
}
$('trakt-search-form').onsubmit = (e) => {
  e.preventDefault();
  traktPage = 1;
  task($('trakt-search-submit'), exploreSearchLists);
};
$('trakt-page-prev').onclick = (e) =>
  task(e.target, async () => {
    traktPage = Math.max(1, traktPage - 1);
    await exploreSearchLists();
  });
$('trakt-page-next').onclick = (e) =>
  task(e.target, async () => {
    traktPage++;
    await exploreSearchLists();
  });
async function explorePreview(body) {
  traktOpen();
  selectExploreTab('lists');
  $('trakt-preview').hidden = false;
  $('trakt-preview-title').textContent = 'Reading list…';
  $('trakt-preview-summary').textContent =
    'Loading the complete source and checking Plex. Large lists can take a moment.';
  $('trakt-preview-rows').innerHTML = '';
  $('trakt-preview-save').disabled = true;
  traktPreview = null;
  const result = await api('explore/preview', body);
  traktPreview = result;
  $('trakt-preview-title').textContent = result.name;
  $('trakt-preview-filter').value = 'all';
  traktRenderPreview();
  $('trakt-preview-save').disabled = false;
  $('trakt-preview').scrollIntoView?.({ behavior: 'smooth', block: 'start' });
}
$('trakt-list-results').onclick = (e) => {
  const saved = e.target.closest('[data-explore-saved]'),
    collection = e.target.closest('[data-explore-collection]'),
    preview = e.target.closest('[data-trakt-preview]');
  if (saved) {
    active = saved.dataset.exploreSaved;
    localStorage.setItem('reelcheck-active-list', active);
    selected.clear();
    render();
    settingsView(false);
    selectListsTab('mine');
  } else if (collection)
    task(collection, () => explorePreview({ collection_id: collection.dataset.exploreCollection }));
  else if (preview) task(preview, () => explorePreview({ url: preview.dataset.traktPreview }));
};
$('explore-url-form').onsubmit = (e) => {
  e.preventDefault();
  const url = $('explore-list-url').value.trim();
  if (url) task(e.submitter, () => explorePreview({ url }));
};
const saveExplorePreviewBeforeCollections = $('trakt-preview-save').onclick;
$('trakt-preview-save').onclick = (e) => {
  if (!traktPreview?.collection_id) return saveExplorePreviewBeforeCollections(e);
  return task(e.target, async () => {
    const result = await api('explore/save', { collection_id: traktPreview.collection_id });
    replaceList(result.entry);
    settingsView(false);
    toast('Collection saved and compared. Review missing titles before adding downloads.');
  });
};

function releaseDateLine(label, date) {
  const today = new Date().toISOString().slice(0, 10);
  return `<span><b>${label}</b> ${date ? esc(exploreCardDate(date)) + (date <= today ? (label === 'TV premiere' ? ' &middot; Premiered' : ' &middot; Released') : ' &middot; Expected') : 'Date not reported'}</span>`;
}
function renderReleaseWatchlist() {
  const entries = (state.release_watchlist || []).filter((r) => !isIgnored(r));
  const ready = entries.filter((r) => ['home', 'premiered'].includes(r.status) && !r.acknowledged);
  $('release-watch-count').textContent = entries.length ? `(${entries.length})` : '';
  $('release-notice').hidden = !ready.length;
  $('release-notice').innerHTML = ready.length
    ? `${ready.length} tracked title${ready.length === 1 ? ' has' : 's have'} reached a home release or TV premiere. <button class="person-link" data-open-release-watch>View release watchlist</button>`
    : '';
  $('release-watch-items').innerHTML =
    entries
      .map(
        (row) =>
          `<article class="release-watch-row"><button class="release-watch-art" data-release-title="${esc(row.tmdb)}" data-release-type="${esc(row.type || 'movie')}" aria-label="Details for ${esc(row.title)}">${row.poster ? `<img src="${esc(row.poster)}" alt="" loading="lazy">` : `<span>${esc(row.title.charAt(0))}</span>`}</button><div class="release-watch-copy"><button class="title-link" data-release-title="${esc(row.tmdb)}" data-release-type="${esc(row.type || 'movie')}">${esc(row.title)}</button><div class="release-date-lines">${row.type === 'show' ? releaseDateLine('TV premiere', row.premiere_date) : releaseDateLine('Theaters', row.theatrical_date) + releaseDateLine('Digital', row.digital_date || (row.home_format === 'Digital' ? row.home_date : null)) + releaseDateLine('DVD / disc', row.disc_date || (row.home_format === 'Disc' ? row.home_date : null))}</div><p class="muted">${esc(regionName(row.region))}${row.error ? ' · Check failed; previous dates retained' : ''}${row.manager_monitor ? ' · ' + esc(row.manager_monitor.message) : ''}</p></div><div class="release-watch-actions"><button class="secondary" data-release-monitor="${esc(row.id)}">${row.manager_monitor ? 'Review automatic download' : 'Set up automatic download'}</button>${['home', 'premiered'].includes(row.status) ? `<button class="secondary" data-release-save="${esc(row.id)}">Save & compare</button>${!row.acknowledged ? `<button class="text-action" data-release-ack="${esc(row.id)}">Dismiss notice</button>` : ''}` : ''}<button class="text-action" data-release-remove="${esc(row.id)}">Stop tracking</button></div></article>`
      )
      .join('') ||
    '<p class="muted">No titles tracked. Select upcoming picks in Discover to start a watchlist.</p>';
}

async function releaseAction(action, body = {}) {
  const data = await api('releases/' + action, body);
  state.release_watchlist = data.items;
  if (data.region) state.release_region = data.region;
  renderReleaseWatchlist();
  return data;
}
async function checkReleaseWatchlist() {
  if (!(state.release_watchlist || []).length) {
    renderReleaseWatchlist();
    return;
  }
  $('release-watch-status').textContent = 'Checking tracked releases...';
  try {
    await releaseAction('check');
    $('release-watch-status').textContent =
      'Release dates checked for the selected country. Dates can change; local streaming availability may differ.';
  } catch (e) {
    $('release-watch-status').textContent = e.message;
  }
}
$('release-region').onchange = (e) =>
  task(e.target, async () => {
    await releaseAction('region', { region: e.target.value });
    exploreHomeLoaded = false;
    if (!$('trakt-explore').hidden) await loadExploreHome();
  });
$('release-watch-check').onclick = (e) => task(e.target, checkReleaseWatchlist);
document.addEventListener?.(
  'click',
  (e) => {
    const track = e.target.closest('[data-track-release]'),
      open = e.target.closest('[data-open-release-watch]'),
      remove = e.target.closest('[data-release-remove]'),
      ack = e.target.closest('[data-release-ack]'),
      title = e.target.closest('[data-release-title]'),
      save = e.target.closest('[data-release-save]');
    if (track) {
      e.preventDefault();
      e.stopImmediatePropagation();
      task(track, async () => {
        await releaseAction('add', {
          tmdb: track.dataset.trackRelease,
          region: exploreFilters().region,
          type: track.dataset.releaseType || 'movie',
        });
        track.textContent = 'Tracking release';
        toast('Title added to your release watchlist.');
      });
    } else if (open) {
      traktOpen();
      selectExploreTab('watchlist');
    } else if (remove)
      task(remove, () => releaseAction('remove', { id: remove.dataset.releaseRemove }));
    else if (ack) task(ack, () => releaseAction('acknowledge', { id: ack.dataset.releaseAck }));
    else if (title)
      openExternalTitle(title.dataset.releaseType || 'movie', title.dataset.releaseTitle);
    else if (save)
      task(save, async () => {
        const row = state.release_watchlist.find((r) => r.id === save.dataset.releaseSave);
        if (!row) return;
        const data = await api('explore/save', {
          items: [{ type: row.type || 'movie', tmdb: row.tmdb }],
        });
        replaceList(data.entry);
        settingsView(false);
      });
  },
  true
);
const readyBeforeReleaseWatch = window.onListweavarrReady;
window.onListweavarrReady = () => {
  readyBeforeReleaseWatch?.();
  $('release-region').value = state.release_region || 'CA';
  renderReleaseWatchlist();
  checkReleaseWatchlist();
};
if (typeof setInterval !== 'undefined')
  setInterval(
    () => {
      if (state.csrf) checkReleaseWatchlist();
    },
    6 * 60 * 60 * 1000
  );

if (state.csrf) window.onListweavarrReady();

let exploreLanguageOptions = [
  { code: 'en', name: 'English' },
  { code: 'fr', name: 'French' },
  { code: 'es', name: 'Spanish' },
  { code: 'ja', name: 'Japanese' },
  { code: 'ko', name: 'Korean' },
  { code: 'de', name: 'German' },
  { code: 'zh', name: 'Mandarin' },
  { code: 'hi', name: 'Hindi' },
];
let exploreLanguageOptionsLoaded = false;
function renderExploreLanguages() {
  const selected = state.explore_languages || [];
  $('explore-language-all').checked = !selected.length;
  const options = [
    ...exploreLanguageOptions,
    ...selected
      .filter((code) => !exploreLanguageOptions.some((r) => r.code === code))
      .map((code) => ({ code, name: code })),
  ];
  $('explore-language-options').innerHTML = options
    .map(
      (r) =>
        `<label><input type="checkbox" data-explore-language="${esc(r.code)}" ${selected.includes(r.code) ? 'checked' : ''}> ${esc(r.name)}</label>`
    )
    .join('');
  $('explore-language-summary').textContent = selected.length
    ? selected.map((code) => options.find((r) => r.code === code)?.name || code).join(', ')
    : 'All languages';
}
$('explore-language-panel').ontoggle = async () => {
  if (!$('explore-language-panel').open || exploreLanguageOptionsLoaded) return;
  try {
    const data = await api('explore/languages', {});
    exploreLanguageOptions = data.languages;
    exploreLanguageOptionsLoaded = true;
    $('explore-language-status').textContent = '';
    renderExploreLanguages();
  } catch (e) {
    $('explore-language-status').textContent =
      'Full language list unavailable. Showing common languages; reopen to retry.';
  }
};
$('explore-language-options').onchange = (e) => {
  if (e.target.checked) $('explore-language-all').checked = false;
};
$('explore-language-all').onchange = (e) => {
  if (e.target.checked)
    document
      .querySelectorAll('[data-explore-language]')
      .forEach((input) => (input.checked = false));
};
$('explore-language-apply').onclick = (e) =>
  task(e.target, async () => {
    const languages = $('explore-language-all').checked
      ? []
      : [...document.querySelectorAll('[data-explore-language]:checked')].map(
          (input) => input.dataset.exploreLanguage
        );
    if (!languages.length && !$('explore-language-all').checked) {
      $('explore-language-status').textContent = 'Select a language or choose All languages.';
      return;
    }
    const data = await api('explore/preferences', { languages });
    state.explore_languages = data.languages;
    renderExploreLanguages();
    $('explore-language-status').textContent = languages.length
      ? 'Preferences saved. Titles with unknown original language are omitted.'
      : 'Preferences saved.';
    $('explore-language-panel').open = false;
    exploreHomeLoaded = false;
    if (!$('trakt-explore').hidden) await loadExploreHome();
  });
const readyBeforeLanguagePreferences = window.onListweavarrReady;
window.onListweavarrReady = () => {
  readyBeforeLanguagePreferences?.();
  renderExploreLanguages();
};
if (state.csrf) renderExploreLanguages();

// Explore sections retain their own content and state when switching tabs.
let exploreTab = 'discover';
function selectExploreTab(name) {
  if (!['discover', 'watchlist', 'lists'].includes(name)) return;
  exploreTab = name;
  setTabGroup('data-explore-tab', name, (key) => 'explore-' + key);
  $('trakt-preview').hidden = true;
  $('trakt-calendar').hidden = true;
  $('breadcrumb').textContent =
    'EXPLORE / ' +
    { discover: 'DISCOVER', watchlist: 'RELEASE WATCHLIST', lists: 'LISTS & WATCH ORDERS' }[name];
  if (name === 'discover') loadExploreHome();
  if (name === 'watchlist') renderReleaseWatchlist();
  if (name === 'lists' && !exploreListsLoaded) {
    exploreListsLoaded = true;
    exploreSearchLists().catch((e) => {
      exploreListsLoaded = false;
      $('trakt-explore-status').textContent = e.message;
    });
  }
}
bindTabKeys('data-explore-tab', selectExploreTab);
traktPreviewList = (url) => explorePreview({ url });
const calendarBeforeTabs = traktCalendar;
traktCalendar = async () => {
  traktOpen();
  selectExploreTab('watchlist');
  await calendarBeforeTabs();
  $('trakt-calendar').hidden = false;
};
let shelfContext = null,
  shelfSequence = 0;
function closeExploreShelf() {
  $('explore-extra-rows').hidden = false;
  ++shelfSequence;
  shelfContext = null;
  $('explore-shelf-page').hidden = true;
  $('explore-home-rows').hidden = false;
}
async function openExploreShelf(id, name) {
  $('explore-extra-rows').hidden = true;
  ++shelfSequence;
  shelfContext = {
    id,
    page: 1,
    filters: exploreFilters(),
    seen: new Set(),
    loading: false,
    hasMore: true,
  };
  $('explore-home-rows').hidden = true;
  $('explore-shelf-page').hidden = false;
  $('explore-shelf-title').textContent = name;
  $('explore-shelf-note').textContent =
    'Your library, language, ignore and rating filters still apply.';
  $('explore-shelf-items').innerHTML = '';
  scrollWorkspace();
  await loadExploreShelf();
}
async function loadExploreShelf() {
  const ctx = shelfContext,
    sequence = shelfSequence;
  if (!ctx || ctx.loading || !ctx.hasMore) return;
  ctx.loading = true;
  $('explore-shelf-more').disabled = true;
  $('explore-shelf-status').textContent = 'Finding more titles...';
  try {
    const data = await api('explore/home', {
      ...ctx.filters,
      shelf: ctx.id,
      page: ctx.page,
      missing_only: $('explore-downloads-missing').checked,
    });
    if (sequence !== shelfSequence || ctx !== shelfContext) return;
    const row = data.rows.find((r) => r.id === ctx.id),
      items = (row?.items || []).filter((item) => !ctx.seen.has(item.key));
    for (const item of items) ctx.seen.add(item.key);
    exploreRows.push(...items);
    $('explore-shelf-items').insertAdjacentHTML('beforeend', items.map(exploreTitleCard).join(''));
    if (row) $('explore-shelf-note').textContent = row.note;
    ctx.page++;
    ctx.hasMore = Boolean(data.has_more);
    $('explore-shelf-status').textContent =
      ctx.seen.size +
      ' titles' +
      (ctx.hasMore ? ' - scroll or load more.' : ' - all available matches loaded.') +
      (data.warnings?.length ? ' ' + data.warnings.join(' ') : '');
    $('explore-shelf-more').hidden = !ctx.hasMore;
  } catch (e) {
    if (sequence === shelfSequence) {
      $('explore-shelf-status').textContent = e.message + ' Use Load more to retry.';
      $('explore-shelf-more').hidden = false;
    }
  } finally {
    ctx.loading = false;
    if (sequence === shelfSequence) $('explore-shelf-more').disabled = false;
  }
}
$('explore-shelf-back').onclick = closeExploreShelf;
$('explore-shelf-more').onclick = loadExploreShelf;
$('explore-shelf-items').onclick = $('explore-home-rows').onclick;
$('explore-shelf-items').onchange = $('explore-home-rows').onchange;
if (typeof IntersectionObserver !== 'undefined') {
  const shelfObserver = new IntersectionObserver(
    (entries) => {
      if (
        entries.some((entry) => entry.isIntersecting) &&
        !$('trakt-explore').hidden &&
        exploreTab === 'discover' &&
        !$('explore-shelf-page').hidden
      )
        loadExploreShelf();
    },
    { rootMargin: '500px' }
  );
  shelfObserver.observe($('explore-shelf-sentinel'));
}

// Optional, slower sources are rendered independently after the main discovery shelves.
function optionalShelfMarkup(row) {
  return `<section class="explore-shelf"><div class="section-heading"><div class="explore-shelf-heading"><h2><button class="shelf-title-link" data-explore-shelf="${esc(row.id)}">${esc(row.name)} <span aria-hidden="true">&#8594;</span></button></h2><span class="muted">${row.items.length} titles</span></div><details class="explore-shelf-about"><summary>About this row</summary><p class="explore-shelf-note">${esc(row.note)}${row.source_url ? ` <a href="${esc(row.source_url)}" target="_blank" rel="noopener noreferrer">Source</a>` : ''}</p></details></div><div class="related-preview explore-shelf-row">${row.items.slice(0, 20).map(exploreTitleCard).join('')}</div>${!row.items.length ? '<p class="muted">No confident matches pass your current library and preference filters.</p>' : ''}</section>`;
}
async function loadExploreExtras(sequence, refresh = false) {
  const options = [
    ...($('explore-media').value !== 'show' ? ['downloads_movies'] : []),
    ...($('explore-media').value !== 'movie' ? ['downloads_tv'] : []),
    ...($('explore-cult').checked ? ['cult'] : []),
    ...($('explore-indexers').checked ? ['indexers'] : []),
  ];
  $('explore-extra-rows').innerHTML = options
    .map(
      (id) =>
        `<div id="extra-shelf-${id}"><p class="muted" role="status">Finding ${id === 'cult' ? 'personalized picks from your curated list' : id === 'downloads_movies' ? 'TorrentFreak movie chart' : id === 'downloads_tv' ? 'popular recent TV shows from EZTV' : 'popular titles on your indexers'}...</p></div>`
    )
    .join('');
  await Promise.all(
    options.map(async (shelf) => {
      try {
        const result = await api('explore/extra', {
          ...exploreFilters(),
          shelf,
          refresh,
          missing_only: $('explore-downloads-missing').checked,
        });
        if (sequence !== exploreHomeSequence) return;
        const row = result.rows[0];
        exploreRows.push(...row.items);
        $('extra-shelf-' + shelf).innerHTML =
          optionalShelfMarkup(row) +
          `<p class="muted explore-shelf-note">${esc((result.warnings || []).join(' '))}</p>`;
      } catch (e) {
        if (sequence === exploreHomeSequence)
          $('extra-shelf-' + shelf).innerHTML = `<p class="metadata-error">${esc(e.message)}</p>`;
      }
    })
  );
}
$('explore-extra-rows').onclick = $('explore-home-rows').onclick;
$('explore-extra-rows').onchange = $('explore-home-rows').onchange;
