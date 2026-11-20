const assert = require('node:assert/strict');
const test = require('node:test');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');
const React = require('react');
const code = ts.transpileModule(fs.readFileSync(`${__dirname}/../components/DatabaseBackupPanel.tsx`, 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.React, esModuleInterop: true }
}).outputText;

async function harness(load) {
  const state = [], timers = [];
  let effect, hook = 0;
  const context = { exports: {},
    setTimeout(fn) { timers.push(fn); return fn; },
    clearTimeout(fn) { const index = timers.indexOf(fn); if (index >= 0) timers.splice(index, 1); },
    AbortController, Error,
    require(id) {
      if (id === '../api') return { ApiService: { getDatabaseBackupCapabilities: load } };
      if (id === 'react') return { ...React,
        useState(initial) { const index = hook++; state[index] = initial; return [initial, value => { state[index] = value; }]; },
        useRef(initial) { return { current: initial }; },
        useEffect(fn) { effect = fn; },
      };
      throw Error(id);
    },
  };
  vm.runInNewContext(code, context);
  context.exports.DatabaseBackupPanel({ mallId: 'mall', mallName: 'Mall', token: 'session', onDownloaded() {} });
  const cleanup = effect();
  const flush = () => new Promise(resolve => setImmediate(resolve));
  await flush();
  return { state, timers, cleanup, flush };
}

test('capabilities recover automatically when backend becomes available after a 404', async () => {
  let calls = 0;
  const view = await harness(async () => {
    if (++calls === 1) throw Object.assign(new Error('Not Found'), { status: 404 });
    return { enabled: true, mall: true, platform: false };
  });
  assert.equal(view.state[1], '');
  assert.equal(view.timers.length, 1);
  view.timers.shift()(); await view.flush();
  assert.equal(view.state[0].mall, true);
  assert.equal(calls, 2);
  view.cleanup();
});

test('persistent 404 ends retries with an actionable message', async () => {
  let calls = 0;
  const view = await harness(async () => { calls++; throw Object.assign(new Error('Not Found'), { status: 404 }); });
  while (view.timers.length) { view.timers.shift()(); await view.flush(); }
  assert.equal(calls, 4);
  assert.match(view.state[1], /actualización del servidor/);
  assert.doesNotMatch(view.state[1], /Not Found/);
  view.cleanup();
});

test('permission errors are not retried and leaving the panel cancels scheduled retries', async () => {
  const denied = await harness(async () => { throw Object.assign(new Error('Sin permiso'), { status: 403 }); });
  assert.equal(denied.timers.length, 0);
  assert.equal(denied.state[1], 'Sin permiso');
  denied.cleanup();
  let signal;
  const unavailable = await harness(async (_mall, _token, current) => {
    signal = current;
    throw Object.assign(new Error('Not Found'), { status: 404 });
  });
  assert.equal(unavailable.timers.length, 1);
  unavailable.cleanup();
  assert.equal(unavailable.timers.length, 0);
  assert.equal(signal.aborted, true);
});
