import React, { useEffect, useMemo, useState } from 'react';
import { Activity, AlertTriangle, CheckCircle2, Clock, Eye, Loader2, PlayCircle, RefreshCw, ShieldAlert, Sparkles, Store, TrendingUp, Wrench } from 'lucide-react';
import { ApiService } from '../api';
import { useAuth } from '../context/AuthProvider';
import { OperationalFinding, OperationsFindingsResponse, OperationsIntelligenceResponse } from '../types';

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
  if (!value) return 'Sin ejecución';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString();
};

const healthFromSummary = (summary?: OperationsFindingsResponse['summary']) => {
  if (!summary) return { label: 'Sin datos', tone: 'bg-slate-100 text-slate-700 border-slate-200' };
  if (summary.critical > 0) return { label: 'Rojo', tone: 'bg-red-50 text-red-700 border-red-200' };
  if (summary.high > 0 || summary.warning > 0) return { label: 'Amarillo', tone: 'bg-amber-50 text-amber-700 border-amber-200' };
  return { label: 'Verde', tone: 'bg-emerald-50 text-emerald-700 border-emerald-200' };
};

const StatCard = ({ label, value, icon: Icon, className }: { label: string; value: React.ReactNode; icon: any; className: string }) => (
  <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
    <div className="flex items-center justify-between gap-4">
      <div>
        <p className="text-xs font-bold uppercase tracking-widest text-slate-400">{label}</p>
        <div className="mt-2 text-2xl font-black text-slate-900">{value}</div>
      </div>
      <div className={`h-12 w-12 rounded-2xl flex items-center justify-center ${className}`}>
        <Icon size={22} />
      </div>
    </div>
  </div>
);

