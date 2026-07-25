import React, { useEffect, useRef, useState } from 'react';
import { AlertTriangle, CheckCircle2, Clock3, Eye, Filter, Loader2, RefreshCw, RotateCcw, Store } from 'lucide-react';
import { ApiService } from '../api';
import { useAuth } from '../context/AuthProvider';
import { OperationalFinding, OperationsCollectionName } from '../types';

const severityTone: Record<string, string> = {
  CRITICAL: 'border-red-200 bg-red-50 text-red-700',
  HIGH: 'border-orange-200 bg-orange-50 text-orange-700',
  WARNING: 'border-amber-200 bg-amber-50 text-amber-700',
  INFO: 'border-sky-200 bg-sky-50 text-sky-700',
};

const formatDate = (value?: string) => {
  if (!value) return 'Sin fecha';
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
};

export const OperationsCenter: React.FC<{ onOpenBigData?: () => void }> = ({ onOpenBigData }) => {
  const { currentMall, session } = useAuth();
  const token = session?.access_token || '';
  const requestVersion = useRef(0);
  const [findings, setFindings] = useState<OperationalFinding[]>([]);
  const [selected, setSelected] = useState<OperationalFinding | null>(null);
  const [loading, setLoading] = useState(false);
  const [working, setWorking] = useState<string | null>(null);
  const [comment, setComment] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [collection, setCollection] = useState<OperationsCollectionName>('findings');
  const [filters, setFilters] = useState({
    severity: '', status: 'OPEN', type: '', source: '', local_id: '', start_date: '', end_date: '',
  });

  const load = async () => {
    const mallId = currentMall?.id;
    const version = ++requestVersion.current;
    setFindings([]);
    setSelected(null);
    setComment('');
    setError(null);
    if (!mallId || !token) return;
    setLoading(true);
    try {
      const response = await ApiService.getOperationsItems<OperationalFinding>(collection, mallId, token, {
        severity: filters.severity || undefined,
        status: filters.status || undefined,
        type: filters.type || undefined,
        source: filters.source || undefined,
        local_id: filters.local_id || undefined,
        start_date: filters.start_date || undefined,
        end_date: filters.end_date || undefined,
        limit: 50,
      });
      if (requestVersion.current !== version || currentMall?.id !== mallId) return;
      setFindings(response.data);
    } catch (err: any) {
      if (requestVersion.current !== version) return;
      setError(err?.message || 'No se pudo cargar Operations Center.');
    } finally {
      if (requestVersion.current === version) setLoading(false);
    }
  };

  useEffect(() => {
    load();
    return () => { requestVersion.current += 1; };
  }, [currentMall?.id, token, collection, filters.severity, filters.status, filters.type, filters.source, filters.local_id, filters.start_date, filters.end_date]);

  const applyAction = async (finding: OperationalFinding, action: 'review' | 'resolve' | 'reopen') => {
    if (!currentMall?.id || !token) return;
    setWorking(finding.id);
    setError(null);
    try {
      await ApiService.updateOperationsFinding(currentMall.id, finding.id, action, token);
      await load();
    } catch (err: any) {
      setError(err?.message || 'No se pudo actualizar el hallazgo.');
    } finally {
      setWorking(null);
    }
  };

  const addComment = async () => {
    if (!selected?.id || !currentMall?.id || !token || !comment.trim()) return;
    setWorking(selected.id);
    try {
      const updated = await ApiService.addOperationsFindingComment(currentMall.id, selected.id, comment.trim(), token);
      setSelected(updated);
      setFindings(current => current.map(item => item.id === updated.id ? updated : item));
      setComment('');
    } catch (err: any) {
      setError(err?.message || 'No se pudo registrar el comentario.');
    } finally {
      setWorking(null);
    }
  };

  if (!currentMall?.id) {
    return <div className="rounded-xl border border-slate-200 bg-white p-5">Selecciona un mall para consultar Operations Center.</div>;
  }

  const critical = findings.filter(row => row.severity === 'CRITICAL').length;
  const high = findings.filter(row => row.severity === 'HIGH').length;
  const incomplete = findings.filter(row => row.type === 'DATA_INCOMPLETE').length;

  return <div className="space-y-2 lg:h-[calc(100dvh-8rem)] animate-in fade-in duration-300">
    <header className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
      <div>
        <h2 className="text-2xl font-bold text-slate-800">Operations Center</h2>
        <p className="text-sm text-slate-500">Eventos, anomalías y hallazgos reales de {currentMall.nombre}.</p>
      </div>
      <button onClick={load} disabled={loading} className="inline-flex items-center gap-2 self-start rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-semibold text-slate-600 disabled:opacity-50">
        <RefreshCw size={15} className={loading ? 'animate-spin' : ''} /> Actualizar
      </button>
    </header>

    {error && <div className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
      {error} Las capacidades <code>BIG_DATA_CORE</code> y <code>BIG_DATA_OPERATIONS</code> deben estar habilitadas para este mall.
    </div>}

    <section role="tablist" className="flex flex-wrap gap-2 rounded-xl border border-slate-100 bg-white p-2">
      {([
        ['events', 'Eventos'],
        ['findings', 'Hallazgos'],
        ['anomalies', 'Anomalías'],
        ['observations', 'Observaciones'],
        ['patterns', 'Patrones'],
      ] as Array<[OperationsCollectionName, string]>).map(([id, label]) => <button
        key={id}
        onClick={() => {
          setCollection(id);
          setFilters(current => ({ ...current, status: id === 'findings' || id === 'anomalies' ? 'OPEN' : '' }));
        }}
        className={`rounded-lg px-3 py-2 text-xs font-bold ${collection === id ? 'bg-indigo-600 text-white' : 'text-slate-600 hover:bg-slate-50'}`}
      >{label}</button>)}
    </section>

    <section id="operations-health-panel" aria-label="Salud de locales" className="max-h-[200px] space-y-2 overflow-y-auto grid grid-cols-2 gap-3 lg:grid-cols-4">
      {[
        ['Hallazgos visibles', findings.length, Clock3, 'text-indigo-600 bg-indigo-50'],
        ['Críticos', critical, AlertTriangle, 'text-red-600 bg-red-50'],
        ['Prioridad alta', high, AlertTriangle, 'text-orange-600 bg-orange-50'],
        ['Datos incompletos', incomplete, Filter, 'text-amber-600 bg-amber-50'],
      ].map(([label, value, Icon, tone]: any) => <div key={label} className="rounded-xl border border-slate-100 bg-white p-3 shadow-sm">
        <div className="flex items-center justify-between"><span className="text-xs font-semibold text-slate-500">{label}</span><span className={`rounded-lg p-1.5 ${tone}`}><Icon size={15} /></span></div>
        <p className="mt-1 text-xl font-black text-slate-800">{value}</p>
      </div>)}
    </section>

    <section className="flex flex-wrap gap-2 rounded-xl border border-slate-100 bg-white p-3">
      <select value={filters.severity} onChange={e => setFilters({ ...filters, severity: e.target.value })} className="rounded-lg border border-slate-200 px-3 py-2 text-sm">
        <option value="">Toda severidad</option><option>CRITICAL</option><option>HIGH</option><option>WARNING</option><option>INFO</option>
      </select>
      <select value={filters.status} onChange={e => setFilters({ ...filters, status: e.target.value })} className="rounded-lg border border-slate-200 px-3 py-2 text-sm">
        <option value="">Todo estado</option><option>OPEN</option><option>ACKNOWLEDGED</option><option>RESOLVED</option>
      </select>
      <input value={filters.type} onChange={e => setFilters({ ...filters, type: e.target.value })} placeholder="Tipo de hallazgo" className="min-w-48 rounded-lg border border-slate-200 px-3 py-2 text-sm" />
      <input value={filters.source} onChange={e => setFilters({ ...filters, source: e.target.value })} placeholder="Origen" className="min-w-36 rounded-lg border border-slate-200 px-3 py-2 text-sm" />
      <input value={filters.local_id} onChange={e => setFilters({ ...filters, local_id: e.target.value })} placeholder="ID del local" className="min-w-36 rounded-lg border border-slate-200 px-3 py-2 text-sm" />
      <input type="date" aria-label="Fecha inicial" value={filters.start_date} onChange={e => setFilters({ ...filters, start_date: e.target.value })} className="rounded-lg border border-slate-200 px-3 py-2 text-sm" />
      <input type="date" aria-label="Fecha final" value={filters.end_date} onChange={e => setFilters({ ...filters, end_date: e.target.value })} className="rounded-lg border border-slate-200 px-3 py-2 text-sm" />
    </section>

    <section id="operations-cases-panel" aria-label="Casos que explican las prioridades" className="max-h-[280px] overflow-auto">
    {loading && <div className="flex h-48 items-center justify-center"><Loader2 className="animate-spin text-indigo-600" /></div>}
    {!loading && !findings.length && !error && <div className="rounded-xl border border-dashed border-slate-300 bg-white p-5 text-center text-slate-500">
      No existen elementos para los filtros seleccionados.
    </div>}
    {!loading && findings.map(finding => <article key={finding.id} className="max-h-[320px] space-y-2 overflow-y-auto rounded-xl border border-slate-100 bg-white p-4 shadow-sm">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className={`rounded-full border px-2 py-0.5 text-[11px] font-bold ${severityTone[finding.severity] || severityTone.INFO}`}>{finding.severity || 'INFO'}</span>
            <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-semibold text-slate-600">{finding.type || (finding as any).event_type || (finding as any).observation_type || (finding as any).pattern_type}</span>
            {finding.local_name && <span className="inline-flex items-center gap-1 text-xs text-slate-500"><Store size={12} />{finding.local_name}</span>}
          </div>
          <h3 className="mt-2 font-bold text-slate-800">{finding.title || (finding as any).pattern_name || (finding as any).event_type || (finding as any).observation_type || finding.type}</h3>
          <p className="mt-1 text-sm text-slate-600">{finding.description || (finding as any).observation || (finding as any).conclusion || 'Evento operacional registrado.'}</p>
          <p className="mt-2 text-xs text-slate-400">{formatDate(finding.detected_at || (finding as any).created_at || (finding as any).last_seen)} · {finding.source || collection}</p>
        </div>
        <div className="flex shrink-0 flex-wrap gap-2">
          <button onClick={() => setSelected(finding)} className="inline-flex items-center gap-1 rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs font-bold text-slate-600"><Eye size={13} /> Detalle</button>
          {(collection === 'findings' || collection === 'anomalies') && finding.status === 'OPEN' && <button disabled={working === finding.id} onClick={() => applyAction(finding, 'review')} className="rounded-lg border border-indigo-200 px-2.5 py-1.5 text-xs font-bold text-indigo-600">Revisado</button>}
          {(collection === 'findings' || collection === 'anomalies') && (finding.status !== 'RESOLVED' ? <button disabled={working === finding.id} onClick={() => applyAction(finding, 'resolve')} className="inline-flex items-center gap-1 rounded-lg bg-emerald-600 px-2.5 py-1.5 text-xs font-bold text-white"><CheckCircle2 size={13} /> Resolver</button>
            : <button disabled={working === finding.id} onClick={() => applyAction(finding, 'reopen')} className="inline-flex items-center gap-1 rounded-lg bg-amber-500 px-2.5 py-1.5 text-xs font-bold text-white"><RotateCcw size={13} /> Reabrir</button>)}
        </div>
      </div>
    </article>)}
    </section>

    {selected && <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4">
      <div className="max-h-[85vh] w-full max-w-2xl overflow-y-auto rounded-2xl bg-white p-5 shadow-2xl">
        <div className="flex items-start justify-between gap-4"><div><p className="text-xs font-bold uppercase tracking-wider text-indigo-500">Detalle operacional</p><h3 className="mt-1 text-xl font-bold text-slate-800">{selected.title || (selected as any).pattern_name || (selected as any).event_type || (selected as any).observation_type}</h3></div><button onClick={() => setSelected(null)} className="text-sm text-slate-500">Cerrar</button></div>
        <p className="mt-3 text-sm leading-6 text-slate-600">{selected.description || (selected as any).observation || (selected as any).conclusion}</p>
        <div className="mt-4 grid gap-3 md:grid-cols-2">
          <div className="rounded-xl bg-slate-50 p-3"><p className="text-xs font-bold text-slate-500">Evidencia</p><pre className="mt-2 whitespace-pre-wrap break-words text-xs text-slate-700">{JSON.stringify(selected.evidence || selected.metadata || {}, null, 2)}</pre></div>
          <div className="rounded-xl bg-emerald-50 p-3"><p className="text-xs font-bold text-emerald-700">Recomendación</p><p className="mt-2 text-sm text-emerald-900">{selected.recommendation || 'Revisar la evidencia disponible.'}</p></div>
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          {selected.local_id && <button onClick={onOpenBigData} className="rounded-lg border border-indigo-200 px-3 py-2 text-sm font-bold text-indigo-600">Ir al perfil 360°</button>}
          <button onClick={onOpenBigData} className="rounded-lg bg-indigo-600 px-3 py-2 text-sm font-bold text-white">Abrir panel Big Data</button>
        </div>
        {(collection === 'findings' || collection === 'anomalies') && <div className="mt-4 flex gap-2 border-t border-slate-100 pt-4">
          <input value={comment} onChange={event => setComment(event.target.value)} maxLength={1000} placeholder="Registrar comentario" className="min-w-0 flex-1 rounded-lg border border-slate-200 px-3 py-2 text-sm" />
          <button onClick={addComment} disabled={!comment.trim() || working === selected.id} className="rounded-lg bg-slate-800 px-3 py-2 text-sm font-bold text-white disabled:opacity-50">Guardar</button>
        </div>}
      </div>
    </div>}
  </div>;
};
