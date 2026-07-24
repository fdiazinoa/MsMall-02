
import React, { useState, useEffect, useMemo } from 'react';
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, BarChart, Bar, LineChart, Line
} from 'recharts';
import {
  TrendingUp, TrendingDown, DollarSign, ShoppingBag,
  CreditCard, BarChart3, Calendar, Info, X, Store, ArrowUpRight,
  AreaChart as AreaChartIcon, LineChart as LineChartIcon, List
} from 'lucide-react';
import { KPIData, DateRange, SegmentStoreDetail } from '../types';
import { ApiService, type Store as MallStore } from '../api';
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
  <div className="bg-white p-4 rounded-xl border border-slate-100 shadow-sm hover:shadow-md transition-shadow relative group">
    {tooltip && (
      <div className="absolute top-3 right-3 text-slate-300 hover:text-indigo-500 transition-colors cursor-help">
        <Info size={14} />
        <div className="absolute right-0 w-48 p-2 mt-2 text-xs text-white bg-slate-800 rounded-lg opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-10 shadow-lg top-full">
          {tooltip}
        </div>
      </div>
    )}
    <div className="flex justify-between items-start mb-3">
      <div className={`p-2.5 rounded-lg ${color} bg-opacity-10`}>
        <Icon className={`w-5 h-5 ${color.replace('bg-', 'text-')}`} />
      </div>
      {trend && (
        <span className={`flex items-center gap-1 text-xs font-bold px-2 py-1 rounded-full ${trend > 0 ? 'bg-green-50 text-green-600' : 'bg-red-50 text-red-600'}`}>
          {trend > 0 ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
          {Math.abs(trend)}%
        </span>
      )}
    </div>
    <p className="text-slate-500 text-xs font-semibold uppercase tracking-wide">{title}</p>
    <h3 className="text-xl font-bold text-slate-900 mt-1">{value}</h3>
  </div>
);

import { useAuth } from '../context/AuthProvider';

type SegmentItem = {
  name: string;
  value: number;
};

type SegmentSelection = {
  kind: 'tipo_negocio' | 'rubro';
  title: string;
  item: SegmentItem;
  stores: SegmentStoreDetail[];
};

const SegmentTooltip = ({ active, payload, format, total }: any) => {
  if (!active || !payload?.length) return null;
  const item = payload[0]?.payload;
  if (!item) return null;
  const share = total > 0 ? (Number(item.value || 0) / total) * 100 : 0;
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-3 py-2 shadow-lg">
      <p className="text-xs font-bold text-slate-800">{item.name}</p>
      <p className="text-xs text-slate-500">{format(item.value || 0)}</p>
      <p className="text-xs font-semibold text-indigo-500">{share.toFixed(1)}%</p>
    </div>
  );
};

const SegmentDonutCard = ({
  title,
  items,
  format,
  detailMap,
  onSelect,
}: {
  title: string;
  items: SegmentItem[];
  format: (value: number) => string;
  detailMap?: Record<string, SegmentStoreDetail[]>;
  onSelect: (selection: SegmentSelection) => void;
}) => {
  const visibleItems = (items || []).filter((item) => item.value > 0).slice(0, 5);
  const total = visibleItems.reduce((sum, item) => sum + item.value, 0);

  return (
    <div className="bg-white p-5 rounded-xl border border-slate-100 shadow-sm min-h-[300px]">
      <div className="flex items-center justify-between mb-4">
        <h4 className="font-bold text-slate-800">{title}</h4>
        <span className="text-xs text-slate-400">Top {visibleItems.length || 0}</span>
      </div>
      {visibleItems.length === 0 ? (
        <div className="h-48 flex items-center justify-center text-sm text-slate-400">
          Sin ventas en el periodo.
        </div>
      ) : (
        <div className="relative h-[260px] sm:h-[300px]">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={visibleItems}
                dataKey="value"
                nameKey="name"
                innerRadius="52%"
                outerRadius="84%"
                paddingAngle={2}
                stroke="white"
                strokeWidth={3}
                onClick={(item) => onSelect({
                  kind: 'tipo_negocio',
                  title,
                  item: item as SegmentItem,
                  stores: detailMap?.[(item as SegmentItem).name] || [],
                })}
              >
                {visibleItems.map((item, index) => (
                  <Cell
                    key={`tipo-cell-${item.name}`}
                    fill={COLORS[index % COLORS.length]}
                    className="cursor-pointer focus:outline-none"
                  />
                ))}
              </Pie>
              <Tooltip content={<SegmentTooltip format={format} total={total} />} />
            </PieChart>
          </ResponsiveContainer>
          <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
            <span className="text-[11px] font-bold uppercase text-slate-400">Total</span>
            <span className="text-base font-bold text-slate-800">{format(total)}</span>
          </div>
        </div>
      )}
    </div>
  );
};