const FindingCard = ({
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
  <article className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
    <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-4">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <span className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-black ${severityStyle[finding.severity] || severityStyle.INFO}`}>
            {severityLabel[finding.severity] || finding.severity}
          </span>
          <span className="inline-flex rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs font-bold text-slate-600">
            {finding.source}
          </span>
          {finding.local_name && (
            <span className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-white px-2.5 py-1 text-xs font-bold text-slate-600">
              <Store size={12} /> {finding.local_name}
            </span>
          )}
        </div>
        <h3 className="mt-3 text-lg font-black text-slate-900">{finding.title}</h3>
        <p className="mt-1 text-sm leading-6 text-slate-600">{finding.description}</p>
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
        <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">Causa probable</p>
        <p className="mt-1 text-sm text-slate-700">{finding.root_cause || 'Pendiente de análisis.'}</p>
      </div>
      <div className="rounded-2xl bg-emerald-50 p-4">
        <p className="text-[10px] font-black uppercase tracking-widest text-emerald-500">Recomendación</p>
        <p className="mt-1 text-sm text-emerald-900">{finding.recommendation || 'Revisar evidencia y confirmar impacto.'}</p>
      </div>
      <div className="rounded-2xl bg-indigo-50 p-4">
        <p className="text-[10px] font-black uppercase tracking-widest text-indigo-500">Evidencia</p>
        <p className="mt-1 text-sm text-indigo-950">
          Confianza {Math.round((finding.confidence || 0) * 100)}% · Detectado {formatDateTime(finding.detected_at)}
        </p>
      </div>
    </div>
  </article>
);

export const OperationsCenter: React.FC = () => {
  const { currentMall, session, isAdmin, isTic } = useAuth();
  const token = session?.access_token || '';
  const [data, setData] = useState<OperationsFindingsResponse | null>(null);
  const [intelligence, setIntelligence] = useState<OperationsIntelligenceResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [workingId, setWorkingId] = useState<string | null>(null);
  const [filterSeverity, setFilterSeverity] = useState('');
  const [flash, setFlash] = useState<{ kind: 'success' | 'error'; message: string } | null>(null);

  const canOperate = Boolean(isAdmin || isTic);
  const health = healthFromSummary(data?.summary);

  const findings = useMemo(() => {
    const rows = data?.findings || [];
    if (!filterSeverity) return rows;
    return rows.filter((row) => row.severity === filterSeverity);
  }, [data, filterSeverity]);

  const loadFindings = async () => {
    if (!currentMall?.id || !token) {
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const response = await ApiService.getOperationsIntelligence(currentMall.id, token);
      setIntelligence(response);
      setData({
        findings: response.open_findings || [],
        summary: {
          total_open: response.summary?.total_open || 0,
          critical: response.summary?.critical || 0,
          high: response.summary?.high || 0,
          warning: response.summary?.warning || 0,
          info: response.summary?.info || 0,
          affected_locals: response.summary?.affected_locals || 0,
          by_severity: response.summary?.by_severity || {},
          by_source: {},
          last_run_at: response.operational_digest?.generated_at || null,
          last_run_status: response.health,
        },
        last_run: null,
      });
    } catch (error: any) {
      setFlash({ kind: 'error', message: error?.message || 'No se pudieron cargar los hallazgos.' });
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
      setFlash({ kind: 'error', message: error?.message || 'No se pudo reconocer el hallazgo.' });
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
      setFlash({ kind: 'error', message: error?.message || 'No se pudo resolver el hallazgo.' });
    } finally {
      setWorkingId(null);
    }
  };

  return (
    <div className="space-y-6">
      <section className="overflow-hidden rounded-[2rem] border border-slate-200 bg-slate-950 text-white shadow-xl shadow-slate-900/10">
        <div className="relative p-6 md:p-8">
          <div className="absolute right-0 top-0 h-48 w-48 rounded-full bg-emerald-400/20 blur-3xl" />
          <div className="absolute bottom-0 left-1/3 h-36 w-36 rounded-full bg-amber-300/10 blur-3xl" />
          <div className="relative flex flex-col gap-5 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <div className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/10 px-3 py-1 text-xs font-black text-slate-200">
                <ShieldAlert size={14} />
                Operations Auditor
              </div>
              <h2 className="mt-4 text-3xl font-black tracking-tight">Operations Center</h2>
              <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-300">
                Hallazgos operativos detectados desde monitor de carga, días de información, ventas y workers. Copilot usa esta misma fuente para responder con contexto y prioridades.
              </p>
            </div>
            <div className="flex flex-col items-start gap-3 sm:flex-row sm:items-center">
              <div className={`rounded-2xl border px-4 py-3 text-sm font-black ${health.tone}`}>
                Estado {health.label}
              </div>
              <button
                onClick={handleRun}
                disabled={!canOperate || running}
                className="inline-flex items-center gap-2 rounded-2xl bg-emerald-400 px-5 py-3 text-sm font-black text-slate-950 hover:bg-emerald-300 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {running ? <Loader2 size={18} className="animate-spin" /> : <PlayCircle size={18} />}
                Ejecutar auditor
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

      <section className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-5">
        <StatCard label="Abiertos" value={data?.summary.total_open ?? 0} icon={Activity} className="bg-slate-900 text-white" />
        <StatCard label="Críticos" value={data?.summary.critical ?? 0} icon={ShieldAlert} className="bg-red-50 text-red-600" />
        <StatCard label="Altos" value={data?.summary.high ?? 0} icon={AlertTriangle} className="bg-orange-50 text-orange-600" />
        <StatCard label="Locales afectados" value={data?.summary.affected_locals ?? 0} icon={Store} className="bg-indigo-50 text-indigo-600" />
        <StatCard label="Último digest" value={<span className="text-sm">{formatDateTime(intelligence?.operational_digest?.generated_at)}</span>} icon={Clock} className="bg-emerald-50 text-emerald-600" />
      </section>

      <section className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm xl:col-span-1">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-slate-900 text-white">
              <Sparkles size={20} />
            </div>
            <div>
              <h3 className="font-black text-slate-900">Operational Digest</h3>
              <p className="text-xs text-slate-500">{formatDateTime(intelligence?.operational_digest?.generated_at)}</p>
            </div>
          </div>
          <p className="mt-4 text-sm leading-6 text-slate-700">
            {intelligence?.operational_digest?.summary_text || 'Aún no hay resumen operativo generado para este mall.'}
          </p>
          <div className="mt-4 rounded-2xl bg-emerald-50 p-4">
            <p className="text-[10px] font-black uppercase tracking-widest text-emerald-500">Recomendación</p>
            <p className="mt-1 text-sm font-semibold text-emerald-900">
              {intelligence?.operational_digest?.recommended_action || 'Continuar monitoreo operativo.'}
            </p>
          </div>
        </div>

        <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm xl:col-span-2">
          <div className="flex items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-indigo-50 text-indigo-600">
                <Eye size={20} />
              </div>
              <div>
                <h3 className="font-black text-slate-900">Observaciones recientes</h3>
                <p className="text-xs text-slate-500">Actividad observada sin crear incidencias innecesarias.</p>
              </div>
            </div>
            <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-black text-slate-600">
              {intelligence?.recent_observations?.length || 0}
            </span>
          </div>
          <div className="mt-4 space-y-3">
            {(intelligence?.recent_observations || []).slice(0, 5).map((item, index) => (
              <div key={item.id || `${item.observation_type}-${index}`} className="rounded-2xl border border-slate-100 bg-slate-50 p-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="rounded-full bg-white px-2.5 py-1 text-[11px] font-black text-slate-600">
                    {item.observation_type}
                  </span>
                  <span className="text-xs font-semibold text-slate-400">{formatDateTime(item.created_at)}</span>
                </div>
                <p className="mt-2 text-sm font-semibold text-slate-800">{item.observation}</p>
                {item.conclusion && <p className="mt-1 text-sm text-slate-600">{item.conclusion}</p>}
              </div>
            ))}
            {(!intelligence?.recent_observations || intelligence.recent_observations.length === 0) && (
              <p className="rounded-2xl bg-slate-50 p-4 text-sm text-slate-500">
                Aún no hay observaciones recientes del agente.
              </p>
            )}
          </div>
        </div>
      </section>

      {Boolean(intelligence?.patterns?.length) && (
        <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-amber-50 text-amber-600">
              <TrendingUp size={20} />
            </div>
            <div>
              <h3 className="font-black text-slate-900">Patrones operativos</h3>
              <p className="text-xs text-slate-500">Comportamientos recurrentes aprendidos por el agente.</p>
            </div>
          </div>
          <div className="mt-4 grid grid-cols-1 gap-3 lg:grid-cols-3">
            {(intelligence?.patterns || []).slice(0, 6).map((pattern, index) => (
              <div key={pattern.id || `${pattern.pattern_type}-${index}`} className="rounded-2xl border border-amber-100 bg-amber-50 p-4">
                <p className="text-xs font-black uppercase tracking-widest text-amber-600">{pattern.pattern_type}</p>
                <h4 className="mt-1 font-black text-slate-900">{pattern.pattern_name}</h4>
                <p className="mt-1 text-sm text-slate-600">{pattern.description || 'Patrón detectado por recurrencia operativa.'}</p>
                <p className="mt-3 text-xs font-bold text-amber-700">
                  {pattern.occurrences} ocurrencias · Confianza {Math.round((pattern.confidence || 0) * 100)}%
                </p>
              </div>
            ))}
          </div>
        </section>
      )}

      <section className="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div>
            <h3 className="text-lg font-black text-slate-900">Hallazgos abiertos</h3>
            <p className="text-sm text-slate-500">Prioriza ventas, días faltantes y trazabilidad de carga.</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <select
              value={filterSeverity}
              onChange={(event) => setFilterSeverity(event.target.value)}
              className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm font-bold text-slate-700"
            >
              <option value="">Todas las severidades</option>
              <option value="CRITICAL">Crítico</option>
              <option value="HIGH">Alto</option>
              <option value="WARNING">Advertencia</option>
              <option value="INFO">Info</option>
            </select>
            <button
              onClick={loadFindings}
              disabled={loading}
              className="inline-flex items-center gap-2 rounded-xl border border-slate-200 px-3 py-2 text-sm font-black text-slate-600 hover:bg-slate-50 disabled:opacity-50"
            >
              <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
              Refrescar
            </button>
          </div>
        </div>
      </section>

      {loading ? (
        <div className="rounded-3xl border border-slate-200 bg-white p-10 text-center text-slate-500">
          <Loader2 className="mx-auto mb-3 animate-spin" />
          Cargando Operations Center...
        </div>
      ) : findings.length === 0 ? (
        <div className="rounded-3xl border border-emerald-200 bg-emerald-50 p-10 text-center">
          <CheckCircle2 className="mx-auto mb-3 text-emerald-600" size={36} />
          <h3 className="text-lg font-black text-emerald-900">Sin hallazgos abiertos</h3>
          <p className="mt-1 text-sm text-emerald-700">El estado operativo no muestra alertas pendientes para este mall.</p>
        </div>
      ) : (
        <div className="space-y-4">
          {findings.map((finding) => (
            <FindingCard
              key={finding.id}
              finding={finding}
              onAcknowledge={handleAcknowledge}
              onResolve={handleResolve}
              actionDisabled={!canOperate || workingId === finding.id}
            />
          ))}
        </div>
      )}

      {!canOperate && (
        <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
          <div className="flex items-center gap-2 font-black">
            <Wrench size={16} />
            Modo lectura
          </div>
          <p className="mt-1">Tu perfil puede consultar hallazgos. Ejecutar el auditor o cerrar hallazgos queda reservado para IT/Admin.</p>
        </div>
      )}
    </div>
  );
};
