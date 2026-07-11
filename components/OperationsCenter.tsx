import React, { useEffect, useMemo, useState } from 'react';
import { Activity, AlertTriangle, CheckCircle2, Clock, Loader2, PlayCircle, RefreshCw, ShieldAlert, Store, Wrench } from 'lucide-react';
import { ApiService } from '../api';
import { useAuth } from '../context/AuthProvider';
import { OperationalFinding, OperationsIntelligenceResponse } from '../types';

const severityStyle: Record<string, string> = {
  CRITICAL: 'bg-red-50 text-red-700 border-red-200',
  HIGH: 'bg-orange-50 text-orange-700 border-orange-200',
  WARNING: 'bg-amber-50 text-amber-700 border-amber-200',
  INFO: 'bg-sky-50 text-sky-700 border-sky-200',
};

const severityLabel: Record<string, string> = {
  CRITICAL: 'Crítico',
  HIGH: 'Alto',
  WARNING: 'Advertencia',
  INFO: 'Info',
};

const formatDateTime = (value?: string | null) => {
  if (!value) return 'Sin registro';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString();
};

const findingText = (finding: OperationalFinding) => [
  finding.type,
  finding.title,
  finding.description,
  finding.source,
].filter(Boolean).join(' ').toLowerCase();

const findingCategory = (finding: OperationalFinding) => {
  const text = findingText(finding);
  if (text.includes('missing') || text.includes('faltante') || text.includes('dias') || text.includes('días')) return 'missing_days';
  if (text.includes('failed') || text.includes('fallo') || text.includes('error') || text.includes('timeout') || text.includes('invalid_file')) return 'import_failure';
  if (text.includes('sin ventas') || text.includes('without_sales') || text.includes('no report')) return 'without_sales';
  if (text.includes('ventas visibles') || text.includes('sales_missing') || text.includes('sales_not_visible')) return 'sales_not_visible';
  return 'follow_up';
};

const missingDaysCount = (finding: OperationalFinding) => {
  const evidence = (finding.evidence || {}) as Record<string, any>;
  const value = evidence.missing_days || evidence.dias_faltantes || evidence.days_missing || evidence.dias || (finding as any).missing_days;
  if (Array.isArray(value)) return value.length;
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : findingCategory(finding) === 'missing_days' ? 1 : 0;
};

const businessReason = (finding: OperationalFinding) => {
  const category = findingCategory(finding);
  if (category === 'missing_days') return 'Tiene días pendientes de información.';
  if (category === 'import_failure') return 'Presenta cargas con error o conexión fallida.';
  if (category === 'sales_not_visible') return 'La carga fue recibida, pero las ventas no aparecen para la fecha procesada.';
  if (category === 'without_sales') return 'No reporta ventas dentro del periodo esperado.';
  return finding.description || 'Requiere seguimiento operativo.';
};

const businessTitle = (finding: OperationalFinding) => `${finding.local_name || 'Local'} requiere revisión`;

const uniqueLocalCount = (findings: OperationalFinding[]) => new Set(findings.map((row) => row.local_id || row.local_name).filter(Boolean)).size;

const scoreTone = (score: number) => {
  if (score < 50) return 'bg-red-50 text-red-700 border-red-200';
  if (score < 80) return 'bg-amber-50 text-amber-700 border-amber-200';
  return 'bg-emerald-50 text-emerald-700 border-emerald-200';
};

const healthTone = (health?: string) => {
  const value = String(health || '').toUpperCase();
  if (value === 'ROJO' || value.includes('RIESGO')) return { label: 'Riesgo operativo', tone: 'bg-red-50 text-red-700 border-red-200' };
  if (value === 'AMARILLO' || value.includes('ATENCION') || value.includes('ATENCIÓN')) return { label: 'Atención requerida', tone: 'bg-amber-50 text-amber-700 border-amber-200' };
  if (value === 'VERDE' || value.includes('SALUD')) return { label: 'Saludable', tone: 'bg-emerald-50 text-emerald-700 border-emerald-200' };
  return { label: 'Sin datos', tone: 'bg-slate-100 text-slate-700 border-slate-200' };
};

