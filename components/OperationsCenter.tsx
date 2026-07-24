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
  <div className="rounded-lg border border-slate-200 bg-white px-2.5 py-2 shadow-sm">
    <div className="flex items-start justify-between gap-2">
      <div>
        <p className="text-[9px] font-bold uppercase tracking-widest text-slate-400">{label}</p>
        <div className="mt-0.5 text-base font-black text-slate-900">{value}</div>
        <p className="mt-0.5 text-[11px] font-semibold text-slate-500">{helper}</p>
      </div>
      <div className={`flex h-8 w-8 items-center justify-center rounded-lg ${className}`}>
        <Icon size={16} />
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
  <article className="rounded-lg border border-slate-200 bg-white p-3 shadow-sm">
    <div className="flex flex-col gap-2 lg:flex-row lg:items-start lg:justify-between">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className={`inline-flex rounded-full border px-2 py-0.5 text-[11px] font-black ${severityStyle[finding.severity] || severityStyle.INFO}`}>
            {severityLabel[finding.severity] || finding.severity}
          </span>
          {finding.local_name && (
            <span className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-white px-2 py-0.5 text-[11px] font-bold text-slate-600">
              <Store size={12} /> {finding.local_name}
            </span>
          )}
          <span className="inline-flex rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-[11px] font-bold text-slate-600">
            Prioridad {finding.priority_score || 0}
          </span>
        </div>
        <h3 className="mt-1.5 text-sm font-black text-slate-900">{businessTitle(finding)}</h3>
        <p className="mt-0.5 text-xs leading-5 text-slate-600">{businessReason(finding)}</p>
      </div>
      <div className="flex shrink-0 gap-2">
        {finding.status === 'OPEN' && (
          <button
            onClick={() => onAcknowledge(finding)}
            disabled={actionDisabled}
            className="rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs font-black text-slate-600 hover:bg-slate-50 disabled:opacity-50"
          >
            Reconocer
          </button>
        )}
        <button
          onClick={() => onResolve(finding)}
          disabled={actionDisabled}
          className="rounded-lg bg-indigo-600 px-2.5 py-1.5 text-xs font-black text-white hover:bg-indigo-700 disabled:opacity-50"
        >
          Resolver
        </button>
      </div>
    </div>

    <div className="mt-2 grid grid-cols-1 gap-2 lg:grid-cols-3">
      <div className="rounded-lg bg-slate-50 p-2.5">
        <p className="text-[9px] font-black uppercase tracking-widest text-slate-400">Motivo</p>
        <p className="mt-0.5 text-xs text-slate-700">{finding.root_cause || businessReason(finding)}</p>
      </div>
      <div className="rounded-lg bg-emerald-50 p-2.5">
        <p className="text-[9px] font-black uppercase tracking-widest text-emerald-500">Acción recomendada</p>
        <p className="mt-0.5 text-xs text-emerald-900">{finding.recommendation || 'Revisar evidencia operativa y confirmar impacto.'}</p>
      </div>
      <div className="rounded-lg bg-indigo-50 p-2.5">
        <p className="text-[9px] font-black uppercase tracking-widest text-indigo-500">Última señal</p>
        <p className="mt-0.5 text-xs text-indigo-950">
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
  const [activeTab, setActiveTab] = useState<'health' | 'cases'>('health');
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
    <div className="space-y-2 lg:h-[calc(100dvh-8rem)] lg:min-h-[500px] lg:overflow-y-auto lg:pr-1">
      <section className="overflow-hidden rounded-xl border border-slate-200 bg-white text-slate-900 shadow-sm">
        <div className="relative px-3 py-2.5">
          <div className="relative flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <div className="inline-flex items-center gap-2 rounded-full border border-indigo-100 bg-indigo-50 px-2.5 py-0.5 text-[11px] font-black text-indigo-700">
                <ShieldAlert size={13} />
                Centro de Salud Operativa
              </div>
              <h2 className="mt-1.5 text-lg font-black tracking-tight">Estado Operativo del Mall</h2>
              <p className="mt-0.5 max-w-2xl text-xs leading-5 text-slate-500">
                Vista ejecutiva para saber qué locales tienen problemas, qué información falta, qué cargas fallaron y qué acción tomar ahora.
              </p>
            </div>
            <div className="flex flex-col items-start gap-2 sm:flex-row sm:items-center">
              <div className={`rounded-xl border px-3 py-2 text-xs font-black ${health.tone}`}>
                {health.label}
              </div>
              <button
                onClick={handleRun}
                disabled={!canOperate || running}
                className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-3 py-2 text-xs font-black text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {running ? <Loader2 size={16} className="animate-spin" /> : <PlayCircle size={16} />}
                Actualizar auditoría
              </button>
            </div>
          </div>
        </div>
      </section>

      {flash && (
        <div className={`rounded-xl border px-3 py-2 text-xs font-bold ${flash.kind === 'success' ? 'border-emerald-200 bg-emerald-50 text-emerald-700' : 'border-red-200 bg-red-50 text-red-700'}`}>
          {flash.message}
        </div>
      )}

      <section className="grid grid-cols-2 gap-2 xl:grid-cols-4">
        <StatCard label="Locales sin ventas hoy" value={model.locationsWithoutSales} helper="Activos sin venta esperada" icon={Store} className="bg-red-50 text-red-600" />
        <StatCard label="Días faltantes detectados" value={model.missingDaysCountTotal} helper="Información pendiente" icon={Clock} className="bg-amber-50 text-amber-600" />
        <StatCard label="Importaciones fallidas" value={model.importFailuresCount} helper="Cargas con error" icon={AlertTriangle} className="bg-orange-50 text-orange-600" />
        <StatCard label="Locales con seguimiento" value={model.attentionRequired} helper="Requieren acción manual" icon={Activity} className="bg-indigo-50 text-indigo-600" />
      </section>

      <section className="grid grid-cols-1 gap-2 xl:grid-cols-3">
        <div className="rounded-lg border border-slate-200 bg-white p-3 shadow-sm xl:col-span-1">
          <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">Resumen operativo</p>
          <h3 className="mt-0.5 text-base font-black text-slate-900">Qué cambió y qué atender</h3>
          <p className="mt-2 text-xs leading-5 text-slate-700">{operationalSummary}</p>
          <div className="mt-2 rounded-lg bg-emerald-50 p-2.5">
            <p className="text-[9px] font-black uppercase tracking-widest text-emerald-500">Prioridad máxima</p>
            <p className="mt-0.5 text-xs font-semibold text-emerald-900">
              {model.priorityLocations[0]?.local_name || intelligence?.operational_digest?.top_priority || 'Sin prioridad crítica detectada.'}
            </p>
            <p className="mt-0.5 text-[11px] text-emerald-800">
              {model.priorityLocations[0]?.action || intelligence?.operational_digest?.recommended_action || 'Continuar monitoreo operativo.'}
            </p>
          </div>
        </div>

        <div className="rounded-lg border border-slate-200 bg-white p-3 shadow-sm xl:col-span-2">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">Prioridades de hoy</p>
              <h3 className="mt-0.5 text-base font-black text-slate-900">Locales que requieren atención</h3>
            </div>
            <button
              onClick={loadFindings}
              disabled={loading}
              className="inline-flex items-center gap-2 rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs font-black text-slate-600 hover:bg-slate-50 disabled:opacity-50"
            >
              <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
              Refrescar
            </button>
          </div>
          <div className="mt-2 max-h-[200px] space-y-2 overflow-y-auto pr-1">
            {model.priorityLocations.length === 0 ? (
              <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-xs text-emerald-800">
                No hay prioridades pendientes para este mall.
              </div>
            ) : model.priorityLocations.map((item, index) => (
              <div key={`${item.local_id || item.local_name}-${index}`} className="rounded-lg border border-slate-100 bg-slate-50 p-2.5">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h4 className="text-sm font-black text-slate-900">{item.local_name}</h4>
                  <span className={`rounded-full border px-2 py-0.5 text-[11px] font-black ${severityStyle[item.severity || 'INFO'] || severityStyle.INFO}`}>
                    Prioridad {item.priority_score || 0}
                  </span>
                </div>
                <p className="mt-1 text-xs text-slate-700">{item.reason}</p>
                <p className="mt-1 text-xs font-bold text-emerald-700">Acción: {item.action}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="rounded-lg border border-slate-200 bg-white shadow-sm">
        <div className="flex overflow-x-auto border-b border-slate-200 px-3" role="tablist" aria-label="Vistas del centro operativo">
          <button
            type="button"
            role="tab"
            id="operations-health-tab"
            aria-selected={activeTab === 'health'}
            aria-controls="operations-health-panel"
            onClick={() => setActiveTab('health')}
            className={`inline-flex min-h-10 shrink-0 items-center gap-2 border-b-2 px-3 text-xs font-black transition-colors ${activeTab === 'health' ? 'border-indigo-600 text-indigo-700' : 'border-transparent text-slate-500 hover:text-slate-800'}`}
          >
            <Activity size={15} />
            Salud de locales
          </button>
          <button
            type="button"
            role="tab"
            id="operations-cases-tab"
            aria-selected={activeTab === 'cases'}
            aria-controls="operations-cases-panel"
            onClick={() => setActiveTab('cases')}
            className={`inline-flex min-h-10 shrink-0 items-center gap-2 border-b-2 px-3 text-xs font-black transition-colors ${activeTab === 'cases' ? 'border-indigo-600 text-indigo-700' : 'border-transparent text-slate-500 hover:text-slate-800'}`}
          >
            <AlertTriangle size={15} />
            Casos que explican las prioridades
            {findings.length > 0 && (
              <span className="rounded-full bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-700">{findings.length}</span>
            )}
          </button>
        </div>

        {activeTab === 'health' && (
          <div className="p-3" role="tabpanel" id="operations-health-panel" aria-labelledby="operations-health-tab">
            <div>
              <h3 className="text-base font-black text-slate-900">Ordenado por mayor riesgo operativo</h3>
              <p className="mt-0.5 text-xs text-slate-500">
                {model.monitoredLocations} locales monitoreados · {model.healthyLocations} saludables · {model.activeIncidents} incidentes activos
              </p>
            </div>

            <div className="mt-2 max-h-[280px] overflow-auto">
          <table className="min-w-full divide-y divide-slate-100 text-xs">
            <thead className="sticky top-0 z-10 bg-white">
              <tr className="text-left text-[10px] font-black uppercase tracking-widest text-slate-400">
                <th className="px-2.5 py-2">Local</th>
                <th className="px-2.5 py-2">Health Score</th>
                <th className="px-2.5 py-2">Estado</th>
                <th className="px-2.5 py-2">Última señal</th>
                <th className="px-2.5 py-2">Días faltantes</th>
                <th className="px-2.5 py-2">Acción</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {model.locations.slice(0, 10).map((local, index) => (
                <tr key={`${local.local_id || local.local_name}-${index}`} className="align-top">
                  <td className="px-2.5 py-2 font-black text-slate-900">{local.local_name}</td>
                  <td className="px-2.5 py-2">
                    <span className={`inline-flex rounded-full border px-2.5 py-0.5 text-[11px] font-black ${scoreTone(local.score)}`}>{local.score}</span>
                  </td>
                  <td className="px-2.5 py-2 text-slate-700">{local.status}</td>
                  <td className="px-2.5 py-2 text-slate-500">{formatDateTime(local.last_activity)}</td>
                  <td className="px-2.5 py-2 text-slate-700">{local.missing_days || 0}</td>
                  <td className="max-w-[22rem] px-2.5 py-2 text-slate-700">{local.action || 'Continuar monitoreo operativo.'}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {model.locations.length === 0 && (
            <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-center text-emerald-800">
              <CheckCircle2 className="mx-auto mb-2 text-emerald-600" size={28} />
              <p className="font-black">No hay locales con seguimiento pendiente.</p>
            </div>
          )}
            </div>
          </div>
        )}

        {activeTab === 'cases' && (
          <div className="p-3" role="tabpanel" id="operations-cases-panel" aria-labelledby="operations-cases-tab">
            <div className="mb-2 flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
              <div>
                <h3 className="text-base font-black text-slate-900">Casos que explican las prioridades</h3>
                <p className="text-xs text-slate-500">Detalle por impacto, causa y acción recomendada.</p>
              </div>
              <select
                value={filterSeverity}
                onChange={(event) => setFilterSeverity(event.target.value)}
                aria-label="Filtrar casos por prioridad"
                className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs font-bold text-slate-700"
              >
                <option value="">Todas las prioridades</option>
                <option value="CRITICAL">Crítico</option>
                <option value="HIGH">Alto</option>
                <option value="WARNING">Advertencia</option>
                <option value="INFO">Info</option>
              </select>
            </div>

            {loading ? (
              <div className="rounded-xl border border-slate-200 bg-white p-6 text-center text-slate-500">
                <Loader2 className="mx-auto mb-2 animate-spin" />
                Cargando salud operativa...
              </div>
            ) : visibleProblems.length === 0 ? (
              <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-6 text-center">
                <CheckCircle2 className="mx-auto mb-2 text-emerald-600" size={28} />
                <h3 className="text-base font-black text-emerald-900">Sin problemas operativos abiertos</h3>
                <p className="mt-1 text-xs text-emerald-700">No hay acciones pendientes para este mall.</p>
              </div>
            ) : (
              <div className="max-h-[320px] space-y-2 overflow-y-auto pr-1">
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
          </div>
        )}
      </section>

      {!canOperate && (
        <div className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800">
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
