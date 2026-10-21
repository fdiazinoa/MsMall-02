const assert = require('node:assert/strict');
const test = require('node:test');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');

function render(file, name, auth, props = {}) {
  const code = ts.transpileModule(fs.readFileSync(`${__dirname}/../components/${file}.tsx`, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.React, esModuleInterop: true }
  }).outputText;
  const context = { exports: {}, require: id => id.includes('AuthProvider') ? { useAuth: () => auth } : id === '../api' ? {} : require(id) };
  vm.runInNewContext(code, context);
  return renderToStaticMarkup(React.createElement(context.exports[name], props));
}
const auth = (permissions, isAdmin = false) => ({ isAdmin, canAccess: key => permissions.includes(key) });

test('backup-only role sees Backup under Herramientas without import tools or admin settings', () => {
  const html = render('Sidebar', 'Sidebar', auth(['import_backup']), { activeTab: 'import-backup' });
  assert(html.indexOf('Herramientas') < html.indexOf('Backup de importaciones'));
  assert(!html.includes('Importación FTP'));
  assert(!html.includes('Límites globales de backup'));
});
test('sales reports alone does not expose backup navigation', () => {
  const html = render('Sidebar', 'Sidebar', auth(['sales_reports']), { activeTab: 'reports' });
  assert(!html.includes('Backup de importaciones'));
});
test('admin settings appear in Administración before Herramientas', () => {
  const html = render('Sidebar', 'Sidebar', auth(['import_backup'], true), { activeTab: 'backup-settings' });
  assert(html.indexOf('Administración') < html.indexOf('Límites globales de backup'));
  assert(html.indexOf('Límites globales de backup') < html.indexOf('Herramientas'));
});
test('quota stays visible without administrative controls or removed legend', () => {
  const html = render('ImportBackupQuotaPanel', 'ImportBackupQuotaPanel', {}, { state: { can_configure: true, quota: {
    user: { downloads_remaining: 9, remaining_bytes: 200000000, active: 0 },
    mall: { remaining_bytes: 1000000000, active: 0 },
    limits: { user_daily_downloads: 10, user_daily_mb: 200, mall_daily_mb: 1000, max_file_mb: 50, max_range_days: 90, user_concurrency: 1, mall_concurrency: 2 },
    resets_at: '2026-10-22T04:00:00Z', timezone: 'America/Santo_Domingo'
  } }, cooldown: 30 });
  assert(html.includes('Tu cuota disponible'));
  assert(html.includes('30'));
  assert(!html.includes('Configurar límites globales'));
  assert(!html.includes('Las solicitudes fallidas'));
});
test('non-admin cannot render the global settings form', () => {
  const html = render('ImportBackupSettings', 'ImportBackupSettings', auth(['import_backup']));
  assert(html.includes('Solo un administrador'));
  assert(!html.includes('Guardar límites'));
});
