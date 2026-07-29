import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import {
  AlertTriangle,
  CalendarPlus,
  CalendarDays,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Database,
  Eye,
  Lightbulb,
  Search,
  ShieldCheck,
  Sparkles,
  Store,
  TrendingDown,
  TrendingUp,
  Trash2,
  X,
} from 'lucide-react';
import { ApiService } from '../api';
import { useAuth } from '../context/AuthProvider';
import { useFormatCurrency } from '../hooks/useFormatCurrency';
import {
  BigDataCalendarDay,
  BigDataCalendarEventType,
  BigDataAnomalyContributor,
  BigDataPhaseOne,
} from '../types';
import { createBigDataRequestGate } from '../utils/bigDataRequestGate';

const WEEKDAY_HEADERS = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom'];
type IntelligenceTab = 'summary' | 'calendar' | 'anomalies' | 'quality';
type AnomalyView = 'pending' | 'explained';
type AnomalyDirection = 'ALL' | 'UP' | 'DOWN';
type AnomalySort = 'impact' | 'deviation' | 'date' | 'confidence';

interface AnomalyListRow {
  id: string;
  status: AnomalyView;
  date: string;
  direction: 'UP' | 'DOWN';
  deviationPercent: number;
  observedSales: number;
  expectedSales: number;
  impact: number;
  confidence: number;
  explanation: string;
  recommendation?: string;
  contributors: BigDataAnomalyContributor[];
  context: string;
}

const INTELLIGENCE_TABS: Array<{
  id: IntelligenceTab;
  label: string;
  description: string;
  icon: React.ElementType;
}> = [
  { id: 'summary', label: 'Resumen', description: 'Hallazgos y patrones', icon: Sparkles },
  { id: 'calendar', label: 'Calendario', description: 'Fechas y actividades', icon: CalendarDays },
  { id: 'anomalies', label: 'Anomalías', description: 'Movimientos relevantes', icon: AlertTriangle },
  { id: 'quality', label: 'Calidad', description: 'Cobertura y trazabilidad', icon: ShieldCheck },
];
const EVENT_TYPES: Array<{ value: BigDataCalendarEventType; label: string }> = [
  { value: 'PROMOTION', label: 'Promoción' },
  { value: 'HALLWAY_SALE', label: 'Venta de pasillo' },
  { value: 'MALL_ACTIVITY', label: 'Actividad del mall' },
  { value: 'HOLIDAY', label: 'Feriado especial' },
  { value: 'OTHER', label: 'Otro evento' },
];

const toIsoDate = (value: Date) => {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, '0');
  const day = String(value.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
};

const initialDates = () => {
  const end = new Date();
  const start = new Date(end);
  start.setDate(start.getDate() - 89);
  return { start: toIsoDate(start), end: toIsoDate(end) };
};

const safeDate = (value: string) => new Date(`${value}T12:00:00`);

const formatDate = (value: string, options: Intl.DateTimeFormatOptions = {}) =>
  safeDate(value).toLocaleDateString('es-DO', options);

const compactNumber = new Intl.NumberFormat('es-DO', {
  notation: 'compact',
  maximumFractionDigits: 1,
});

const toneClasses: Record<string, string> = {
  positive: 'border-emerald-100 bg-emerald-50/70 text-emerald-800',
  negative: 'border-rose-100 bg-rose-50/70 text-rose-800',
  warning: 'border-amber-100 bg-amber-50/80 text-amber-900',
  neutral: 'border-indigo-100 bg-indigo-50/70 text-indigo-800',
};

const qualityCopy = {
  RELIABLE: {
    label: 'Confiable',
    color: '#10b981',
    classes: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  },
  REVIEW: {
    label: 'Revisar',
    color: '#f59e0b',
    classes: 'bg-amber-50 text-amber-700 border-amber-200',
  },
  LOW_CONFIDENCE: {
    label: 'Confianza baja',
    color: '#f43f5e',
    classes: 'bg-rose-50 text-rose-700 border-rose-200',
  },
};

const calendarCellClasses = (day: BigDataCalendarDay) => {
  if (day.status === 'MISSING') {
    return 'border-dashed border-slate-200 bg-slate-50 text-slate-400';
  }
  if (day.status === 'ANOMALY') {
    return Number(day.deviation_percent || 0) >= 0
      ? 'border-emerald-300 bg-emerald-100 text-emerald-950 shadow-sm'
      : 'border-rose-300 bg-rose-100 text-rose-950 shadow-sm';
  }
  if (day.status === 'EXPLAINED_EVENT') {
    return 'border-sky-300 bg-sky-100 text-sky-950 shadow-sm';
  }
  if (day.is_holiday) {
    return 'border-violet-300 bg-violet-100 text-violet-950';
  }
  if (day.is_weekend) {
    return 'border-amber-200 bg-amber-50 text-amber-950';
  }
  return 'border-slate-100 bg-white text-slate-700 hover:border-indigo-200 hover:bg-indigo-50/40';
};

