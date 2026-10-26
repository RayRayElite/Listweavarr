// SPDX-License-Identifier: AGPL-3.0-only
/* Single-user approval workflow, explicit manager routes, and opt-in Discord. */
let requestScopeLoading = false;
let workflowManagers = { instances: [], defaults: {} },
  editingManager = null,
  newRequestResults = [],
  newRequestItem = null,
  requestDecision = null,
  newRequestSequence = 0;
async function loadWorkflowSettings() {
  const results = await Promise.allSettled([
    api('managers/list', {}),
    api('requests/policy', {}),
    api('notifications/settings', {}),
  ]);
  if (results[0].status === 'fulfilled') {
    workflowManagers = results[0].value;
    drawManagerRoutes();
  } else $('manager-route-status').textContent = results[0].reason.message;
  if (results[1].status === 'fulfilled')
    $('workflow-approval').checked = Boolean(results[1].value.require_approval);
  if (results[2].status === 'fulfilled') paintDiscordSettings(results[2].value);
  else $('discord-status').textContent = results[2].reason.message;
}
function drawManagerRoutes() {
  $('manager-route-list').innerHTML = workflowManagers.instances
    .map(
      (row) =>
        `<article class="manager-route-row"><div><strong>${esc(row.name)}</strong><p class="muted">${esc(row.service)} &middot; ${row.tier === '4k' ? '4K' : 'Standard'} &middot; ${row.enabled ? 'Enabled' : 'Disabled'}${workflowManagers.defaults[row.service + ':' + row.tier] === row.id ? ' &middot; Default' : ''}</p><small class="muted">${esc(row.url || 'Not connected')}</small></div>${row.id === 'primary' ? '<button class="text-action" data-settings-open="connections">Primary connection settings</button>' : `<button class="secondary" data-manager-edit="${esc(row.id)}">Edit</button>`}</article>`
    )
    .join('');
}
function managerFormBody() {
  return {
    id: editingManager,
    service: $('manager-service').value,
    name: $('manager-name').value,
    tier: $('manager-tier').value,
    url: $('manager-url').value,
    key: $('manager-key').value,
    enabled: $('manager-enabled').checked,
    default: $('manager-default').checked,
  };
}
function editManager(id = null) {
  const row = workflowManagers.instances.find((r) => r.id === id);
  editingManager = id;
  $('manager-editor-title').textContent = row ? 'Edit ' + row.name : 'Add manager instance';
  $('manager-name').value = row?.name || '';
  $('manager-service').value = row?.service || 'radarr';
  $('manager-tier').value = row?.tier || 'standard';
  $('manager-url').value = row?.url || '';
  $('manager-key').value = '';
  $('manager-enabled').checked = row?.enabled ?? true;
  $('manager-default').checked = row
    ? workflowManagers.defaults[row.service + ':' + row.tier] === row.id
    : false;
  $('manager-editor-status').textContent = '';
  $('manager-editor').showModal();
}
$('manager-add').onclick = () => editManager();
$('manager-route-list').onclick = (e) => {
  const button = e.target.closest('[data-manager-edit]');
  if (button) editManager(button.dataset.managerEdit);
};
$('manager-form').onsubmit = (e) => {
  e.preventDefault();
  task(e.submitter, async () => {
    workflowManagers = await api('managers/save', managerFormBody());
    drawManagerRoutes();
    $('manager-editor').close();
    $('manager-route-status').textContent =
      'Manager route saved. Existing requests retain their selected route.';
  });
};
$('manager-test').onclick = (e) =>
  task(e.target, async () => {
    await api('managers/test', managerFormBody());
    $('manager-editor-status').textContent =
      'Connection successful. Save the instance to keep these settings.';
  });
$('workflow-policy-save').onclick = (e) =>
  task(e.target, async () => {
    await api('requests/policy-save', { require_approval: $('workflow-approval').checked });
    $('workflow-policy-status').textContent =
      'Request workflow saved. Existing downloads and monitored releases are unchanged.';
  });
