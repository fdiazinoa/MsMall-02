import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';

const source = fs.readFileSync(new URL('../components/ImportManager.tsx', import.meta.url), 'utf8');
const start = source.indexOf('  const maskToRegex =');
const end = source.indexOf('  const resolveProcessedCountFromLogs', start);
assert.ok(start >= 0 && end > start);
const script = ts.transpileModule(
  source.slice(start, end) + '\nresult = filteredBatchCandidates;',
  { compilerOptions: { target: ts.ScriptTarget.ES2022 } },
).outputText;
const manualFiles = [
  { nombre: 'ERR_Ventas kryolan2026-07-16.txt', fecha: null },
  { nombre: 'ventas2026-07-17.txt', fecha: '2026-07-17' },
  { nombre: 'PR_Ventas kryolan2026-07-18.txt', fecha: null },
  { nombre: 'err_Ventas kryolan2026-07-19.txt', fecha: null },
  { nombre: 'Ventas2025.txt', fecha: null },
];
for (const batchMask of ['*2026*', '%2026%']) {
  const context = { manualFiles, batchMask, useMemo: (fn) => fn() };
  vm.runInNewContext(script, context);
  assert.deepEqual(
    Array.from(context.result, (file) => file.nombre).sort(),
    [manualFiles[0].nombre, manualFiles[1].nombre, manualFiles[3].nombre].sort(),
  );
}
console.log('Manual batch: error files match 2026 masks; processed files stay excluded.');
