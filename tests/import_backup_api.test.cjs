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
    URLSearchParams, FormData, AbortController, setTimeout, clearTimeout
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

test('quota availability is fetched for the authenticated user and active Mall', async () => {
  const api = harness(async (url, init) => {
    assert.equal(url, '/api/v1/export/import-backup/quota');
    assert.equal(init.headers['X-Mall-Id'], 'mall-a');
    assert.equal(init.headers.Authorization, 'Bearer token');
    return new Response(JSON.stringify({ quota: { user: { downloads_remaining: 7 } }, can_configure: false }));
  });
  const state = await api.getImportBackupQuota('mall-a', 'token');
  assert.equal(state.quota.user.downloads_remaining, 7);
  assert.equal(state.can_configure, false);
});

test('global quota settings are sent as an authenticated PUT', async () => {
  const policy = { max_file_mb: 50, user_daily_mb: 200, mall_daily_mb: 1000 };
  const api = harness(async (url, init) => {
    assert.equal(url, '/api/v1/export/import-backup/settings');
    assert.equal(init.method, 'PUT');
    assert.equal(init.headers.Authorization, 'Bearer token');
    assert.deepEqual(JSON.parse(init.body), policy);
    return new Response(JSON.stringify({ quota: { limits: policy }, can_configure: true }));
  });
  assert.equal((await api.saveImportBackupPolicy('mall', 'token', policy)).quota.limits.max_file_mb, 50);
});

test('quota rejection is displayed without a fallback download attempt', async () => {
  let calls = 0;
  const api = harness(async () => {
    calls++;
    return new Response(JSON.stringify({ detail: 'Puedes reintentar en 60 segundos.' }), { status: 429, headers: { 'Retry-After': '60' } });
  }, { VITE_DIRECT_BACKEND_BASE_URL: 'https://backend.example.test' });
  await assert.rejects(api.downloadImportBackup('mall', 'token', '2026-01-01', '2026-01-31', null, new AbortController().signal), /60 segundos/);
  assert.equal(calls, 1);
});


test('admin settings load separately from download quota with authenticated Mall context', async () => {
  const api = harness(async (url, init) => {
    assert.equal(url, '/api/v1/export/import-backup/settings');
    assert.equal(init.headers.Authorization, 'Bearer token');
    assert.equal(init.headers['X-Mall-Id'], 'mall');
    return new Response(JSON.stringify({ quota: { limits: { max_file_mb: 50 } }, can_configure: true }));
  });
  assert.equal((await api.getImportBackupPolicy('mall', 'token')).quota.limits.max_file_mb, 50);
});

test('automatic backup settings use authenticated owner context and validated API path', async () => {
  const requests = [];
  const api = harness(async (url, init) => {
    requests.push({url,...init});
    assert.equal(init.headers.Authorization,'Bearer token');
    assert.equal(init.headers['X-Mall-Id'],'mall');
    return new Response(JSON.stringify({schedule:null,artifacts:[],automation_enabled:false}));
  });
  const config={frequency:'fortnightly',run_hour:2,folder:'reportes/ventas',local_ids:['store'],retention_days:30,enabled:true};
  await api.getImportBackupSchedule('mall','token');
  await api.saveImportBackupSchedule('mall','token',config);
  await api.deleteImportBackupSchedule('mall','token');
  assert(requests.every(r=>r.url==='/api/v1/export/import-backup/schedule'));
  assert.equal(requests[1].method,'PUT');
  assert.deepEqual(JSON.parse(requests[1].body),config);
  assert.equal(requests[2].method,'DELETE');
});

test('stored backup downloads stay behind authenticated quota-protected endpoint', async () => {
  const api=harness(async(url,init)=>{
    assert.equal(url,'/api/v1/export/import-backup/artifacts/file-id/csv');
    assert.equal(init.method,'POST');
    assert.equal(init.headers.Authorization,'Bearer token');
    assert.equal(init.headers['X-Mall-Id'],'mall');
    return csvResponse();
  });
  const result=await api.downloadStoredImportBackup('mall','token','file-id',new AbortController().signal);
  assert.equal(result.records,1);
});


test('configuration snapshots use distinct paths, preserve selection and omit sale dates', async () => {
  const requests = [];
  const api = harness(async (url, init) => { requests.push({ url, ...init }); return csvResponse(); });
  for (const kind of ['locales', 'importadores', 'ftp', 'webservice']) {
    await api.downloadImportBackup('mall', 'token', '', '', ['local'], new AbortController().signal, undefined, kind);
  }
  assert.equal(new Set(requests.map(request => request.url)).size, 4);
  for (const request of requests) {
    assert.match(request.url, /\/configuration\/(locales|importadores|ftp|webservice)\/csv$/);
    assert.equal(request.headers['X-Mall-Id'], 'mall');
    assert.equal(request.headers.Authorization, 'Bearer token');
    assert.deepEqual(JSON.parse(request.body), { local_ids: ['local'] });
  }
});


test('restore sends multipart file, preview flag, authenticated Mall and explicit apply', async () => {
  const calls = [];
  const api = harness(async (url, init) => {
    calls.push({ url, init });
    return Response.json({ total: 1, pendientes: 1, omitidos: 0, restaurados: 0, errores: [], preview: [] });
  });
  const file = new File(['id\\n'], 'backup.csv', { type: 'text/csv' });
  const controller = new AbortController();
  await api.restoreImportBackup('mall-a', 'session-token', 'ventas', file, false, controller.signal);
  assert.equal(calls[0].url, '/api/v1/export/import-backup/restore/ventas?apply=false');
  assert.equal(calls[0].init.headers.Authorization, 'Bearer session-token');
  assert.equal(calls[0].init.headers['X-Mall-Id'], 'mall-a');
  assert.equal(calls[0].init.headers['Content-Type'], undefined);
  assert.equal(calls[0].init.body.get('file').name, 'backup.csv');
  await api.restoreImportBackup('mall-a', 'session-token', 'ventas', file, true, controller.signal);
  assert.equal(calls[1].url, '/api/v1/export/import-backup/restore/ventas?apply=true');
});


test('SQL capabilities use authenticated Mall and platform export performs one request', async () => {
  const calls = [];
  const api = harness(async (url, init) => {
    calls.push({url, init});
    if (url.endsWith('capabilities')) return Response.json({enabled: true, mall: true, platform: false});
    return new Response('ZIP', {headers: {'Content-Type': 'application/zip'}});
  });
  const signal = new AbortController().signal;
  const caps = await api.getDatabaseBackupCapabilities('mall-1', 'token', signal);
  assert.equal(caps.platform, false);
  assert.equal(calls[0].init.headers['X-Mall-Id'], 'mall-1');
  const blob = await api.downloadDatabaseBackup('mall-1', 'token', 'platform', signal);
  assert.equal(calls[1].url, '/api/v1/export/import-backup/database/platform');
  assert.equal(calls[1].init.method, 'POST');
  assert.equal(calls[1].init.headers.Authorization, 'Bearer token');
  assert.equal(await blob.text(), 'ZIP');
  assert.equal(calls.length, 2);
});

test('SQL dumps reject HTML and never retry generation after errors', async () => {
  let calls = 0;
  const api = harness(async () => { calls++; return new Response('<html>error</html>', {headers: {'Content-Type': 'text/html'}}); });
  await assert.rejects(api.downloadDatabaseBackup('mall', 'token', 'mall', new AbortController().signal), /ZIP/);
  assert.equal(calls, 1);
});