export const BigDataDashboard: React.FC = () => {
  const { currentMall, session, isAdmin, isTic } = useAuth();
  const { format } = useFormatCurrency();
  const [dates, setDates] = useState(initialDates);
  const [data, setData] = useState<BigDataPhaseOne | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<IntelligenceTab>('summary');
  const [anomalyView, setAnomalyView] = useState<AnomalyView>('pending');
  const [anomalySearch, setAnomalySearch] = useState('');
  const [anomalyDirection, setAnomalyDirection] = useState<AnomalyDirection>('ALL');
  const [anomalySort, setAnomalySort] = useState<AnomalySort>('impact');
  const [selectedAnomalyId, setSelectedAnomalyId] = useState<string | null>(null);
  const [selectedMonth, setSelectedMonth] = useState('');
  const [reloadKey, setReloadKey] = useState(0);
  const [showEventForm, setShowEventForm] = useState(false);
  const [eventSaving, setEventSaving] = useState(false);
  const [eventError, setEventError] = useState<string | null>(null);
  const [eventForm, setEventForm] = useState({
    name: '',
    event_type: 'MALL_ACTIVITY' as BigDataCalendarEventType,
    start_date: toIsoDate(new Date()),
    end_date: toIsoDate(new Date()),
    expected_impact: 'UP' as 'UP' | 'DOWN' | 'NEUTRAL',
    notes: '',
  });
  const requestVersion = useRef(0);
  const requestGate = useRef(createBigDataRequestGate());

  useEffect(() => {
    const mallId = currentMall?.id;
    const token = session?.access_token;
    const version = ++requestVersion.current;
    const requestId = requestGate.current.begin();
    setData(null);
    setError(null);
    if (!mallId || !token) {
      setLoading(false);
      return;
    }
    setLoading(true);
    ApiService.getBigDataPhaseOne(mallId, dates.start, dates.end, token)
      .then((response) => {
        if (currentMall?.id !== mallId) return;
        if (
          requestGate.current.isCurrent(requestId)
          && requestVersion.current === version
        ) {
          setData(response);
        }
      })
      .catch((requestError: any) => {
        if (requestGate.current.isCurrent(requestId) && requestVersion.current === version) {
          setError(requestError?.message || 'No se pudo cargar Inteligencia Comercial');
        }
      })
      .finally(() => {
        if (requestGate.current.isCurrent(requestId) && requestVersion.current === version) {
          setLoading(false);
        }
      });
  }, [currentMall?.id, session?.access_token, dates.start, dates.end, reloadKey]);

  const availableMonths = useMemo(
    () => Array.from(new Set((data?.calendar || []).map((day) => day.date.slice(0, 7)))).sort(),
    [data?.calendar],
  );

  useEffect(() => {
    if (!availableMonths.length) {
      setSelectedMonth('');
      return;
    }
    if (!availableMonths.includes(selectedMonth)) {
      setSelectedMonth(availableMonths[availableMonths.length - 1]);
    }
  }, [availableMonths, selectedMonth]);

  const visibleCalendar = useMemo(
    () => (data?.calendar || []).filter((day) => day.date.startsWith(selectedMonth)),
    [data?.calendar, selectedMonth],
  );

  const calendarLeadingSpaces = useMemo(() => {
    if (!selectedMonth) return 0;
    const sundayBased = safeDate(`${selectedMonth}-01`).getDay();
    return (sundayBased + 6) % 7;
  }, [selectedMonth]);

  const anomalyRows = useMemo<AnomalyListRow[]>(() => {
    if (!data) return [];
    const pending: AnomalyListRow[] = data.anomalies.map((anomaly) => ({
      id: `pending-${anomaly.date}`,
      status: 'pending',
      date: anomaly.date,
      direction: anomaly.direction,
      deviationPercent: anomaly.deviation_percent,
      observedSales: anomaly.observed_sales,
      expectedSales: anomaly.expected_sales,
      impact: anomaly.impact,
      confidence: anomaly.confidence,
      explanation: anomaly.explanation,
      recommendation: anomaly.recommendation,
      contributors: anomaly.contributors,
      context: anomaly.holiday_name
        || (anomaly.is_weekend ? 'Fin de semana' : 'Sin contexto comercial registrado'),
    }));
    const explained: AnomalyListRow[] = data.explained_events.map((movement) => ({
      id: `explained-${movement.date}`,
      status: 'explained',
      date: movement.date,
      direction: movement.direction,
      deviationPercent: movement.deviation_percent,
      observedSales: movement.observed_sales,
      expectedSales: movement.expected_sales,
      impact: movement.impact,
      confidence: movement.confidence,
      explanation: movement.explanation,
      contributors: movement.contributors,
      context: movement.events.length
        ? movement.events.map((event) => event.name).join(', ')
        : movement.holiday_name || 'Calendario comercial',
    }));
    return [...pending, ...explained];
  }, [data]);

  const visibleAnomalyRows = useMemo(() => {
    const normalizedSearch = anomalySearch.trim().toLocaleLowerCase('es');
    return anomalyRows
      .filter((row) => row.status === anomalyView)
      .filter((row) => anomalyDirection === 'ALL' || row.direction === anomalyDirection)
      .filter((row) => {
        if (!normalizedSearch) return true;
        const contributorNames = row.contributors
          .map((contributor) => contributor.local_name)
          .join(' ');
        return [
          row.date,
          row.context,
          row.explanation,
          contributorNames,
        ].join(' ').toLocaleLowerCase('es').includes(normalizedSearch);
      })
      .sort((left, right) => {
        if (anomalySort === 'date') return right.date.localeCompare(left.date);
        if (anomalySort === 'confidence') return right.confidence - left.confidence;
        if (anomalySort === 'deviation') {
          return Math.abs(right.deviationPercent) - Math.abs(left.deviationPercent);
        }
        return Math.abs(right.impact) - Math.abs(left.impact);
      });
  }, [anomalyDirection, anomalyRows, anomalySearch, anomalySort, anomalyView]);

  const selectedAnomaly = useMemo(
    () => anomalyRows.find((row) => row.id === selectedAnomalyId) || null,
    [anomalyRows, selectedAnomalyId],
  );

  useEffect(() => {
    setSelectedAnomalyId(null);
  }, [anomalyView, currentMall?.id]);

  useEffect(() => {
    if (!selectedAnomalyId) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setSelectedAnomalyId(null);
    };
    window.addEventListener('keydown', closeOnEscape);
    return () => window.removeEventListener('keydown', closeOnEscape);
  }, [selectedAnomalyId]);

  const shiftMonth = (direction: number) => {
    const index = availableMonths.indexOf(selectedMonth);
    const next = availableMonths[index + direction];
    if (next) setSelectedMonth(next);
  };

  const applyQuickRange = (days: number) => {
    const end = new Date();
    const start = new Date(end);
    start.setDate(start.getDate() - (days - 1));
    setDates({ start: toIsoDate(start), end: toIsoDate(end) });
  };

  const saveCalendarEvent = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!currentMall?.id || !session?.access_token) return;
    setEventSaving(true);
    setEventError(null);
    try {
      await ApiService.createBigDataCalendarEvent(
        currentMall.id,
        eventForm,
        session.access_token,
      );
      setShowEventForm(false);
      setEventForm({
        name: '',
        event_type: 'MALL_ACTIVITY',
        start_date: toIsoDate(new Date()),
        end_date: toIsoDate(new Date()),
        expected_impact: 'UP',
        notes: '',
      });
      setReloadKey((value) => value + 1);
    } catch (saveError: any) {
      setEventError(saveError?.message || 'No se pudo guardar el evento.');
    } finally {
      setEventSaving(false);
    }
  };

  const removeCalendarEvent = async (eventId: string, eventName: string) => {
    if (
      !currentMall?.id
      || !session?.access_token
      || !window.confirm(`¿Eliminar "${eventName}" del calendario comercial?`)
    ) return;
    try {
      await ApiService.deleteBigDataCalendarEvent(
        currentMall.id,
        eventId,
        session.access_token,
      );
      setReloadKey((value) => value + 1);
    } catch (deleteError: any) {
      setError(deleteError?.message || 'No se pudo eliminar el evento.');
    }
  };

  if (!currentMall?.id) {
    return (
      <div className="rounded-2xl border border-slate-200 bg-white p-6">
        Selecciona un mall para consultar Inteligencia Comercial.
      </div>
    );
  }

  const apiUnavailable = Boolean(error && /not found|http 404/i.test(error));
  const quality = data?.quality;
  const qualityState = quality ? qualityCopy[quality.status] : qualityCopy.LOW_CONFIDENCE;
  const statusLabel = data?.general_status === 'DATA_INCOMPLETE'
    ? 'Información incompleta'
    : data?.general_status === 'ATTENTION_REQUIRED'
    ? 'Requiere atención'
    : 'Comportamiento estable';

  return (
    <div className="space-y-4 animate-in fade-in duration-500">
      <header className="overflow-hidden rounded-2xl border border-slate-200 bg-slate-950 text-white shadow-lg shadow-slate-200/60">
        <div className="relative px-5 py-4 lg:px-6">
          <div className="absolute -right-20 -top-28 h-72 w-72 rounded-full bg-indigo-500/20 blur-3xl" />
          <div className="absolute bottom-0 left-1/3 h-28 w-64 rounded-full bg-cyan-400/10 blur-3xl" />
          <div className="relative flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
            <div className="max-w-3xl">
              <div className="flex flex-wrap items-center gap-2">
                <span className="rounded-full border border-indigo-300/30 bg-indigo-400/15 px-3 py-1 text-[10px] font-black uppercase tracking-[0.2em] text-indigo-200">
                  Big Data · Fase 1
                </span>
                {data && (
                  <span className="rounded-full border border-white/10 bg-white/10 px-3 py-1 text-xs font-semibold text-slate-200">
                    {statusLabel}
                  </span>
                )}
              </div>
              <h2 className="mt-2 text-xl font-black tracking-tight lg:text-2xl">
                Inteligencia Comercial
              </h2>
              <p className="mt-1 max-w-2xl text-xs leading-5 text-slate-300">
                Descubre cuándo se repiten los patrones, qué fechas se salen de lo esperado,
                cuáles locales explican el movimiento y si los datos son confiables para actuar.
              </p>
            </div>
            <div className="rounded-xl border border-white/10 bg-white/5 p-2.5 backdrop-blur">
              <div className="flex flex-wrap items-center gap-2">
                {[30, 90, 180].map((days) => (
                  <button
                    key={days}
                    type="button"
                    onClick={() => applyQuickRange(days)}
                    className="rounded-lg border border-white/10 px-2.5 py-1.5 text-xs font-bold text-slate-300 hover:bg-white/10 hover:text-white"
                  >
                    {days} días
                  </button>
                ))}
                <input
                  className="rounded-lg border border-white/10 bg-slate-900 px-2.5 py-1.5 text-xs text-white"
                  type="date"
                  value={dates.start}
                  max={dates.end}
                  onChange={(event) => setDates({ ...dates, start: event.target.value })}
                />
                <span className="text-slate-500">→</span>
                <input
                  className="rounded-lg border border-white/10 bg-slate-900 px-2.5 py-1.5 text-xs text-white"
                  type="date"
                  value={dates.end}
                  min={dates.start}
                  onChange={(event) => setDates({ ...dates, end: event.target.value })}
                />
              </div>
            </div>
          </div>
        </div>
      </header>

      <nav
        role="tablist"
        aria-label="Secciones de Inteligencia Comercial"
        className="overflow-x-auto rounded-2xl border border-slate-200 bg-white p-1.5 shadow-sm"
      >
        <div className="flex min-w-max gap-1">
          {INTELLIGENCE_TABS.map((tab) => {
            const Icon = tab.icon;
            const selected = activeTab === tab.id;
            const badge = tab.id === 'anomalies'
              ? data?.anomalies.length
              : tab.id === 'calendar'
              ? data?.calendar_context.registered_events.length
              : tab.id === 'quality'
              ? data?.quality.missing_days
              : undefined;
            return (
              <button
                key={tab.id}
                type="button"
                role="tab"
                aria-selected={selected}
                onClick={() => setActiveTab(tab.id)}
                className={`flex min-w-40 items-center gap-2.5 rounded-xl px-3 py-2 text-left transition-colors ${
                  selected
                    ? 'bg-indigo-600 text-white shadow-sm'
                    : 'text-slate-500 hover:bg-slate-50 hover:text-slate-800'
                }`}
              >
                <Icon size={17} className="shrink-0" />
                <span>
                  <span className="flex items-center gap-2 text-xs font-black">
                    {tab.label}
                    {badge != null && badge > 0 && (
                      <span className={`rounded-full px-1.5 py-0.5 text-[9px] ${
                        selected ? 'bg-white/20 text-white' : 'bg-slate-100 text-slate-500'
                      }`}>
                        {badge}
                      </span>
                    )}
                  </span>
                  <span className={`mt-0.5 block text-[9px] ${
                    selected ? 'text-indigo-100' : 'text-slate-400'
                  }`}>
                    {tab.description}
                  </span>
                </span>
              </button>
            );
          })}
        </div>
      </nav>

      {error && (
        <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
          {error}. {apiUnavailable
            ? 'La API de Inteligencia Comercial todavía no está desplegada en Railway.'
            : <>Verifica la licencia <code>BIG_DATA_CORE</code> y la cobertura del mall.</>}
        </div>
      )}

      {loading && (
        <div className="grid min-h-[420px] place-items-center rounded-3xl border border-slate-100 bg-white">
          <div className="text-center">
            <div className="mx-auto h-10 w-10 animate-spin rounded-full border-2 border-indigo-100 border-b-indigo-600" />
            <p className="mt-3 text-sm font-medium text-slate-500">
              Analizando patrones, contexto y cobertura…
            </p>
          </div>
        </div>
      )}

      {data && quality && (
        <>
          {activeTab === 'summary' && (
          <section
            role="tabpanel"
            className="grid gap-3 xl:grid-cols-[1.6fr_0.8fr]"
          >
            <div className="rounded-2xl border border-indigo-100 bg-gradient-to-br from-white via-white to-indigo-50/70 p-4 shadow-sm">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="flex items-center gap-2 text-xs font-black uppercase tracking-[0.16em] text-indigo-600">
                    <Sparkles size={15} /> Lectura ejecutiva
                  </p>
                  <h3 className="mt-1 text-lg font-black text-slate-900">
                    Lo que merece atención en este período
                  </h3>
                </div>
                <span className={`rounded-full border px-3 py-1 text-xs font-bold ${qualityState.classes}`}>
                  Confianza {quality.confidence.toLowerCase()}
                </span>
              </div>
              <div className="mt-4 grid gap-3 md:grid-cols-2">
                {data.insights.slice(0, 4).map((insight) => (
                  <article
                    key={insight.type}
                    className={`rounded-xl border p-3 ${toneClasses[insight.tone] || toneClasses.neutral}`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="text-sm font-black">{insight.title}</p>
                        <p className="mt-1 text-xs leading-5 opacity-80">{insight.statement}</p>
                      </div>
                      <Lightbulb size={18} className="shrink-0 opacity-70" />
                    </div>
                  </article>
                ))}
                {!data.insights.length && (
                  <div className="rounded-2xl border border-emerald-100 bg-emerald-50 p-4 text-sm text-emerald-800 md:col-span-2">
                    No se detectaron patrones suficientemente sólidos para emitir conclusiones.
                  </div>
                )}
              </div>
            </div>

            <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs font-black uppercase tracking-[0.14em] text-slate-400">
                    Confiabilidad
                  </p>
                  <p className="mt-1 text-sm font-bold text-slate-700">{qualityState.label}</p>
                </div>
                <div
                  className="grid h-16 w-16 place-items-center rounded-full"
                  style={{
                    background: `conic-gradient(${qualityState.color} ${quality.score * 3.6}deg, #e2e8f0 0deg)`,
                  }}
                >
                  <div className="grid h-11 w-11 place-items-center rounded-full bg-white">
                    <span className="text-lg font-black text-slate-900">{quality.score}</span>
                  </div>
                </div>
              </div>
              <div className="mt-3 grid grid-cols-2 gap-2">
                <div className="rounded-lg bg-slate-50 p-2.5">
                  <p className="text-[10px] font-bold uppercase text-slate-400">Días cubiertos</p>
                  <p className="mt-1 text-lg font-black text-slate-800">
                    {quality.day_coverage_percent.toFixed(1)}%
                  </p>
                </div>
                <div className="rounded-lg bg-slate-50 p-2.5">
                  <p className="text-[10px] font-bold uppercase text-slate-400">Locales reportando</p>
                  <p className="mt-1 text-lg font-black text-slate-800">
                    {quality.reporting_local_count}/{quality.active_local_count}
                  </p>
                </div>
              </div>
              <p className="mt-3 text-xs leading-5 text-slate-500">
                {quality.blockers[0] || 'La información disponible permite interpretar los patrones con confianza.'}
              </p>
            </div>
          </section>
          )}

          {activeTab === 'calendar' && (
          <section role="tabpanel">
            <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <p className="flex items-center gap-2 text-xs font-black uppercase tracking-[0.14em] text-indigo-600">
                    <CalendarDays size={16} /> Calendario de comportamiento
                  </p>
                  <h3 className="mt-1 text-lg font-black text-slate-900">
                    Picos, caídas, fines de semana y feriados
                  </h3>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  {(isAdmin || isTic) && (
                    <button
                      type="button"
                      onClick={() => {
                        setEventError(null);
                        setShowEventForm(true);
                      }}
                      className="mr-1 inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-3 py-2 text-xs font-black text-white shadow-sm hover:bg-indigo-700"
                    >
                      <CalendarPlus size={15} /> Registrar contexto
                    </button>
                  )}
                  <button
                    type="button"
                    disabled={availableMonths.indexOf(selectedMonth) <= 0}
                    onClick={() => shiftMonth(-1)}
                    className="rounded-lg border border-slate-200 p-2 text-slate-500 disabled:opacity-30"
                    aria-label="Mes anterior"
                  >
                    <ChevronLeft size={16} />
                  </button>
                  <span className="min-w-36 text-center text-sm font-black capitalize text-slate-700">
                    {selectedMonth
                      ? formatDate(`${selectedMonth}-01`, { month: 'long', year: 'numeric' })
                      : 'Sin período'}
                  </span>
                  <button
                    type="button"
                    disabled={availableMonths.indexOf(selectedMonth) >= availableMonths.length - 1}
                    onClick={() => shiftMonth(1)}
                    className="rounded-lg border border-slate-200 p-2 text-slate-500 disabled:opacity-30"
                    aria-label="Mes siguiente"
                  >
                    <ChevronRight size={16} />
                  </button>
                </div>
              </div>
              <div className="mt-4 grid grid-cols-7 gap-1.5">
                {WEEKDAY_HEADERS.map((label) => (
                  <div key={label} className="pb-1 text-center text-[10px] font-black uppercase text-slate-400">
                    {label}
                  </div>
                ))}
                {Array.from({ length: calendarLeadingSpaces }).map((_, index) => (
                  <div key={`empty-${index}`} />
                ))}
                {visibleCalendar.map((day) => (
                  <div
                    key={day.date}
                    className={`min-h-[72px] rounded-lg border p-2 transition-colors ${calendarCellClasses(day)}`}
                    title={[
                      formatDate(day.date, { weekday: 'long', day: 'numeric', month: 'long' }),
                      day.sales_net == null ? 'Sin datos' : `Venta: ${format(day.sales_net)}`,
                      day.expected_sales == null ? '' : `Referencia: ${format(day.expected_sales)}`,
                      day.deviation_percent == null ? '' : `Desviación: ${day.deviation_percent.toFixed(1)}%`,
                      day.holiday_name || '',
                      ...day.events.map((event) => `${event.event_type_label}: ${event.name}`),
                    ].filter(Boolean).join(' · ')}
                  >
                    <div className="flex items-start justify-between gap-1">
                      <span className="text-xs font-black">{Number(day.date.slice(-2))}</span>
                      {(day.status === 'ANOMALY' || day.status === 'EXPLAINED_EVENT') && (
                        <span className="h-2 w-2 rounded-full bg-current opacity-60" />
                      )}
                    </div>
                    <p className="mt-1.5 truncate text-[11px] font-black">
                      {day.sales_net == null ? 'Sin datos' : compactNumber.format(day.sales_net)}
                    </p>
                    {day.deviation_percent != null && (
                      <p className="mt-0.5 text-[9px] font-bold opacity-70">
                        {day.deviation_percent > 0 ? '+' : ''}{day.deviation_percent.toFixed(0)}%
                      </p>
                    )}
                    {day.holiday_name && (
                      <p className="mt-1 line-clamp-2 text-[8px] font-bold leading-3 text-violet-700">
                        {day.holiday_name}
                      </p>
                    )}
                    {day.events[0] && (
                      <p className="mt-1 line-clamp-2 text-[8px] font-black leading-3 text-sky-700">
                        {day.events[0].name}
                      </p>
                    )}
                  </div>
                ))}
              </div>
              <div className="mt-4 flex flex-wrap gap-3 text-[10px] font-semibold text-slate-500">
                <span className="flex items-center gap-1.5"><i className="h-2.5 w-2.5 rounded bg-emerald-200" /> Pico</span>
                <span className="flex items-center gap-1.5"><i className="h-2.5 w-2.5 rounded bg-rose-200" /> Caída</span>
                <span className="flex items-center gap-1.5"><i className="h-2.5 w-2.5 rounded bg-sky-200" /> Evento conocido</span>
                <span className="flex items-center gap-1.5"><i className="h-2.5 w-2.5 rounded bg-violet-200" /> Feriado RD</span>
                <span className="flex items-center gap-1.5"><i className="h-2.5 w-2.5 rounded bg-amber-100" /> Fin de semana</span>
                <span className="flex items-center gap-1.5"><i className="h-2.5 w-2.5 rounded border border-dashed bg-slate-50" /> Sin datos</span>
              </div>
              {data.calendar_context.registered_events.length > 0 && (
                <div className="mt-3 border-t border-slate-100 pt-3">
                  <p className="text-[10px] font-black uppercase tracking-wide text-slate-400">
                    Actividades registradas
                  </p>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {data.calendar_context.registered_events.map((event) => (
                      <span
                        key={event.id}
                        className="inline-flex items-center gap-2 rounded-full bg-sky-50 px-2.5 py-1 text-[10px] font-bold text-sky-800"
                      >
                        {event.event_type_label}: {event.name}
                        {(isAdmin || isTic) && (
                          <button
                            type="button"
                            onClick={() => removeCalendarEvent(event.id, event.name)}
                            className="text-sky-300 hover:text-rose-600"
                            aria-label={`Eliminar ${event.name}`}
                          >
                            <Trash2 size={11} />
                          </button>
                        )}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </section>
          )}

          {activeTab === 'summary' && (
          <section role="tabpanel">
            <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
              <div>
                <p className="text-xs font-black uppercase tracking-[0.14em] text-indigo-600">
                  Patrón semanal
                </p>
                <h3 className="mt-1 text-lg font-black text-slate-900">
                  ¿El fin de semana realmente cambia la venta?
                </h3>
              </div>
              <div className="mt-3 h-56">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={data.weekday_pattern} margin={{ top: 8, right: 4, left: -22, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
                    <XAxis dataKey="label" tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
                    <YAxis tick={{ fontSize: 9 }} axisLine={false} tickLine={false} tickFormatter={(value) => compactNumber.format(Number(value))} />
                    <Tooltip
                      cursor={{ fill: '#f8fafc' }}
                      formatter={(value: number) => [format(Number(value)), 'Venta promedio']}
                    />
                    <Bar dataKey="average_sales" radius={[8, 8, 2, 2]}>
                      {data.weekday_pattern.map((row) => (
                        <Cell key={row.weekday} fill={row.is_weekend ? '#f59e0b' : '#6366f1'} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <div className="rounded-xl bg-slate-950 p-3.5 text-white">
                <p className="text-[10px] font-black uppercase tracking-[0.14em] text-slate-400">
                  Efecto fin de semana
                </p>
                {data.seasonality.weekend_lift_percent == null ? (
                  <p className="mt-2 text-sm text-slate-300">No hay suficientes fechas comparables.</p>
                ) : (
                  <div className="mt-2 flex items-end justify-between gap-3">
                    <p className="text-3xl font-black">
                      {data.seasonality.weekend_lift_percent > 0 ? '+' : ''}
                      {data.seasonality.weekend_lift_percent.toFixed(1)}%
                    </p>
                    <p className="max-w-40 text-right text-xs leading-5 text-slate-400">
                      frente al promedio de lunes a viernes
                    </p>
                  </div>
                )}
              </div>
            </div>
          </section>
          )}

          {activeTab === 'anomalies' && (
            <div className="flex w-fit rounded-xl border border-slate-200 bg-white p-1" role="tablist" aria-label="Tipos de anomalías">
              <button
                type="button"
                role="tab"
                aria-selected={anomalyView === 'pending'}
                onClick={() => setAnomalyView('pending')}
                className={`rounded-lg px-3 py-1.5 text-xs font-black ${
                  anomalyView === 'pending' ? 'bg-slate-900 text-white' : 'text-slate-500'
                }`}
              >
                Por investigar · {data.anomalies.length}
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={anomalyView === 'explained'}
                onClick={() => setAnomalyView('explained')}
                className={`rounded-lg px-3 py-1.5 text-xs font-black ${
                  anomalyView === 'explained' ? 'bg-sky-600 text-white' : 'text-slate-500'
                }`}
              >
                Explicadas · {data.explained_events.length}
              </button>
            </div>
          )}

          {activeTab === 'anomalies' && (
            <section role="tabpanel" className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
              <div className="flex flex-col gap-3 border-b border-slate-100 p-4 xl:flex-row xl:items-end xl:justify-between">
                <div>
                  <p className="flex items-center gap-2 text-xs font-black uppercase tracking-[0.14em] text-indigo-600">
                    <AlertTriangle size={16} />
                    {anomalyView === 'pending' ? 'Anomalías por investigar' : 'Movimientos explicados'}
                  </p>
                  <h3 className="mt-1 text-lg font-black text-slate-900">
                    Compara el impacto y abre la ficha para profundizar
                  </h3>
                </div>
                <div className="flex flex-col gap-2 sm:flex-row">
                  <label className="relative">
                    <Search size={14} className="pointer-events-none absolute left-3 top-2.5 text-slate-400" />
                    <input
                      value={anomalySearch}
                      onChange={(event) => setAnomalySearch(event.target.value)}
                      placeholder="Buscar fecha, local o contexto"
                      className="w-full rounded-lg border border-slate-200 py-2 pl-9 pr-3 text-xs outline-none focus:border-indigo-400 sm:w-56"
                    />
                  </label>
                  <select
                    value={anomalyDirection}
                    onChange={(event) => setAnomalyDirection(event.target.value as AnomalyDirection)}
                    className="rounded-lg border border-slate-200 px-3 py-2 text-xs font-bold text-slate-600 outline-none focus:border-indigo-400"
                    aria-label="Filtrar dirección"
                  >
                    <option value="ALL">Todas las direcciones</option>
                    <option value="UP">Picos</option>
                    <option value="DOWN">Caídas</option>
                  </select>
                  <select
                    value={anomalySort}
                    onChange={(event) => setAnomalySort(event.target.value as AnomalySort)}
                    className="rounded-lg border border-slate-200 px-3 py-2 text-xs font-bold text-slate-600 outline-none focus:border-indigo-400"
                    aria-label="Ordenar anomalías"
                  >
                    <option value="impact">Mayor impacto</option>
                    <option value="deviation">Mayor desviación</option>
                    <option value="date">Fecha más reciente</option>
                    <option value="confidence">Mayor confianza</option>
                  </select>
                </div>
              </div>

              {visibleAnomalyRows.length > 0 ? (
                <>
                  <div className="hidden overflow-x-auto md:block">
                    <table className="min-w-[1050px] w-full border-collapse text-left">
                      <thead className="bg-slate-50 text-[9px] font-black uppercase tracking-wide text-slate-400">
                        <tr>
                          {['Fecha', 'Estado', 'Dirección', 'Desviación', 'Observado', 'Esperado', 'Impacto', 'Confianza', 'Contribuyente', ''].map((label) => (
                            <th key={label || 'action'} className="whitespace-nowrap px-3 py-2.5">{label}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100">
                        {visibleAnomalyRows.map((row) => {
                          const contributor = row.contributors[0];
                          return (
                            <tr key={row.id} className="text-xs text-slate-600 hover:bg-indigo-50/30">
                              <td className="whitespace-nowrap px-3 py-3 font-black capitalize text-slate-800">
                                {formatDate(row.date, { day: '2-digit', month: 'short', year: 'numeric' })}
                              </td>
                              <td className="px-3 py-3">
                                <span className={`rounded-full px-2 py-1 text-[9px] font-black uppercase ${
                                  row.status === 'pending'
                                    ? 'bg-amber-50 text-amber-700'
                                    : 'bg-sky-50 text-sky-700'
                                }`}>
                                  {row.status === 'pending' ? 'Pendiente' : 'Explicada'}
                                </span>
                              </td>
                              <td className="px-3 py-3">
                                <span className={`inline-flex items-center gap-1 font-black ${
                                  row.direction === 'UP' ? 'text-emerald-600' : 'text-rose-600'
                                }`}>
                                  {row.direction === 'UP' ? <TrendingUp size={14} /> : <TrendingDown size={14} />}
                                  {row.direction === 'UP' ? 'Pico' : 'Caída'}
                                </span>
                              </td>
                              <td className={`px-3 py-3 font-black ${
                                row.direction === 'UP' ? 'text-emerald-600' : 'text-rose-600'
                              }`}>
                                {row.deviationPercent > 0 ? '+' : ''}{row.deviationPercent.toFixed(1)}%
                              </td>
                              <td className="whitespace-nowrap px-3 py-3 font-bold text-slate-800">{format(row.observedSales)}</td>
                              <td className="whitespace-nowrap px-3 py-3">{format(row.expectedSales)}</td>
                              <td className={`whitespace-nowrap px-3 py-3 font-black ${
                                row.impact >= 0 ? 'text-emerald-600' : 'text-rose-600'
                              }`}>
                                {row.impact > 0 ? '+' : ''}{format(row.impact)}
                              </td>
                              <td className="px-3 py-3 font-bold">{(row.confidence * 100).toFixed(0)}%</td>
                              <td className="max-w-40 truncate px-3 py-3 font-bold text-slate-700">
                                {contributor?.local_name || 'Sin atribución'}
                              </td>
                              <td className="px-3 py-3 text-right">
                                <button
                                  type="button"
                                  onClick={() => setSelectedAnomalyId(row.id)}
                                  className="inline-flex items-center gap-1 rounded-lg border border-indigo-100 px-2.5 py-1.5 text-[10px] font-black text-indigo-600 hover:bg-indigo-50"
                                >
                                  <Eye size={13} /> Ver ficha
                                </button>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>

                  <div className="divide-y divide-slate-100 md:hidden">
                    {visibleAnomalyRows.map((row) => (
                      <button
                        key={row.id}
                        type="button"
                        onClick={() => setSelectedAnomalyId(row.id)}
                        className="flex w-full items-center justify-between gap-3 p-4 text-left"
                      >
                        <span>
                          <span className="block text-xs font-black capitalize text-slate-800">
                            {formatDate(row.date, { day: '2-digit', month: 'short', year: 'numeric' })}
                          </span>
                          <span className="mt-1 block max-w-52 truncate text-[10px] text-slate-500">
                            {row.contributors[0]?.local_name || row.context}
                          </span>
                        </span>
                        <span className="text-right">
                          <span className={`block text-sm font-black ${
                            row.direction === 'UP' ? 'text-emerald-600' : 'text-rose-600'
                          }`}>
                            {row.deviationPercent > 0 ? '+' : ''}{row.deviationPercent.toFixed(1)}%
                          </span>
                          <span className="mt-1 block text-[9px] font-bold text-indigo-600">Ver ficha</span>
                        </span>
                      </button>
                    ))}
                  </div>
                </>
              ) : (
                <div className="flex items-center gap-3 p-6 text-sm text-slate-500">
                  <CheckCircle2 size={20} className="text-emerald-500" />
                  No hay movimientos que coincidan con los filtros seleccionados.
                </div>
              )}
            </section>
          )}

          {activeTab === 'quality' && (
          <section role="tabpanel" className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
              <div>
                <p className="flex items-center gap-2 text-xs font-black uppercase tracking-[0.14em] text-indigo-600">
                  <ShieldCheck size={16} /> Calidad y trazabilidad
                </p>
                <h3 className="mt-1 text-lg font-black text-slate-900">
                  Antes de interpretar, validamos si la información alcanza
                </h3>
              </div>
              <div className="flex items-center gap-2 text-xs text-slate-400">
                <Database size={14} />
                Último dato: {quality.last_processed_sale_date || 'sin confirmar'}
              </div>
            </div>
            <div className="mt-4 grid gap-2.5 sm:grid-cols-2 xl:grid-cols-5">
              {[
                ['Cobertura de días', `${quality.day_coverage_percent.toFixed(1)}%`],
                ['Cobertura local-día', `${quality.store_day_coverage_percent.toFixed(1)}%`],
                ['Días faltantes', quality.missing_days.toLocaleString()],
                ['Importaciones fallidas', quality.failed_imports.toLocaleString()],
                ['Importaciones parciales', quality.partial_imports.toLocaleString()],
              ].map(([label, value]) => (
                <div key={label} className="rounded-xl border border-slate-100 bg-slate-50/70 p-3">
                  <p className="text-[10px] font-black uppercase tracking-wide text-slate-400">{label}</p>
                  <p className="mt-2 text-xl font-black text-slate-900">{value}</p>
                </div>
              ))}
            </div>
            {quality.missing_dates.length > 0 && (
              <div className="mt-4 rounded-2xl border border-amber-100 bg-amber-50/70 p-4">
                <p className="text-xs font-black text-amber-900">Fechas sin agregados</p>
                <div className="mt-2 flex flex-wrap gap-2">
                  {quality.missing_dates.slice(0, 14).map((missingDate) => (
                    <span key={missingDate} className="rounded-full bg-white px-2.5 py-1 text-[10px] font-bold text-amber-800">
                      {formatDate(missingDate, { day: '2-digit', month: 'short' })}
                    </span>
                  ))}
                  {quality.missing_days > 14 && (
                    <span className="rounded-full bg-amber-100 px-2.5 py-1 text-[10px] font-bold text-amber-800">
                      +{quality.missing_days - 14} más
                    </span>
                  )}
                </div>
              </div>
            )}
          </section>
          )}

          {activeTab === 'quality' && (
          <footer className="flex flex-col gap-2 rounded-xl border border-slate-100 bg-slate-50 px-3 py-2.5 text-[10px] leading-5 text-slate-500 lg:flex-row lg:items-center lg:justify-between">
            <span>{data.methodology}</span>
            <span className="shrink-0">Versión {data.version}</span>
          </footer>
          )}
        </>
      )}

      {selectedAnomaly && (
        <div className="fixed inset-0 z-50">
          <button
            type="button"
            aria-label="Cerrar ficha de anomalía"
            onClick={() => setSelectedAnomalyId(null)}
            className="absolute inset-0 bg-slate-950/45 backdrop-blur-sm"
          />
          <aside
            role="dialog"
            aria-modal="true"
            aria-label="Ficha de anomalía"
            className="absolute inset-y-0 right-0 w-full max-w-xl overflow-y-auto bg-white shadow-2xl"
          >
            <div className="sticky top-0 z-10 border-b border-slate-100 bg-white/95 px-5 py-4 backdrop-blur">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <span className={`rounded-full px-2 py-1 text-[9px] font-black uppercase ${
                    selectedAnomaly.status === 'pending'
                      ? 'bg-amber-50 text-amber-700'
                      : 'bg-sky-50 text-sky-700'
                  }`}>
                    {selectedAnomaly.status === 'pending' ? 'Por investigar' : 'Movimiento explicado'}
                  </span>
                  <h3 className="mt-2 text-xl font-black capitalize text-slate-900">
                    {formatDate(selectedAnomaly.date, {
                      weekday: 'long',
                      day: 'numeric',
                      month: 'long',
                      year: 'numeric',
                    })}
                  </h3>
                  <p className="mt-1 text-xs text-slate-500">
                    Ficha analítica del movimiento comercial
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setSelectedAnomalyId(null)}
                  className="rounded-xl border border-slate-200 p-2 text-slate-400 hover:text-slate-700"
                  aria-label="Cerrar"
                >
                  <X size={18} />
                </button>
              </div>
            </div>

            <div className="space-y-5 p-5">
              <section className="rounded-2xl bg-slate-950 p-4 text-white">
                <div className="flex items-center justify-between gap-4">
                  <div className="flex items-center gap-2">
                    {selectedAnomaly.direction === 'UP'
                      ? <TrendingUp size={20} className="text-emerald-400" />
                      : <TrendingDown size={20} className="text-rose-400" />}
                    <span className="text-sm font-black">
                      {selectedAnomaly.direction === 'UP' ? 'Pico de venta' : 'Caída de venta'}
                    </span>
                  </div>
                  <span className={selectedAnomaly.direction === 'UP'
                    ? 'text-2xl font-black text-emerald-400'
                    : 'text-2xl font-black text-rose-400'}
                  >
                    {selectedAnomaly.deviationPercent > 0 ? '+' : ''}
                    {selectedAnomaly.deviationPercent.toFixed(1)}%
                  </span>
                </div>
                <div className="mt-4 grid grid-cols-3 gap-2">
                  {[
                    ['Observado', format(selectedAnomaly.observedSales)],
                    ['Esperado', format(selectedAnomaly.expectedSales)],
                    ['Impacto', `${selectedAnomaly.impact > 0 ? '+' : ''}${format(selectedAnomaly.impact)}`],
                  ].map(([label, value]) => (
                    <div key={label} className="rounded-xl bg-white/10 p-3">
                      <p className="text-[9px] font-bold uppercase text-slate-400">{label}</p>
                      <p className="mt-1 truncate text-sm font-black">{value}</p>
                    </div>
                  ))}
                </div>
              </section>

              <section>
                <p className="text-[10px] font-black uppercase tracking-[0.14em] text-slate-400">
                  Interpretación
                </p>
                <p className="mt-2 text-sm leading-6 text-slate-700">
                  {selectedAnomaly.explanation}
                </p>
              </section>

              <section className="rounded-xl border border-sky-100 bg-sky-50/70 p-4">
                <p className="text-[10px] font-black uppercase tracking-wide text-sky-600">
                  Contexto de la fecha
                </p>
                <p className="mt-1 text-sm font-bold text-sky-900">{selectedAnomaly.context}</p>
              </section>

              <section>
                <div className="flex items-center justify-between">
                  <p className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.14em] text-slate-400">
                    <Store size={13} /> Locales contribuyentes
                  </p>
                  <span className="text-[10px] font-bold text-slate-400">
                    Confianza {(selectedAnomaly.confidence * 100).toFixed(0)}%
                  </span>
                </div>
                <div className="mt-2 overflow-hidden rounded-xl border border-slate-200">
                  {selectedAnomaly.contributors.length > 0 ? (
                    selectedAnomaly.contributors.map((contributor) => (
                      <div
                        key={contributor.local_id}
                        className="grid grid-cols-[1fr_auto] gap-3 border-b border-slate-100 px-3 py-2.5 last:border-0"
                      >
                        <div className="min-w-0">
                          <p className="truncate text-xs font-black text-slate-800">
                            {contributor.local_name}
                          </p>
                          <p className="mt-0.5 text-[10px] text-slate-400">
                            {contributor.impact_share_percent.toFixed(1)}% del impacto · {contributor.peer_days} días comparables
                          </p>
                        </div>
                        <p className={contributor.contribution >= 0
                          ? 'text-xs font-black text-emerald-600'
                          : 'text-xs font-black text-rose-600'}
                        >
                          {contributor.contribution > 0 ? '+' : ''}
                          {format(contributor.contribution)}
                        </p>
                      </div>
                    ))
                  ) : (
                    <p className="p-4 text-xs text-slate-500">
                      No hay suficiente historial por local para atribuir la causa.
                    </p>
                  )}
                </div>
              </section>

              {selectedAnomaly.recommendation && (
                <section className="rounded-xl border border-indigo-100 bg-indigo-50/70 p-4">
                  <p className="text-[10px] font-black uppercase tracking-wide text-indigo-600">
                    Recomendación
                  </p>
                  <p className="mt-1 text-sm leading-6 text-indigo-900">
                    {selectedAnomaly.recommendation}
                  </p>
                </section>
              )}

              <section className="rounded-xl border border-slate-100 bg-slate-50 p-3">
                <div className="flex items-center justify-between text-[10px] font-bold text-slate-500">
                  <span>Confianza analítica</span>
                  <span>{(selectedAnomaly.confidence * 100).toFixed(0)}%</span>
                </div>
                <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-200">
                  <div
                    className="h-full rounded-full bg-indigo-500"
                    style={{ width: `${Math.min(selectedAnomaly.confidence * 100, 100)}%` }}
                  />
                </div>
              </section>
            </div>
          </aside>
        </div>
      )}

      {showEventForm && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-slate-950/55 p-4 backdrop-blur-sm">
          <form
            onSubmit={saveCalendarEvent}
            className="w-full max-w-xl rounded-3xl border border-slate-200 bg-white p-6 shadow-2xl"
          >
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-xs font-black uppercase tracking-[0.14em] text-indigo-600">
                  Calendario comercial
                </p>
                <h3 className="mt-1 text-xl font-black text-slate-900">
                  Registrar contexto del mall
                </h3>
                <p className="mt-1 text-xs leading-5 text-slate-500">
                  Evita interpretar una promoción o actividad planificada como una anomalía.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setShowEventForm(false)}
                className="rounded-xl border border-slate-200 p-2 text-slate-400 hover:text-slate-700"
                aria-label="Cerrar"
              >
                <X size={18} />
              </button>
            </div>

            <div className="mt-5 grid gap-4 sm:grid-cols-2">
              <label className="sm:col-span-2">
                <span className="text-xs font-bold text-slate-600">Nombre del evento</span>
                <input
                  required
                  minLength={2}
                  maxLength={160}
                  value={eventForm.name}
                  onChange={(event) => setEventForm({ ...eventForm, name: event.target.value })}
                  placeholder="Ej. Feria de verano"
                  className="mt-1.5 w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm outline-none focus:border-indigo-400"
                />
              </label>
              <label>
                <span className="text-xs font-bold text-slate-600">Tipo</span>
                <select
                  value={eventForm.event_type}
                  onChange={(event) => setEventForm({
                    ...eventForm,
                    event_type: event.target.value as BigDataCalendarEventType,
                  })}
                  className="mt-1.5 w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm outline-none focus:border-indigo-400"
                >
                  {EVENT_TYPES.map((option) => (
                    <option key={option.value} value={option.value}>{option.label}</option>
                  ))}
                </select>
              </label>
              <label>
                <span className="text-xs font-bold text-slate-600">Impacto esperado</span>
                <select
                  value={eventForm.expected_impact}
                  onChange={(event) => setEventForm({
                    ...eventForm,
                    expected_impact: event.target.value as 'UP' | 'DOWN' | 'NEUTRAL',
                  })}
                  className="mt-1.5 w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm outline-none focus:border-indigo-400"
                >
                  <option value="UP">Aumento</option>
                  <option value="DOWN">Disminución</option>
                  <option value="NEUTRAL">Sin dirección definida</option>
                </select>
              </label>
              <label>
                <span className="text-xs font-bold text-slate-600">Desde</span>
                <input
                  required
                  type="date"
                  value={eventForm.start_date}
                  max={eventForm.end_date}
                  onChange={(event) => setEventForm({
                    ...eventForm,
                    start_date: event.target.value,
                    end_date: event.target.value > eventForm.end_date
                      ? event.target.value
                      : eventForm.end_date,
                  })}
                  className="mt-1.5 w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm outline-none focus:border-indigo-400"
                />
              </label>
              <label>
                <span className="text-xs font-bold text-slate-600">Hasta</span>
                <input
                  required
                  type="date"
                  value={eventForm.end_date}
                  min={eventForm.start_date}
                  onChange={(event) => setEventForm({ ...eventForm, end_date: event.target.value })}
                  className="mt-1.5 w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm outline-none focus:border-indigo-400"
                />
              </label>
              <label className="sm:col-span-2">
                <span className="text-xs font-bold text-slate-600">Notas (opcional)</span>
                <textarea
                  rows={3}
                  maxLength={1000}
                  value={eventForm.notes}
                  onChange={(event) => setEventForm({ ...eventForm, notes: event.target.value })}
                  placeholder="Locales participantes, objetivo o detalle relevante."
                  className="mt-1.5 w-full resize-none rounded-xl border border-slate-200 px-3 py-2.5 text-sm outline-none focus:border-indigo-400"
                />
              </label>
            </div>

            {eventError && (
              <p className="mt-4 rounded-xl border border-rose-100 bg-rose-50 p-3 text-xs text-rose-700">
                {eventError}
              </p>
            )}

            <div className="mt-5 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setShowEventForm(false)}
                className="rounded-xl border border-slate-200 px-4 py-2.5 text-sm font-bold text-slate-600"
              >
                Cancelar
              </button>
              <button
                type="submit"
                disabled={eventSaving}
                className="rounded-xl bg-indigo-600 px-4 py-2.5 text-sm font-black text-white disabled:opacity-50"
              >
                {eventSaving ? 'Guardando…' : 'Guardar contexto'}
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
};
