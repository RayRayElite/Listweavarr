// SPDX-License-Identifier: AGPL-3.0-only
/* One compact entry point; recipes create reviewed snapshots, not automation. */
let smartReadyProposal = null,
  smartReadySequence = 0,
  smartReadyKind = 'ready';
const openFavoritesBeforeRecipes = $('favorites-open').onclick;
$('favorites-open').textContent = 'Smart lists';
$('favorites-open').onclick = () => {
  smartReadyProposal = null;
  ++smartReadySequence;
  $('smart-ready-options').hidden = true;
  smartReadyKind = 'ready';
  $('smart-personal-refresh').checked = false;
  $('smart-ready-results').innerHTML = '';
  $('smart-ready-status').textContent = '';
  $('smart-ready-create').hidden = true;
  $('smart-ready-unknown').checked = false;
  $('smart-ready-sources').innerHTML = state.lists
    .map(
      (entry) =>
        `<label class="preference-check"><input type="checkbox" data-smart-source="${esc(entry.id)}"><span>${esc(entry.name)} <small>${entry.items.length} entries</small></span></label>`
    )
    .join('');
  $('smart-lists-dialog').showModal();
};
$('smart-favorites').onclick = () => {
  $('smart-lists-dialog').close();
  openFavoritesBeforeRecipes();
};
function chooseSmartRecipe(kind) {
  smartReadyKind = kind;
  invalidateSmartReady();
  $('smart-ready-options').hidden = false;
  $('smart-personal-options').hidden = kind === 'ready';
  const unknownLabel = $('smart-ready-unknown').closest?.('label');
  if (unknownLabel) unknownLabel.hidden = kind !== 'ready';
  $('smart-source-heading').textContent =
    kind === 'comfort'
      ? 'Optional: restrict to source lists'
      : kind === 'catchup'
        ? 'Choose lists containing shows to follow'
        : 'Choose source lists';
  $('smart-ready-preview').textContent = {
    ready: 'Preview Ready list',
    catchup: 'Preview catch-up episodes',
    comfort: 'Preview comfort rotation',
  }[kind];
  $('smart-ready-status').textContent =
    kind === 'catchup'
      ? 'Checks Plex episodes for up to eight shows with a cached season return within 180 days. Refresh title/calendar metadata if return dates are missing.'
      : kind === 'comfort'
        ? 'Uses your personal Plex ratings and repeat-play counts. Leave sources empty to use your library.'
        : '';
}
$('smart-ready').onclick = () => chooseSmartRecipe('ready');
$('smart-catchup').onclick = () => chooseSmartRecipe('catchup');
$('smart-comfort').onclick = () => chooseSmartRecipe('comfort');
$('smart-personal-limit').onchange = invalidateSmartReady;
$('smart-personal-refresh').onchange = invalidateSmartReady;
function invalidateSmartReady() {
  ++smartReadySequence;
  smartReadyProposal = null;
  $('smart-ready-create').hidden = true;
  $('smart-ready-results').innerHTML = '';
}
$('smart-ready-sources').onchange = invalidateSmartReady;
$('smart-ready-unknown').onchange = invalidateSmartReady;
$('smart-ready-preview').onclick = (event) =>
  task(event.target, async () => {
    invalidateSmartReady();
    const sequence = smartReadySequence;
    const sources = [...document.querySelectorAll('[data-smart-source]:checked')].map(
      (input) => input.dataset.smartSource
    );
    const body =
      smartReadyKind === 'ready'
        ? { sources, include_unknown: $('smart-ready-unknown').checked }
        : {
            sources,
            kind: smartReadyKind,
            limit: Number($('smart-personal-limit').value),
            refresh: $('smart-personal-refresh').checked,
          };
    $('smart-ready-status').textContent =
      smartReadyKind === 'ready'
        ? 'Reading saved availability and watched checks...'
        : 'Reading your Plex library and personal history...';
    try {
      const data = await api('smart-lists/preview', body);
      if (sequence !== smartReadySequence) return;
      smartReadyProposal = { ...body, token: data.token };
      $('smart-ready-status').textContent =
        `${data.items.length} entries (first 60 shown). ${data.note}` +
        (smartReadyKind === 'ready'
          ? ` Excluded: ${data.skipped.watched} watched / ${data.skipped.unknown} unknown watch status / ${data.skipped.unavailable} unavailable / ${data.skipped.scope} show or season scopes / ${data.skipped.ignored} ignored / ${data.skipped.duplicate} duplicates. Refresh watched progress in a source list if its history is unknown.`
          : '');
      $('smart-ready-results').innerHTML = data.items
        .slice(0, 60)
        .map(
          (row) =>
            `<div><strong>${esc(row.show_title ? row.show_title + ' / ' + row.title : row.title)}</strong><small>${esc(row.reason || row.type)}${row.type === 'episode' ? ` / S${esc(row.season)} E${esc(row.episode)}` : ''}</small></div>`
        )
        .join('');
      $('smart-ready-create').hidden = false;
      $('smart-ready-create').disabled = !data.items.length;
    } catch (error) {
      if (sequence === smartReadySequence) $('smart-ready-status').textContent = error.message;
    }
  });
$('smart-ready-create').onclick = (event) =>
  task(event.target, async () => {
    if (!smartReadyProposal) return;
    try {
      const result = await api('smart-lists/create', { ...smartReadyProposal, confirmed: true });
      $('smart-lists-dialog').close();
      replaceList(result.entry);
      toast(
        'Smart list created. Compare with Plex to verify current availability before publishing.'
      );
    } catch (error) {
      $('smart-ready-status').textContent = error.message;
    }
  });
