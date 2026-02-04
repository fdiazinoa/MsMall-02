import React, { useEffect, useState } from 'react';
import { useAuth } from '../context/AuthProvider';
import { Building, ChevronDown, Activity, AlertCircle } from 'lucide-react';
import { supabase } from '../api';

export const Header: React.FC = () => {
  const { currentMall, malls, setCurrentMall } = useAuth();
  const [systemStatus, setSystemStatus] = useState<'operational' | 'down' | 'loading'>('loading');
  const [lastHeartbeat, setLastHeartbeat] = useState<string | null>(null);

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
    <header className="h-16 bg-white border-b border-slate-200 flex items-center justify-between px-6 sticky top-0 z-10">
      <div className="flex items-center gap-4">
        <h2 className="text-lg font-semibold text-slate-800 hidden md:block">Panel de Control de Auditoría</h2>

        {/* Mall Selector */}
        {malls && malls.length > 0 && (
          <div className="relative group">
            {malls.length > 1 ? (
              <div className="relative">
                <select
                  value={currentMall?.id || ''}
                  onChange={(e) => {
                    const selected = malls.find(m => m.id === e.target.value);
                    if (selected) setCurrentMall(selected);
                  }}
                  className="appearance-none bg-slate-100 border border-slate-200 text-slate-700 font-medium py-1.5 pl-9 pr-8 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20 cursor-pointer hover:bg-slate-200 transition-colors"
                >
                  {malls.map(mall => (
                    <option key={mall.id} value={mall.id}>{mall.nombre}</option>
                  ))}
                </select>
                <Building size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500 pointer-events-none" />
                <ChevronDown size={14} className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 pointer-events-none" />
              </div>
            ) : (
              <div className="flex items-center gap-2 px-3 py-1.5 bg-slate-50 border border-slate-100 rounded-lg text-sm font-medium text-slate-600">
                <Building size={14} className="text-indigo-500" />
                {currentMall?.nombre}
              </div>
            )}
          </div>
        )}
      </div>

      <div className="flex items-center gap-4">
        {/* System Health Indicator */}
        <div className={`flex items-center gap-2 px-3 py-1.5 rounded-full border ${systemStatus === 'operational'
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

        <span className="flex items-center gap-1.5 text-xs font-bold text-indigo-600 bg-indigo-50 px-2.5 py-1 rounded-full border border-indigo-100 hidden md:flex">
          <span className="w-2 h-2 bg-indigo-500 rounded-full animate-pulse"></span>
          MVP ACTIVO
        </span>
        <span className="text-xs font-medium text-slate-400 hidden md:inline">v1.2.0</span>
      </div>
    </header>
  );
};
