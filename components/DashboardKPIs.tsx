
import React, { useState, useEffect, useMemo, useRef } from 'react';
import {
  Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  Cell, BarChart, Bar, LineChart, Line, ComposedChart
} from 'recharts';
import {
  TrendingUp, TrendingDown, DollarSign, ShoppingBag,
  CreditCard, BarChart3, Calendar, Info, X, Store, ArrowUpRight,
  AreaChart as AreaChartIcon, LineChart as LineChartIcon, List
} from 'lucide-react';
import { KPIData, DateRange, SegmentStoreDetail } from '../types';
import { ApiService, type DashboardStore as MallStore } from '../api';
import { useFormatCurrency } from '../hooks/useFormatCurrency';

const COLORS = ['#6366f1', '#8b5cf6', '#a855f7', '#d946ef', '#ec4899'];

type TrendChartMode = 'area' | 'line' | 'bar';
type TopLocalesMode = 'list' | 'bar';
type SegmentChartMode = 'composition' | 'bar';
type RubroChartMode = 'pareto' | 'bar';

const formatCompactCurrency = (
  rawValue: number,
  locale = 'es-DO',
  currency = 'DOP',
) => {
  const value = Number(rawValue || 0);
  try {
    return new Intl.NumberFormat(locale, {
      style: 'currency',
      currency,
      currencyDisplay: 'symbol',
      notation: 'compact',
      maximumFractionDigits: 1,
    }).format(value);
  } catch {
    return new Intl.NumberFormat('es-DO', {
      style: 'currency',
      currency: 'DOP',
      currencyDisplay: 'symbol',
      notation: 'compact',
      maximumFractionDigits: 1,
    }).format(value);
  }
};

