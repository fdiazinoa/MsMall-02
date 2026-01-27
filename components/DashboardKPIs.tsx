
import React, { useState, useEffect } from 'react';
import { 
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  BarChart, Bar, Cell
} from 'recharts';
import { 
  TrendingUp, TrendingDown, DollarSign, ShoppingBag, 
  CreditCard, BarChart3, Calendar 
} from 'lucide-react';
import { KPIData, DateRange } from '../types';
import { ApiService } from '../api';

const COLORS = ['#6366f1', '#8b5cf6', '#a855f7', '#d946ef', '#ec4899'];

const KPICard = ({ title, value, icon: Icon, trend, color }: any) => (
  <div className="bg-white p-6 rounded-2xl border border-slate-100 shadow-sm hover:shadow-md transition-shadow">
    <div className="flex justify-between items-start mb-4">
      <div className={`p-3 rounded-xl ${color} bg-opacity-10`}>
        <Icon className={`w-6 h-6 ${color.replace('bg-', 'text-')}`} />
      </div>
      {trend && (
        <span className={`flex items-center gap-1 text-xs font-bold px-2 py-1 rounded-full ${trend > 0 ? 'bg-green-50 text-green-600' : 'bg-red-50 text-red-600'}`}>
          {trend > 0 ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
          {Math.abs(trend)}%
        </span>
      )}
    </div>
    <p className="text-slate-500 text-sm font-medium">{title}</p>
    <h3 className="text-2xl font-bold text-slate-900 mt-1">{value}</h3>
  </div>
);

export const DashboardKPIs: React.FC = () => {
  const [data, setData] = useState<KPIData | null>(null);
  const [loading, setLoading] = useState(true);
  const [dates, setDates] = useState<DateRange>({
    startDate: '2024-01-20',
    endDate: '2024-01-26'
  });

  const loadKPIs = async () => {
    setLoading(true);
    try {
      const kpis = await ApiService.getKPIs(dates);
      setData(kpis);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadKPIs();
  }, [dates]);

  if (loading || !data) return (
    <div className="flex items-center justify-center h-96">
      <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600"></div>
    </div>
  );

  return (
    <div className="space-y-8 animate-in fade-in duration-500">
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
        <div>
          <h2 className="text-2xl font-bold text-slate-800">Business Intelligence</h2>
          <p className="text-slate-500">Indicadores clave de rendimiento del mall.</p>
        </div>
        <div className="bg-white p-2 rounded-xl shadow-sm border border-slate-100 flex items-center gap-2">
          <Calendar size={16} className="text-slate-400 ml-2" />
          <input 
            type="date" 
            value={dates.startDate}
            onChange={(e) => setDates({...dates, startDate: e.target.value})}
            className="text-sm border-none focus:ring-0 outline-none p-1"
          />
          <span className="text-slate-300">-</span>
          <input 
            type="date" 
            value={dates.endDate}
            onChange={(e) => setDates({...dates, endDate: e.target.value})}
            className="text-sm border-none focus:ring-0 outline-none p-1"
          />
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <KPICard 
          title="Ventas Brutas" 
          value={`$${data.ventas_totales_bruto.toLocaleString()}`} 
          icon={DollarSign} 
          trend={data.variacion_ventas}
          color="bg-indigo-500"
        />
        <KPICard 
          title="Transacciones" 
          value={data.transacciones} 
          icon={CreditCard} 
          trend={2.4}
          color="bg-emerald-500"
        />
        <KPICard 
          title="Ticket Promedio" 
          value={`$${data.ticket_promedio.toFixed(2)}`} 
          icon={ShoppingBag} 
          trend={-1.2}
          color="bg-amber-500"
        />
        <KPICard 
          title="Ventas Netas" 
          value={`$${data.ventas_totales_neto.toLocaleString()}`} 
          icon={BarChart3} 
          color="bg-rose-500"
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        <div className="lg:col-span-2 bg-white p-6 rounded-2xl border border-slate-100 shadow-sm">
          <div className="flex justify-between items-center mb-8">
            <h4 className="font-bold text-slate-800">Tendencia de Ventas Diarias</h4>
            <div className="text-xs text-slate-400">Últimos 7 días</div>
          </div>
          <div className="h-80 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={data.ventas_por_dia}>
                <defs>
                  <linearGradient id="colorTotal" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#6366f1" stopOpacity={0.1}/>
                    <stop offset="95%" stopColor="#6366f1" stopOpacity={0}/>
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                <XAxis 
                  dataKey="fecha" 
                  axisLine={false} 
                  tickLine={false} 
                  tick={{fill: '#94a3b8', fontSize: 12}}
                  tickFormatter={(val) => val.split('-').slice(2).join('/')}
                />
                <YAxis axisLine={false} tickLine={false} tick={{fill: '#94a3b8', fontSize: 12}} />
                <Tooltip 
                  contentStyle={{borderRadius: '12px', border: 'none', boxShadow: '0 4px 12px rgba(0,0,0,0.1)'}}
                />
                <Area 
                  type="monotone" 
                  dataKey="total" 
                  stroke="#6366f1" 
                  strokeWidth={3}
                  fillOpacity={1} 
                  fill="url(#colorTotal)" 
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="bg-white p-6 rounded-2xl border border-slate-100 shadow-sm">
          <h4 className="font-bold text-slate-800 mb-8">Top 5 Locales</h4>
          <div className="h-80 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart layout="vertical" data={data.top_locales}>
                <XAxis type="number" hide />
                <YAxis 
                  dataKey="name" 
                  type="category" 
                  axisLine={false} 
                  tickLine={false} 
                  width={80}
                  tick={{fill: '#475569', fontSize: 12, fontWeight: 500}}
                />
                <Tooltip 
                  cursor={{fill: 'transparent'}}
                  contentStyle={{borderRadius: '12px', border: 'none', boxShadow: '0 4px 12px rgba(0,0,0,0.1)'}}
                />
                <Bar dataKey="total" radius={[0, 8, 8, 0]} barSize={20}>
                  {data.top_locales.map((_entry, index) => (
                    <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
    </div>
  );
};
