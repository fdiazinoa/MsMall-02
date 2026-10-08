import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';

const source = fs.readFileSync(new URL('../api.ts', import.meta.url), 'utf8');
const start = source.indexOf('  async getLoadLogs(');
const end = source.indexOf('  async reactivateStore', start);
assert.ok(start >= 0 && end > start);
const code = ts.transpileModule(
  'const api = {' + source.slice(start, end) + '}; result = api;',
  { compilerOptions: { target: ts.ScriptTarget.ES2022 } },
).outputText;
const denied = new Error('No tienes permiso para ver Monitor de Cargas.');
const context = {
  URLSearchParams,
  console: { error() {} },
  withAuthHeaders: (_token, headers) => headers,
  fetchJsonWithBaseFallback: async () => { throw denied; },
};
vm.runInNewContext(code, context);
await assert.rejects(
  context.result.getLoadLogs('mall-demo', 'test-token', { throwOnError: true }),
  (error) => error === denied,
);
assert.equal((await context.result.getLoadLogs('mall-demo', 'test-token')).length, 0);
console.log('Monitor receives authorization errors; existing callers keep their fallback.');
