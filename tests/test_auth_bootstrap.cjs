const assert = require('node:assert/strict');
const test = require('node:test');
const vm = require('node:vm');
const fs = require('node:fs');
const ts = require('typescript');

function harness() {
  let effect, callback;
  const requests = [], profiles = [], scheduled = new Map();
  let sequence = 0, unsubscribed = false;
  const react = {
    createContext: () => ({}), createElement: () => null,
    useRef: value => ({current: value}),
    useContext: () => ({}), useState: value => [value, () => {}],
    useEffect: fn => { effect = fn; },
  };
  react.default = react;
  const supabase = {
    auth: {
      onAuthStateChange: fn => { callback = fn; return {data: {subscription: {unsubscribe: () => {unsubscribed = true;}}}}; },
    },
    from: () => ({select: () => ({eq: (_key, id) => ({single: async () => {profiles.push(id); return {data: {role: 'admin'}};}})})}),
  };
  const source = fs.readFileSync(require('node:path').join(__dirname, '../context/AuthProvider.tsx'), 'utf8')
    .replaceAll('import.meta.env', 'testEnv');
  const js = ts.transpileModule(source, {compilerOptions: {target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.React}}).outputText;
  const context = {
    exports: {}, require: name => {
      if (name === 'react') return react;
      if (name.includes('authRequests')) {
        const helpers = { ...context, exports: {} };
        const helperSource = fs.readFileSync(require('node:path').join(__dirname, '../utils/authRequests.js'), 'utf8');
        vm.runInNewContext(ts.transpileModule(helperSource, {compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022}}).outputText, helpers);
        return helpers.exports;
      }
      return {supabase};
    },
    testEnv: {VITE_API_URL: 'msmall-02-production.up.railway.app'},
    window: {location: {href: 'https://msmall.vercel.app/', hostname: 'msmall.vercel.app'}},
    URL, URLSearchParams, AbortSignal, console: {log: () => {}, warn: console.warn, error: console.error},
    localStorage: {getItem: () => null, setItem: () => {}, removeItem: () => {}},
    setTimeout: fn => {scheduled.set(++sequence, fn); return sequence;},
    clearTimeout: id => scheduled.delete(id),
    fetch: async url => {
      requests.push(url);
      const payload = url.endsWith('/access') ? {role: 'admin', permissions: {}} : [{id:'mall-1', nombre:'Mall'}];
      return {ok: true, status: 200, json: async () => payload};
    },
  };
  vm.runInNewContext(js, context);
  context.exports.AuthProvider({children: null});
  const cleanup = effect();
  return {
    emit: (event, token = 'token-1') => callback(event, token ? {access_token:token, user:{id:'user-1'}} : null),
    flush: async () => {for (const [id, fn] of scheduled) {scheduled.delete(id); fn();} for(let i=0;i<10;i++) await Promise.resolve();},
    requests, profiles, cleanup, unsubscribed: () => unsubscribed,
  };
}

test('initial and repeated sign-in events load once, with a valid Railway URL', async () => {
  const h = harness();
  h.emit('INITIAL_SESSION'); h.emit('SIGNED_IN');
  assert.equal(h.requests.length, 0, 'queries must wait until the auth callback ends');
  await h.flush();
  assert.deepEqual(h.requests, [
    'https://msmall-02-production.up.railway.app/api/v1/users/me/access',
    'https://msmall-02-production.up.railway.app/api/v1/users/me/malls',
  ]);
  assert.equal(h.profiles.length, 1);
  h.emit('SIGNED_IN'); await h.flush();
  assert.equal(h.requests.length, 2);
  h.emit('TOKEN_REFRESHED', 'token-2'); await h.flush();
  assert.equal(h.requests.length, 4);
  h.emit('USER_UPDATED', 'token-2'); await h.flush();
  assert.equal(h.requests.length, 6);
});

test('sign-out and unmount cancel deferred loads; a new login can load again', async () => {
  const h = harness();
  h.emit('INITIAL_SESSION'); h.emit('SIGNED_OUT', null); await h.flush();
  assert.equal(h.requests.length, 0);
  h.emit('SIGNED_IN'); await h.flush();
  assert.equal(h.requests.length, 2);
  h.emit('TOKEN_REFRESHED', 'token-2'); h.cleanup(); await h.flush();
  assert.equal(h.requests.length, 2);
  assert.equal(h.unsubscribed(), true);
});
