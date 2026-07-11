
import React, { useState, useEffect } from 'react';
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  BarChart, Bar, LineChart, Line, Cell
} from 'recharts';
import {
  TrendingUp, TrendingDown, DollarSign, ShoppingBag,
  CreditCard, BarChart3, Calendar, Info, AreaChart as AreaChartIcon, LineChart as LineChartIcon, List
} from 'lucide-react';
import { KPIData, DateRange } from '../types';
import { ApiService } from '../api';
import { useFormatCurrency } from '../hooks/useFormatCurrency';

const COLORS = ['#6366f1', '#8b5cf6', '#a855f7', '#d946ef', '#ec4899'];

type TrendChartMode = 'area' | 'line' | 'bar';
type TopLocalesMode = 'list' | 'bar';

const ChartModeButton = ({ active, label, onClick, children }: {
  active: boolean;
  label: string;
  onClick: () => void;
  children: React.ReactNode;
}) => (
  <button
    type="button"
    aria-label={label}
    title={label}
    onClick={onClick}
    className={`flex h-8 w-8 items-center justify-center rounded-lg border transition-colors ${
      active
        ? 'border-indigo-200 bg-indigo-50 text-indigo-600'
        : 'border-slate-200 bg-white text-slate-400 hover:border-slate-300 hover:text-slate-700'
    }`}
  >
    {children}
  </button>
);

