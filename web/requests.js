// SPDX-License-Identifier: AGPL-3.0-only
/* Optional connections and persistent, explicitly reviewed requests. */
let requestRows = [],
  requestNotices = [],
  requestReadSequence = 0,
  requestRetry = null;
const renderConnectionsBeforeIndexer = renderArr;
renderArr = function () {
  renderConnectionsBeforeIndexer();
  const cfg = state.settings.prowlarr || {};
  $('connection-fields').insertAdjacentHTML(
    'beforeend',
    `<div class="connection"><h2>Prowlarr - optional discovery</h2><p class="muted">Adds a read-only Popular on your indexers row. Uses exact title IDs and observed seed counts; browse support varies by indexer. Turn the row on in Explore after connecting.</p><div class="fields"><label>Server address<input type="url" name="prowlarr-url" value="${esc(cfg.url || '')}" placeholder="http://192.168.1.20:9696"></label><label>API key<input type="password" name="prowlarr-key" autocomplete="new-password" placeholder="${cfg.configured ? 'Saved - leave blank to keep' : 'Prowlarr API key'}"></label></div><button type="button" class="secondary" data-test="prowlarr">Test connection</button></div>`
  );
};
const indexerControlChange = $('explore-indexers').onchange;
$('explore-indexers').checked = localStorage.getItem('reelcheck-indexer-discovery') === 'true';
$('explore-indexers').onchange = (e) => {
  if (e.target.checked && !state.settings.prowlarr?.configured) {
    e.target.checked = false;
    toast('Connect optional Prowlarr under Settings / Connections first.');
    settingsView(true);
    selectSettingsTab('connections');
    return;
  }
  localStorage.setItem('reelcheck-indexer-discovery', String(e.target.checked));
  indexerControlChange(e);
};
const REQUEST_LABELS = {
  pending: 'Awaiting confirmation',
  awaiting_approval: 'Awaiting approval',
  declined: 'Declined',
  cancelled: 'Cancelled',
  requested: 'Requested',
  monitored: 'Monitoring',
  downloading: 'Downloading',
  importing: 'Waiting for import',
  attention: 'Needs attention',
  imported: 'Imported - checking Plex',
  available: 'Available in Plex',
  failed: 'Failed',
  unavailable: 'Status unavailable',
};
function requestPriority(row) {
  return [
    'attention',
    'failed',
    'awaiting_approval',
    'pending',
    'unavailable',
    'importing',
    'downloading',
    'requested',
    'imported',
    'monitored',
    'available',
    'declined',
    'cancelled',
  ].indexOf(row.status);
}
function requestArtwork(row) {
  const item = row.item,
    cached = metadataCache.get(metadataKey(item));
  const watched = (state.release_watchlist || []).find(
    (r) =>
      String(r.tmdb) === String(item.tmdb || item.show_tmdb) &&
      r.type === (item.type === 'movie' ? 'movie' : 'show')
  );
  const poster = item.poster || cached?.poster || watched?.poster;
  return `<button class="request-artwork" data-request-title="${esc(row.id)}" aria-label="Details for ${esc(item.title)}">${
    poster
      ? `<img src="${esc(poster)}" alt="" loading="lazy">`
      : `<span aria-hidden="true">${esc(
          item.title
            .split(/\s+/)
            .slice(0, 2)
            .map((word) => word[0])
            .join('')
        )}</span>`
  }</button>`;
}
function drawRequests() {
  const query = $('requests-search').value.trim().toLowerCase(),
    filter = $('requests-filter').value;
  const visible = requestRows
    .filter(
      (r) =>
        (filter ? r.status === filter : !['declined', 'cancelled'].includes(r.status)) &&
        (!query || r.item.title.toLowerCase().includes(query))
    )
    .sort(
      (a, b) =>
        requestPriority(a) - requestPriority(b) ||
        (b.updated_at || b.created_at) - (a.updated_at || a.created_at)
    );
  const needs = requestRows.filter((r) =>
    ['attention', 'failed', 'unavailable'].includes(r.status)
  ).length;
  const activeCount = requestRows.filter((r) =>
    ['downloading', 'importing', 'requested', 'imported', 'monitored'].includes(r.status)
  ).length;
  const available = requestRows.filter((r) => r.status === 'available').length;
  const overview = visible.length
    ? `<div class="request-overview" aria-label="Request overview"><span><strong>${needs}</strong> need attention</span><span><strong>${activeCount}</strong> in progress</span><span><strong>${available}</strong> available in Plex</span></div>`
    : '';
  $('requests-items').innerHTML =
    overview +
    (visible
      .map(
        (row) =>
          `<article class="request-history-row" data-status="${esc(row.status)}">${requestArtwork(row)}<div class="request-history-copy"><span class="request-state">${esc(REQUEST_LABELS[row.status] || row.status)}${row.percent != null ? ' &middot; ' + esc(row.percent) + '%' : ''}</span><button class="title-link" data-request-title="${esc(row.id)}">${esc(row.item.title)}</button><p class="muted">${row.item.type === 'movie' ? 'Movie' : row.item.type === 'episode' ? 'Episode' : 'TV'}${row.item.year ? ' &middot; ' + esc(row.item.year) : ''}${row.item.season != null ? ' &middot; S' + esc(row.item.season) : ''}${row.item.episode != null ? ' E' + esc(row.item.episode) : ''} &middot; ${esc(row.service)} &middot; ${row.tier === '4k' ? '4K' : 'Standard'}${row.mode === 'monitor' ? ' &middot; Release monitoring' : ''}</p><p class="request-message">${esc(row.message === (REQUEST_LABELS[row.status] || row.status) ? '' : row.message || '')}${row.check_warning ? ' &middot; ' + esc(row.check_warning) : ''}</p><details><summary>Request history</summary>${(
            row.events || []
          )
            .slice()
            .reverse()
            .map(
              (event) =>
                `<p class="muted">${esc(new Date(event.at * 1000).toLocaleString())} &middot; ${esc(event.message)}</p>`
            )
            .join(
              ''
            )}</details></div><div class="request-history-actions">${!['available', 'declined', 'cancelled'].includes(row.status) ? `<button class="${['attention', 'failed', 'pending', 'awaiting_approval'].includes(row.status) ? 'primary' : 'secondary'}" data-request-retry="${esc(row.id)}">${row.status === 'awaiting_approval' ? 'Review & approve' : row.status === 'pending' ? 'Review request' : 'Review / retry'}</button>${['pending', 'awaiting_approval'].includes(row.status) ? `<button class="text-action" data-request-decision="${esc(row.id)}">${row.status === 'pending' ? 'Cancel draft' : 'Decline'}</button>` : ''}` : ''}</div></article>`
      )
      .join('') ||
      '<div class="empty"><h2>No matching requests.</h2><p>Requests made from lists and release monitoring will appear here.</p></div>');
  const unread = requestNotices.filter((n) => !n.read);
  $('requests-notice').hidden = !unread.length;
  $('requests-notice').innerHTML = unread.length
    ? `${unread.length} requested title${unread.length === 1 ? ' is' : 's are'} now in Plex. <button class="person-link" data-open-requests>View requests</button>`
    : '';
}
async function readRequests(refresh = false, force = false) {
  const seq = ++requestReadSequence;
  try {
    const result = await api('requests/' + (refresh ? 'refresh' : 'list'), { force });
    if (seq !== requestReadSequence) return;
    requestRows = result.items || [];
    requestNotices = result.notifications || [];
    drawRequests();
    $('requests-status').textContent =
      (result.warnings || []).join(' ') +
      (result.checked_at
        ? ' Status checked ' + new Date(result.checked_at * 1000).toLocaleTimeString() + '.'
        : '');
  } catch (e) {
    if (seq === requestReadSequence) $('requests-status').textContent = e.message;
  }
}
function openRequests() {
  openWorkspacePanel('requests-page');
  $('library-nav').classList.toggle('active', false);
  $('settings-nav').classList.toggle('active', false);
  $('breadcrumb').textContent = 'REQUESTS';
  drawRequests();
  readRequests();
}
$('requests-nav').onclick = openRequests;
$('requests-notice').onclick = (e) => {
  if (e.target.closest('[data-open-requests]')) openRequests();
};
$('requests-search').oninput = drawRequests;
$('requests-filter').onchange = drawRequests;
$('requests-refresh').onclick = (e) => task(e.target, () => readRequests(true, true));
$('requests-read').onclick = (e) =>
  task(e.target, async () => {
    const result = await api('requests/acknowledge', {});
    requestNotices = result.notifications;
    drawRequests();
  });
