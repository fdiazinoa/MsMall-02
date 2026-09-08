import React, { useEffect, useMemo, useState } from 'react';
import {
  BarChart3, Building2, CalendarDays, Download, RefreshCw, ShoppingBag,
  Store, Tags, TrendingUp, WalletCards, X,
} from 'lucide-react';
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { ApiService } from '../api';
import { useAuth } from '../context/AuthProvider';
import {
  MallComparisonDimensionRow,
  MallComparisonMetric,
  MallComparisonResponse,
} from '../types';

type Dimension = 'malls' | 'locales' | 'rubros' | 'categorias';

type ComparisonRow = MallComparisonDimensionRow & {
  key: string;
  mall: string;
  rubro?: string;
  categoria?: string;
};

const METRICS: Array<{ id: MallComparisonMetric; label: string }> = [
  { id: 'total_bruto', label: 'Venta bruta' },
  { id: 'total_neto', label: 'Venta neta' },
  { id: 'transacciones', label: 'Transacciones' },
  { id: 'ticket_promedio', label: 'Ticket promedio' },
];

const DIMENSIONS: Array<{ id: Dimension; label: string; icon: React.ElementType }> = [
  { id: 'malls', label: 'Malls', icon: Building2 },
  { id: 'locales', label: 'Locales', icon: Store },
  { id: 'rubros', label: 'Rubros', icon: Tags },
  { id: 'categorias', label: 'Categorías', icon: ShoppingBag },
];

const today = () => new Date().toISOString().slice(0, 10);
const monthStart = () => {
  const value = new Date();
  value.setDate(1);
  return value.toISOString().slice(0, 10);
};

const csvCell = (value: string | number) => `"${String(value ?? '').replaceAll('"', '""')}"`;