const RubroExplorerCard = ({
  title,
  items,
  format,
  detailMap,
  onSelect,
}: {
  title: string;
  items: SegmentItem[];
  format: (value: number) => string;
  detailMap?: Record<string, SegmentStoreDetail[]>;
  onSelect: (selection: SegmentSelection) => void;
}) => {
  const visibleItems = (items || []).filter((item) => item.value > 0).slice(0, 8);
  const total = visibleItems.reduce((sum, item) => sum + item.value, 0);
  const maxValue = Math.max(...visibleItems.map((item) => item.value), 0);

  return (
    <div className="bg-white p-5 rounded-xl border border-slate-100 shadow-sm min-h-[300px]">
      <div className="flex items-center justify-between mb-5">
        <h4 className="font-bold text-slate-800">{title}</h4>
        <span className="text-xs text-slate-400">Top {visibleItems.length || 0}</span>
      </div>
      {visibleItems.length === 0 ? (
        <div className="h-48 flex items-center justify-center text-sm text-slate-400">
          Sin ventas en el periodo.
        </div>
      ) : (
        <div className="space-y-3">
          {visibleItems.map((item, index) => {
            const percent = maxValue > 0 ? (item.value / maxValue) * 100 : 0;
            const share = total > 0 ? (item.value / total) * 100 : 0;
            return (
              <button
                key={`rubro-${item.name}-${index}`}
                type="button"
                onClick={() => onSelect({
                  kind: 'rubro',
                  title,
                  item,
                  stores: detailMap?.[item.name] || [],
                })}
                className="group w-full rounded-lg border border-transparent px-2 py-2.5 text-left hover:border-slate-200 hover:bg-slate-50 transition-colors"
              >
                <div className="flex items-center justify-between gap-3">
                  <span className="min-w-0 flex items-center gap-2">
                    <span className="text-xs font-bold text-slate-400 w-5">{String(index + 1).padStart(2, '0')}</span>
                    <span className="text-sm font-semibold text-slate-700 truncate">{item.name}</span>
                  </span>
                  <span className="flex items-center gap-2 text-xs font-mono text-slate-500 whitespace-nowrap">
                    {format(item.value)}
                    <ArrowUpRight size={13} className="text-slate-300 group-hover:text-indigo-500" />
                  </span>
                </div>
                <div className="mt-2 flex items-center gap-3">
                  <div className="h-2 flex-1 rounded-full bg-slate-100 overflow-hidden">
                    <div
                      className="h-full rounded-full transition-all duration-500"
                      style={{
                        width: `${percent}%`,
                        background: `linear-gradient(90deg, ${COLORS[index % COLORS.length]}, ${COLORS[(index + 1) % COLORS.length]})`,
                      }}
                    />
                  </div>
                  <span className="w-12 text-right text-xs font-semibold text-slate-400">{share.toFixed(1)}%</span>
                </div>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
};

const SegmentDetailModal = ({
  selection,
  format,
  onClose,
}: {
  selection: SegmentSelection | null;
  format: (value: number) => string;
  onClose: () => void;
}) => {
  if (!selection) return null;
  const stores = selection.stores || [];
  const maxValue = Math.max(...stores.map((store) => store.total), 0);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/50 px-4 py-6">
      <div className="w-full max-w-3xl rounded-2xl bg-white shadow-2xl border border-slate-200 max-h-[88vh] overflow-hidden">
        <div className="flex items-start justify-between gap-4 border-b border-slate-100 px-6 py-5">
          <div>
            <p className="text-xs font-bold uppercase tracking-wide text-indigo-500">
              {selection.kind === 'tipo_negocio' ? 'Tipo de negocio' : 'Rubro'}
            </p>
            <h3 className="text-xl font-bold text-slate-900 mt-1">{selection.item.name}</h3>
            <p className="text-sm text-slate-500 mt-1">{format(selection.item.value)}</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="h-9 w-9 inline-flex items-center justify-center rounded-lg border border-slate-200 text-slate-500 hover:bg-slate-50 hover:text-slate-900"
            aria-label="Cerrar"
          >
            <X size={18} />
          </button>
        </div>

        <div className="px-6 py-5 overflow-y-auto max-h-[68vh]">
          {stores.length === 0 ? (
            <div className="h-40 flex flex-col items-center justify-center text-center text-slate-400">
              <Store size={24} />
              <p className="mt-2 text-sm">Sin detalle de locales para el periodo.</p>
            </div>
          ) : (
            <div className="space-y-3">
              {stores.map((store, index) => {
                const percent = maxValue > 0 ? (store.total / maxValue) * 100 : 0;
                const hasOperationalMetrics = store.transacciones > 0;
                return (
                  <div key={`${selection.item.name}-${store.name}`} className="rounded-xl border border-slate-100 p-4">
                    <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
                      <div className="min-w-0">
                        <p className="text-sm font-bold text-slate-800 truncate">
                          {index + 1}. {store.name}
                        </p>
                        <p className="text-xs text-slate-400 mt-1">
                          {hasOperationalMetrics ? `${store.transacciones} transacciones · ` : ''}
                          {store.participacion.toFixed(1)}% participación
                        </p>
                      </div>
                      <div className="text-left sm:text-right">
                        <p className="text-sm font-bold text-slate-900">{format(store.total)}</p>
                        <p className="text-xs text-slate-400">
                          {hasOperationalMetrics
                            ? `Neto ${format(store.total_neto)} · Ticket ${format(store.ticket_promedio)}`
                            : 'Detalle calculado desde ventas por tienda'}
                        </p>
                      </div>
                    </div>
                    <div className="mt-3 h-2 w-full rounded-full bg-slate-100 overflow-hidden">
                      <div
                        className="h-full rounded-full bg-indigo-500"
                        style={{ width: `${percent}%` }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

const formatDisplayName = (value: string) => value
  .split(' ')
  .map((part) => {
    if (!part || part !== part.toLowerCase()) return part;
    return part.charAt(0).toUpperCase() + part.slice(1);
  })
  .join(' ');

const normalizeSegmentLabel = (value: string | null | undefined, fallback: string) => {
  const label = String(value || '').trim();
  return label || fallback;
};

const buildFallbackSegmentDetails = (
  segmentName: string,
  kind: SegmentSelection['kind'],
  salesByStore: Record<string, number> | undefined,
  stores: MallStore[]
): SegmentStoreDetail[] => {
  if (!salesByStore || stores.length === 0) return [];

  const fallback = kind === 'tipo_negocio' ? 'Sin tipo de negocio' : 'Sin rubro';
  const rows = stores
    .filter((store) => {
      const segment = kind === 'tipo_negocio' ? store.tipo_negocio : store.rubro;
      return normalizeSegmentLabel(segment, fallback) === segmentName;
    })
    .map((store) => ({
      name: store.nombre,
      total: Number(salesByStore[store.nombre] || 0),
      total_neto: 0,
      transacciones: 0,
      ticket_promedio: 0,
      participacion: 0,
    }))
    .filter((store) => store.total > 0)
    .sort((a, b) => b.total - a.total)
    .slice(0, 10);

  const segmentTotal = rows.reduce((sum, store) => sum + store.total, 0);
  return rows.map((store) => ({
    ...store,
    participacion: segmentTotal > 0 ? (store.total / segmentTotal) * 100 : 0,
  }));
};

const buildFallbackDetailMap = (
  kind: SegmentSelection['kind'],
  items: SegmentItem[] | undefined,
  salesByStore: Record<string, number> | undefined,
  stores: MallStore[]
) => {
  return (items || []).reduce<Record<string, SegmentStoreDetail[]>>((map, item) => {
    const details = buildFallbackSegmentDetails(item.name, kind, salesByStore, stores);
    if (details.length > 0) {
      map[item.name] = details;
    }
    return map;
  }, {});
};

const mergeDetailMaps = (
  fallbackMap: Record<string, SegmentStoreDetail[]>,
  backendMap?: Record<string, SegmentStoreDetail[]>
) => {
  const merged = { ...fallbackMap };
  Object.entries(backendMap || {}).forEach(([segment, details]) => {
    if (details?.length) {
      merged[segment] = details;
    }
  });
  return merged;
};

export const DashboardKPIs: React.FC = () => {
  const { currentMall, session, user } = useAuth();
  const { format } = useFormatCurrency();
  const [data, setData] = useState<KPIData | null>(null);
  const [stores, setStores] = useState<MallStore[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedSegment, setSelectedSegment] = useState<SegmentSelection | null>(null);
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
      setStores([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const [kpis, mallStores] = await Promise.all([
        ApiService.getKPIs({ ...dates, mallId: currentMall.id }, session.access_token),
        ApiService.getStores(currentMall.id),
      ]);
      setData(kpis);
      setStores(mallStores);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadKPIs();
  }, [dates, currentMall?.id, session?.access_token]);

  const businessTypeDetailMap = useMemo(() => {
    const fallbackMap = buildFallbackDetailMap(
      'tipo_negocio',
      data?.ventas_por_tipo_negocio,
      data?.ventas_por_tienda_completo,
      stores
    );
    return mergeDetailMaps(fallbackMap, data?.ventas_por_tipo_negocio_top_locales);
  }, [data?.ventas_por_tipo_negocio, data?.ventas_por_tienda_completo, data?.ventas_por_tipo_negocio_top_locales, stores]);

  const rubroDetailMap = useMemo(() => {
    const fallbackMap = buildFallbackDetailMap(
      'rubro',
      data?.ventas_por_rubro,
      data?.ventas_por_tienda_completo,
      stores
    );
    return mergeDetailMaps(fallbackMap, data?.ventas_por_rubro_top_locales);
  }, [data?.ventas_por_rubro, data?.ventas_por_tienda_completo, data?.ventas_por_rubro_top_locales, stores]);

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

  const displayName = formatDisplayName(
    user?.nombre ||
    user?.name ||
    session?.user?.user_metadata?.full_name ||
    session?.user?.user_metadata?.name ||
    session?.user?.email?.split('@')[0] ||
    'usuario'
  );

  return (
    <div className="space-y-6 animate-in fade-in duration-500">
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
        <div className="space-y-1">
          <p className="text-2xl font-bold text-slate-900">Hola, {displayName}</p>
          <h2 className="pt-1 text-lg font-semibold text-slate-700">Business Intelligence</h2>
          <p className="text-sm text-slate-500">Indicadores clave de rendimiento del mall.</p>
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

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
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

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 bg-white p-5 rounded-xl border border-slate-100 shadow-sm">
          <div className="flex justify-between items-center mb-6">
            <h4 className="font-bold text-slate-800">Tendencia de Ventas Diarias</h4>
            <div className="flex items-center gap-2">
              <span className="text-xs text-slate-400 mr-1">Últimos 7 días</span>
              <ChartModeButton active={trendChartMode === 'area'} label="Ver gráfica de área" onClick={() => setTrendChartMode('area')}><AreaChartIcon size={16} /></ChartModeButton>
              <ChartModeButton active={trendChartMode === 'line'} label="Ver gráfica de línea" onClick={() => setTrendChartMode('line')}><LineChartIcon size={16} /></ChartModeButton>
              <ChartModeButton active={trendChartMode === 'bar'} label="Ver gráfica de barras" onClick={() => setTrendChartMode('bar')}><BarChart3 size={16} /></ChartModeButton>
            </div>
          </div>
          <div className="h-[300px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              {trendChartMode === 'area' ? <AreaChart data={data.ventas_por_dia} margin={{ top: 10, right: 18, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="colorTotal" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#6366f1" stopOpacity={0.1} />
                    <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                <XAxis
                  dataKey="fecha"
                  axisLine={false}
                  tickLine={false}
                  tick={{ fill: '#94a3b8', fontSize: 12 }}
                />
                <YAxis axisLine={false} tickLine={false} tick={{ fill: '#94a3b8', fontSize: 12 }} />
                <Tooltip />
                <Area
                  type="monotone"
                  dataKey="total"
                  stroke="#6366f1"
                  strokeWidth={3}
                  fillOpacity={1}
                  fill="url(#colorTotal)"
                />
              </AreaChart> : trendChartMode === 'line' ? <LineChart data={data.ventas_por_dia} margin={{ top: 10, right: 18, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                <XAxis dataKey="fecha" axisLine={false} tickLine={false} tick={{ fill: '#94a3b8', fontSize: 12 }} />
                <YAxis axisLine={false} tickLine={false} tick={{ fill: '#94a3b8', fontSize: 12 }} />
                <Tooltip />
                <Line type="monotone" dataKey="total" stroke="#6366f1" strokeWidth={3} dot={{ r: 3 }} activeDot={{ r: 5 }} />
              </LineChart> : <BarChart data={data.ventas_por_dia} margin={{ top: 10, right: 18, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                <XAxis dataKey="fecha" axisLine={false} tickLine={false} tick={{ fill: '#94a3b8', fontSize: 12 }} />
                <YAxis axisLine={false} tickLine={false} tick={{ fill: '#94a3b8', fontSize: 12 }} />
                <Tooltip />
                <Bar dataKey="total" fill="#6366f1" radius={[6, 6, 0, 0]} />
              </BarChart>}
            </ResponsiveContainer>
          </div>
        </div>

        <div className="bg-white p-5 rounded-xl border border-slate-100 shadow-sm">
          <div className="flex justify-between items-center gap-3 mb-6"><h4 className="font-bold text-slate-800">Top 5 Locales</h4><div className="flex items-center gap-2"><ChartModeButton active={topLocalesMode === 'list'} label="Ver ranking compacto" onClick={() => setTopLocalesMode('list')}><List size={16} /></ChartModeButton><ChartModeButton active={topLocalesMode === 'bar'} label="Ver gráfica de barras" onClick={() => setTopLocalesMode('bar')}><BarChart3 size={16} /></ChartModeButton></div></div>
          <div className="h-80 w-full overflow-y-auto pr-2">
            {topLocalesMode === 'list' ? <div className="space-y-4">
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
            </div> : <ResponsiveContainer width="100%" height="100%"><BarChart data={data.top_locales} layout="vertical" margin={{ top: 4, right: 12, left: 8, bottom: 4 }}><CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#f1f5f9" /><XAxis type="number" hide /><YAxis type="category" dataKey="name" width={90} axisLine={false} tickLine={false} tick={{ fill: '#64748b', fontSize: 12 }} /><Tooltip /><Bar dataKey="total" radius={[0, 6, 6, 0]}>{data.top_locales.map((_locale, index) => <Cell key={`top-locale-${index}`} fill={COLORS[index % COLORS.length]} />)}</Bar></BarChart></ResponsiveContainer>}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <SegmentDonutCard
          title="Ventas por Tipo de Negocio"
          items={data.ventas_por_tipo_negocio || []}
          format={format}
          detailMap={businessTypeDetailMap}
          onSelect={setSelectedSegment}
        />
        <RubroExplorerCard
          title="Ventas por Rubro"
          items={data.ventas_por_rubro || []}
          format={format}
          detailMap={rubroDetailMap}
          onSelect={setSelectedSegment}
        />
      </div>

      <SegmentDetailModal
        selection={selectedSegment}
        format={format}
        onClose={() => setSelectedSegment(null)}
      />

    </div>
  );
};