$('requests-items').onclick = (e) => {
  const title = e.target.closest('[data-request-title]'),
    retry = e.target.closest('[data-request-retry]');
  if (title) {
    const row = requestRows.find((r) => r.id === title.dataset.requestTitle);
    const item = row.item;
    openExternalTitle(
      item.type === 'movie' ? 'movie' : item.type === 'episode' ? 'episode' : 'show',
      item.type === 'movie' || item.type === 'show' ? item.tmdb : item.show_tmdb,
      item.season,
      item.episode
    );
  }
  if (retry) task(retry, () => reviewRequestRetry(retry.dataset.requestRetry));
};
async function reviewRequestRetry(id) {
  const row = requestRows.find((r) => r.id === id);
  if (!row) return;
  const result = await api('options', {
      services: [row.service],
      routes: { [row.service]: row.route || 'primary' },
    }),
    options = result[row.service];
  requestRetry = row;
  $('request-retry-heading').textContent =
    (row.mode === 'monitor' ? 'Monitor ' : 'Request ') + row.item.title;
  $('request-retry-scope').textContent =
    row.mode === 'monitor'
      ? 'Enable future-release monitoring; no immediate search. Whole-show monitoring includes future seasons and excludes specials.'
      : 'Search only this saved ' +
        row.item.type +
        ' scope. Plex and the manager are checked again to avoid duplicate downloads.';
  $('request-retry-options').innerHTML =
    `<p class="muted">${esc(options.routes?.find((r) => r.id === (row.route || 'primary'))?.name || row.service)} &middot; ${row.tier === '4k' ? '4K' : 'Standard'}</p><label>Quality profile<select id="retry-profile">${options.profiles.map((p) => `<option value="${p.id}">${esc(p.name)}</option>`).join('')}</select></label><label>Destination<select id="retry-root">${options.roots.map((r) => `<option value="${esc(r.path)}">${esc(r.path)}</option>`).join('')}</select></label>`;
  if (options.defaults?.profile) $('retry-profile').value = options.defaults.profile;
  if (options.defaults?.root) $('retry-root').value = options.defaults.root;
  $('request-retry-status').textContent = '';
  $('request-retry-confirm').hidden = false;
  $('request-retry-confirm').textContent =
    row.status === 'awaiting_approval' ? 'Approve & submit' : 'Confirm request';
  $('request-retry-dialog').showModal();
}
$('request-retry-confirm').onclick = (e) =>
  task(e.target, async () => {
    const result = await api('requests/retry', {
      id: requestRetry.id,
      profile: $('retry-profile').value,
      root: $('retry-root').value,
      confirmed: true,
      approved: requestRetry.status === 'awaiting_approval',
    });
    requestRows = result.items;
    requestNotices = result.notifications;
    drawRequests();
    const row = requestRows.find((r) => r.id === requestRetry.id);
    $('request-retry-status').textContent = row?.message || 'Request processed.';
    $('request-retry-confirm').hidden = row?.status !== 'failed';
    if (
      row &&
      !['failed', 'pending', 'awaiting_approval', 'unavailable', 'attention'].includes(row.status)
    ) {
      $('request-retry-dialog').close();
      toast(row.message || 'Request submitted.');
    }
  });
