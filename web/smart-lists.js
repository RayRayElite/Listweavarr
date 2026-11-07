// SPDX-License-Identifier: AGPL-3.0-only
/* One compact entry point; recipes create reviewed snapshots, not automation. */
let smartReadyProposal = null,
  smartReadySequence = 0;
const openFavoritesBeforeRecipes = $('favorites-open').onclick;
$('favorites-open').textContent = 'Smart lists';
$('favorites-open').onclick = () => {
  smartReadyProposal = null;
  ++smartReadySequence;
  $('smart-ready-options').hidden = true;
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
$('smart-ready').onclick = () => {
  $('smart-ready-options').hidden = false;
};
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
    const body = { sources, include_unknown: $('smart-ready-unknown').checked };
    $('smart-ready-status').textContent = 'Reading saved availability and watched checks...';
    try {
      const data = await api('smart-lists/preview', body);
      if (sequence !== smartReadySequence) return;
      smartReadyProposal = { ...body, token: data.token };
      $('smart-ready-status').textContent =
        `${data.items.length} ready. ${data.note} Excluded: ${data.skipped.watched} watched / ${data.skipped.unknown} unknown watch status / ${data.skipped.unavailable} unavailable / ${data.skipped.scope} show or season scopes / ${data.skipped.ignored} ignored / ${data.skipped.duplicate} duplicates. Refresh watched progress in a source list if its history is unknown.`;
      $('smart-ready-results').innerHTML = data.items
        .slice(0, 60)
        .map(
          (row) =>
            `<div><strong>${esc(row.show_title ? row.show_title + ' / ' + row.title : row.title)}</strong><small>${esc(row.type)}${row.type === 'episode' ? ` / S${esc(row.season)} E${esc(row.episode)}` : ''}</small></div>`
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
        'Ready snapshot created. Compare with Plex to verify current availability before publishing.'
      );
    } catch (error) {
      $('smart-ready-status').textContent = error.message;
    }
  });
