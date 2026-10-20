const assert = require('node:assert/strict');
const test = require('node:test');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');

const source = fs.readFileSync(path.join(__dirname, '../api.ts'), 'utf8').replaceAll('import.meta.env', 'testEnv');
const code = ts.transpileModule(source, {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS }
}).outputText;

function harness(fetch, env = {}) {
  const context = {
    exports: {}, require: () => ({}), testEnv: env,
    window: { location: { hostname: 'msmall.vercel.app' } },
    console: { warn() {}, error() {} }, fetch,
    URLSearchParams, AbortController, setTimeout, clearTimeout
  };
  vm.runInNewContext(code, context);
  return context.exports.ApiService;
}

const csvResponse = () => new Response('\ufeffid_registro,fecha_venta\r\n1,2026-01-01\r\n', {
  headers: { 'Content-Type': 'text/csv; charset=utf-8', 'X-Backup-Records': '1' }
});

test('CSV request carries session, Mall, sale dates and selected store IDs', async () => {
  let request;
  const api = harness(async (url, init) => { request = { url, ...init }; return csvResponse(); });
  const controller = new AbortController();
  const result = await api.downloadImportBackup('mall-a', 'session-token', '2026-01-01', '2026-01-31', ['store-a', 'store-b'], controller.signal);
  assert.equal(request.url, '/api/v1/export/import-backup/csv');
  assert.equal(request.method, 'POST');
  assert.equal(request.headers.Authorization, 'Bearer session-token');
  assert.equal(request.headers['X-Mall-Id'], 'mall-a');
  assert.equal(request.signal, controller.signal);
  assert.deepEqual(JSON.parse(request.body), { fecha_inicio: '2026-01-01', fecha_fin: '2026-01-31', local_ids: ['store-a', 'store-b'] });
  assert.equal(result.records, 1);
  assert((await result.blob.text()).includes('1,2026-01-01'));
});

test('all stores is sent as null and CSV without exposed count remains downloadable', async () => {
  const api = harness(async (_url, init) => {
    assert.equal(JSON.parse(init.body).local_ids, null);
    return new Response('id_registro\r\n', { headers: { 'Content-Type': 'text/csv' } });
  });
  const result = await api.downloadImportBackup('mall', 'token', '2026-01-01', '2026-01-31', null, new AbortController().signal);
  assert.equal(result.records, null);
  assert.equal(await result.blob.text(), 'id_registro\r\n');
});

test('authorization denial is shown without trying other backends', async () => {
  let calls = 0;
  const api = harness(async () => {
    calls++;
    return new Response(JSON.stringify({ detail: 'Sin permiso de ventas' }), { status: 403 });
  }, { VITE_DIRECT_BACKEND_BASE_URL: 'https://backend.example.test' });
  await assert.rejects(api.downloadImportBackup('mall', 'token', '2026-01-01', '2026-01-31', null, new AbortController().signal), /Sin permiso de ventas/);
  assert.equal(calls, 1);
});

test('proxy HTML is never offered as CSV and retries the configured backend', async () => {
  const calls = [];
  const api = harness(async url => {
    calls.push(url);
    return calls.length === 1 ? new Response('<html>proxy</html>', { headers: { 'Content-Type': 'text/html' } }) : csvResponse();
  }, { VITE_DIRECT_BACKEND_BASE_URL: 'https://backend.example.test' });
  const result = await api.downloadImportBackup('mall', 'token', '2026-01-01', '2026-01-31', null, new AbortController().signal);
  assert.equal(calls.length, 2);
  assert.equal(calls[1], 'https://backend.example.test/api/v1/export/import-backup/csv');
  assert.match(result.blob.type, /^text\/csv;\s*charset=utf-8$/);
});

test('canceling a download stops backend fallback attempts', async () => {
  let calls = 0;
  const controller = new AbortController();
  const api = harness(async () => {
    calls++;
    controller.abort();
    throw new TypeError('Failed to fetch');
  }, { VITE_DIRECT_BACKEND_BASE_URL: 'https://backend.example.test' });
  await assert.rejects(api.downloadImportBackup('mall', 'token', '2026-01-01', '2026-01-31', null, controller.signal));
  assert.equal(calls, 1);
});

test('store selector uses the same authorized Mall context and supports cancellation', async () => {
  const controller = new AbortController();
  const api = harness(async (url, init) => {
    assert.equal(url, '/api/v1/export/import-backup/stores');
    assert.equal(init.headers['X-Mall-Id'], 'mall');
    assert.equal(init.headers.Authorization, 'Bearer token');
    assert.equal(init.signal, controller.signal);
    return new Response(JSON.stringify([{ id: 'inactive', activo: false }]));
  });
  const stores = await api.getImportBackupStores('mall', 'token', controller.signal);
  assert.equal(stores[0].activo, false);
});
