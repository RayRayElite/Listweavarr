// SPDX-License-Identifier: AGPL-3.0-only
/* Presentation wiring keeps existing reviewed actions as the source of truth. */
function titleActionMarkup() {
  return ['title-add', 'parent-request', 'title-save']
    .map((id) => {
      const button = $(id);
      if (button.hidden) return '';
      return `<button type="button" class="${id === 'title-save' ? 'secondary' : 'primary'}" data-title-command="${id}" ${button.disabled ? 'disabled' : ''}>${esc(button.textContent)}</button>`;
    })
    .join('');
}
function syncTitleActions() {
  const slot = document.querySelector('#title-content .title-main-actions');
  if (!slot) return;
  const html = titleActionMarkup();
  if (slot.dataset.actions !== html) {
    slot.dataset.actions = html;
    slot.innerHTML = html;
  }
  slot.hidden = !html;
}
if (typeof MutationObserver !== 'undefined') {
  document.documentElement.classList.add('enhanced-title-actions');
  const inbox = document.createElement('details');
  inbox.className = 'workspace-inbox';
  const summary = document.createElement('summary');
  summary.textContent = 'Updates';
  const messages = document.createElement('div');
  messages.className = 'workspace-inbox-messages';
  inbox.append(summary, messages);
  document.querySelector('main>header').append(inbox);
  const legacy = document.createElement('div');
  legacy.hidden = true;
  legacy.className = 'legacy-update-notices';
  legacy.append($('release-notice'), $('requests-notice'));
  inbox.append(legacy);
  window.notificationEntries = [];
  window.updateWorkspaceInbox = (items) => {
    window.notificationEntries = items;
    const count = items.filter((row) => !row.read).length;
    summary.textContent = count ? `Updates (${count})` : 'Updates';
    inbox.hidden = false;
    window.renderNotificationPopover?.();
  };
  window.updateWorkspaceInbox([]);
  const observer = new MutationObserver(syncTitleActions);
  observer.observe($('title-content'), { childList: true, subtree: true });
  observer.observe($('title-save').parentElement, {
    attributes: true,
    attributeFilter: ['hidden', 'disabled', 'aria-busy'],
    childList: true,
    characterData: true,
    subtree: true,
  });
  document.addEventListener('click', (event) => {
    const command = event.target.closest('[data-title-command]');
    if (command) {
      const original = $(command.dataset.titleCommand);
      if (!original.hidden && !original.disabled) original.click();
    }
  });
  document.addEventListener('keydown', (event) => {
    if (event.key !== 'Escape') return;
    const menus = [...document.querySelectorAll('details[open]')].filter((node) =>
      node.matches(
        '.explore-card-menu,.list-tools-menu,.explore-filter-options,.list-switcher,.workspace-inbox,.list-display-options'
      )
    );
    if (menus.length) {
      menus.forEach((node) => (node.open = false));
      menus[menus.length - 1].querySelector('summary')?.focus();
      event.preventDefault();
    }
  });
  document.addEventListener('click', (event) => {
    for (const menu of document.querySelectorAll(
      '.explore-card-menu[open],.list-tools-menu[open],.explore-filter-options[open],.list-switcher[open],.workspace-inbox[open],.list-display-options[open]'
    ))
      if (!menu.contains(event.target)) menu.open = false;
  });
  syncTitleActions();
}
