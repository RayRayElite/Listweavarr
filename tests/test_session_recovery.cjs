// SPDX-License-Identifier: AGPL-3.0-only
const assert = require('node:assert/strict'),
  fs = require('node:fs'),
  vm = require('node:vm');
const source = fs.readFileSync('web/app.js', 'utf8');
const code = source.slice(
  source.indexOf('let sessionRenewal = null;'),
  source.indexOf('for (const [id, revoke]')
);
function setup(fetch) {
  const context = vm.createContext({ state: { csrf: 'old' }, fetch });
  vm.runInContext(code, context);
  return context;
}
const response = (status, result) => ({
  status,
  ok: status >= 200 && status < 300,
  json: async () => result,
});
(async () => {
  const calls = [];
  let context = setup(async (path, options) => {
    calls.push({ path, options });
    if (path === '/api/session') return response(200, { csrf: 'new' });
    return options.headers['X-Listweavarr-Token'] === 'old'
      ? response(403, { code: 'session_expired' })
      : response(200, { saved: true });
  });
  assert.equal((await vm.runInContext("api('request',{ids:['one']})", context)).saved, true);
  assert.equal(calls.length, 3);
  assert.equal(calls[0].options.body, calls[2].options.body);
  assert.equal(calls[2].options.headers['X-Listweavarr-Token'], 'new');
  for (const [status, error] of [
    [500, { error: 'failed' }],
    [403, { error: 'wrong host' }],
  ]) {
    let count = 0;
    context = setup(async () => {
      count++;
      return response(status, error);
    });
    await assert.rejects(vm.runInContext("api('request',{})", context));
    assert.equal(count, 1, 'Never retry ambiguous failures');
  }
  let count = 0;
  context = setup(async (path) => {
    count++;
    return path === '/api/session'
      ? response(200, { csrf: 'new' })
      : response(403, { code: 'session_expired' });
  });
  await assert.rejects(vm.runInContext("api('request',{})", context));
  assert.equal(count, 3, 'Only one retry');
  let release,
    renews = 0;
  context = setup(async (path, options) => {
    if (path === '/api/session') {
      renews++;
      return new Promise((resolve) => {
        release = () => resolve(response(200, { csrf: 'new' }));
      });
    }
    return options.headers['X-Listweavarr-Token'] === 'old'
      ? response(403, { code: 'session_expired' })
      : response(200, { saved: true });
  });
  const first = vm.runInContext("api('first',{})", context),
    second = vm.runInContext("api('second',{})", context);
  for (let i = 0; i < 5 && !release; i++) await new Promise((resolve) => setImmediate(resolve));
  assert.equal(typeof release, 'function');
  release();
  await Promise.all([first, second]);
  assert.equal(renews, 1, 'Concurrent failures share renewal');
  console.log(
    'Session renewal, exact retry limits, concurrent renewal and no ambiguous replay passed.'
  );
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
