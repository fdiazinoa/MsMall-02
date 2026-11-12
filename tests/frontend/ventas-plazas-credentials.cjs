const fs = require('node:fs');
const assert = require('node:assert/strict');
const ts = require('typescript');
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');
const source = fs.readFileSync('components/ImportManager.tsx', 'utf8');
const start = source.indexOf('{(editingConfig.protocolo !== \'WEBSERVICE\' || isMalalaWebservice)');
assert.ok(start >= 0);
const end = source.indexOf('\n                        )}', start) + '\n                        )}'.length;
const jsx = source.slice(start, end);
const output = ts.transpileModule(`function Credential({editingConfig, selectedApiProvider, isMalalaWebservice = false}) {
  const Server = () => null;
  const setEditingConfig = () => {};
  return <>${jsx}</>;
}`, { compilerOptions: { jsx: ts.JsxEmit.React, target: ts.ScriptTarget.ES2020 } }).outputText;
const Credential = new Function('React', output + '; return Credential;')(React);
function render(protocol, provider) {
  return renderToStaticMarkup(React.createElement(Credential, {
    editingConfig: { protocolo: protocol, usuario: 'equipment-test' }, selectedApiProvider: provider
  }));
}
assert.match(render('API', 'ventas_plazas'), /placeholder="X-Equipment-Id autorizado"/);
assert.match(render('API', 'ventas_plazas'), /value="equipment-test"/);
assert.match(render('API', 'studio_g'), /placeholder="Client ID"/);
for (const provider of ['cookieontop', 'invupos', 'bundaberg']) {
  assert.equal(render('API', provider), '');
}
assert.match(render('SFTP', 'studio_g'), /Nombre de usuario/);
assert.equal(render('WEBSERVICE', 'studio_g'), '');
console.log('Credential field rendering: 7 scenarios passed');

const handlerStart = source.indexOf('  const handleTestConnection = async () => {');
const handlerEnd = source.indexOf('\n  const applySavedConnection', handlerStart);
assert.ok(handlerStart >= 0 && handlerEnd > handlerStart);
const handlerCode = ts.transpileModule(source.slice(handlerStart, handlerEnd), {
  compilerOptions: { target: ts.ScriptTarget.ES2020 }
}).outputText;
async function testConnection(overrides = {}, password = 'jwt-test', stored = false) {
  const alerts = [];
  const requests = [];
  const handler = new Function('editingConfig', 'selectedApiProvider', 'tempPassword', 'hasStoredCredential',
    'testingConnection', 'setTestingConnection', 'ApiService', 'authToken', 'alert', 'console',
    handlerCode + '; return handleTestConnection;')(
      { protocolo: 'API', host: 'https://egord.ddns.net/api/Ventas/ConsultarVentas',
        ruta_remota: 'M021944', usuario: 'equipment-test', constants: {}, ...overrides },
      'ventas_plazas', password, stored, false, () => {},
      { testConnection: async (...args) => { requests.push(args); return { message: 'ok' }; } },
      'session-test', message => alerts.push(message), { log() {}, error() {} }
    );
  await handler();
  return { alerts, requests };
}
(async () => {
  for (const [overrides, expected] of [
    [{ host: '' }, /endpoint/], [{ ruta_remota: '.' }, /ID TPV/], [{ usuario: '' }, /X-Equipment-Id/]
  ]) {
    const result = await testConnection(overrides);
    assert.equal(result.requests.length, 0);
    assert.match(result.alerts[0], expected);
  }
  const missingToken = await testConnection({}, '');
  assert.equal(missingToken.requests.length, 0);
  assert.match(missingToken.alerts[0], /token JWT/);
  for (const [password, stored] of [['jwt-test', false], ['', true]]) {
    const valid = await testConnection({}, password, stored);
    assert.equal(valid.requests.length, 1);
    assert.equal(valid.requests[0][0].constants.provider, 'ventas_plazas');
    assert.equal(valid.requests[0][0].usuario, 'equipment-test');
    assert.equal(valid.requests[0][0].ruta_remota, 'M021944');
  }
  console.log('Connection validation and provider: 6 scenarios passed');
})().catch(error => { console.error(error); process.exitCode = 1; });
