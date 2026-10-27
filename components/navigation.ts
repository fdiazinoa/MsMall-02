import { AppTab } from './appTabs';

export interface NavigationAccess {
  isAdmin?: boolean;
  isTic?: boolean;
  isAuditor?: boolean;
  canAccess: (key: string) => boolean;
}
export const navigationModules = [
  { id: 'general', label: 'General' },
  { id: 'audit', label: 'Auditoría IT' },
  { id: 'admin', label: 'Administración' },
  { id: 'tools', label: 'Herramientas' },
] as const;
export type NavigationModule = typeof navigationModules[number]['id'];
const staff = (a: NavigationAccess) => Boolean(a.isAdmin || a.isTic);
const permission = (key: string) => (a: NavigationAccess) => a.canAccess(key);
const staffed = (key: string) => (a: NavigationAccess) => staff(a) || a.canAccess(key);
const reporting = (key: string) => (a: NavigationAccess) => staff(a) || Boolean(a.isAuditor) || a.canAccess(key);
// The existing destinations and access policies live here for both desktop and mobile.
export const navigationItems: { id: AppTab; label: string; module: NavigationModule; allowed: (a: NavigationAccess) => boolean }[] = [
  { id: 'analytics', label: 'Dashboard BI', module: 'general', allowed: staffed('dashboard') },
  { id: 'big-data', label: 'Big Data', module: 'general', allowed: staffed('dashboard') },
  { id: 'operations', label: 'Operations Center', module: 'general', allowed: staffed('dashboard') },
  { id: 'insights', label: 'Inteligencia IA', module: 'general', allowed: staffed('dashboard') },
  { id: 'financial', label: 'Gestión Financiera', module: 'general', allowed: staffed('financial') },
  { id: 'cube', label: 'Cubo de Ventas', module: 'general', allowed: staffed('cube') },
  { id: 'comparisons', label: 'Comparativa Malls', module: 'general', allowed: reporting('comparisons') },
  { id: 'reports', label: 'Auditoría Ventas', module: 'general', allowed: reporting('sales_reports') },
  { id: 'monitor', label: 'Monitor de Cargas', module: 'audit', allowed: a => staff(a) || a.canAccess('monitor') || a.canAccess('imports') },
  { id: 'stores', label: 'Mantenimiento de Locales', module: 'admin', allowed: staffed('stores') },
  { id: 'store-catalogs', label: 'Catálogos Locales', module: 'admin', allowed: staffed('stores') },
  { id: 'malls', label: 'Gestión de Malls', module: 'admin', allowed: a => Boolean(a.isAdmin) || a.canAccess('malls') },
  { id: 'users', label: 'Usuarios y Roles', module: 'admin', allowed: a => Boolean(a.isAdmin) || a.canAccess('users') || a.canAccess('roles') },
  { id: 'backup-settings', label: 'Límites globales de backup', module: 'admin', allowed: permission('backup_settings') },
  { id: 'messaging', label: 'Mensajería Resend', module: 'admin', allowed: a => Boolean(a.isAdmin) },
  { id: 'copilot', label: 'Copilot MsMall', module: 'admin', allowed: a => Boolean(a.isAdmin) },
  { id: 'security', label: 'Seguridad Tokens', module: 'admin', allowed: a => Boolean(a.isAdmin) },
  { id: 'import-backup', label: 'Backup de importaciones', module: 'tools', allowed: permission('import_backup') },
  { id: 'auto-import', label: 'Importación FTP', module: 'tools', allowed: staffed('imports') },
  { id: 'erp-webservice', label: 'ERP Webservice', module: 'tools', allowed: staffed('imports') },
  { id: 'upload', label: 'Ingesta CSV', module: 'tools', allowed: staffed('imports') },
  { id: 'store-import', label: 'Importador Locales', module: 'tools', allowed: staffed('imports') },
];
export const visibleNavigation = (access: NavigationAccess) => navigationItems.filter(item => item.allowed(access));
export function searchNavigation<T extends { label: string }>(items: T[], query: string): T[] {
  const normalize = (text: string) => text.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase();
  return items.filter(item => normalize(item.label).includes(normalize(query.trim())));
}
export interface NavigationPreferences { module: string; open: boolean; pinned: boolean; favorites: AppTab[]; recent: AppTab[]; active?: AppTab }
export const defaultNavigationPreferences: NavigationPreferences = { module: 'general', open: false, pinned: false, favorites: [], recent: [] };
export function readNavigationPreferences(key: string): NavigationPreferences {
  try {
    const saved = JSON.parse(localStorage.getItem(key) || '{}');
    const ids = (value: unknown): AppTab[] => Array.isArray(value) ? [...new Set(value.filter(id => navigationItems.some(item => item.id === id)))].slice(0, 22) : [];
    return { module: navigationModules.some(m => m.id === saved.module) ? saved.module : 'general', open: saved.open === true, pinned: saved.pinned === true,
      favorites: ids(saved.favorites), recent: ids(saved.recent).slice(0, 8), active: navigationItems.find(item => item.id === saved.active)?.id };
  } catch { return { ...defaultNavigationPreferences }; }
}
