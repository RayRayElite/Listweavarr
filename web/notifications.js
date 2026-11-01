// SPDX-License-Identifier: AGPL-3.0-only
/* Optional outbound services stay inside Notifications settings, off by default. */
let notificationServices = {},
  notificationSettingsSequence = 0;
const NOTIFY_HELP = {
  ntfy: [
    'https://ntfy.sh/your-topic',
    'Use the full topic URL. An access token is optional for public topics.',
  ],
  gotify: [
    'https://gotify.example/message',
    'Use the /message endpoint and a Gotify application token.',
  ],
  webhook: [
    'https://your-service.example/webhook',
    'POSTs JSON with title, message, event and source. Optional token uses Bearer authentication.',
  ],
};
function paintNotificationService() {
  const kind = $('notify-kind').value,
    cfg = notificationServices[kind] || {};
  $('notify-help').textContent = NOTIFY_HELP[kind][1];
  $('notify-url').value = '';
  $('notify-url').placeholder = cfg.configured
    ? 'Saved - leave blank to keep'
    : NOTIFY_HELP[kind][0];
  $('notify-token').value = '';
  $('notify-token').placeholder = cfg.token_saved
    ? 'Saved - leave blank to keep'
    : kind === 'gotify'
      ? 'Application token required'
      : 'Optional access token';
  $('notify-enabled').checked = Boolean(cfg.enabled);
  $('notify-clear-token').checked = false;
  $('notify-quiet-start').value = cfg.quiet_start || '';
  $('notify-quiet-end').value = cfg.quiet_end || '';
  $('notify-batch').checked = Boolean(cfg.batch);
  document
    .querySelectorAll('[data-notify-event]')
    .forEach(
      (input) => (input.checked = (cfg.events || ['available']).includes(input.dataset.notifyEvent))
    );
  $('notify-status').textContent =
    cfg.last_error ||
    (cfg.enabled ? `${cfg.pending || 0} messages pending.` : 'This service is disabled.');
  $('notify-history').innerHTML =
    (cfg.history || [])
      .map(
        (row) =>
          `<article class="notification-delivery"><strong>${esc(row.status)} / ${esc(REQUEST_LABELS[row.event] || row.event)}</strong><span class="muted">${esc(new Date((row.sent_at || row.created_at) * 1000).toLocaleString())} / ${row.attempts || 0} attempts</span>${row.content ? `<p>${esc(row.content)}</p>` : ''}</article>`
      )
      .join('') || '<p class="muted">No deliveries yet.</p>';
}
async function loadNotificationServices() {
  const seq = ++notificationSettingsSequence;
  try {
    const data = await api('notifications/channels', {});
    if (seq !== notificationSettingsSequence) return;
    notificationServices = data;
    paintNotificationService();
  } catch (error) {
    if (seq === notificationSettingsSequence) $('notify-status').textContent = error.message;
  }
}
const workflowSettingsBeforeServices = loadWorkflowSettings;
loadWorkflowSettings = async function () {
  await workflowSettingsBeforeServices();
  await loadNotificationServices();
};
$('notify-kind').value ||= 'ntfy';
$('notify-kind').onchange = paintNotificationService;
$('notify-save').onclick = (e) =>
  task(e.target, async () => {
    const kind = $('notify-kind').value;
    notificationSettingsSequence++;
    notificationServices = await api('notifications/channel-save', {
      kind,
      url: $('notify-url').value,
      token: $('notify-token').value,
      clear_token: $('notify-clear-token').checked,
      enabled: $('notify-enabled').checked,
      quiet_start: $('notify-quiet-start').value,
      quiet_end: $('notify-quiet-end').value,
      batch: $('notify-batch').checked,
      events: [...document.querySelectorAll('[data-notify-event]:checked')].map(
        (input) => input.dataset.notifyEvent
      ),
    });
    paintNotificationService();
    $('notify-status').textContent = kind + ' settings saved. No test notification was sent.';
  });
$('notify-test').onclick = (e) =>
  task(e.target, async () => {
    const kind = $('notify-kind').value;
    await api('notifications/channel-test', { kind, confirmed: true });
    $('notify-status').textContent = 'Test notification accepted by ' + kind + '.';
  });