function paintDiscordSettings(cfg) {
  $('discord-enabled').checked = cfg.enabled;
  $('discord-webhook').value = '';
  $('discord-webhook').placeholder = cfg.configured
    ? 'Saved - leave blank to keep'
    : 'https://discord.com/api/webhooks/...';
  document
    .querySelectorAll('[data-discord-event]')
    .forEach((input) => (input.checked = cfg.events.includes(input.dataset.discordEvent)));
  $('discord-status').textContent =
    (cfg.last_error ? cfg.last_error + ' ' : '') +
    (cfg.pending ? cfg.pending + ' notification(s) waiting. ' : '') +
    (cfg.failed ? cfg.failed + ' failed delivery attempt(s).' : '');
}
$('discord-save').onclick = (e) =>
  task(e.target, async () => {
    const cfg = await api('notifications/save', {
      url: $('discord-webhook').value,
      enabled: $('discord-enabled').checked,
      events: [...document.querySelectorAll('[data-discord-event]:checked')].map(
        (input) => input.dataset.discordEvent
      ),
    });
    paintDiscordSettings(cfg);
    $('discord-status').textContent =
      'Discord settings saved. ' +
      (cfg.enabled
        ? 'New selected request events will be sent to your channel.'
        : 'Notifications are disabled.');
  });
$('discord-test').onclick = (e) =>
  task(e.target, async () => {
    await api('notifications/test', { confirmed: true });
    $('discord-status').textContent = 'Test notification sent to your saved Discord channel.';
  });
// Switching a route reloads profiles and roots from that exact instance.
document.addEventListener?.('change', (e) => {
  const select = e.target.closest?.('[data-manager-route]');
  if (!select) return;
  task(select, async () => {
    const service = select.dataset.managerRoute,
      prefix = select.dataset.routePrefix,
      previous = select.dataset.loadedRoute || 'primary';
    try {
      const options = (
        await api('options', { services: [service], routes: { [service]: select.value } })
      )[service];
      $(prefix + '-profile').innerHTML = options.profiles
        .map((p) => `<option value="${p.id}">${esc(p.name)}</option>`)
        .join('');
      $(prefix + '-root').innerHTML = options.roots
        .map((r) => `<option value="${esc(r.path)}">${esc(r.path)}</option>`)
        .join('');
      if (options.defaults?.profile) $(prefix + '-profile').value = options.defaults.profile;
      if (options.defaults?.root) $(prefix + '-root').value = options.defaults.root;
      select.dataset.loadedRoute = options.route;
    } catch (error) {
      select.value = previous;
      throw error;
    }
  });
});
function drawNewRequestRoutes() {
  const tv = $('request-new-type').value === 'show';
  for (const [id, show] of [
    ['request-new-scope', tv],
    ['request-new-season', tv && $('request-new-scope').value !== 'show'],
    ['request-new-episode', tv && $('request-new-scope').value === 'episode'],
  ]) {
    const label = $(id).closest?.('label');
    if (label) label.hidden = !show;
  }
  const previousRoute = $('request-new-route').value;
  const service = $('request-new-type').value === 'movie' ? 'radarr' : 'sonarr',
    tier = $('request-new-tier').value;
  const rows = workflowManagers.instances.filter(
    (r) => r.service === service && r.tier === tier && r.enabled && r.configured
  );
  $('request-new-route').innerHTML = rows
    .map((r) => `<option value="${esc(r.id)}">${esc(r.name)}</option>`)
    .join('');
  const preferred = workflowManagers.defaults[service + ':' + tier];
  if (rows.some((r) => r.id === previousRoute)) $('request-new-route').value = previousRoute;
  else if (rows.some((r) => r.id === preferred)) $('request-new-route').value = preferred;
  $('request-new-continue').disabled =
    !newRequestItem ||
    !rows.length ||
    requestScopeLoading ||
    (tv && $('request-new-scope').value !== 'show' && !$('request-new-season').value) ||
    (tv && $('request-new-scope').value === 'episode' && !$('request-new-episode').value);
  $('request-new-status').textContent = rows.length
    ? ''
    : 'Connect an enabled ' + tier + ' ' + service + ' route under Settings / Requests first.';
}
$('request-new').onclick = (e) =>
  task(e.target, async () => {
    workflowManagers = await api('managers/list', {});
    newRequestItem = null;
    newRequestResults = [];
    $('request-new-results').innerHTML = '';
    $('request-new-selection').textContent = '';
    $('request-new-query').value = '';
    $('request-new-queue').checked = $('workflow-approval').checked;
    drawNewRequestRoutes();
    $('request-new-dialog').showModal();
  });
