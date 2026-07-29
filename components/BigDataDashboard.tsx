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
  Lightbulb,
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
  BigDataPhaseOne,
  BigDataPhaseOneAnomaly,
} from '../types';
import { createBigDataRequestGate } from '../utils/bigDataRequestGate';

const WEEKDAY_HEADERS = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom'];
type IntelligenceTab = 'summary' | 'calendar' | 'anomalies' | 'quality';
type AnomalyView = 'pending' | 'explained';

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

const anomalyCopy = (anomaly: BigDataPhaseOneAnomaly) => ({
  icon: anomaly.direction === 'UP' ? TrendingUp : TrendingDown,
  accent: anomaly.direction === 'UP' ? 'text-emerald-600' : 'text-rose-600',
  badge: anomaly.direction === 'UP'
    ? 'bg-emerald-50 text-emerald-700'
    : 'bg-rose-50 text-rose-700',
  label: anomaly.direction === 'UP' ? 'Pico inusual' : 'Caída inusual',
});

export const BigDataDashboard: React.FC = () => {
  const { currentMall, session, isAdmin, isTic } = useAuth();
  const { format } = useFormatCurrency();
  const [dates, setDates] = useState(initialDates);
  const [data, setData] = useState<BigDataPhaseOne | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<IntelligenceTab>('summary');
  const [anomalyView, setAnomalyView] = useState<AnomalyView>('pending');
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

          {activeTab === 'anomalies' && anomalyView === 'explained' && (
          <section role="tabpanel" className="rounded-2xl border border-sky-100 bg-gradient-to-br from-sky-50 to-white p-4 shadow-sm">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
              <div>
                <p className="flex items-center gap-2 text-xs font-black uppercase tracking-[0.14em] text-sky-700">
                  <CalendarPlus size={16} /> Contexto comercial
                </p>
                <h3 className="mt-1 text-lg font-black text-slate-900">
                  Movimientos explicados por actividades del mall
                </h3>
                <p className="mt-1 max-w-2xl text-xs leading-5 text-slate-500">
                  Promociones, ventas de pasillo y actividades puntuales se separan de las
                  anomalías que todavía requieren investigación.
                </p>
              </div>
              <span className="rounded-full border border-sky-200 bg-white px-3 py-1 text-xs font-black text-sky-700">
                {data.calendar_context.registered_events.length} evento(s) en el período
              </span>
            </div>

            {data.explained_events.length > 0 && (
              <div className="mt-4 grid gap-3 lg:grid-cols-2">
                {data.explained_events.map((movement) => (
                  <article key={movement.date} className="rounded-xl border border-sky-100 bg-white p-3.5">
                    <div className="flex items-start justify-between gap-4">
                      <div>
                        <p className="text-[10px] font-black uppercase tracking-wide text-sky-600">
                          {movement.events.length
                            ? movement.events.map((event) => event.event_type_label).join(' · ')
                            : 'Feriado RD'}
                        </p>
                        <h4 className="mt-1 font-black text-slate-900">
                          {movement.events.length
                            ? movement.events.map((event) => event.name).join(', ')
                            : movement.holiday_name}
                        </h4>
                        <p className="mt-1 text-xs capitalize text-slate-400">
                          {formatDate(movement.date, { weekday: 'long', day: 'numeric', month: 'long' })}
                        </p>
                      </div>
                      <p className={movement.deviation_percent >= 0
                        ? 'text-xl font-black text-emerald-600'
                        : 'text-xl font-black text-rose-600'}
                      >
                        {movement.deviation_percent > 0 ? '+' : ''}
                        {movement.deviation_percent.toFixed(1)}%
                      </p>
                    </div>
                    <p className="mt-3 text-xs leading-5 text-slate-600">{movement.explanation}</p>
                  </article>
                ))}
              </div>
            )}

            {data.explained_events.length === 0 && (
              <div className="mt-4 rounded-2xl border border-sky-100 bg-white p-4 text-xs leading-5 text-slate-600">
                {data.calendar_context.registered_events.length
                  ? 'Hay eventos registrados, pero ninguno coincide con una desviación material en el período.'
                  : 'Aún no hay promociones, ventas de pasillo o actividades registradas para este período.'}
              </div>
            )}

            {data.calendar_context.registered_events.length > 0 && (
              <div className="mt-4 flex flex-wrap gap-2">
                {data.calendar_context.registered_events.map((event) => (
                  <span
                    key={event.id}
                    className="inline-flex items-center gap-2 rounded-full border border-sky-100 bg-white px-3 py-1.5 text-[10px] font-bold text-slate-600"
                  >
                    {event.event_type_label}: {event.name}
                    <span className="text-slate-400">
                      {formatDate(event.start_date, { day: '2-digit', month: 'short' })}
                      {event.end_date !== event.start_date
                        ? `–${formatDate(event.end_date, { day: '2-digit', month: 'short' })}`
                        : ''}
                    </span>
                    {(isAdmin || isTic) && (
                      <button
                        type="button"
                        onClick={() => removeCalendarEvent(event.id, event.name)}
                        className="text-slate-300 hover:text-rose-600"
                        aria-label={`Eliminar ${event.name}`}
                      >
                        <Trash2 size={12} />
                      </button>
                    )}
                  </span>
                ))}
              </div>
            )}
          </section>
          )}

          {activeTab === 'anomalies' && anomalyView === 'pending' && (
          <section role="tabpanel" className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
              <div>
                <p className="flex items-center gap-2 text-xs font-black uppercase tracking-[0.14em] text-indigo-600">
                  <AlertTriangle size={16} /> Anomalías por investigar
                </p>
                <h3 className="mt-1 text-lg font-black text-slate-900">
                  Qué cambió sin una causa comercial registrada
                </h3>
              </div>
              <p className="max-w-xl text-xs leading-5 text-slate-500">
                Se compara cada fecha con la mediana de otros días equivalentes. No se concluye
                desempeño comercial cuando la confiabilidad de los datos es baja.
              </p>
            </div>
            <div className="mt-4 grid gap-3 xl:grid-cols-2">
              {data.anomalies.map((anomaly) => {
                const copy = anomalyCopy(anomaly);
                const Icon = copy.icon;
                return (
                  <article key={anomaly.date} className="rounded-xl border border-slate-200 p-3.5">
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex gap-3">
                        <div className={`rounded-xl bg-slate-50 p-2.5 ${copy.accent}`}>
                          <Icon size={20} />
                        </div>
                        <div>
                          <div className="flex flex-wrap items-center gap-2">
                            <span className={`rounded-full px-2 py-1 text-[9px] font-black uppercase ${copy.badge}`}>
                              {copy.label}
                            </span>
                            <span className="text-[10px] font-bold text-slate-400">
                              confianza {(anomaly.confidence * 100).toFixed(0)}%
                            </span>
                          </div>
                          <h4 className="mt-2 font-black text-slate-900">
                            {formatDate(anomaly.date, { weekday: 'long', day: 'numeric', month: 'long' })}
                          </h4>
                        </div>
                      </div>
                      <div className="text-right">
                        <p className={`text-xl font-black ${copy.accent}`}>
                          {anomaly.deviation_percent > 0 ? '+' : ''}{anomaly.deviation_percent.toFixed(1)}%
                        </p>
                        <p className="text-[10px] text-slate-400">vs. día comparable</p>
                      </div>
                    </div>
                    <p className="mt-3 text-xs leading-5 text-slate-600">{anomaly.explanation}</p>
                    <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
                      <div className="rounded-xl bg-slate-50 p-3">
                        <p className="text-slate-400">Observado</p>
                        <p className="mt-1 font-black text-slate-800">{format(anomaly.observed_sales)}</p>
                      </div>
                      <div className="rounded-xl bg-slate-50 p-3">
                        <p className="text-slate-400">Referencia</p>
                        <p className="mt-1 font-black text-slate-800">{format(anomaly.expected_sales)}</p>
                      </div>
                    </div>
                    <div className="mt-4 border-t border-slate-100 pt-3">
                      <p className="flex items-center gap-2 text-[10px] font-black uppercase tracking-wide text-slate-400">
                        <Store size={13} /> Principales contribuyentes
                      </p>
                      <div className="mt-2 space-y-2">
                        {anomaly.contributors.slice(0, 3).map((contributor) => (
                          <div key={contributor.local_id} className="flex items-center justify-between gap-3 text-xs">
                            <span className="truncate font-bold text-slate-700">{contributor.local_name}</span>
                            <span className={contributor.contribution >= 0 ? 'font-black text-emerald-600' : 'font-black text-rose-600'}>
                              {contributor.contribution >= 0 ? '+' : ''}{format(contributor.contribution)}
                            </span>
                          </div>
                        ))}
                        {!anomaly.contributors.length && (
                          <p className="text-xs text-slate-400">No hay suficiente historial por local para atribuir la causa.</p>
                        )}
                      </div>
                    </div>
                  </article>
                );
              })}
              {!data.anomalies.length && (
                <div className="flex items-center gap-3 rounded-2xl border border-emerald-100 bg-emerald-50 p-5 text-emerald-800 xl:col-span-2">
                  <CheckCircle2 size={22} />
                  <div>
                    <p className="font-black">Sin desviaciones materiales</p>
                    <p className="mt-1 text-xs">No hubo fechas con al menos 30% de diferencia y suficiente historial comparable.</p>
                  </div>
                </div>
              )}
            </div>
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
