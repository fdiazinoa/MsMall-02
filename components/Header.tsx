
import React from 'react';

export const Header: React.FC = () => {
  return (
    <header className="h-16 bg-white border-b border-slate-200 flex items-center justify-between px-6 sticky top-0 z-10">
      <div className="flex items-center gap-4">
        <h2 className="text-lg font-semibold text-slate-800">Panel de Control de Auditoría</h2>
      </div>
      <div className="flex items-center gap-3">
        <span className="flex items-center gap-1.5 text-xs font-bold text-indigo-600 bg-indigo-50 px-2.5 py-1 rounded-full border border-indigo-100">
          <span className="w-2 h-2 bg-indigo-500 rounded-full animate-pulse"></span>
          MVP ACTIVO
        </span>
        <span className="text-xs font-medium text-slate-400">v1.0.2</span>
      </div>
    </header>
  );
};
