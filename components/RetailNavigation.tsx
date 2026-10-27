import React, { useEffect, useRef, useState } from 'react';
import { Activity, BarChart3, Building2, Wrench, Search, Star, Pin, PinOff, X, LogOut, KeyRound, ChevronRight } from 'lucide-react';
import { useAuth } from '../context/AuthProvider';
import { AppTab } from './appTabs';
import { defaultNavigationPreferences, navigationModules, readNavigationPreferences, searchNavigation, visibleNavigation } from './navigation';
import './navigation.css';

const moduleIcons = { general: BarChart3, audit: Activity, admin: Building2, tools: Wrench };
interface Props { activeTab: AppTab; setActiveTab: (tab: AppTab) => void; onPassword: () => void }

export function RetailNavigation(props: Props) {
  const auth = useAuth();
  const key = `msmall.navigation.v1:${auth.session?.user?.id || auth.user?.id || 'anonymous'}:${auth.currentMall?.id || 'none'}`;
  // Remount only navigation preferences when the user/mall changes; the work area stays mounted.
  return <NavigationPanel key={key} {...props} storageKey={key} access={auth} />;
}
function NavigationPanel({ activeTab, setActiveTab, onPassword, storageKey, access }: Props & { key?: string; storageKey: string; access: ReturnType<typeof useAuth> }) {
  const items = visibleNavigation(access);
  const modules = navigationModules.filter(module => items.some(item => item.module === module.id));
  const [preferences, setPreferences] = useState(() => readNavigationPreferences(storageKey));
  const [globalSearch, setGlobalSearch] = useState(false);
  const [query, setQuery] = useState('');
  const [smallScreen, setSmallScreen] = useState(() => typeof window !== 'undefined' && window.matchMedia('(max-width: 767px)').matches);
  const panelRef = useRef<HTMLElement>(null);
  const railRef = useRef<HTMLElement>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const restored = useRef(false);
  const open = preferences.open && items.length > 0;
  const selectedModule = modules.find(module => module.id === preferences.module) || modules[0];
  const activeModule = items.find(item => item.id === activeTab)?.module;
  const pinned = preferences.pinned && !smallScreen;
  const setActiveTabRef = useRef(setActiveTab);
  setActiveTabRef.current = setActiveTab;
  const accessibleIds = items.map(item => item.id).join(',');

  useEffect(() => {
    const media = window.matchMedia('(max-width: 767px)');
    const update = () => setSmallScreen(media.matches);
    media.addEventListener('change', update);
    return () => media.removeEventListener('change', update);
  }, []);
  useEffect(() => {
    if (!restored.current && items.length > 0) {
      restored.current = true;
      const saved = items.find(item => item.id === preferences.active);
      if (saved) setActiveTabRef.current(saved.id);
    }
    // Remembered entries are filtered at render time, including after permission changes.
    // The stable ID list tracks visibility without depending on a recreated auth object.
  }, [accessibleIds]);
  useEffect(() => {
    if (!items.some(item => item.id === activeTab)) return;
    setPreferences(previous => ({ ...previous, active: activeTab,
      recent: [activeTab, ...previous.recent.filter(id => id !== activeTab)].slice(0, 8) }));
  }, [activeTab, accessibleIds]);
  useEffect(() => {
    try { localStorage.setItem(storageKey, JSON.stringify(preferences)); } catch { /* Navigation remains usable with storage disabled. */ }
  }, [preferences, storageKey]);

  function close(restoreFocus = true) {
    setPreferences(previous => ({ ...previous, open: false }));
    if (restoreFocus) triggerRef.current?.focus();
  }
  useEffect(() => {
    if (!open) return;
    searchRef.current?.focus();
    const outside = (event: PointerEvent) => {
      const target = event.target as Node;
      if (!panelRef.current?.contains(target) && !railRef.current?.contains(target)) close(false);
    };
    document.addEventListener('pointerdown', outside);
    return () => document.removeEventListener('pointerdown', outside);
  }, [open]);
  useEffect(() => {
    if (!open) return;
    const keydown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        if (event.defaultPrevented) return;
        event.preventDefault(); close();
      }
      if (event.key === 'Tab' && smallScreen) {
        const focusable = panelRef.current?.querySelectorAll<HTMLElement>('button:not(:disabled), input');
        if (!focusable?.length) return;
        const first = focusable[0]; const last = focusable[focusable.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
      }
    };
    document.addEventListener('keydown', keydown);
    const shell = railRef.current?.parentElement?.querySelector<HTMLElement>(':scope > .min-h-0');
    const previousInert = shell?.inert;
    if (smallScreen && shell) shell.inert = true;
    return () => {
      document.removeEventListener('keydown', keydown);
      if (shell) shell.inert = Boolean(previousInert);
    };
  }, [open, smallScreen]);

  function show(module: string, trigger: HTMLButtonElement, search = false) {
    triggerRef.current = trigger;
    setGlobalSearch(search); setQuery('');
    setPreferences(previous => ({ ...previous, module, open: true }));
    if (open) searchRef.current?.focus();
  }
  function navigate(id: AppTab) {
    if (!items.some(item => item.id === id)) return;
    setActiveTab(id);
    setPreferences(previous => ({ ...previous, module: items.find(item => item.id === id)!.module,
      active: id, recent: [id, ...previous.recent.filter(tab => tab !== id)].slice(0, 8), open: pinned }));
    if (!pinned) triggerRef.current?.focus();
  }
  const filtered = searchNavigation(globalSearch ? items : items.filter(item => item.module === selectedModule?.id), query);
  const renderItem = (item: typeof items[number]) => <div key={item.id} className={`ms-nav-option ${activeTab === item.id ? 'is-active' : ''}`}>
    <button className="ms-nav-destination" onClick={() => navigate(item.id)} aria-current={activeTab === item.id ? 'page' : undefined}>
      <span>{item.label}</span><ChevronRight size={15} aria-hidden="true" />
    </button>
    <button className="ms-nav-star" aria-label={`${preferences.favorites.includes(item.id) ? 'Quitar de' : 'Añadir a'} favoritos: ${item.label}`}
      aria-pressed={preferences.favorites.includes(item.id)} onClick={() => setPreferences(previous => ({ ...previous,
        favorites: previous.favorites.includes(item.id) ? previous.favorites.filter(id => id !== item.id) : [...previous.favorites, item.id] }))}>
      <Star size={16} fill={preferences.favorites.includes(item.id) ? 'currentColor' : 'none'} aria-hidden="true" />
    </button>
  </div>;
  const section = (label: string, ids: AppTab[]) => {
    const entries = ids.map(id => items.find(item => item.id === id)).filter((item): item is typeof items[number] => Boolean(item));
    return entries.length > 0 && <section className="ms-nav-section" aria-label={label}><h3>{label}</h3>{entries.map(renderItem)}</section>;
  };
  return <>
    <aside ref={railRef} className="ms-nav-rail" aria-label="Navegación principal">
      <img src="/msmall-icon-192.png" alt="MsMall" width="34" height="34" className="ms-nav-logo" />
      <button className="ms-nav-icon" title="Buscar en MsMall" aria-label="Buscar en MsMall" aria-controls="msmall-navigation-panel" aria-expanded={open && globalSearch}
        onClick={event => show(selectedModule?.id || defaultNavigationPreferences.module, event.currentTarget, true)}><Search size={21} /></button>
      <nav className="ms-nav-modules" aria-label="Módulos" onKeyDown={event => {
        if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) return;
        const buttons = Array.from<HTMLButtonElement>(event.currentTarget.querySelectorAll('button'));
        const index = buttons.indexOf(document.activeElement as HTMLButtonElement);
        const next = event.key === 'Home' ? 0 : event.key === 'End' ? buttons.length - 1 : (index + (event.key === 'ArrowDown' ? 1 : -1) + buttons.length) % buttons.length;
        event.preventDefault(); buttons[next]?.focus();
      }}>
        {modules.map(module => { const Icon = moduleIcons[module.id]; return <button key={module.id} className={`ms-nav-icon ${activeModule === module.id ? 'is-active' : ''} ${open && selectedModule?.id === module.id && !globalSearch ? 'is-open' : ''}`}
          title={module.label} aria-label={module.label} aria-current={activeModule === module.id ? 'true' : undefined} aria-expanded={open && selectedModule?.id === module.id && !globalSearch}
          aria-controls="msmall-navigation-panel" onClick={event => show(module.id, event.currentTarget)}><Icon size={21} /><span className="ms-nav-tooltip">{module.label}</span></button>; })}
      </nav>
      <div className="ms-nav-account">
        <button className="ms-nav-icon" title="Cambiar Contraseña" aria-label="Cambiar Contraseña" onClick={() => { close(false); onPassword(); }}><KeyRound size={20} /></button>
        <button className="ms-nav-icon" title="Cerrar Sesión" aria-label="Cerrar Sesión" onClick={access.signOut}><LogOut size={20} /></button>
      </div>
    </aside>
    {open && <>
      {smallScreen && <div className="ms-nav-backdrop" aria-hidden="true" onClick={() => close()} />}
      <section ref={panelRef} id="msmall-navigation-panel" className="ms-nav-panel" role={smallScreen ? 'dialog' : 'region'} aria-modal={smallScreen || undefined} aria-labelledby="ms-nav-title">
        <header className="ms-nav-panel-heading"><div><span className="ms-nav-brand">MSMALL</span><h2 id="ms-nav-title">{globalSearch ? 'Buscar en MsMall' : selectedModule?.label}</h2></div>
          <div className="ms-nav-actions">{!smallScreen && <button aria-label={pinned ? 'Desfijar panel' : 'Fijar panel'} title={pinned ? 'Desfijar panel' : 'Fijar panel'} aria-pressed={pinned} onClick={() => setPreferences(previous => ({ ...previous, pinned: !previous.pinned }))}>{pinned ? <PinOff size={18} /> : <Pin size={18} />}</button>}
            <button aria-label="Cerrar navegación" onClick={() => close()}><X size={20} /></button></div>
        </header>
        <label className="ms-nav-search"><Search size={17} aria-hidden="true" /><input ref={searchRef} value={query} onChange={event => setQuery(event.target.value)} aria-label={globalSearch ? 'Buscar en todos los módulos' : 'Buscar en este módulo'} placeholder={globalSearch ? 'Buscar opciones…' : 'Buscar en el módulo…'} /></label>
        <div className="ms-nav-scroll">
          <nav className="ms-nav-section" aria-label={globalSearch ? 'Resultados generales' : selectedModule?.label}><h3>{globalSearch ? 'Todos los módulos' : 'Opciones del módulo'}</h3>
            {filtered.map(renderItem)}{!filtered.length && <p className="ms-nav-empty" role="status">No hay opciones disponibles{query ? ' para esta búsqueda' : ''}.</p>}
          </nav>
          {!query && <>{section('Favoritos', preferences.favorites)}{section('Recientes', preferences.recent)}</>}
        </div>
        <footer className="ms-nav-footer"><span>{access.user?.nombre_completo || 'Usuario'}</span><small>{access.role || 'MsMall'}</small></footer>
      </section>
    </>}
  </>;
}