$('request-new-tier').onchange = drawNewRequestRoutes;
$('request-new-scope').onchange = drawNewRequestRoutes;
$('request-new-type').onchange = () => {
  ++newRequestSequence;
  newRequestItem = null;
  $('request-new-results').innerHTML = '';
  $('request-new-selection').textContent = '';
  drawNewRequestRoutes();
};
$('request-new-search').onclick = (e) =>
  task(e.target, async () => {
    const sequence = ++newRequestSequence,
      kind = $('request-new-type').value;
    newRequestItem = null;
    $('request-new-selection').textContent = '';
    drawNewRequestRoutes();
    const result = await api('lists/search', { query: $('request-new-query').value, type: kind });
    if (sequence !== newRequestSequence) return;
    newRequestResults = result.items;
    $('request-new-results').innerHTML =
      result.items.map((row, index) => requestCandidateMarkup(row, index)).join('') ||
      '<p class="muted">No exact title candidates found.</p>';
  });
$('request-new-results').onclick = (e) => {
  if (e.target.closest('[data-change-request-title]')) {
    newRequestItem = null;
    $('request-new-selection').textContent = '';
    $('request-new-results').innerHTML = newRequestResults
      .map((row, index) => requestCandidateMarkup(row, index))
      .join('');
    drawNewRequestRoutes();
    return;
  }
  const choice = e.target.closest('[data-request-choice]');
  if (!choice) return;
  const index = Number(choice.dataset.requestChoice);
  newRequestItem = newRequestResults[index];
  if (newRequestItem.type === 'show') loadRequestScopes('', '');
  $('request-new-results').innerHTML =
    requestCandidateMarkup(newRequestItem, index) +
    '<button type="button" class="text-action" data-change-request-title>Change title</button>';
  $('request-new-results')
    .querySelector('[data-request-choice]')
    .setAttribute('aria-pressed', 'true');
  $('request-new-selection').textContent =
    'Selected: ' +
    newRequestItem.title +
    (newRequestItem.year ? ' (' + newRequestItem.year + ')' : '');
  drawNewRequestRoutes();
};
$('request-new-continue').onclick = (e) =>
  task(e.target, async () => {
    if (!newRequestItem) throw Error('Choose a title first.');
    const item = { ...newRequestItem };
    if (item.type === 'show' && $('request-new-scope').value !== 'show') {
      const season = $('request-new-season').value,
        episode = $('request-new-episode').value;
      if (season === '' || !Number.isInteger(Number(season)) || Number(season) < 0)
        throw Error('Enter a valid season number.');
      item.type = $('request-new-scope').value;
      item.show_tmdb = item.tmdb;
      delete item.tmdb;
      item.season = season;
      if (item.type === 'episode') {
        if (!episode || !Number.isInteger(Number(episode)) || Number(episode) < 1)
          throw Error('Enter a valid episode number.');
        item.episode = episode;
      }
    }
    const result = await api('requests/create', {
      item,
      route: $('request-new-route').value,
      tier: $('request-new-tier').value,
      mode: $('request-new-mode').value,
      queue: $('request-new-queue').checked,
    });
    requestRows = result.items;
    requestNotices = result.notifications;
    drawRequests();
    $('request-new-dialog').close();
    openRequests();
    const row = requestRows.find((r) => r.id === result.request_id);
    if (row.status === 'awaiting_approval') {
      toast('Request queued. Review and approve it from Requests.');
    } else if (row.status === 'available') {
      toast('This request is already available in Plex.');
    } else await reviewRequestRetry(result.request_id);
  });
$('requests-items').addEventListener('click', (e) => {
  const button = e.target.closest('[data-request-decision]');
  if (!button) return;
  requestDecision = requestRows.find((r) => r.id === button.dataset.requestDecision);
  $('request-decision-heading').textContent =
    (requestDecision.status === 'pending' ? 'Cancel draft: ' : 'Decline: ') +
    requestDecision.item.title;
  $('request-decision-reason').value = '';
  $('request-decision-dialog').showModal();
});
$('request-decision-confirm').onclick = (e) =>
  task(e.target, async () => {
    const result = await api(
      'requests/' + (requestDecision.status === 'pending' ? 'cancel' : 'decline'),
      {
        id: requestDecision.id,
        expected_updated: requestDecision.updated_at,
        reason: $('request-decision-reason').value,
      }
    );
    requestRows = result.items;
    requestNotices = result.notifications;
    drawRequests();
    $('request-decision-dialog').close();
  });
const readyBeforeWorkflow = window.onListweavarrReady;
window.onListweavarrReady = () => {
  readyBeforeWorkflow?.();
  loadWorkflowSettings();
};