// Opening a review records pending intent; confirmation remains an explicit separate action.
const reviewBeforeLedger = $('review').onclick;
$('review').onclick = async (e) => {
  if (busy) return;
  await reviewBeforeLedger(e);
  if ($('review-dialog').open) {
    try {
      await api('requests/pending', { list_id: active, ids: [...selected] });
    } catch (error) {
      toast('The review is ready, but pending history could not be saved: ' + error.message);
    }
  }
};
const submitBeforeLedger = $('submit-requests').onclick;
$('submit-requests').onclick = async (e) => {
  await submitBeforeLedger(e);
  readRequests();
};
const readyBeforeRequests = window.onListweavarrReady;
window.onListweavarrReady = () => {
  readyBeforeRequests?.();
  readRequests().then(() => readRequests(true));
};
if (typeof setInterval !== 'undefined')
  setInterval(() => {
    if (
      state.csrf &&
      requestRows.some(
        (r) =>
          ![
            'pending',
            'awaiting_approval',
            'declined',
            'failed',
            'available',
            'cancelled',
          ].includes(r.status)
      )
    )
      readRequests(true);
  }, 90000);

$('activity-items').addEventListener('click', (e) => {
  const button = e.target.closest('[data-request-title]');
  if (!button) return;
  const item = requestRows.find((r) => r.id === button.dataset.requestTitle)?.item;
  if (item)
    openExternalTitle(
      item.type === 'movie' ? 'movie' : item.type === 'episode' ? 'episode' : 'show',
      item.type === 'movie' || item.type === 'show' ? item.tmdb : item.show_tmdb,
      item.season,
      item.episode
    );
});