const KPICard = ({ title, value, icon: Icon, trend, color, tooltip }: any) => (
  <div className="bg-white p-6 rounded-2xl border border-slate-100 shadow-sm hover:shadow-md transition-shadow relative group">
    {tooltip && (
      <div className="absolute top-4 right-4 text-slate-300 hover:text-indigo-500 transition-colors cursor-help">
        <Info size={16} />
        <div className="absolute right-0 w-48 p-2 mt-2 text-xs text-white bg-slate-800 rounded-lg opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-10 shadow-lg top-full">
          {tooltip}
        </div>
      </div>
    )}
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

import { useAuth } from '../context/AuthProvider';

export const DashboardKPIs: React.FC = () => {
  const { currentMall, session } = useAuth();
  const { format } = useFormatCurrency();
  const [data, setData] = useState<KPIData | null>(null);
  const [loading, setLoading] = useState(true);
  const [trendChartMode, setTrendChartMode] = useState<TrendChartMode>('area');
  const [topLocalesMode, setTopLocalesMode] = useState<TopLocalesMode>('list');
  const [dates, setDates] = useState<DateRange>(() => {
    const now = new Date();
    const firstDay = new Date(now.getFullYear(), now.getMonth(), 1);
    return {
      startDate: firstDay.toISOString().split('T')[0],
      endDate: now.toISOString().split('T')[0]
    };
  });

  const loadKPIs = async () => {
    if (!currentMall?.id || !session?.access_token) {
      setData(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const kpis = await ApiService.getKPIs({ ...dates, mallId: currentMall.id }, session.access_token);
      setData(kpis);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadKPIs();
  }, [dates, currentMall?.id, session?.access_token]);

  if (!currentMall?.id) {
    return (
      <div className="bg-white border border-slate-200 rounded-2xl p-6 text-slate-700">
        No hay mall asignado o seleccionado para este usuario.
      </div>
    );
  }

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
        <div className="bg-white p-2 rounded-xl shadow-sm border border-slate-100 flex flex-wrap items-center gap-2 w-full md:w-auto">
          <Calendar size={16} className="text-slate-400 ml-2" />
          <input
            type="date"
            value={dates.startDate}
            onChange={(e) => setDates({ ...dates, startDate: e.target.value })}
            className="text-sm border-none focus:ring-0 outline-none p-1 min-w-[130px]"
          />
          <span className="text-slate-300">-</span>
          <input
            type="date"
            value={dates.endDate}
            onChange={(e) => setDates({ ...dates, endDate: e.target.value })}
            className="text-sm border-none focus:ring-0 outline-none p-1 min-w-[130px]"
          />
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <KPICard
          title="Ventas Netas"
          value={format(data.ventas_totales_neto || 0)}
          icon={DollarSign}
          trend={data.variacion_ventas}
          color="bg-indigo-500"
          tooltip="Total de ingresos sin impuestos en el periodo seleccionado."
        />
        <KPICard
          title="Transacciones"
          value={data.transacciones}
          icon={CreditCard}
          trend={2.4}
          color="bg-emerald-500"
          tooltip="Número total de operaciones de venta procesadas en el periodo seleccionado."
        />
        <KPICard
          title="Ticket Promedio"
          value={format(data.ticket_promedio || 0)}
          icon={ShoppingBag}
          trend={-1.2}
          color="bg-amber-500"
          tooltip="Promedio de venta por transacción: Ventas Totales / Número de Transacciones."
        />
        <KPICard
          title="Ventas Brutas"
          value={format(data.ventas_totales_bruto || 0)}
          icon={BarChart3}
          color="bg-rose-500"
          tooltip="Total de ingresos incluyendo impuestos en el periodo seleccionado."
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        <div className="lg:col-span-2 bg-white p-6 rounded-2xl border border-slate-100 shadow-sm">
          <div className="flex flex-wrap justify-between items-center gap-3 mb-8">
            <h4 className="font-bold text-slate-800">Tendencia de Ventas Diarias</h4>
            <div className="flex items-center gap-2">
              <div className="text-xs text-slate-400 mr-1">Últimos 7 días</div>
              <ChartModeButton active={trendChartMode === 'area'} label="Ver gráfica de área" onClick={() => setTrendChartMode('area')}>
                <AreaChartIcon size={16} />
              </ChartModeButton>
              <ChartModeButton active={trendChartMode === 'line'} label="Ver gráfica de línea" onClick={() => setTrendChartMode('line')}>
                <LineChartIcon size={16} />
              </ChartModeButton>
              <ChartModeButton active={trendChartMode === 'bar'} label="Ver gráfica de barras" onClick={() => setTrendChartMode('bar')}>
                <BarChart3 size={16} />
              </ChartModeButton>
            </div>
          </div>
          <div className="w-full overflow-x-auto">
            <div className="h-[300px] min-w-[560px]">
              <ResponsiveContainer width="100%" height="100%">
                {trendChartMode === 'area' ? (
                  <AreaChart data={data.ventas_por_dia} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
                    <defs>
                      <linearGradient id="colorTotal" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#6366f1" stopOpacity={0.1} />
                        <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                    <XAxis dataKey="fecha" axisLine={false} tickLine={false} tick={{ fill: '#94a3b8', fontSize: 12 }} />
                    <YAxis axisLine={false} tickLine={false} tick={{ fill: '#94a3b8', fontSize: 12 }} />
                    <Tooltip />
                    <Area type="monotone" dataKey="total" stroke="#6366f1" strokeWidth={3} fillOpacity={1} fill="url(#colorTotal)" />
                  </AreaChart>
                ) : trendChartMode === 'line' ? (
                  <LineChart data={data.ventas_por_dia} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                    <XAxis dataKey="fecha" axisLine={false} tickLine={false} tick={{ fill: '#94a3b8', fontSize: 12 }} />
                    <YAxis axisLine={false} tickLine={false} tick={{ fill: '#94a3b8', fontSize: 12 }} />
                    <Tooltip />
                    <Line type="monotone" dataKey="total" stroke="#6366f1" strokeWidth={3} dot={{ r: 3 }} activeDot={{ r: 5 }} />
                  </LineChart>
                ) : (
                  <BarChart data={data.ventas_por_dia} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                    <XAxis dataKey="fecha" axisLine={false} tickLine={false} tick={{ fill: '#94a3b8', fontSize: 12 }} />
                    <YAxis axisLine={false} tickLine={false} tick={{ fill: '#94a3b8', fontSize: 12 }} />
                    <Tooltip />
                    <Bar dataKey="total" fill="#6366f1" radius={[6, 6, 0, 0]} />
                  </BarChart>
                )}
              </ResponsiveContainer>
            </div>
          </div>
        </div>

        <div className="bg-white p-6 rounded-2xl border border-slate-100 shadow-sm">
          <div className="flex justify-between items-center gap-3 mb-8">
            <h4 className="font-bold text-slate-800">Top 5 Locales</h4>
            <div className="flex items-center gap-2">
              <ChartModeButton active={topLocalesMode === 'list'} label="Ver ranking compacto" onClick={() => setTopLocalesMode('list')}>
                <List size={16} />
              </ChartModeButton>
              <ChartModeButton active={topLocalesMode === 'bar'} label="Ver gráfica de barras" onClick={() => setTopLocalesMode('bar')}>
                <BarChart3 size={16} />
              </ChartModeButton>
            </div>
          </div>
          <div className="h-80 w-full overflow-y-auto pr-2">
            {topLocalesMode === 'list' ? (
              <div className="space-y-4">
                {data.top_locales.map((locale, index) => {
                  const maxTotal = Math.max(...data.top_locales.map(l => l.total));
                  const percent = maxTotal > 0 ? (locale.total / maxTotal) * 100 : 0;

                  return (
                    <div key={index} className="flex flex-col gap-1">
                      <div className="flex justify-between text-sm">
                        <span className="font-medium text-slate-700">{locale.name}</span>
                        <span className="text-slate-500 font-mono">{format(locale.total)}</span>
                      </div>
                      <div className="h-2 w-full bg-slate-100 rounded-full overflow-hidden">
                        <div
                          className="h-full rounded-full transition-all duration-500"
                          style={{
                            width: `${percent}%`,
                            backgroundColor: COLORS[index % COLORS.length]
                          }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={data.top_locales}
                  layout="vertical"
                  margin={{ top: 4, right: 12, left: 8, bottom: 4 }}
                >
                  <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#f1f5f9" />
                  <XAxis type="number" hide />
                  <YAxis
                    type="category"
                    dataKey="name"
                    width={90}
                    axisLine={false}
                    tickLine={false}
                    tick={{ fill: '#64748b', fontSize: 12 }}
                  />
                  <Tooltip />
                  <Bar dataKey="total" radius={[0, 6, 6, 0]}>
                    {data.top_locales.map((_locale, index) => (
                      <Cell key={`top-locale-${index}`} fill={COLORS[index % COLORS.length]} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>
      </div>

    </div>
  );
};
