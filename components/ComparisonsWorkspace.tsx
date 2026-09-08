import React, { useState } from 'react';
import { Building2, CalendarRange } from 'lucide-react';
import { MallComparison } from './MallComparison';
import { PeriodComparison } from './PeriodComparison';

export const ComparisonsWorkspace: React.FC = () => {
  const [view, setView] = useState<'malls' | 'periods'>('malls');
  return (
    <div className="space-y-4">
      <div className="inline-flex rounded-xl border border-slate-200 bg-white p-1 shadow-sm">
        <button type="button" onClick={() => setView('malls')} className={`inline-flex items-center gap-2 rounded-lg px-3 py-2 text-xs font-bold ${view === 'malls' ? 'bg-indigo-600 text-white' : 'text-slate-500'}`}><Building2 size={14} /> Entre malls</button>
        <button type="button" onClick={() => setView('periods')} className={`inline-flex items-center gap-2 rounded-lg px-3 py-2 text-xs font-bold ${view === 'periods' ? 'bg-indigo-600 text-white' : 'text-slate-500'}`}><CalendarRange size={14} /> Entre períodos</button>
      </div>
      {view === 'malls' ? <MallComparison /> : <PeriodComparison />}
    </div>
  );
};
