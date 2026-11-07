// SPDX-License-Identifier: AGPL-3.0-only
/* Move only our own Explore sections; native Plex rows need their own adapter. */
let exploreOrderDraft = [],
  exploreDefaultCounter = 0;
function sortExploreRows(rows, order) {
  const positions = new Map(order.map((id, index) => [id, index]));
  return [...rows].sort(
    (a, b) =>
      (positions.get(a.key) ?? 10000) - (positions.get(b.key) ?? 10000) ||
      (a.defaultOrder ?? 0) - (b.defaultOrder ?? 0)
  );
}
window.applyExploreOrder = function (reset = false) {
  const host = $('explore-ordered-rows');
  if (reset) {
    host.replaceChildren();
    exploreDefaultCounter = 0;
  }
  for (const parent of [$('explore-home-rows'), $('explore-extra-rows')])
    for (const child of [...parent.children]) host.append(child);
  const rows = [...host.children].map((element, index) => {
    const button = element.querySelector('[data-explore-shelf]');
    const key =
      element.dataset.shelfKey ||
      button?.dataset.exploreShelf ||
      (element.id?.startsWith('extra-shelf-') ? element.id.slice('extra-shelf-'.length) : '');
    if (key) element.dataset.shelfKey = key;
    if (element.dataset.defaultOrder === undefined)
      element.dataset.defaultOrder = String(exploreDefaultCounter++);
    return {
      element,
      defaultOrder: Number(element.dataset.defaultOrder),
      key: key || 'empty-' + index,
      title: button?.textContent.replace(/\s*\u2192\s*$/, '') || key,
    };
  });
  for (const row of sortExploreRows(rows, state.explore_row_order || [])) host.append(row.element);
  host.onclick = $('explore-home-rows').onclick;
  host.onchange = $('explore-home-rows').onchange;
};
function drawExploreOrder() {
  $('explore-order-rows').innerHTML =
    exploreOrderDraft
      .map(
        (row, index) =>
          `<div class="saved-list-append-row"><span>${index + 1}. ${esc(row.title)}</span><button class="secondary" data-row-move="${index}" data-direction="-1" ${index === 0 ? 'disabled' : ''} aria-label="Move ${esc(row.title)} up">Up</button><button class="secondary" data-row-move="${index}" data-direction="1" ${index === exploreOrderDraft.length - 1 ? 'disabled' : ''} aria-label="Move ${esc(row.title)} down">Down</button></div>`
      )
      .join('') || '<p>Load discovery rows first, then arrange them.</p>';
}
$('explore-arrange').onclick = () => {
  exploreOrderDraft = [...$('explore-ordered-rows').children]
    .filter((element) => element.dataset.shelfKey)
    .map((element) => ({
      key: element.dataset.shelfKey,
      title:
        element.querySelector('[data-explore-shelf]')?.textContent.replace(/\s*\u2192\s*$/, '') ||
        element.dataset.shelfKey,
    }));
  $('explore-order-status').textContent = '';
  drawExploreOrder();
  $('explore-order-dialog').showModal();
};
$('explore-order-rows').onclick = (event) => {
  const button = event.target.closest('[data-row-move]');
  if (!button) return;
  const index = Number(button.dataset.rowMove),
    next = index + Number(button.dataset.direction);
  if (next < 0 || next >= exploreOrderDraft.length) return;
  [exploreOrderDraft[index], exploreOrderDraft[next]] = [
    exploreOrderDraft[next],
    exploreOrderDraft[index],
  ];
  drawExploreOrder();
};
async function saveExploreOrder(reset = false) {
  try {
    const order = reset
      ? []
      : [
          ...exploreOrderDraft.map((row) => row.key),
          ...(state.explore_row_order || []).filter(
            (key) => !exploreOrderDraft.some((row) => row.key === key)
          ),
        ];
    const result = await api('explore/row-order', { order });
    state.explore_row_order = result.order;
    window.applyExploreOrder();
    $('explore-order-dialog').close();
    toast(reset ? 'Default row order restored.' : 'Explore row order saved.');
  } catch (error) {
    $('explore-order-status').textContent = error.message;
  }
}
$('explore-order-save').onclick = (event) => task(event.target, () => saveExploreOrder());
$('explore-order-reset').onclick = (event) => task(event.target, () => saveExploreOrder(true));
