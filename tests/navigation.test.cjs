const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');
const source = fs.readFileSync('components/navigation.ts', 'utf8');
const context = { exports: {}, localStorage: { getItem: () => context.saved } };
vm.runInNewContext(ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS } }).outputText, context);
const { navigationItems, visibleNavigation, searchNavigation, readNavigationPreferences } = context.exports;
const access = (keys, extra = {}) => ({ canAccess: key => keys.includes(key), ...extra });
test('every existing destination is declared exactly once and opens the existing AppTab', () => {
  const tabs = [...fs.readFileSync('components/appTabs.ts', 'utf8').matchAll(/'([^']+)'/g)].map(match => match[1]);
  assert.deepEqual(Array.from(navigationItems, item => item.id).sort(), tabs.sort());
  assert.equal(new Set(navigationItems.map(item => item.id)).size, tabs.length);
});
test('restricted users never get import, admin or finance options through search', () => {
  const items = visibleNavigation(access(['sales_reports']));
  assert.deepEqual(Array.from(items, item => item.id), ['reports']);
  assert.equal(searchNavigation(items, 'backup').length, 0);
  assert.equal(visibleNavigation(access([])).length, 0);
});
test('admin and delegated backup grants retain independent checks', () => {
  assert.equal(visibleNavigation(access([], { isAdmin: true })).length, navigationItems.length - 2);
  assert.deepEqual(Array.from(visibleNavigation(access(['import_backup'])), item => item.id), ['import-backup']);
  assert.deepEqual(Array.from(visibleNavigation(access(['backup_settings'])), item => item.id), ['backup-settings']);
});
test('module searches support accents and whitespace', () => {
  const items = visibleNavigation(access([], { isAdmin: true }));
  assert.equal(searchNavigation(items, '  auditoria ventas ')[0].id, 'reports');
  assert.equal(searchNavigation(items.filter(item => item.module === 'tools'), 'usuarios').length, 0);
});
test('stored preferences tolerate corrupted data, missing storage, invalid and duplicate destinations', () => {
  context.saved = '{broken'; assert.equal(readNavigationPreferences('x').open, false);
  context.saved = JSON.stringify({ module: 'payroll', pinned: true, open: true, favorites: ['reports', 'reports', 'unknown'], active: 'unknown' });
  const saved = readNavigationPreferences('x');
  assert.equal(saved.module, 'general'); assert.equal(saved.pinned, true);
  assert.deepEqual(Array.from(saved.favorites), ['reports']); assert.equal(saved.active, undefined);
  context.localStorage.getItem = () => { throw new Error('blocked'); };
  assert.equal(readNavigationPreferences('x').favorites.length, 0);
});
