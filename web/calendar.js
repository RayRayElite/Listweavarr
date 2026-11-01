// SPDX-License-Identifier: AGPL-3.0-only
/* Cached-first release browsing. Filters and navigation never request media. */
const calendarMonths = new Map();
let calendarSequence = 0,
  calendarData = null,
  calendarSelectedDay = null;
const CALENDAR_KINDS = {
  theatrical: 'In theaters',
  digital: 'Digital release',
  disc: 'Disc release',
  premiere: 'TV premiere',
  episode: 'Episode airs',
  expected: 'Expected movie release',
};
function currentCalendarMonth() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
}
function calendarDateLabel(day, options = { weekday: 'long', month: 'long', day: 'numeric' }) {
  return new Date(day + 'T12:00:00').toLocaleDateString(undefined, options);
}
function calendarFilteredItems() {
  return (calendarData?.items || []).filter(
    (row) =>
      ($('calendar-source').value === 'all' ||
        row.sources.some((source) => source.type === $('calendar-source').value)) &&
      ($('calendar-media').value === 'all' ||
        (row.item.type === 'movie' ? 'movie' : 'tv') === $('calendar-media').value)
  );
}
function calendarCard(row) {
  const item = row.item,
    title = item.show_title || item.title;
  const sourceLinks = row.sources
    .map((source) =>
      source.list_id
        ? `<a href="#/lists/view/${encodeURIComponent(source.list_id)}">${esc(source.name)}</a>`
        : source.person_id
          ? `<a href="#/projects/person/${encodeURIComponent(source.person_id)}">${esc(source.name)}</a>`
          : `<span>${esc(source.name)}</span>`
    )
    .join('');
  const spoilerSafe = state.companion_preferences?.spoiler_safe && item.type === 'episode';
  return `<article class="calendar-card"><a class="calendar-art" href="${esc(mediaRoute(item))}" aria-label="Details for ${esc(title)}">${item.poster ? `<img src="${esc(item.poster)}" alt="" loading="lazy" referrerpolicy="no-referrer">` : `<span>${esc(title.charAt(0))}</span>`}</a><div class="calendar-card-copy"><p class="eyebrow" data-release-kind="${esc(row.release_kind)}">${esc(CALENDAR_KINDS[row.release_kind] || 'Release')}${row.region ? ' / ' + esc(row.region) : ''}</p><h3><a href="${esc(mediaRoute(item))}">${esc(title)}</a></h3>${item.type === 'episode' ? `<p>${spoilerSafe ? 'Episode details hidden' : esc(item.title)} <span class="muted">S${esc(item.season)} / E${esc(item.episode)}</span></p>` : ''}<time datetime="${esc(row.date)}">${esc(calendarDateLabel(row.date))}</time>${row.note ? `<p class="muted">${esc(row.note)}</p>` : ''}<div class="calendar-sources">${sourceLinks}</div></div></article>`;
}
function drawReleaseCalendar() {
  if (!calendarData) return;
  const items = calendarFilteredItems(),
    monthMode = $('calendar-view').value === 'month';
  $('calendar-grid').hidden = !monthMode;
  let shown = items;
  if (monthMode) {
    const month = calendarData.month,
      first = new Date(month + '-01T12:00:00');
    const days = new Date(first.getFullYear(), first.getMonth() + 1, 0).getDate();
    const offset = (first.getDay() + 6) % 7;
    if (!calendarSelectedDay?.startsWith(month)) calendarSelectedDay = month + '-01';
    let grid =
      ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
        .map((day) => `<span class="calendar-weekday" aria-hidden="true">${day}</span>`)
        .join('') + '<span class="calendar-blank" aria-hidden="true"></span>'.repeat(offset);
    for (let day = 1; day <= days; day++) {
      const date = `${month}-${String(day).padStart(2, '0')}`,
        rows = items.filter((row) => row.date === date);
      grid += `<button type="button" class="calendar-day" data-calendar-day="${date}" aria-pressed="${date === calendarSelectedDay}" aria-label="${esc(calendarDateLabel(date))}, ${rows.length} releases"><strong>${day}</strong>${rows.length ? `<span>${rows.length} release${rows.length === 1 ? '' : 's'}</span>` : ''}<span class="calendar-day-preview">${rows
        .slice(0, 2)
        .map((row) => esc(row.item.show_title || row.item.title))
        .join('<br>')}</span></button>`;
    }
    $('calendar-grid').innerHTML = grid;
    shown = items.filter((row) => row.date === calendarSelectedDay);
  }
  const groups = new Map();
  for (const row of shown) {
    if (!groups.has(row.date)) groups.set(row.date, []);
    groups.get(row.date).push(row);
  }
  $('calendar-items').innerHTML = shown.length
    ? [...groups]
        .map(
          ([date, rows]) =>
            `<section class="calendar-agenda-day"><h3>${esc(calendarDateLabel(date))} <span class="muted">${rows.length}</span></h3><div class="calendar-day-cards">${rows.map(calendarCard).join('')}</div></section>`
        )
        .join('')
    : `<div class="empty"><h3>${monthMode ? 'No known releases on this day.' : 'No known dates match these filters.'}</h3><p>Follow a list, track a release or follow a creator. Refresh dates to check providers. Unannounced dates cannot be scheduled yet.</p></div>`;
  $('calendar-note').textContent = calendarData.note;
}
async function loadReleaseCalendar(refresh = false) {
  const month = $('calendar-month').value || currentCalendarMonth(),
    seq = ++calendarSequence;
  $('calendar-month').value = month;
  const saved = calendarMonths.get(month);
  if (!saved) {
    calendarData = null;
    $('calendar-items').innerHTML = '';
    $('calendar-grid').innerHTML = '';
  }
  $('calendar-refresh').disabled = false;
  if (saved) {
    calendarData = saved.data;
    drawReleaseCalendar();
  }
  $('calendar-status').textContent = refresh
    ? 'Refreshing provider dates. Saved dates remain visible.'
    : 'Loading saved release dates...';
  if (refresh) $('calendar-refresh').disabled = true;
  try {
    const data = await api('calendar', { month, refresh });
    if (seq !== calendarSequence) return;
    calendarData = data;
    calendarMonths.set(month, { data, refreshed: refresh ? Date.now() : saved?.refreshed || 0 });
    drawReleaseCalendar();
    $('calendar-status').textContent = [
      data.items.length + ' known releases this month.',
      ...(data.warnings || []),
    ].join(' ');
    if (!refresh && Date.now() - (saved?.refreshed || 0) > 300000) return loadReleaseCalendar(true);
  } catch (error) {
    if (seq === calendarSequence)
      $('calendar-status').textContent =
        (calendarData ? 'Showing saved dates. ' : '') + error.message;
  } finally {
    if (seq === calendarSequence) $('calendar-refresh').disabled = false;
  }
}
const selectExploreBeforeCalendar = selectExploreTab;
selectExploreTab = function (name) {
  if (name !== 'calendar') return selectExploreBeforeCalendar(name);
  exploreTab = 'calendar';
  setTabGroup('data-explore-tab', name, (key) => 'explore-' + key);
  $('trakt-preview').hidden = true;
  $('trakt-calendar').hidden = true;
  $('breadcrumb').textContent = 'EXPLORE / CALENDAR';
  loadReleaseCalendar();
};
traktCalendar = async () => {
  traktOpen();
  selectExploreTab('calendar');
};
$('trakt-upcoming').textContent = 'Release calendar';
$('calendar-month').value = currentCalendarMonth();
$('calendar-month').onchange = () => loadReleaseCalendar();
$('calendar-refresh').onclick = () => loadReleaseCalendar(true);
for (const id of ['calendar-view', 'calendar-source', 'calendar-media'])
  $(id).onchange = drawReleaseCalendar;
function moveCalendarMonth(delta) {
  const [year, month] = $('calendar-month').value.split('-').map(Number);
  const next = new Date(Date.UTC(year, month - 1 + delta, 1));
  $('calendar-month').value = next.toISOString().slice(0, 7);
  calendarSelectedDay = null;
  loadReleaseCalendar();
}
$('calendar-prev').onclick = () => moveCalendarMonth(-1);
$('calendar-next').onclick = () => moveCalendarMonth(1);
$('calendar-today').onclick = () => {
  $('calendar-month').value = currentCalendarMonth();
  calendarSelectedDay = null;
  loadReleaseCalendar();
};
$('calendar-grid').onclick = (e) => {
  const day = e.target.closest('[data-calendar-day]');
  if (day) {
    calendarSelectedDay = day.dataset.calendarDay;
    drawReleaseCalendar();
  }
};
bindTabKeys('data-explore-tab', selectExploreTab);