const StatCard = ({ label, value, helper, icon: Icon, className }: { label: string; value: React.ReactNode; helper: string; icon: any; className: string }) => (
  <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
    <div className="flex items-start justify-between gap-4">
      <div>
        <p className="text-xs font-bold uppercase tracking-widest text-slate-400">{label}</p>
        <div className="mt-2 text-xl font-black text-slate-900">{value}</div>
        <p className="mt-1 text-xs font-semibold text-slate-500">{helper}</p>
      </div>
      <div className={`flex h-12 w-12 items-center justify-center rounded-2xl ${className}`}>
        <Icon size={22} />
      </div>
    </div>
  </div>
);

const OperationalProblemCard = ({
  finding,
  onAcknowledge,
  onResolve,
  actionDisabled,
}: {
  finding: OperationalFinding;
  onAcknowledge: (finding: OperationalFinding) => void;
  onResolve: (finding: OperationalFinding) => void;
  actionDisabled: boolean;
}) => (
  <article className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
    <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <span className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-black ${severityStyle[finding.severity] || severityStyle.INFO}`}>
            {severityLabel[finding.severity] || finding.severity}
          </span>
          {finding.local_name && (
            <span className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-white px-2.5 py-1 text-xs font-bold text-slate-600">
              <Store size={12} /> {finding.local_name}
            </span>
          )}
          <span className="inline-flex rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs font-bold text-slate-600">
            Prioridad {finding.priority_score || 0}
          </span>
        </div>
        <h3 className="mt-3 text-lg font-black text-slate-900">{businessTitle(finding)}</h3>
        <p className="mt-1 text-sm leading-6 text-slate-600">{businessReason(finding)}</p>
      </div>
      <div className="flex shrink-0 gap-2">
        {finding.status === 'OPEN' && (
          <button
            onClick={() => onAcknowledge(finding)}
            disabled={actionDisabled}
            className="rounded-xl border border-slate-200 px-3 py-2 text-xs font-black text-slate-600 hover:bg-slate-50 disabled:opacity-50"
          >
            Reconocer
          </button>
        )}
        <button
          onClick={() => onResolve(finding)}
          disabled={actionDisabled}
          className="rounded-xl bg-slate-900 px-3 py-2 text-xs font-black text-white hover:bg-slate-700 disabled:opacity-50"
        >
          Resolver
        </button>
      </div>
    </div>

    <div className="mt-4 grid grid-cols-1 gap-3 lg:grid-cols-3">
      <div className="rounded-2xl bg-slate-50 p-4">
        <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">Motivo</p>
        <p className="mt-1 text-sm text-slate-700">{finding.root_cause || businessReason(finding)}</p>
      </div>
      <div className="rounded-2xl bg-emerald-50 p-4">
        <p className="text-[10px] font-black uppercase tracking-widest text-emerald-500">Acción recomendada</p>
        <p className="mt-1 text-sm text-emerald-900">{finding.recommendation || 'Revisar evidencia operativa y confirmar impacto.'}</p>
      </div>
      <div className="rounded-2xl bg-indigo-50 p-4">
        <p className="text-[10px] font-black uppercase tracking-widest text-indigo-500">Última señal</p>
        <p className="mt-1 text-sm text-indigo-950">
          {formatDateTime(finding.detected_at)} · Confianza {Math.round((finding.confidence || 0) * 100)}%
        </p>
      </div>
    </div>
  </article>
);

export const OperationsCenter: React.FC = () => {
  const { currentMall, session, isAdmin, isTic } = useAuth();
  const token = session?.access_token || '';
  const [intelligence, setIntelligence] = useState<OperationsIntelligenceResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [workingId, setWorkingId] = useState<string | null>(null);
  const [filterSeverity, setFilterSeverity] = useState('');
  const [flash, setFlash] = useState<{ kind: 'success' | 'error'; message: string } | null>(null);

  const canOperate = Boolean(isAdmin || isTic);
  const findings = intelligence?.open_findings || [];

  const model = useMemo(() => {
    const withoutSales = findings.filter((row) => ['without_sales', 'sales_not_visible'].includes(findingCategory(row)));
    const missingDays = findings.filter((row) => findingCategory(row) === 'missing_days');
    const importFailures = findings.filter((row) => findingCategory(row) === 'import_failure');
    const locations = intelligence?.operational_health?.locations?.length
      ? intelligence.operational_health.locations
      : Object.values(findings.reduce((acc, finding) => {
        const key = finding.local_id || finding.local_name || 'sin-local';
        const current = acc[key] || {
          local_id: finding.local_id,
          local_name: finding.local_name || 'Local sin identificar',
          score: 100,
          status: 'Saludable',
          last_activity: finding.detected_at,
          missing_days: 0,
          import_failures: 0,
          action: finding.recommendation || 'Continuar monitoreo operativo.',
          priority_score: 0,
        };
        const severityPenalty = { CRITICAL: 36, HIGH: 26, WARNING: 16, INFO: 8 }[finding.severity] || 8;
        const category = findingCategory(finding);
        current.score = Math.max(0, current.score - severityPenalty - (category === 'sales_not_visible' ? 12 : 0));
        current.missing_days += missingDaysCount(finding);
        current.import_failures += category === 'import_failure' ? 1 : 0;
        current.priority_score = Math.max(current.priority_score, finding.priority_score || 0);
        current.action = finding.recommendation || current.action;
        current.last_activity = finding.detected_at || current.last_activity;
        current.status = current.score < 50 ? 'Riesgo operativo' : current.score < 80 ? 'Atención requerida' : 'Saludable';
        acc[key] = current;
        return acc;
      }, {} as Record<string, NonNullable<OperationsIntelligenceResponse['operational_health']>['locations'][number]>)).sort((a, b) => a.score - b.score);

    const priorityLocations = intelligence?.priority_locations?.length
      ? intelligence.priority_locations
      : [...findings]
        .sort((a, b) => (b.priority_score || 0) - (a.priority_score || 0))
        .slice(0, 5)
        .map((finding) => ({
          local_id: finding.local_id,
          local_name: finding.local_name || 'Local sin identificar',
          reason: businessReason(finding),
          action: finding.recommendation || 'Revisar evidencia operativa.',
          priority_score: finding.priority_score || 0,
          severity: finding.severity,
        }));

    const locationsWithoutSales = intelligence?.locations_without_sales?.count ?? uniqueLocalCount(withoutSales);
    const missingDaysCountTotal = intelligence?.missing_days_summary?.days_missing ?? missingDays.reduce((total, row) => total + missingDaysCount(row), 0);
    const importFailuresCount = intelligence?.import_failures_summary?.count ?? importFailures.length;
    const attentionRequired = intelligence?.operational_health?.attention_required ?? uniqueLocalCount(findings);
    const monitoredLocations = intelligence?.operational_health?.monitored_locations ?? uniqueLocalCount(findings);
    const healthyLocations = intelligence?.operational_health?.healthy_locations ?? Math.max(0, monitoredLocations - attentionRequired);
    const activeIncidents = intelligence?.operational_health?.active_incidents ?? findings.length;

    return {
      locations,
      priorityLocations,
      locationsWithoutSales,
      missingDaysCountTotal,
      importFailuresCount,
      attentionRequired,
      monitoredLocations,
      healthyLocations,
      activeIncidents,
    };
  }, [findings, intelligence]);

  const health = healthTone(intelligence?.health || (model.activeIncidents > 0 ? 'AMARILLO' : 'VERDE'));
  const visibleProblems = useMemo(() => {
    if (!filterSeverity) return findings;
    return findings.filter((row) => row.severity === filterSeverity);
  }, [findings, filterSeverity]);

  const operationalSummary = intelligence?.operational_digest?.summary_text && !intelligence.operational_digest.summary_text.toLowerCase().includes('analice')
    ? intelligence.operational_digest.summary_text
    : `Hoy se detectaron ${model.locationsWithoutSales} locales sin ventas, ${model.importFailuresCount} importaciones fallidas, ${model.missingDaysCountTotal} días faltantes y ${model.attentionRequired} locales con seguimiento requerido.`;

  const loadFindings = async () => {
    if (!currentMall?.id || !token) {
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const response = await ApiService.getOperationsIntelligence(currentMall.id, token);
      setIntelligence(response);
    } catch (error: any) {
      setFlash({ kind: 'error', message: error?.message || 'No se pudo cargar la salud operativa.' });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadFindings();
  }, [currentMall?.id, token]);

  const handleRun = async () => {
    if (!currentMall?.id || !token || !canOperate) return;
    setRunning(true);
    setFlash(null);
    try {
      const result = await ApiService.runOperationsAuditor(currentMall.id, token, 7);
      setFlash({
        kind: result.errors?.length ? 'error' : 'success',
        message: `Auditor ejecutado: ${result.findings_created} nuevos, ${result.findings_updated} actualizados.`,
      });
      await loadFindings();
    } catch (error: any) {
      setFlash({ kind: 'error', message: error?.message || 'No se pudo ejecutar Operations Auditor.' });
    } finally {
      setRunning(false);
    }
  };

  const handleAcknowledge = async (finding: OperationalFinding) => {
    if (!currentMall?.id || !token) return;
    setWorkingId(finding.id);
    try {
      await ApiService.acknowledgeOperationalFinding(currentMall.id, finding.id, token);
      await loadFindings();
    } catch (error: any) {
      setFlash({ kind: 'error', message: error?.message || 'No se pudo reconocer el problema.' });
    } finally {
      setWorkingId(null);
    }
  };

  const handleResolve = async (finding: OperationalFinding) => {
    if (!currentMall?.id || !token) return;
    setWorkingId(finding.id);
    try {
      await ApiService.resolveOperationalFinding(currentMall.id, finding.id, token);
      await loadFindings();
    } catch (error: any) {
      setFlash({ kind: 'error', message: error?.message || 'No se pudo resolver el problema.' });
    } finally {
      setWorkingId(null);
    }
  };

  return (
    <div className="space-y-4">
      <section className="overflow-hidden rounded-[2rem] border border-slate-200 bg-slate-950 text-white shadow-xl shadow-slate-900/10">
        <div className="relative p-4 md:p-4">
          <div className="absolute right-0 top-0 h-48 w-48 rounded-full bg-emerald-400/20 blur-3xl" />
          <div className="absolute bottom-0 left-1/3 h-36 w-36 rounded-full bg-amber-300/10 blur-3xl" />
          <div className="relative flex flex-col gap-5 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <div className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/10 px-3 py-1 text-xs font-black text-slate-200">
                <ShieldAlert size={14} />
                Centro de Salud Operativa
              </div>
              <h2 className="mt-4 text-xl font-black tracking-tight">Estado Operativo del Mall</h2>
              <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-300">
                Vista ejecutiva para saber qué locales tienen problemas, qué información falta, qué cargas fallaron y qué acción tomar ahora.
              </p>
            </div>
            <div className="flex flex-col items-start gap-3 sm:flex-row sm:items-center">
              <div className={`rounded-2xl border px-4 py-3 text-sm font-black ${health.tone}`}>
                {health.label}
              </div>
              <button
                onClick={handleRun}
                disabled={!canOperate || running}
                className="inline-flex items-center gap-2 rounded-2xl bg-emerald-400 px-5 py-3 text-sm font-black text-slate-950 hover:bg-emerald-300 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {running ? <Loader2 size={18} className="animate-spin" /> : <PlayCircle size={18} />}
                Actualizar auditoría
              </button>
            </div>
          </div>
        </div>
      </section>

      {flash && (
        <div className={`rounded-2xl border px-4 py-3 text-sm font-bold ${flash.kind === 'success' ? 'border-emerald-200 bg-emerald-50 text-emerald-700' : 'border-red-200 bg-red-50 text-red-700'}`}>
          {flash.message}
        </div>
      )}

      <section className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Locales sin ventas hoy" value={model.locationsWithoutSales} helper="Activos sin venta esperada" icon={Store} className="bg-red-50 text-red-600" />
        <StatCard label="Días faltantes detectados" value={model.missingDaysCountTotal} helper="Información pendiente" icon={Clock} className="bg-amber-50 text-amber-600" />
        <StatCard label="Importaciones fallidas" value={model.importFailuresCount} helper="Cargas con error" icon={AlertTriangle} className="bg-orange-50 text-orange-600" />
        <StatCard label="Locales con seguimiento" value={model.attentionRequired} helper="Requieren acción manual" icon={Activity} className="bg-indigo-50 text-indigo-600" />
      </section>

      <section className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm xl:col-span-1">
          <p className="text-xs font-black uppercase tracking-widest text-slate-400">Resumen operativo</p>
          <h3 className="mt-2 text-xl font-black text-slate-900">Qué cambió y qué atender</h3>
          <p className="mt-4 text-sm leading-6 text-slate-700">{operationalSummary}</p>
          <div className="mt-4 rounded-2xl bg-emerald-50 p-4">
            <p className="text-[10px] font-black uppercase tracking-widest text-emerald-500">Prioridad máxima</p>
            <p className="mt-1 text-sm font-semibold text-emerald-900">
              {model.priorityLocations[0]?.local_name || intelligence?.operational_digest?.top_priority || 'Sin prioridad crítica detectada.'}
            </p>
            <p className="mt-1 text-xs text-emerald-800">
              {model.priorityLocations[0]?.action || intelligence?.operational_digest?.recommended_action || 'Continuar monitoreo operativo.'}
            </p>
          </div>
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm xl:col-span-2">
          <div className="flex items-center justify-between gap-4">
            <div>
              <p className="text-xs font-black uppercase tracking-widest text-slate-400">Prioridades de hoy</p>
              <h3 className="mt-2 text-xl font-black text-slate-900">Locales que requieren atención</h3>
            </div>
            <button
              onClick={loadFindings}
              disabled={loading}
              className="inline-flex items-center gap-2 rounded-xl border border-slate-200 px-3 py-2 text-sm font-black text-slate-600 hover:bg-slate-50 disabled:opacity-50"
            >
              <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
              Refrescar
            </button>
          </div>
          <div className="mt-4 space-y-3">
            {model.priorityLocations.length === 0 ? (
              <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-800">
                No hay prioridades pendientes para este mall.
              </div>
            ) : model.priorityLocations.map((item, index) => (
              <div key={`${item.local_id || item.local_name}-${index}`} className="rounded-2xl border border-slate-100 bg-slate-50 p-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h4 className="font-black text-slate-900">{item.local_name}</h4>
                  <span className={`rounded-full border px-2.5 py-1 text-xs font-black ${severityStyle[item.severity || 'INFO'] || severityStyle.INFO}`}>
                    Prioridad {item.priority_score || 0}
                  </span>
                </div>
                <p className="mt-2 text-sm text-slate-700">{item.reason}</p>
                <p className="mt-2 text-sm font-bold text-emerald-700">Acción: {item.action}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
          <div>
            <p className="text-xs font-black uppercase tracking-widest text-slate-400">Salud de locales</p>
            <h3 className="mt-2 text-xl font-black text-slate-900">Ordenado por mayor riesgo operativo</h3>
            <p className="mt-1 text-sm text-slate-500">
              {model.monitoredLocations} locales monitoreados · {model.healthyLocations} saludables · {model.activeIncidents} incidentes activos
            </p>
          </div>
          <select
            value={filterSeverity}
            onChange={(event) => setFilterSeverity(event.target.value)}
            className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm font-bold text-slate-700"
          >
            <option value="">Todas las prioridades</option>
            <option value="CRITICAL">Crítico</option>
            <option value="HIGH">Alto</option>
            <option value="WARNING">Advertencia</option>
            <option value="INFO">Info</option>
          </select>
        </div>

        <div className="mt-5 overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-100 text-sm">
            <thead>
              <tr className="text-left text-xs font-black uppercase tracking-widest text-slate-400">
                <th className="px-3 py-3">Local</th>
                <th className="px-3 py-3">Health Score</th>
                <th className="px-3 py-3">Estado</th>
                <th className="px-3 py-3">Última señal</th>
                <th className="px-3 py-3">Días faltantes</th>
                <th className="px-3 py-3">Acción</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {model.locations.slice(0, 12).map((local, index) => (
                <tr key={`${local.local_id || local.local_name}-${index}`} className="align-top">
                  <td className="px-3 py-4 font-black text-slate-900">{local.local_name}</td>
                  <td className="px-3 py-4">
                    <span className={`inline-flex rounded-full border px-3 py-1 text-xs font-black ${scoreTone(local.score)}`}>{local.score}</span>
                  </td>
                  <td className="px-3 py-4 text-slate-700">{local.status}</td>
                  <td className="px-3 py-4 text-slate-500">{formatDateTime(local.last_activity)}</td>
                  <td className="px-3 py-4 text-slate-700">{local.missing_days || 0}</td>
                  <td className="px-3 py-4 text-slate-700">{local.action || 'Continuar monitoreo operativo.'}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {model.locations.length === 0 && (
            <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-4 text-center text-emerald-800">
              <CheckCircle2 className="mx-auto mb-3 text-emerald-600" size={36} />
              <p className="font-black">No hay locales con seguimiento pendiente.</p>
            </div>
          )}
        </div>
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="mb-4">
          <p className="text-xs font-black uppercase tracking-widest text-slate-400">Problemas operativos</p>
          <h3 className="mt-2 text-lg font-black text-slate-900">Casos que explican las prioridades</h3>
          <p className="text-sm text-slate-500">El detalle técnico queda debajo; la lectura principal es por impacto y acción.</p>
        </div>

        {loading ? (
          <div className="rounded-2xl border border-slate-200 bg-white p-10 text-center text-slate-500">
            <Loader2 className="mx-auto mb-3 animate-spin" />
            Cargando salud operativa...
          </div>
        ) : visibleProblems.length === 0 ? (
          <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-10 text-center">
            <CheckCircle2 className="mx-auto mb-3 text-emerald-600" size={36} />
            <h3 className="text-lg font-black text-emerald-900">Sin problemas operativos abiertos</h3>
            <p className="mt-1 text-sm text-emerald-700">No hay acciones pendientes para este mall.</p>
          </div>
        ) : (
          <div className="space-y-4">
            {visibleProblems.map((finding) => (
              <OperationalProblemCard
                key={finding.id}
                finding={finding}
                onAcknowledge={handleAcknowledge}
                onResolve={handleResolve}
                actionDisabled={!canOperate || workingId === finding.id}
              />
            ))}
          </div>
        )}
      </section>

      {!canOperate && (
        <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
          <div className="flex items-center gap-2 font-black">
            <Wrench size={16} />
            Modo lectura
          </div>
          <p className="mt-1">Tu perfil puede consultar la salud operativa. Ejecutar auditoría o cerrar problemas queda reservado para IT/Admin.</p>
        </div>
      )}
    </div>
  );
};
