import React from 'react';
import { useAuth } from '../context/AuthProvider';
import { Building, ChevronDown } from 'lucide-react';

export const Header: React.FC = () => {
  const { currentMall, malls, setCurrentMall } = useAuth();

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

      <div className="flex items-center gap-3">
        <span className="flex items-center gap-1.5 text-xs font-bold text-indigo-600 bg-indigo-50 px-2.5 py-1 rounded-full border border-indigo-100">
          <span className="w-2 h-2 bg-indigo-500 rounded-full animate-pulse"></span>
          MVP ACTIVO
        </span>
        <span className="text-xs font-medium text-slate-400">v1.1.0</span>
      </div>
    </header>
  );
};