export const MallComparison: React.FC = () => {
  const { malls = [], session } = useAuth();
  const [selectedMallIds, setSelectedMallIds] = useState<string[]>([]);
  const [startDate, setStartDate] = useState(monthStart);
  const [endDate, setEndDate] = useState(today);
  const [metric, setMetric] = useState<MallComparisonMetric>('total_bruto');
  const [dimension, setDimension] = useState<Dimension>('malls');
  const [rubroFilter, setRubroFilter] = useState('ALL');
  const [categoryFilter, setCategoryFilter] = useState('ALL');
  const [selectedLocalKeys, setSelectedLocalKeys] = useState<string[]>([]);
  const [data, setData] = useState<MallComparisonResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const allowed = new Set(malls.map((mall: any) => String(mall.id)));
    setSelectedMallIds((current) => {
      const preserved = current.filter((id) => allowed.has(id));
      if (preserved.length >= 2) return preserved;
      return malls.slice(0, Math.min(3, malls.length)).map((mall: any) => String(mall.id));
    });
  }, [malls]);

  useEffect(() => {
    if (!session?.access_token || selectedMallIds.length < 2 || !startDate || !endDate) {
      setData(null);
      setLoading(false);
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    ApiService.getMallComparison(
      selectedMallIds,
      { startDate, endDate },
      session.access_token,
      controller.signal,
    )
      .then(setData)
      .catch((reason) => {
        if (reason?.name !== 'AbortError') {
          setData(null);
          setError(reason?.message || 'No se pudo cargar la comparativa.');
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [selectedMallIds.join('|'), startDate, endDate, session?.access_token]);

  const rubros = useMemo(() => Array.from(new Set(
    (data?.malls || []).flatMap((mall) => mall.locales.map((local) => local.rubro)),
  )).sort(), [data]);
  const categories = useMemo(() => Array.from(new Set(
    (data?.malls || []).flatMap((mall) => mall.locales.map((local) => local.categoria)),
  )).sort(), [data]);

  useEffect(() => {
    if (!data) {
      setSelectedLocalKeys([]);
      return;
    }
    const available = new Set(data.malls.flatMap((mall) =>
      mall.locales.map((local) => `${mall.id}:${local.id}`),
    ));
    setSelectedLocalKeys((current) => current.filter((key) => available.has(key)));
  }, [data]);

  const selectedLocalKeySet = useMemo(() => new Set(selectedLocalKeys), [selectedLocalKeys]);

  const rows = useMemo<ComparisonRow[]>(() => {
    if (!data) return [];
    if (dimension === 'malls') {
      return data.malls.map((mall) => ({ ...mall, key: mall.id, mall: mall.nombre }));
    }
    if (dimension === 'locales') {
      return data.malls.flatMap((mall) => mall.locales
        .filter((local) => selectedLocalKeys.length === 0 || selectedLocalKeySet.has(`${mall.id}:${local.id}`))
        .filter((local) => rubroFilter === 'ALL' || local.rubro === rubroFilter)
        .filter((local) => categoryFilter === 'ALL' || local.categoria === categoryFilter)
        .map((local) => ({ ...local, key: `${mall.id}:${local.id}`, mall: mall.nombre })));
    }
    const field = dimension === 'rubros' ? 'rubros' : 'categorias';
    return data.malls.flatMap((mall) => mall[field].map((item) => ({
      ...item,
      key: `${mall.id}:${item.nombre}`,
      mall: mall.nombre,
    })));
  }, [data, dimension, rubroFilter, categoryFilter, selectedLocalKeys, selectedLocalKeySet]);

  const rankedRows = useMemo(
    () => [...rows].sort((left, right) => Number(right[metric] || 0) - Number(left[metric] || 0)),
    [rows, metric],
  );
  const chartRows = rankedRows.slice(0, 12).map((row) => ({
    ...row,
    chartLabel: dimension === 'malls' ? row.nombre : `${row.nombre} · ${row.mall}`,
  }));
  const totalSales = rows.reduce((sum, row) => sum + row.total_bruto, 0);
  const totalTransactions = rows.reduce((sum, row) => sum + row.transacciones, 0);
  const leader = rankedRows[0];
  const second = rankedRows[1];
  const spread = leader && second && Number(second[metric]) !== 0
    ? ((Number(leader[metric]) - Number(second[metric])) / Math.abs(Number(second[metric]))) * 100
    : 0;
  const currencies = new Set((data?.malls || []).map((mall) => mall.moneda));
  const displayCurrency = data?.malls?.[0]?.moneda || 'DOP';
  const displayLocale = data?.malls?.[0]?.locale || 'es-DO';

  const formatMetric = (value: number, selectedMetric = metric) => {
    if (selectedMetric === 'transacciones') return Math.round(value || 0).toLocaleString(displayLocale);
    try {
      return new Intl.NumberFormat(displayLocale, {
        style: 'currency', currency: displayCurrency, maximumFractionDigits: 0,
      }).format(value || 0);
    } catch {
      return `$${Number(value || 0).toLocaleString('en-US', { maximumFractionDigits: 0 })}`;
    }
  };

  const toggleMall = (mallId: string) => {
    setSelectedMallIds((current) => current.includes(mallId)
      ? current.filter((id) => id !== mallId)
      : current.length < 8 ? [...current, mallId] : current);
  };

  const addLocal = (mallId: string, localId: string) => {
    if (!localId) return;
    const key = `${mallId}:${localId}`;
    setSelectedLocalKeys((current) => current.includes(key) ? current : [...current, key]);
  };

  const removeLocal = (key: string) => {
    setSelectedLocalKeys((current) => current.filter((item) => item !== key));
  };

  const exportCsv = () => {
    const headers = ['Mall', dimension === 'malls' ? 'Mall comparado' : dimension.slice(0, -1), 'Venta bruta', 'Venta neta', 'Transacciones', 'Ticket promedio'];
    const body = rankedRows.map((row) => [row.mall, row.nombre, row.total_bruto, row.total_neto, row.transacciones, row.ticket_promedio]);
    const csv = [headers, ...body].map((row) => row.map(csvCell).join(',')).join('\n');
    const url = URL.createObjectURL(new Blob([`\uFEFF${csv}`], { type: 'text/csv;charset=utf-8' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = `comparativa_malls_${startDate}_${endDate}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  };

  if (malls.length < 2) {
    return (
      <div className="rounded-2xl border border-amber-200 bg-amber-50 p-6 text-amber-900">
        <h2 className="text-lg font-bold">Comparativa entre malls</h2>
        <p className="mt-2 text-sm">Necesitas acceso a por lo menos dos centros comerciales para utilizar esta vista.</p>
      </div>
    );
  }

  return (
    <div className="space-y-4 animate-in fade-in duration-300">
      <div className="flex flex-col justify-between gap-3 lg:flex-row lg:items-end">
        <div>
          <h2 className="text-xl font-extrabold text-slate-900">Comparativa entre centros comerciales</h2>
          <p className="mt-1 text-sm text-slate-500">Mide malls, locales, rubros y categorías bajo el mismo período.</p>
        </div>
        <button type="button" onClick={exportCsv} disabled={!rankedRows.length} className="inline-flex items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2 text-xs font-bold text-slate-700 shadow-sm disabled:opacity-40">
          <Download size={15} /> Exportar CSV
        </button>
      </div>

      <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="grid gap-4 xl:grid-cols-[1fr_auto]">
          <div>
            <p className="mb-2 text-[10px] font-bold uppercase tracking-widest text-slate-400">Malls a comparar</p>
            <div className="flex flex-wrap gap-2">
              {malls.map((mall: any) => {
                const selected = selectedMallIds.includes(String(mall.id));
                return (
                  <button key={mall.id} type="button" aria-pressed={selected} onClick={() => toggleMall(String(mall.id))} className={`rounded-full border px-3 py-1.5 text-xs font-bold transition-colors ${selected ? 'border-indigo-600 bg-indigo-600 text-white' : 'border-slate-200 bg-white text-slate-500 hover:border-indigo-300'}`}>
                    {mall.nombre}
                  </button>
                );
              })}
            </div>
            {selectedMallIds.length < 2 && <p className="mt-2 text-xs font-semibold text-amber-600">Selecciona al menos dos malls.</p>}
          </div>
          <div className="flex flex-wrap items-end gap-2">
            <label className="text-[10px] font-bold uppercase tracking-wide text-slate-400">Desde
              <input type="date" value={startDate} max={endDate} onChange={(event) => setStartDate(event.target.value)} className="mt-1 block rounded-lg border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-700" />
            </label>
            <label className="text-[10px] font-bold uppercase tracking-wide text-slate-400">Hasta
              <input type="date" value={endDate} min={startDate} max={today()} onChange={(event) => setEndDate(event.target.value)} className="mt-1 block rounded-lg border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-700" />
            </label>
            <div className="flex h-9 items-center gap-2 rounded-lg bg-slate-100 px-3 text-xs font-semibold text-slate-500"><CalendarDays size={14} /> Período común</div>
          </div>
        </div>
      </div>

      {error && <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-semibold text-rose-700">{error}</div>}
      {currencies.size > 1 && <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">Los malls seleccionados usan monedas distintas. Los valores se muestran sin conversión cambiaria.</div>}

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <SummaryCard icon={WalletCards} label="Venta combinada" value={formatMetric(totalSales, 'total_bruto')} />
        <SummaryCard icon={ShoppingBag} label="Transacciones" value={formatMetric(totalTransactions, 'transacciones')} />
        <SummaryCard icon={TrendingUp} label="Líder actual" value={leader?.nombre || 'Sin datos'} detail={leader ? formatMetric(Number(leader[metric])) : undefined} />
        <SummaryCard icon={BarChart3} label="Ventaja del líder" value={`${spread.toFixed(1)}%`} detail="Sobre el segundo lugar" />
      </div>

      <div className="rounded-2xl border border-slate-200 bg-white shadow-sm">
        <div className="flex flex-col gap-3 border-b border-slate-100 p-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex flex-wrap gap-2">
            {DIMENSIONS.map(({ id, label, icon: Icon }) => (
              <button key={id} type="button" onClick={() => setDimension(id)} className={`inline-flex items-center gap-2 rounded-lg px-3 py-2 text-xs font-bold ${dimension === id ? 'bg-slate-900 text-white' : 'bg-slate-100 text-slate-500'}`}>
                <Icon size={14} /> {label}
              </button>
            ))}
          </div>
          <select value={metric} onChange={(event) => setMetric(event.target.value as MallComparisonMetric)} className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-bold text-slate-700">
            {METRICS.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
          </select>
        </div>

        {dimension === 'locales' && (
          <div className="space-y-3 border-b border-slate-100 bg-slate-50/60 px-4 py-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex flex-wrap gap-2">
                <select value={rubroFilter} onChange={(event) => setRubroFilter(event.target.value)} className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs text-slate-600">
                  <option value="ALL">Todos los rubros</option>
                  {rubros.map((rubro) => <option key={rubro} value={rubro}>{rubro}</option>)}
                </select>
                <select value={categoryFilter} onChange={(event) => setCategoryFilter(event.target.value)} className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs text-slate-600">
                  <option value="ALL">Todas las categorías</option>
                  {categories.map((category) => <option key={category} value={category}>{category}</option>)}
                </select>
              </div>
              {selectedLocalKeys.length > 0 && (
                <button type="button" onClick={() => setSelectedLocalKeys([])} className="text-xs font-bold text-indigo-600 hover:text-indigo-800">
                  Mostrar todos
                </button>
              )}
            </div>

            <div>
              <div className="mb-2 flex items-center justify-between gap-3">
                <div>
                  <p className="text-[10px] font-bold uppercase tracking-widest text-slate-500">Locales a comparar</p>
                  <p className="mt-0.5 text-[11px] text-slate-400">Selecciona locales concretos en cada centro comercial.</p>
                </div>
                <span className="rounded-full bg-indigo-100 px-2.5 py-1 text-[10px] font-bold text-indigo-700">
                  {selectedLocalKeys.length || 'Todos'} seleccionados
                </span>
              </div>
              <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                {(data?.malls || []).map((mall) => {
                  const selectedInMall = mall.locales.filter((local) => selectedLocalKeySet.has(`${mall.id}:${local.id}`));
                  const availableInMall = [...mall.locales]
                    .filter((local) => !selectedLocalKeySet.has(`${mall.id}:${local.id}`))
                    .sort((left, right) => left.nombre.localeCompare(right.nombre, 'es'));
                  return (
                    <div key={`local-selector-${mall.id}`} className="rounded-xl border border-slate-200 bg-white p-3">
                      <p className="mb-2 truncate text-xs font-bold text-slate-800" title={mall.nombre}>{mall.nombre}</p>
                      <select
                        value=""
                        aria-label={`Agregar local de ${mall.nombre}`}
                        onChange={(event) => addLocal(mall.id, event.target.value)}
                        className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs text-slate-600"
                      >
                        <option value="">Seleccionar local...</option>
                        {availableInMall.map((local) => <option key={local.id} value={local.id}>{local.nombre}</option>)}
                      </select>
                      <div className="mt-2 flex min-h-6 flex-wrap gap-1.5">
                        {selectedInMall.length === 0 ? (
                          <span className="text-[10px] text-slate-400">Ningún local específico</span>
                        ) : selectedInMall.map((local) => {
                          const key = `${mall.id}:${local.id}`;
                          return (
                            <button key={key} type="button" onClick={() => removeLocal(key)} aria-label={`Quitar ${local.nombre} de ${mall.nombre}`} className="inline-flex items-center gap-1 rounded-full bg-indigo-50 px-2 py-1 text-[10px] font-bold text-indigo-700 hover:bg-indigo-100">
                              {local.nombre} <X size={11} />
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        )}

        <div className="h-72 p-4">
          {loading ? (
            <div className="flex h-full items-center justify-center gap-2 text-sm font-semibold text-slate-400"><RefreshCw className="animate-spin" size={18} /> Calculando comparativa...</div>
          ) : chartRows.length ? (
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartRows} margin={{ top: 8, right: 10, left: 8, bottom: 45 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
                <XAxis dataKey="chartLabel" angle={-24} textAnchor="end" interval={0} height={70} tick={{ fontSize: 10, fill: '#64748b' }} />
                <YAxis tickFormatter={(value) => metric === 'transacciones' ? Number(value).toLocaleString() : new Intl.NumberFormat('es', { notation: 'compact' }).format(Number(value))} tick={{ fontSize: 10, fill: '#94a3b8' }} />
                <Tooltip formatter={(value: number) => formatMetric(Number(value))} labelStyle={{ fontWeight: 700, color: '#0f172a' }} />
                <Bar dataKey={metric} fill="#4f46e5" radius={[6, 6, 0, 0]} maxBarSize={54} />
              </BarChart>
            </ResponsiveContainer>
          ) : <div className="flex h-full items-center justify-center text-sm text-slate-400">No hay datos para los filtros seleccionados.</div>}
        </div>

        <div className="max-h-[420px] overflow-auto border-t border-slate-100">
          <table className="w-full min-w-[760px] text-left text-xs">
            <thead className="sticky top-0 bg-slate-50 text-[10px] uppercase tracking-wide text-slate-400">
              <tr><th className="px-4 py-3">Posición</th><th className="px-4 py-3">Elemento</th><th className="px-4 py-3">Mall</th><th className="px-4 py-3 text-right">Venta bruta</th><th className="px-4 py-3 text-right">Venta neta</th><th className="px-4 py-3 text-right">Transacciones</th><th className="px-4 py-3 text-right">Ticket promedio</th></tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {rankedRows.map((row, index) => (
                <tr key={row.key} className="hover:bg-slate-50"><td className="px-4 py-3 font-bold text-indigo-600">#{index + 1}</td><td className="px-4 py-3"><p className="font-bold text-slate-800">{row.nombre}</p>{dimension === 'locales' && <p className="mt-0.5 text-[10px] text-slate-400">{row.rubro} · {row.categoria}</p>}</td><td className="px-4 py-3 text-slate-500">{row.mall}</td><td className="px-4 py-3 text-right font-semibold text-slate-700">{formatMetric(row.total_bruto, 'total_bruto')}</td><td className="px-4 py-3 text-right text-slate-500">{formatMetric(row.total_neto, 'total_neto')}</td><td className="px-4 py-3 text-right text-slate-500">{formatMetric(row.transacciones, 'transacciones')}</td><td className="px-4 py-3 text-right text-slate-500">{formatMetric(row.ticket_promedio, 'ticket_promedio')}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

const SummaryCard = ({ icon: Icon, label, value, detail }: { icon: React.ElementType; label: string; value: string; detail?: string }) => (
  <div className="rounded-xl border border-slate-200 bg-white p-3 shadow-sm">
    <div className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-widest text-slate-400"><Icon size={14} className="text-indigo-500" /> {label}</div>
    <p className="mt-2 truncate text-lg font-black text-slate-900" title={value}>{value}</p>
    {detail && <p className="mt-1 truncate text-[10px] font-semibold text-slate-400">{detail}</p>}
  </div>
);
