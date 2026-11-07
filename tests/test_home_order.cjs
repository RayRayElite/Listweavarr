// SPDX-License-Identifier: AGPL-3.0-only
const assert = require('node:assert/strict'),
  fs = require('node:fs'),
  vm = require('node:vm');
const nodes = new Map();
function element(id) {
  if (!nodes.has(id))
    nodes.set(id, {
      id,
      dataset: {},
      children: [],
      onclick() {},
      onchange() {},
      append(child) {
        if (child.parent) child.parent.children.splice(child.parent.children.indexOf(child), 1);
        this.children.push(child);
        child.parent = this;
      },
      replaceChildren() {
        this.children.forEach((child) => (child.parent = null));
        this.children = [];
      },
      querySelector() {
        return this.heading || null;
      },
      showModal() {},
      close() {},
    });
  return nodes.get(id);
}
function row(key) {
  const node = element(key);
  node.heading = { dataset: { exploreShelf: key }, textContent: key };
  return node;
}
const context = vm.createContext({
  $: element,
  state: { explore_row_order: ['third', 'first'] },
  window: {},
  esc: String,
  task: async (_, fn) => fn(),
  toast() {},
  api: async (_, body) => body,
});
vm.runInContext(fs.readFileSync('web/home-order.js', 'utf8'), context);
const first = row('first'),
  second = row('second'),
  third = row('third');
first.selection = { checked: true };
element('explore-home-rows').append(first);
element('explore-home-rows').append(second);
context.window.applyExploreOrder(true);
element('explore-extra-rows').append(third);
context.window.applyExploreOrder();
const keys = () => element('explore-ordered-rows').children.map((row) => row.id);
assert.deepEqual(keys(), ['third', 'first', 'second']);
assert.equal(first.selection.checked, true);
context.state.explore_row_order = [];
context.window.applyExploreOrder();
assert.deepEqual(
  keys(),
  ['first', 'second', 'third'],
  'Restore uses original order rather than current DOM order'
);
context.state.explore_row_order = ['third', 'first'];
context.window.applyExploreOrder();
const fourth = row('fourth');
element('explore-extra-rows').append(fourth);
context.window.applyExploreOrder();
assert.deepEqual(keys(), ['third', 'first', 'second', 'fourth']);
assert.equal(element('explore-ordered-rows').onclick, element('explore-home-rows').onclick);
console.log('Explore order preserves selections, applies late rows and restores defaults.');
