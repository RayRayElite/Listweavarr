// SPDX-License-Identifier: AGPL-3.0-only
/* Cache-only totals never block navigation or start provider work implicitly. */
let runtimeSequence = 0,
  runtimeTimer = null,
  runtimeKey = '',
  runtimeBusy = false,
  runtimeCache = new Map();
function watchLengthLabel(data) {
  if (!data.known_units && !data.estimated_units) return 'Watch length unavailable';
  const value = Math.round(data.minutes),
    days = Math.floor(value / 1440),
    hours = Math.floor((value % 1440) / 60),
    mins = value % 60;
  return `${data.complete ? (data.estimated ? 'Estimated watch length' : 'Watch length') : data.estimated ? 'Partial estimated watch length' : 'Known watch length'}: ${days ? days + 'd ' : ''}${hours ? hours + 'h ' : ''}${mins || (!days && !hours) ? mins + 'm' : ''}${data.unknown_entries ? ` + ${data.unknown_entries} ${data.unknown_entries === 1 ? 'entry' : 'entries'} without complete runtime` : ''}`;
}
function paintWatchLength(data) {
  $('list-runtime-summary').textContent = watchLengthLabel(data);
  $('list-runtime-summary').title =
    data.note +
    (data.estimated_units
      ? ` ${data.estimated_units} episodes use a series-average estimate.`
      : '');
  $('list-runtime-fill').hidden = !data.missing_paths || !state.settings.tmdb?.configured;
}
async function loadWatchLength(fill = false) {
  const entry = current();
  if (!entry || $('list-detail').hidden) return;
  const order = selectedCuratedOrder(),
    key = JSON.stringify([
      entry.id,
      entry.updated_at,
      order,
      curatedListItems(entry).map((row) => row.id),
    ]);
  if (!fill && runtimeBusy && runtimeKey === key) return;
  const seq = ++runtimeSequence;
  runtimeKey = key;
  const cached = runtimeCache.get(key);
  if (!fill && cached && Date.now() - cached.at < 60000) {
    runtimeBusy = false;
    return paintWatchLength(cached.data);
  }
  runtimeBusy = true;
  if (!cached) $('list-runtime-summary').textContent = 'Calculating watch length...';
  $('list-runtime-fill').disabled = true;
  if (fill)
    $('list-runtime-summary').textContent = 'Filling runtime gaps (up to 20 metadata requests)...';
  try {
    const data = await api('lists/runtime', {
      list_id: entry.id,
      watch_order: order || null,
      fill,
    });
    if (seq !== runtimeSequence || current()?.id !== entry.id) return;
    runtimeCache.set(key, { at: Date.now(), data });
    if (runtimeCache.size > 20) runtimeCache.delete(runtimeCache.keys().next().value);
    paintWatchLength(data);
    if (data.failed)
      $('list-runtime-summary').textContent +=
        ` / ${data.failed} metadata requests failed; retry later`;
  } catch (error) {
    if (seq === runtimeSequence)
      $('list-runtime-summary').textContent = cached
        ? watchLengthLabel(cached.data)
        : error.message;
  } finally {
    if (seq === runtimeSequence) {
      runtimeBusy = false;
      $('list-runtime-fill').disabled = false;
    }
  }
}
const renderBeforeWatchLength = render;
render = function () {
  renderBeforeWatchLength();
  clearTimeout(runtimeTimer);
  if (current()) runtimeTimer = setTimeout(() => loadWatchLength(), 120);
};
$('list-runtime-fill').onclick = () => loadWatchLength(true);
