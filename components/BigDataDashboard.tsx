import React, { useEffect, useRef, useState } from 'react';
import { Area, AreaChart, Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { Activity, AlertTriangle, Calendar, Database, DollarSign, ShoppingBag, Store, TrendingUp } from 'lucide-react';
import { ApiService } from '../api';
import { useAuth } from '../context/AuthProvider';
import { useFormatCurrency } from '../hooks/useFormatCurrency';
import { createBigDataRequestGate } from '../utils/bigDataRequestGate';

const initialDates = () => {
  const now = new Date();
  return { start: new Date(now.getFullYear(), now.getMonth(), 1).toISOString().slice(0, 10), end: now.toISOString().slice(0, 10) };
};

const Metric = ({ label, value, icon: Icon }: { label: string; value: React.ReactNode; icon: any }) => (
  <div className="bg-white rounded-2xl border border-slate-100 shadow-sm p-5">
    <div className="flex justify-between text-slate-500 text-sm"><span>{label}</span><Icon size={18} className="text-indigo-500" /></div>
    <div className="mt-2 text-2xl font-bold text-slate-800">{value}</div>
  </div>
);

export const BigDataDashboard: React.FC = () => {
  const { currentMall, session } = useAuth();
  const { format } = useFormatCurrency();
  const [dates, setDates] = useState(initialDates);
  const [data, setData] = useState<any>(null);
  const [profile, setProfile] = useState<any>(null);
  const [profileLoading, setProfileLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [executive, setExecutive] = useState<any>(null);
  const requestVersion = useRef(0);
  const dashboardRequestGate = useRef(createBigDataRequestGate());
  const profileRequestGate = useRef(createBigDataRequestGate());

  useEffect(() => {
    const mallId = currentMall?.id;
    const token = session?.access_token;
    const version = ++requestVersion.current;
    const requestId = dashboardRequestGate.current.begin();
    profileRequestGate.current.begin();
    setData(null); setExecutive(null); setProfile(null); setProfileLoading(false); setError(null);
    if (!mallId || !token) { setLoading(false); return; }
    setLoading(true);
    Promise.allSettled([
      ApiService.getBigDataDashboard(mallId, dates.start, dates.end, token),
      ApiService.getBigDataExecutiveSummary(mallId, dates.start, dates.end, token),
    ]).then(([dashboardResult, executiveResult]) => {
      if (!dashboardRequestGate.current.isCurrent(requestId) || requestVersion.current !== version || currentMall?.id !== mallId) return;
      if (dashboardResult.status === 'fulfilled') setData(dashboardResult.value);
      else setError(dashboardResult.reason?.message || 'No se pudo cargar Big Data');
      if (executiveResult.status === 'fulfilled') setExecutive(executiveResult.value);
    }).finally(() => {
      if (dashboardRequestGate.current.isCurrent(requestId) && requestVersion.current === version) setLoading(false);
    });
  }, [currentMall?.id, session?.access_token, dates.start, dates.end]);

  if (!currentMall?.id) return <div className="bg-white rounded-2xl p-6 border border-slate-200">Selecciona un mall para consultar Big Data.</div>;
  const current = data?.summary?.current || {};
  const previous = Number(data?.summary?.previous?.sales_net || 0);
  const ranking = data?.ranking?.data || [];
  const apiUnavailable = Boolean(error && /not found|http 404/i.test(error));
  const openProfile = async (localId: string) => {
    const mallId = currentMall?.id;
    const token = session?.access_token;
    if (!mallId || !token) return;
    const version = requestVersion.current;
    const requestId = profileRequestGate.current.begin();
    setProfile(null);
    setProfileLoading(true);
    try {
      const [storeProfile, benchmark] = await Promise.all([
        ApiService.getBigData<any>(`stores/${encodeURIComponent(localId)}/profile`, mallId, dates.start, dates.end, token),
        ApiService.getBigData<any>(`stores/${encodeURIComponent(localId)}/category-benchmark`, mallId, dates.start, dates.end, token)
      ]);
      if (profileRequestGate.current.isCurrent(requestId) && requestVersion.current === version && currentMall?.id === mallId) setProfile({ ...storeProfile, benchmark });
    } catch (err: any) {
      if (profileRequestGate.current.isCurrent(requestId) && requestVersion.current === version) setError(err.message || 'No se pudo cargar el perfil del local');
    }
    finally {
      if (profileRequestGate.current.isCurrent(requestId) && requestVersion.current === version) setProfileLoading(false);
    }
  };

  return <div className="space-y-6 animate-in fade-in duration-500">
    <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
      <div><h2 className="text-2xl font-bold text-slate-800">Big Data</h2><p className="text-slate-500">Analítica comercial incremental del mall seleccionado.</p></div>
      <div className="bg-white border border-slate-100 rounded-xl p-2 flex items-center gap-2"><Calendar size={16} className="text-slate-400 ml-1" />
        <input className="text-sm" type="date" value={dates.start} onChange={e => setDates({ ...dates, start: e.target.value })} />
        <span className="text-slate-300">-</span><input className="text-sm" type="date" value={dates.end} onChange={e => setDates({ ...dates, end: e.target.value })} />
      </div>
    </div>
    {error && <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-amber-800 text-sm">{error}. {apiUnavailable ? 'La API de Big Data todavía no está desplegada en el backend seleccionado; despliega esta rama en Railway antes de activar o probar el módulo.' : <>El módulo está desactivado por defecto; actívalo con la licencia <code>BIG_DATA_CORE</code> para este mall.</>}</div>}
    {loading && <div className="h-64 flex items-center justify-center"><div className="animate-spin h-9 w-9 rounded-full border-b-2 border-indigo-600" /></div>}
    {data && <>
      {executive && <section className="rounded-2xl border border-indigo-100 bg-gradient-to-br from-white to-indigo-50 p-5 shadow-sm">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div><p className="text-xs font-bold uppercase tracking-wider text-indigo-500">Resumen ejecutivo</p><h3 className="mt-1 text-lg font-bold text-slate-800">{executive.general_status === 'DATA_INCOMPLETE' ? 'El período requiere completar información' : executive.general_status === 'ATTENTION_REQUIRED' ? 'Existen hallazgos que requieren revisión' : 'Desempeño sin alertas activas'}</h3><p className="mt-1 text-sm text-slate-600">Cobertura {Number(executive.coverage || 0).toFixed(1)}% · actualizado {executive.updated_at ? new Date(executive.updated_at).toLocaleString() : 'pendiente'}</p></div>
          <div className="rounded-xl bg-white px-4 py-3 shadow-sm"><p className="text-xs text-slate-500">Proyección de cierre</p>{executive.forecast?.status === 'OK' ? <><p className="text-xl font-black text-indigo-700">{format(executive.forecast.expected_close || 0)}</p><p className="text-xs text-slate-500">{format(executive.forecast.lower_bound || 0)} – {format(executive.forecast.upper_bound || 0)} · confianza {executive.forecast.confidence}</p></> : <p className="mt-1 font-bold text-amber-700">Datos insuficientes</p>}</div>
        </div>
        <div className="mt-4 grid gap-3 lg:grid-cols-3">
          <div className="rounded-xl bg-white p-3"><p className="flex items-center gap-2 text-sm font-bold text-slate-700"><TrendingUp size={15} className="text-emerald-500"/> Categorías destacadas</p><div className="mt-2 flex flex-wrap gap-2">{(executive.top_categories || []).slice(0, 4).map((row: any) => <span key={row.category_id || row.category_name} className="rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-semibold text-emerald-700">{row.category_name}: {format(row.sales_net)}</span>)}</div></div>
          <div className="rounded-xl bg-white p-3"><p className="flex items-center gap-2 text-sm font-bold text-slate-700"><Store size={15} className="text-indigo-500"/> Locales destacados</p><div className="mt-2 space-y-1">{(executive.highlighted_stores || []).slice(0, 3).map((row: any) => <button key={row.local_id} onClick={() => openProfile(row.local_id)} className="block w-full truncate text-left text-xs font-semibold text-indigo-700">{row.local_name}: {format(row.sales_net)}</button>)}{!(executive.highlighted_stores || []).length && <p className="text-xs text-slate-500">Sin datos suficientes.</p>}</div></div>
          <div className="rounded-xl bg-white p-3"><p className="flex items-center gap-2 text-sm font-bold text-slate-700"><AlertTriangle size={15} className="text-amber-500"/> Observaciones principales</p><p className="mt-2 text-xs leading-5 text-slate-600">{executive.observations?.[0]?.observation || executive.anomalies?.[0]?.description || 'Sin observaciones para este período.'}</p></div>
        </div>
      </section>}
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
        <Metric label="Ventas netas" value={format(Number(current.sales_net || 0))} icon={DollarSign} />
        <Metric label="Variación vs. período anterior" value={`${Number(data.summary.variation_percent || 0).toFixed(1)}%`} icon={Activity} />
        <Metric label="Registros de venta" value={Number(current.transactions || 0).toLocaleString()} icon={ShoppingBag} />
        <Metric label="Promedio por registro" value={format(Number(current.ticket_average || 0))} icon={Store} />
      </div>
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        <section className="xl:col-span-2 bg-white p-5 rounded-2xl border border-slate-100 shadow-sm"><h3 className="font-bold text-slate-800 mb-4">Evolución diaria</h3><div className="h-72"><ResponsiveContainer width="100%" height="100%"><AreaChart data={data.daily.data}><defs><linearGradient id="bigDataSales" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor="#6366f1" stopOpacity={.25}/><stop offset="95%" stopColor="#6366f1" stopOpacity={0}/></linearGradient></defs><CartesianGrid strokeDasharray="3 3" vertical={false}/><XAxis dataKey="period_date" tick={{fontSize:11}}/><YAxis tick={{fontSize:11}}/><Tooltip formatter={(value: number) => format(value)}/><Area type="monotone" dataKey="sales_net" stroke="#6366f1" fill="url(#bigDataSales)" /></AreaChart></ResponsiveContainer></div></section>
        <section className="bg-white p-5 rounded-2xl border border-slate-100 shadow-sm"><h3 className="font-bold text-slate-800 mb-4">Calidad de datos</h3><div className="space-y-4 text-sm"><div><p className="text-slate-500">Cobertura del período</p><p className="font-bold text-slate-800">{Number(data.quality.coverage_percent || 0).toFixed(1)}%</p></div><div><p className="text-slate-500">Días incompletos</p><p className="font-bold text-slate-800">{data.quality.days_incomplete}</p></div><div><p className="text-slate-500">Importaciones fallidas</p><p className="font-bold text-slate-800">{data.quality.failed_imports}</p></div><div className="text-xs text-slate-500">Actualizado: {data.quality.last_analytics_update ? new Date(data.quality.last_analytics_update).toLocaleString() : 'Pendiente de primer proceso'}</div></div></section>
      </div>
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        <section className="bg-white p-5 rounded-2xl border border-slate-100 shadow-sm"><h3 className="font-bold text-slate-800 mb-4">Ventas por categoría</h3><div className="h-72"><ResponsiveContainer width="100%" height="100%"><BarChart data={data.categories.data.slice(0, 10)} layout="vertical"><XAxis type="number" hide/><YAxis type="category" dataKey="category_name" width={120} tick={{fontSize:11}}/><Tooltip formatter={(value: number) => format(value)}/><Bar dataKey="sales_net" fill="#8b5cf6" radius={[0, 4, 4, 0]}/></BarChart></ResponsiveContainer></div></section>
        <section className="bg-white p-5 rounded-2xl border border-slate-100 shadow-sm"><h3 className="font-bold text-slate-800 mb-4">Ranking de locales</h3><div className="space-y-3 max-h-72 overflow-y-auto">{ranking.map((row: any, index: number) => <button type="button" onClick={() => openProfile(row.local_id)} key={row.local_id} className="w-full flex justify-between items-center border-b border-slate-50 pb-2 text-left hover:bg-slate-50"><span className="text-sm text-slate-700"><b className="text-indigo-600 mr-2">{index + 1}</b>{row.name}</span><span className="text-sm font-semibold">{format(row.sales_net)}</span></button>)}</div></section>
      </div>
      <div className="text-xs text-slate-500 flex items-center gap-2"><Database size={14}/> Datos agregados; ventas del período anterior: {format(previous)}.</div>
    </>}
    {(profile || profileLoading) && <div className="fixed inset-0 z-50 bg-slate-900/40 flex items-center justify-center p-4"><div className="w-full max-w-2xl max-h-[85vh] overflow-y-auto bg-white rounded-2xl p-6 shadow-2xl"><div className="flex justify-between gap-4"><div><h3 className="text-xl font-bold text-slate-800">{profileLoading ? 'Cargando perfil 360°...' : profile.local?.nombre}</h3><p className="text-sm text-slate-500">Rubro: {profile?.local?.rubro || 'Sin clasificar'}</p></div><button onClick={() => setProfile(null)} className="text-slate-500">Cerrar</button></div>{profile && <div className="grid grid-cols-2 gap-4 mt-5 text-sm"><div><p className="text-slate-500">Ventas del período</p><b>{format(profile.period.sales_net || 0)}</b></div><div><p className="text-slate-500">Promedio por registro</p><b>{format(profile.period.ticket_average || 0)}</b></div><div><p className="text-slate-500">Última venta</p><b>{profile.period.last_sale_received || 'Sin ventas'}</b></div><div><p className="text-slate-500">Comparación categoría</p><b>{profile.benchmark?.status === 'ok' ? `Posición ${profile.benchmark.rank} de ${profile.benchmark.comparable_stores}` : 'Datos insuficientes'}</b></div></div>}</div></div>}
  </div>;
};
