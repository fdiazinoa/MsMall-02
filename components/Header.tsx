import React, { useEffect, useState } from 'react';
import { useAuth } from '../context/AuthProvider';
import { Building, ChevronDown, Activity, AlertCircle } from 'lucide-react';
import { supabase } from '../api';
import { AppTab } from './appTabs';

interface HeaderProps {
  activeTab: AppTab;
  setActiveTab: (tab: AppTab) => void;
}

export const Header: React.FC<HeaderProps> = ({ activeTab, setActiveTab }) => {
  const { currentMall, malls, setCurrentMall, isAdmin, isTic, isAuditor } = useAuth();
  const [systemStatus, setSystemStatus] = useState<'operational' | 'down' | 'loading'>('loading');
  const [lastHeartbeat, setLastHeartbeat] = useState<string | null>(null);

  const mobileTabs: Array<{ id: AppTab; label: string; visible: boolean }> = [
    { id: 'analytics', label: 'Dashboard BI', visible: true },
    { id: 'big-data', label: 'Big Data', visible: true },
    { id: 'insights', label: 'Inteligencia IA', visible: true },
    { id: 'financial', label: 'Gestión Financiera', visible: true },
    { id: 'cube', label: 'Cubo de Ventas', visible: true },
    { id: 'comparisons', label: 'Comparativas BI', visible: true },
    { id: 'reports', label: 'Auditoría Ventas', visible: isAdmin || isTic || isAuditor },
    { id: 'operations', label: 'Operations Center', visible: isAdmin || isTic || isAuditor },
    { id: 'monitor', label: 'Monitor de Cargas', visible: isAdmin || isTic },
    { id: 'stores', label: 'Mantenimiento', visible: isAdmin || isTic },
    { id: 'store-catalogs', label: 'Catálogos Locales', visible: isAdmin || isTic },
    { id: 'auto-import', label: 'Importación FTP', visible: isAdmin || isTic },
    { id: 'erp-webservice', label: 'ERP Webservice', visible: isAdmin || isTic },
    { id: 'upload', label: 'Ingesta CSV', visible: isAdmin || isTic },
    { id: 'store-import', label: 'Importador Locales', visible: isAdmin || isTic },
    { id: 'malls', label: 'Gestión de Malls', visible: isAdmin },
    { id: 'users', label: 'Usuarios y Roles', visible: isAdmin },
    { id: 'messaging', label: 'Mensajería Resend', visible: isAdmin },
    { id: 'copilot', label: 'Copilot MsMall', visible: isAdmin },
    { id: 'security', label: 'Seguridad Tokens', visible: isAdmin }
  ];

  useEffect(() => {
    const checkHealth = async () => {
      try {
        const { data, error } = await supabase
          .from('system_health')
          .select('*')
          .eq('key', 'CRON_LAST_RUN')
          .single();

        if (error || !data) {
          // If table doesn't exist yet or no data, assume loading/unknown or down?
          // For MVP let's assume down if we can't find it.
          console.warn("Health check failed:", error);
          setSystemStatus('down');
          return;
        }

        const lastRun = new Date(data.value); // Value stores ISO string from worker
        const now = new Date();
        const diffMinutes = (now.getTime() - lastRun.getTime()) / (1000 * 60);

        setLastHeartbeat(lastRun.toLocaleTimeString());

        if (diffMinutes < 75) { // 60 min + 15 min buffer
          setSystemStatus('operational');
        } else {
          setSystemStatus('down');
        }

      } catch (e) {
        console.error("Error checking health:", e);
        setSystemStatus('down');
      }
    };

    checkHealth();
    const interval = setInterval(checkHealth, 60000); // Check every minute
    return () => clearInterval(interval);
  }, []);

  return (
    <>
      <header className="bg-white border-b border-slate-200 px-3 py-2 lg:px-5 sticky top-0 z-10">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0">
            <h2 className="text-base font-semibold text-slate-800 hidden md:block">Panel de Control de Auditoría</h2>

            {malls && malls.length > 0 && (
              <div className="relative group min-w-0">
                {malls.length > 1 ? (
                  <div className="relative">
                    <select
                      value={currentMall?.id || ''}
                      onChange={(e) => {
                        const selected = malls.find(m => m.id === e.target.value);
                        if (selected) setCurrentMall(selected);
                      }}
                      className="h-9 appearance-none bg-slate-100 border border-slate-200 text-slate-700 font-medium py-1.5 pl-9 pr-8 rounded-lg text-xs focus:outline-none focus:ring-2 focus:ring-indigo-500/20 cursor-pointer hover:bg-slate-200 transition-colors max-w-[200px] md:max-w-none"
                    >
                      {malls.map(mall => (
                        <option key={mall.id} value={mall.id}>{mall.nombre}</option>
                      ))}
                    </select>
                    <Building size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500 pointer-events-none" />
                    <ChevronDown size={14} className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 pointer-events-none" />
                  </div>
                ) : (
                  <div className="flex h-9 items-center gap-2 px-3 bg-slate-50 border border-slate-100 rounded-lg text-xs font-medium text-slate-600">
                    <Building size={14} className="text-indigo-500" />
                    {currentMall?.nombre}
                  </div>
                )}
              </div>
            )}
          </div>

          <div className="flex items-center gap-2 md:gap-4">
            <div className={`hidden md:flex items-center gap-2 px-3 py-1.5 rounded-full border ${systemStatus === 'operational'
              ? 'bg-emerald-50 border-emerald-200 text-emerald-700'
              : 'bg-red-50 border-red-200 text-red-700'
              } transition-colors duration-500`}>
              {systemStatus === 'operational' ? (
                <Activity size={14} className="animate-pulse" />
              ) : (
                <AlertCircle size={14} />
              )}
              <div className="flex flex-col leading-none">
                <span className="text-[10px] uppercase font-bold tracking-wider">
                  {systemStatus === 'operational' ? 'Sistema Operativo' : 'Sistema Detenido'}
                </span>
                {lastHeartbeat && (
                  <span className="text-[9px] opacity-80 font-mono">
                    Último latido: {lastHeartbeat}
                  </span>
                )}
              </div>
            </div>

            <span className="text-xs font-medium text-slate-400 hidden md:inline">v1.2.1</span>
          </div>
        </div>

        <div className="md:hidden mt-2">
          <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1">
            Módulo
          </label>
          <select
            value={activeTab}
            onChange={(e) => setActiveTab(e.target.value as AppTab)}
            className="w-full appearance-none bg-slate-100 border border-slate-200 text-slate-700 font-medium py-2 px-3 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20"
          >
            {mobileTabs.filter(t => t.visible).map(tab => (
              <option key={tab.id} value={tab.id}>{tab.label}</option>
            ))}
          </select>
        </div>
      </header>
    </>
  );
};