const formatChartDate = (value: string, includeYear = false) => {
  const parsed = new Date(`${value}T12:00:00`);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleDateString('es-DO', {
    day: '2-digit',
    month: 'short',
    ...(includeYear ? { year: 'numeric' } : {}),
  });
};

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
    className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-md border transition-colors ${
      active
        ? 'border-indigo-200 bg-indigo-50 text-indigo-600'
        : 'border-slate-200 bg-white text-slate-400 hover:border-slate-300 hover:text-slate-700'
    }`}
  >
    {children}
  </button>
);

const KPICard = ({ title, value, icon: Icon, trend, color, tooltip }: any) => (
  <div className="min-w-0 bg-white px-3 py-2.5 sm:px-4 sm:py-3 rounded-xl border border-slate-100 shadow-sm hover:shadow-md transition-shadow relative group">
    {tooltip && (
      <div className="absolute top-2.5 right-2.5 text-slate-300 hover:text-indigo-500 transition-colors cursor-help">
        <Info size={14} />
        <div className="absolute right-0 w-48 p-2 mt-2 text-xs text-white bg-slate-800 rounded-lg opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-10 shadow-lg top-full">
          {tooltip}
        </div>
      </div>
    )}
    <div className="flex justify-between items-start mb-1.5">
      <div className={`p-1.5 rounded-lg ${color} bg-opacity-10`}>
        <Icon className={`w-4 h-4 ${color.replace('bg-', 'text-')}`} />
      </div>
      {trend && (
        <span className={`flex items-center gap-1 text-xs font-bold px-2 py-1 rounded-full ${trend > 0 ? 'bg-green-50 text-green-600' : 'bg-red-50 text-red-600'}`}>
          {trend > 0 ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
          {Math.abs(trend)}%
        </span>
      )}
    </div>
    <p className="text-slate-500 text-[11px] font-semibold uppercase tracking-wide">{title}</p>
    <h3 className="break-words text-base sm:text-lg font-bold text-slate-900 mt-0.5 leading-tight">{value}</h3>
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

const DailySalesTooltip = ({ active, payload, label, format }: any) => {
  if (!active || !payload?.length) return null;
  const total = Number(
    payload.find((entry: any) => entry.dataKey === 'total')?.value || 0,
  );
  const movingAverage = Number(
    payload.find((entry: any) => entry.dataKey === 'moving_average_7')?.value || 0,
  );
  const variation = movingAverage
    ? ((total - movingAverage) / Math.abs(movingAverage)) * 100
    : null;

  return (
    <div className="min-w-44 rounded-xl border border-slate-200 bg-white px-3 py-2.5 shadow-xl">
      <p className="text-[11px] font-semibold capitalize text-slate-500">
        {formatChartDate(String(label || ''), true)}
      </p>
      <p className="mt-1 text-sm font-bold text-slate-900">{format(total)}</p>
      {variation !== null && (
        <p className={`mt-1 text-[11px] font-semibold ${
          variation >= 0 ? 'text-emerald-600' : 'text-rose-600'
        }`}>
          {variation > 0 ? '+' : ''}{variation.toFixed(1)}% vs. promedio móvil
        </p>
      )}
    </div>
  );
};

const RankingTooltip = ({ active, payload, format }: any) => {
  if (!active || !payload?.length) return null;
  const item = payload[0]?.payload;
  if (!item) return null;
  return (
    <div className="rounded-xl border border-slate-200 bg-white px-3 py-2.5 shadow-xl">
      <p className="text-xs font-bold text-slate-800">{item.name}</p>
      <p className="mt-1 text-xs text-slate-500">
        {format(Number(payload[0]?.value || 0))}
      </p>
    </div>
  );
};

const SegmentCompositionCard = ({
  title,
  items,
  format,
  compactFormat,
  detailMap,
  onSelect,
  mode,
  onModeChange,
}: {
  title: string;
  items: SegmentItem[];
  format: (value: number) => string;
  compactFormat: (value: number) => string;
  detailMap?: Record<string, SegmentStoreDetail[]>;
  onSelect: (selection: SegmentSelection) => void;
  mode: SegmentChartMode;
  onModeChange: (mode: SegmentChartMode) => void;
}) => {
  const positiveItems = (items || []).filter((item) => item.value > 0);
  const visibleItems = positiveItems.slice(0, 4);
  const total = positiveItems.reduce((sum, item) => sum + item.value, 0);
  const visibleTotal = visibleItems.reduce((sum, item) => sum + item.value, 0);
  const remainingTotal = Math.max(total - visibleTotal, 0);
  const selectItem = (item: SegmentItem) => onSelect({
    kind: 'tipo_negocio',
    title,
    item,
    stores: detailMap?.[item.name] || [],
  });

  return (
    <div className="bg-white p-3 sm:p-4 rounded-xl border border-slate-100 shadow-sm lg:min-h-[220px]">
      <div className="flex items-start justify-between gap-3 mb-3">
        <div>
          <h4 className="font-bold text-sm text-slate-800">{title}</h4>
          <p className="mt-0.5 text-[11px] text-slate-400">
            Composición del total por segmento
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-400">Top {visibleItems.length || 0}</span>
          <ChartModeButton active={mode === 'composition'} label="Ver composición apilada" onClick={() => onModeChange('composition')}>
            <List size={15} />
          </ChartModeButton>
          <ChartModeButton active={mode === 'bar'} label="Ver gráfica de barras" onClick={() => onModeChange('bar')}>
            <BarChart3 size={15} />
          </ChartModeButton>
        </div>
      </div>
      {visibleItems.length === 0 ? (
        <div className="h-36 flex items-center justify-center text-sm text-slate-400">
          Sin ventas en el periodo.
        </div>
      ) : mode === 'composition' ? (
        <div>
          <div className="flex items-baseline justify-between gap-3">
            <span className="text-[10px] font-bold uppercase tracking-wide text-slate-400">
              Venta representada
            </span>
            <span className="text-sm font-bold text-slate-800">{format(total)}</span>
          </div>
          <div
            className="mt-3 flex h-4 w-full overflow-hidden rounded-md bg-slate-100"
            role="img"
            aria-label={`Composición de ${title}`}
          >
            {visibleItems.map((item, index) => (
              <button
                key={`tipo-segment-${item.name}`}
                type="button"
                aria-label={`${item.name}: ${total > 0 ? ((item.value / total) * 100).toFixed(1) : 0}%`}
                title={`${item.name}: ${format(item.value)}`}
                onClick={() => selectItem(item)}
                className="h-full border-r border-white/70 transition-opacity hover:opacity-80 last:border-r-0"
                style={{
                  width: `${total > 0 ? (item.value / total) * 100 : 0}%`,
                  backgroundColor: COLORS[index % COLORS.length],
                }}
              />
            ))}
            {remainingTotal > 0 && (
              <div
                title={`Otros: ${format(remainingTotal)}`}
                className="h-full bg-slate-300"
                style={{ width: `${(remainingTotal / total) * 100}%` }}
              />
            )}
          </div>
          <div className="mt-3 space-y-1">
            {visibleItems.map((item, index) => {
              const share = total > 0 ? (item.value / total) * 100 : 0;
              return (
                <button
                  key={`tipo-row-${item.name}`}
                  type="button"
                  onClick={() => selectItem(item)}
                  className="group grid w-full grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-2 rounded-lg px-1.5 py-1.5 text-left transition-colors hover:bg-slate-50"
                >
                  <span
                    className="h-2.5 w-2.5 rounded-[3px]"
                    style={{ backgroundColor: COLORS[index % COLORS.length] }}
                  />
                  <span className="min-w-0">
                    <span className="block truncate text-xs font-semibold text-slate-700">
                      {item.name}
                    </span>
                    <span className="block text-[10px] text-slate-400">
                      {compactFormat(item.value)}
                    </span>
                  </span>
                  <span className="flex items-center gap-1 text-xs font-bold text-slate-500">
                    {share.toFixed(1)}%
                    <ArrowUpRight size={12} className="text-slate-300 group-hover:text-indigo-500" />
                  </span>
                </button>
              );
            })}
            {remainingTotal > 0 && (
              <div className="grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-2 px-1.5 py-1.5">
                <span className="h-2.5 w-2.5 rounded-[3px] bg-slate-300" />
                <span className="truncate text-xs font-semibold text-slate-500">Otros</span>
                <span className="text-xs font-bold text-slate-400">
                  {((remainingTotal / total) * 100).toFixed(1)}%
                </span>
              </div>
            )}
          </div>
        </div>
      ) : (
        <div className="h-[185px]">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={visibleItems} layout="vertical" margin={{ top: 4, right: 12, left: 8, bottom: 4 }}>
              <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#f1f5f9" />
              <XAxis type="number" hide />
              <YAxis type="category" dataKey="name" width={110} axisLine={false} tickLine={false} tick={{ fill: '#64748b', fontSize: 11 }} />
              <Tooltip content={<SegmentTooltip format={format} total={total} />} />
              <Bar dataKey="value" radius={[0, 6, 6, 0]} onClick={(item) => selectItem(item.payload as SegmentItem)}>
                {visibleItems.map((item, index) => (
                  <Cell key={`tipo-bar-${item.name}`} fill={COLORS[index % COLORS.length]} className="cursor-pointer focus:outline-none" />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
};

const RubroExplorerCard = ({
  title,
  items,
  format,
  compactFormat,
  detailMap,
  onSelect,
  mode,
  onModeChange,
}: {
  title: string;
  items: SegmentItem[];
  format: (value: number) => string;
  compactFormat: (value: number) => string;
  detailMap?: Record<string, SegmentStoreDetail[]>;
  onSelect: (selection: SegmentSelection) => void;
  mode: RubroChartMode;
  onModeChange: (mode: RubroChartMode) => void;
}) => {
  const positiveItems = (items || []).filter((item) => item.value > 0);
  const visibleItems = positiveItems.slice(0, 8);
  const total = positiveItems.reduce((sum, item) => sum + item.value, 0);
  const selectItem = (item: SegmentItem) => onSelect({
    kind: 'rubro',
    title,
    item,
    stores: detailMap?.[item.name] || [],
  });

  return (
    <div className="bg-white p-3 sm:p-4 rounded-xl border border-slate-100 shadow-sm lg:min-h-[220px]">
      <div className="flex items-start justify-between gap-3 mb-2.5">
        <div>
          <h4 className="font-bold text-sm text-slate-800">{title}</h4>
          <p className="mt-0.5 text-[11px] text-slate-400">
            Participación y concentración acumulada
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-400">Top {visibleItems.length || 0}</span>
          <ChartModeButton active={mode === 'pareto'} label="Ver análisis Pareto" onClick={() => onModeChange('pareto')}>
            <TrendingUp size={15} />
          </ChartModeButton>
          <ChartModeButton active={mode === 'bar'} label="Ver gráfica de barras" onClick={() => onModeChange('bar')}>
            <BarChart3 size={15} />
          </ChartModeButton>
        </div>
      </div>
      {visibleItems.length === 0 ? (
        <div className="h-36 flex items-center justify-center text-sm text-slate-400">
          Sin ventas en el periodo.
        </div>
      ) : mode === 'pareto' ? (
        <div className="max-h-[190px] xl:max-h-[205px] space-y-1.5 overflow-y-auto pr-1">
          {visibleItems.map((item, index) => {
            const share = total > 0 ? (item.value / total) * 100 : 0;
            const cumulative = total > 0
              ? (
                visibleItems
                  .slice(0, index + 1)
                  .reduce((sum, current) => sum + current.value, 0)
                / total
              ) * 100
              : 0;
            return (
              <button
                key={`rubro-${item.name}-${index}`}
                type="button"
                onClick={() => selectItem(item)}
                className="group w-full rounded-lg border border-transparent px-2 py-1.5 text-left transition-colors hover:border-slate-200 hover:bg-slate-50"
              >
                <div className="flex items-center justify-between gap-3">
                  <span className="min-w-0 flex items-center gap-2">
                    <span className="text-xs font-bold text-slate-400 w-5">{String(index + 1).padStart(2, '0')}</span>
                    <span className="text-sm font-semibold text-slate-700 truncate">{item.name}</span>
                  </span>
                  <span
                    title={format(item.value)}
                    className="flex items-center gap-2 whitespace-nowrap text-xs font-semibold text-slate-500"
                  >
                    {compactFormat(item.value)}
                    <ArrowUpRight size={13} className="text-slate-300 group-hover:text-indigo-500" />
                  </span>
                </div>
                <div className="mt-1.5 flex items-center gap-3">
                  <div className="h-2 flex-1 rounded-full bg-slate-100 overflow-hidden">
                    <div
                      className="h-full rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 transition-all duration-500"
                      style={{
                        width: `${share}%`,
                      }}
                    />
                  </div>
                  <span className="w-12 text-right text-xs font-semibold text-slate-500">
                    {share.toFixed(1)}%
                  </span>
                  <span className="w-20 rounded-md bg-violet-50 px-1.5 py-0.5 text-right text-[10px] font-bold text-violet-600">
                    Acum. {cumulative.toFixed(1)}%
                  </span>
                </div>
              </button>
            );
          })}
        </div>
      ) : (
        <div className="h-[190px] xl:h-[205px]">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={visibleItems} layout="vertical" margin={{ top: 6, right: 12, left: 8, bottom: 6 }}>
              <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#f1f5f9" />
              <XAxis type="number" hide />
              <YAxis type="category" dataKey="name" width={120} axisLine={false} tickLine={false} tick={{ fill: '#64748b', fontSize: 11 }} />
              <Tooltip content={<SegmentTooltip format={format} total={total} />} />
              <Bar dataKey="value" radius={[0, 6, 6, 0]} onClick={(item) => selectItem(item.payload as SegmentItem)}>
                {visibleItems.map((item, index) => (
                  <Cell key={`rubro-bar-${item.name}`} fill={COLORS[index % COLORS.length]} className="cursor-pointer focus:outline-none" />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
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

const defaultDashboardDateRange = (): DateRange => {
  const now = new Date();
  const firstDay = new Date(now.getFullYear(), now.getMonth(), 1);
  return {
    startDate: firstDay.toISOString().split('T')[0],
    endDate: now.toISOString().split('T')[0],
  };
};

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
  const { format, locale, currency } = useFormatCurrency();
  const compactFormat = (value: number) => (
    formatCompactCurrency(value, locale, currency)
  );
  const [data, setData] = useState<KPIData | null>(null);
  const [stores, setStores] = useState<MallStore[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [selectedSegment, setSelectedSegment] = useState<SegmentSelection | null>(null);
  const [trendChartMode, setTrendChartMode] = useState<TrendChartMode>('area');
  const [topLocalesMode, setTopLocalesMode] = useState<TopLocalesMode>('list');
  const [businessTypeChartMode, setBusinessTypeChartMode] = useState<SegmentChartMode>('composition');
  const [rubroChartMode, setRubroChartMode] = useState<RubroChartMode>('pareto');
  const [dates, setDates] = useState<DateRange>(defaultDashboardDateRange);
  const [draftDates, setDraftDates] = useState<DateRange>(defaultDashboardDateRange);
  const requestSequence = useRef(0);

  const loadKPIs = async () => {
    const requestId = ++requestSequence.current;
    if (!currentMall?.id || !session?.access_token) {
      setData(null);
      setStores([]);
      setLoading(false);
      setRefreshing(false);
      return;
    }
    if (data) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }
    try {
      const [kpis, mallStores] = await Promise.all([
        ApiService.getKPIs({ ...dates, mallId: currentMall.id }, session.access_token),
        ApiService.getDashboardStores(currentMall.id),
      ]);
      if (requestId !== requestSequence.current) return;
      setData(kpis);
      setStores(mallStores);
    } catch (e) {
      console.error(e);
    } finally {
      if (requestId === requestSequence.current) {
        setLoading(false);
        setRefreshing(false);
      }
    }
  };

  useEffect(() => {
    loadKPIs();
    return () => {
      requestSequence.current += 1;
    };
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

  const trendData = useMemo(() => {
    const rows = data?.ventas_por_dia || [];
    return rows.map((row, index) => {
      const window = rows.slice(Math.max(0, index - 6), index + 1);
      const movingAverage = window.length
        ? window.reduce((sum, item) => sum + Number(item.total || 0), 0) / window.length
        : 0;
      return {
        ...row,
        total: Number(row.total || 0),
        moving_average_7: movingAverage,
      };
    });
  }, [data?.ventas_por_dia]);

  if (!currentMall?.id) {
    return (
      <div className="bg-white border border-slate-200 rounded-2xl px-4 py-4 text-slate-700">
        No hay mall asignado o seleccionado para este usuario.
      </div>
    );
  }

  if (loading || !data) return (
    <div className="flex items-center justify-center h-[calc(100dvh-12rem)] min-h-[320px]">
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
    <div className="min-w-0 space-y-3 lg:h-[calc(100dvh-9rem)] xl:h-[calc(100dvh-8rem)] lg:min-h-[520px] xl:min-h-[580px] lg:overflow-y-auto lg:pr-1 animate-in fade-in duration-500">
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-3">
        <div className="space-y-0.5">
          <div className="flex items-center gap-3">
            <p className="text-xl font-bold text-slate-900">Hola, {displayName}</p>
            {refreshing && (
              <span className="rounded-full bg-indigo-50 px-2.5 py-1 text-xs font-semibold text-indigo-600">
                Actualizando…
              </span>
            )}
          </div>
          <h2 className="pt-0.5 text-base font-semibold text-slate-700">Business Intelligence</h2>
          <p className="text-sm text-slate-500">Indicadores clave de rendimiento del mall.</p>
        </div>
        <div className="bg-white p-2 rounded-xl shadow-sm border border-slate-100 flex flex-wrap items-center gap-2 w-full md:w-auto">
          <Calendar size={16} className="text-slate-400 ml-2" />
          <input
            type="date"
            value={draftDates.startDate}
            onChange={(e) => setDraftDates({ ...draftDates, startDate: e.target.value })}
            className="text-sm border-none focus:ring-0 outline-none p-1 min-w-[120px]"
          />
          <span className="text-slate-300">-</span>
          <input
            type="date"
            value={draftDates.endDate}
            onChange={(e) => setDraftDates({ ...draftDates, endDate: e.target.value })}
            className="text-sm border-none focus:ring-0 outline-none p-1 min-w-[120px]"
          />
          <button
            type="button"
            onClick={() => setDates(draftDates)}
            disabled={
              refreshing ||
              !draftDates.startDate ||
              !draftDates.endDate ||
              draftDates.startDate > draftDates.endDate ||
              (draftDates.startDate === dates.startDate && draftDates.endDate === dates.endDate)
            }
            className="rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-bold text-white transition-colors hover:bg-indigo-700 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-400"
          >
            Aplicar
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3">
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

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="min-w-0 lg:col-span-2 bg-white p-4 rounded-xl border border-slate-100 shadow-sm">
          <div className="flex justify-between items-start gap-3 mb-3">
            <div>
              <h4 className="font-bold text-sm text-slate-800">Tendencia de Ventas Diarias</h4>
              <p className="mt-0.5 text-[11px] text-slate-400">
                Venta diaria <span className="mx-1 text-indigo-400">●</span>
                Promedio móvil 7 días <span className="ml-1 text-slate-400">━</span>
              </p>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-xs text-slate-400 mr-1">{trendData.length} días</span>
              <ChartModeButton active={trendChartMode === 'area'} label="Ver gráfica de área" onClick={() => setTrendChartMode('area')}><AreaChartIcon size={16} /></ChartModeButton>
              <ChartModeButton active={trendChartMode === 'line'} label="Ver gráfica de línea" onClick={() => setTrendChartMode('line')}><LineChartIcon size={16} /></ChartModeButton>
              <ChartModeButton active={trendChartMode === 'bar'} label="Ver gráfica de barras" onClick={() => setTrendChartMode('bar')}><BarChart3 size={16} /></ChartModeButton>
            </div>
          </div>
          <div className="h-[180px] xl:h-[200px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              {trendChartMode === 'area' ? <ComposedChart data={trendData} margin={{ top: 10, right: 18, left: 4, bottom: 0 }}>
                <defs>
                  <linearGradient id="colorTotal" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#6366f1" stopOpacity={0.28} />
                    <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid vertical={false} stroke="#eef2f7" />
                <XAxis
                  dataKey="fecha"
                  axisLine={false}
                  tickLine={false}
                  minTickGap={24}
                  tickFormatter={(value) => formatChartDate(String(value))}
                  tick={{ fill: '#94a3b8', fontSize: 11 }}
                />
                <YAxis
                  width={76}
                  axisLine={false}
                  tickLine={false}
                  tickFormatter={(value) => compactFormat(Number(value))}
                  tick={{ fill: '#94a3b8', fontSize: 11 }}
                />
                <Tooltip content={<DailySalesTooltip format={format} />} />
                <Area
                  type="monotone"
                  dataKey="total"
                  stroke="#6366f1"
                  strokeWidth={3}
                  fillOpacity={1}
                  fill="url(#colorTotal)"
                />
                <Line
                  type="monotone"
                  dataKey="moving_average_7"
                  stroke="#94a3b8"
                  strokeWidth={2}
                  dot={false}
                  activeDot={false}
                />
              </ComposedChart> : trendChartMode === 'line' ? <LineChart data={trendData} margin={{ top: 10, right: 18, left: 4, bottom: 0 }}>
                <CartesianGrid vertical={false} stroke="#eef2f7" />
                <XAxis dataKey="fecha" axisLine={false} tickLine={false} minTickGap={24} tickFormatter={(value) => formatChartDate(String(value))} tick={{ fill: '#94a3b8', fontSize: 11 }} />
                <YAxis width={76} axisLine={false} tickLine={false} tickFormatter={(value) => compactFormat(Number(value))} tick={{ fill: '#94a3b8', fontSize: 11 }} />
                <Tooltip content={<DailySalesTooltip format={format} />} />
                <Line type="monotone" dataKey="total" stroke="#6366f1" strokeWidth={3} dot={false} activeDot={{ r: 5 }} />
                <Line type="monotone" dataKey="moving_average_7" stroke="#94a3b8" strokeWidth={2} dot={false} activeDot={false} />
              </LineChart> : <ComposedChart data={trendData} margin={{ top: 10, right: 18, left: 4, bottom: 0 }}>
                <CartesianGrid vertical={false} stroke="#eef2f7" />
                <XAxis dataKey="fecha" axisLine={false} tickLine={false} minTickGap={24} tickFormatter={(value) => formatChartDate(String(value))} tick={{ fill: '#94a3b8', fontSize: 11 }} />
                <YAxis width={76} axisLine={false} tickLine={false} tickFormatter={(value) => compactFormat(Number(value))} tick={{ fill: '#94a3b8', fontSize: 11 }} />
                <Tooltip content={<DailySalesTooltip format={format} />} />
                <Bar dataKey="total" fill="#6366f1" radius={[6, 6, 0, 0]} />
                <Line type="monotone" dataKey="moving_average_7" stroke="#94a3b8" strokeWidth={2} dot={false} activeDot={false} />
              </ComposedChart>}
            </ResponsiveContainer>
          </div>
        </div>

        <div className="min-w-0 bg-white p-4 rounded-xl border border-slate-100 shadow-sm">
          <div className="flex justify-between items-start gap-3 mb-3">
            <div>
              <h4 className="font-bold text-sm text-slate-800">Top 5 Locales</h4>
              <p className="mt-0.5 text-[11px] text-slate-400">
                Ranking por venta neta
              </p>
            </div>
            <div className="flex items-center gap-2">
              <ChartModeButton active={topLocalesMode === 'list'} label="Ver ranking ejecutivo" onClick={() => setTopLocalesMode('list')}><List size={15} /></ChartModeButton>
              <ChartModeButton active={topLocalesMode === 'bar'} label="Ver gráfica de barras" onClick={() => setTopLocalesMode('bar')}><BarChart3 size={15} /></ChartModeButton>
            </div>
          </div>
          <div className="h-[180px] xl:h-[200px] w-full">
            {data.top_locales.length === 0 ? (
              <div className="flex h-full items-center justify-center text-sm text-slate-400">
                Sin ventas por local en el periodo.
              </div>
            ) : topLocalesMode === 'list' ? <div className="space-y-1">
              {data.top_locales.slice(0, 5).map((locale, index) => {
                const maxTotal = Math.max(...data.top_locales.map((item) => item.total), 0);
                const percent = maxTotal > 0 ? (locale.total / maxTotal) * 100 : 0;

                return (
                  <div
                    key={`${locale.name}-${index}`}
                    className={`rounded-lg px-2 py-1.5 ${
                      index === 0 ? 'border border-indigo-100 bg-indigo-50/60' : ''
                    }`}
                  >
                    <div className="grid grid-cols-[26px_minmax(0,1fr)_auto] items-center gap-2">
                      <span className={`grid h-6 w-6 place-items-center rounded-md text-[10px] font-bold ${
                        index === 0
                          ? 'bg-indigo-600 text-white'
                          : 'bg-slate-100 text-slate-500'
                      }`}>
                        {String(index + 1).padStart(2, '0')}
                      </span>
                      <span className="truncate text-xs font-bold text-slate-700">
                        {locale.name}
                      </span>
                      <span
                        title={format(locale.total)}
                        className="whitespace-nowrap text-xs font-semibold text-slate-500"
                      >
                        {compactFormat(locale.total)}
                      </span>
                    </div>
                    <div className="ml-8 mt-1 h-1.5 overflow-hidden rounded-full bg-slate-100">
                      <div
                        className="h-full rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 transition-all duration-500"
                        style={{
                          width: `${percent}%`,
                        }}
                      />
                    </div>
                  </div>
                );
              })}
            </div> : <ResponsiveContainer width="100%" height="100%"><BarChart data={data.top_locales.slice(0, 5)} layout="vertical" margin={{ top: 4, right: 12, left: 8, bottom: 4 }}><CartesianGrid horizontal={false} stroke="#eef2f7" /><XAxis type="number" hide /><YAxis type="category" dataKey="name" width={90} axisLine={false} tickLine={false} tick={{ fill: '#64748b', fontSize: 11 }} /><Tooltip content={<RankingTooltip format={format} />} /><Bar dataKey="total" fill="#6366f1" radius={[0, 6, 6, 0]} /></BarChart></ResponsiveContainer>}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <SegmentCompositionCard
          title="Ventas por Tipo de Negocio"
          items={data.ventas_por_tipo_negocio || []}
          format={format}
          compactFormat={compactFormat}
          detailMap={businessTypeDetailMap}
          onSelect={setSelectedSegment}
          mode={businessTypeChartMode}
          onModeChange={setBusinessTypeChartMode}
        />
        <RubroExplorerCard
          title="Ventas por Rubro"
          items={data.ventas_por_rubro || []}
          format={format}
          compactFormat={compactFormat}
          detailMap={rubroDetailMap}
          onSelect={setSelectedSegment}
          mode={rubroChartMode}
          onModeChange={setRubroChartMode}
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
