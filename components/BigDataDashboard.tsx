import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import {
  AlertTriangle,
  ArrowLeft,
  Activity,
  BadgeCheck,
  BarChart3,
  CalendarPlus,
  CalendarDays,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  ClipboardList,
  Database,
  Eye,
  FileWarning,
  Info,
  Lightbulb,
  Loader2,
  Play,
  Plus,
  Save,
  Search,
  ShieldCheck,
  Sparkles,
  Store,
  Target,
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
  BigDataAnomalyCauseType,
  BigDataAnomalyContributor,
  BigDataAnomalyReview,
  BigDataAnomalyReviewStatus,
  BigDataPhaseOne,
  BigDataPhaseTwoDiagnostic,
  BigDataPhaseThreePrediction,
  BigDataScenario,
  BigDataScenarioActionStatus,
  BigDataScenarioInput,
  BigDataScenarioSimulation,
  BigDataScenarioStatus,
  BigDataScenarioType,
} from '../types';
import { createBigDataRequestGate } from '../utils/bigDataRequestGate';

const WEEKDAY_HEADERS = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom'];
type IntelligenceTab =
  | 'summary'
  | 'prediction'
  | 'scenarios'
  | 'calendar'
  | 'anomalies'
  | 'quality';
type AnomalyView = 'pending' | 'explained';
type AnomalyDirection = 'ALL' | 'UP' | 'DOWN';
type AnomalySort = 'impact' | 'deviation' | 'date' | 'confidence';
type PredictionHorizon = 7 | 30 | 90;

interface AnomalyListRow {
  id: string;
  status: AnomalyView;
  reviewStatus: 'OPEN' | BigDataAnomalyReviewStatus;
  review?: BigDataAnomalyReview | null;
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

const ANOMALY_TABLE_COLUMNS = [
  { key: 'date', label: 'Fecha', width: 'w-[102px]' },
  {
    key: 'status',
    label: 'Estado',
    help: 'Por explicar significa que todavía no existe un contexto comercial registrado que coincida con el movimiento.',
    width: 'w-[90px]',
  },
  { key: 'direction', label: 'Dirección', width: 'w-[72px]' },
  {
    key: 'deviation',
    label: 'Desviación',
    help: 'Porcentaje de diferencia entre la venta real del mall y su referencia histórica.',
    width: 'w-[68px]',
  },
  {
    key: 'observed',
    label: 'Venta real del mall',
    help: 'Venta neta total registrada por el mall durante esa fecha.',
    width: 'w-[104px]',
  },
  {
    key: 'expected',
    label: 'Referencia histórica',
    help: 'Mediana de otros días del mismo tipo dentro del período, excluyendo feriados y eventos registrados.',
    width: 'w-[104px]',
  },
  {
    key: 'impact',
    label: 'Diferencia vs. referencia',
    help: 'Venta real del mall menos la referencia histórica. No representa venta causada por un local.',
    width: 'w-[110px]',
  },
  {
    key: 'confidence',
    label: 'Confianza',
    help: 'Solidez de la comparación según los días comparables disponibles y la calidad de los datos.',
    width: 'w-[66px]',
  },
  {
    key: 'contributor',
    label: 'Principal local asociado',
    help: 'Local con la mayor contribución matemática al movimiento. Es una asociación, no una causa comprobada.',
    width: 'w-[150px]',
  },
  { key: 'action', label: '', width: 'w-[82px]' },
] as const;

const INTELLIGENCE_TABS: Array<{
  id: IntelligenceTab;
  label: string;
  description: string;
  icon: React.ElementType;
}> = [
  { id: 'summary', label: 'Resumen', description: 'Hallazgos y patrones', icon: Sparkles },
  { id: 'prediction', label: 'Predicción', description: 'Próximos 7, 30 y 90 días', icon: TrendingUp },
  { id: 'scenarios', label: 'Escenarios', description: 'Simulación y planes', icon: Target },
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
const ANOMALY_CAUSES: Array<{ value: BigDataAnomalyCauseType; label: string }> = [
  { value: 'UNKNOWN', label: 'Por determinar' },
  { value: 'COMMERCIAL_EVENT', label: 'Promoción o actividad comercial' },
  { value: 'DATA_IMPORT', label: 'Importación o archivo' },
  { value: 'STORE_ACTIVITY', label: 'Situación de un local' },
  { value: 'OPERATIONS', label: 'Operación del mall' },
  { value: 'EXTERNAL_FACTOR', label: 'Factor externo' },
  { value: 'DATA_CORRECTION', label: 'Corrección de datos' },
  { value: 'FALSE_POSITIVE', label: 'Falso positivo' },
  { value: 'OTHER', label: 'Otra causa' },
];
const anomalyReviewCopy: Record<'OPEN' | BigDataAnomalyReviewStatus, {
  label: string;
  classes: string;
}> = {
  OPEN: { label: 'Por explicar', classes: 'bg-amber-50 text-amber-700' },
  IN_REVIEW: { label: 'En revisión', classes: 'bg-indigo-50 text-indigo-700' },
  EXPLAINED: { label: 'Explicada', classes: 'bg-emerald-50 text-emerald-700' },
  DISMISSED: { label: 'Descartada', classes: 'bg-slate-100 text-slate-600' },
};
const SCENARIO_TYPES: Array<{ value: BigDataScenarioType; label: string }> = [
  { value: 'PROMOTION', label: 'Promoción' },
  { value: 'HALLWAY_SALE', label: 'Venta de pasillo' },
  { value: 'MALL_ACTIVITY', label: 'Actividad del mall' },
  { value: 'HOLIDAY', label: 'Feriado especial' },
  { value: 'EXTENDED_HOURS', label: 'Horario extendido' },
  { value: 'OTHER', label: 'Otro escenario' },
];

const scenarioStatusCopy: Record<BigDataScenarioStatus, {
  label: string;
  classes: string;
}> = {
  DRAFT: { label: 'Borrador', classes: 'border-slate-200 bg-slate-50 text-slate-600' },
  APPROVED: { label: 'Aprobado', classes: 'border-indigo-200 bg-indigo-50 text-indigo-700' },
  ACTIVE: { label: 'En ejecución', classes: 'border-amber-200 bg-amber-50 text-amber-700' },
  COMPLETED: { label: 'Completado', classes: 'border-emerald-200 bg-emerald-50 text-emerald-700' },
  CANCELLED: { label: 'Cancelado', classes: 'border-rose-200 bg-rose-50 text-rose-600' },
};

const actionStatusCopy: Record<BigDataScenarioActionStatus, string> = {
  PENDING: 'Pendiente',
  IN_PROGRESS: 'En curso',
  DONE: 'Completada',
  CANCELLED: 'Cancelada',
};

const nextScenarioStatus: Partial<Record<
  BigDataScenarioStatus,
  Exclude<BigDataScenarioStatus, 'DRAFT'>
>> = {
  DRAFT: 'APPROVED',
  APPROVED: 'ACTIVE',
  ACTIVE: 'COMPLETED',
};

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

const initialScenarioForm = (): BigDataScenarioInput => {
  const start = new Date();
  start.setDate(start.getDate() + 1);
  const end = new Date(start);
  end.setDate(end.getDate() + 6);
  return {
    name: '',
    scenario_type: 'MALL_ACTIVITY',
    start_date: toIsoDate(start),
    end_date: toIsoDate(end),
    adjustment_percent: 10,
    notes: '',
  };
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

const diagnosticCopy = {
  COMMERCIAL_MOVEMENT: {
    label: 'Movimiento comercial',
    classes: 'border-emerald-200 bg-emerald-50 text-emerald-700',
  },
  IMPORT_ISSUE: {
    label: 'Problema de datos',
    classes: 'border-rose-200 bg-rose-50 text-rose-700',
  },
  MIXED: {
    label: 'Causa mixta',
    classes: 'border-amber-200 bg-amber-50 text-amber-800',
  },
  INSUFFICIENT_DATA: {
    label: 'Evidencia insuficiente',
    classes: 'border-slate-200 bg-slate-50 text-slate-600',
  },
};

const predictionConfidenceCopy = {
  HIGH: {
    label: 'Alta',
    classes: 'border-emerald-200 bg-emerald-50 text-emerald-700',
  },
  MEDIUM: {
    label: 'Media',
    classes: 'border-amber-200 bg-amber-50 text-amber-700',
  },
  LOW: {
    label: 'Baja',
    classes: 'border-rose-200 bg-rose-50 text-rose-700',
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
  const [diagnosticLocalId, setDiagnosticLocalId] = useState<string | null>(null);
  const [diagnostic, setDiagnostic] = useState<BigDataPhaseTwoDiagnostic | null>(null);
  const [diagnosticLoading, setDiagnosticLoading] = useState(false);
  const [diagnosticError, setDiagnosticError] = useState<string | null>(null);
  const [prediction, setPrediction] = useState<BigDataPhaseThreePrediction | null>(null);
  const [predictionLoading, setPredictionLoading] = useState(false);
  const [predictionError, setPredictionError] = useState<string | null>(null);
  const [predictionHorizon, setPredictionHorizon] = useState<PredictionHorizon>(30);
  const [scenarios, setScenarios] = useState<BigDataScenario[]>([]);
  const [scenariosLoading, setScenariosLoading] = useState(false);
  const [scenariosError, setScenariosError] = useState<string | null>(null);
  const [scenarioReloadKey, setScenarioReloadKey] = useState(0);
  const [selectedScenarioId, setSelectedScenarioId] = useState<string | null>(null);
  const [showScenarioForm, setShowScenarioForm] = useState(false);
  const [scenarioForm, setScenarioForm] = useState<BigDataScenarioInput>(
    initialScenarioForm,
  );
  const [scenarioActions, setScenarioActions] = useState([
    { title: '', owner_name: '', due_date: '', notes: '' },
  ]);
  const [scenarioSimulation, setScenarioSimulation] =
    useState<BigDataScenarioSimulation | null>(null);
  const [scenarioSimulating, setScenarioSimulating] = useState(false);
  const [scenarioSaving, setScenarioSaving] = useState(false);
  const [scenarioFormError, setScenarioFormError] = useState<string | null>(null);
  const [scenarioWorkflowBusy, setScenarioWorkflowBusy] = useState(false);
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
  const [showAnomalyReviewForm, setShowAnomalyReviewForm] = useState(false);
  const [anomalyReviewTarget, setAnomalyReviewTarget] =
    useState<AnomalyListRow | null>(null);
  const [anomalyReviewSaving, setAnomalyReviewSaving] = useState(false);
  const [anomalyReviewError, setAnomalyReviewError] = useState<string | null>(null);
  const [anomalyReviewForm, setAnomalyReviewForm] = useState({
    status: 'IN_REVIEW' as BigDataAnomalyReviewStatus,
    cause_type: 'UNKNOWN' as BigDataAnomalyCauseType,
    explanation: '',
    evidence: '',
    owner_name: '',
    add_to_calendar: false,
    calendar_name: '',
    calendar_event_type: 'MALL_ACTIVITY' as BigDataCalendarEventType,
  });
  const requestVersion = useRef(0);
  const diagnosticRequestVersion = useRef(0);
  const predictionRequestVersion = useRef(0);
  const scenarioRequestVersion = useRef(0);
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

  useEffect(() => {
    if (activeTab !== 'prediction') return;
    const mallId = currentMall?.id;
    const token = session?.access_token;
    const version = ++predictionRequestVersion.current;
    setPrediction(null);
    setPredictionError(null);
    if (!mallId || !token) {
      setPredictionLoading(false);
      return;
    }
    setPredictionLoading(true);
    ApiService.getBigDataPhaseThreePrediction(
      mallId,
      dates.start,
      dates.end,
      token,
    )
      .then((response) => {
        if (
          predictionRequestVersion.current === version
          && currentMall?.id === response.mall_id
        ) {
          setPrediction(response);
        }
      })
      .catch((requestError: any) => {
        if (predictionRequestVersion.current === version) {
          setPredictionError(
            requestError?.message || 'No se pudo construir la predicción comercial.',
          );
        }
      })
      .finally(() => {
        if (predictionRequestVersion.current === version) {
          setPredictionLoading(false);
        }
      });
  }, [
    activeTab,
    currentMall?.id,
    session?.access_token,
    dates.start,
    dates.end,
    reloadKey,
  ]);

  useEffect(() => {
    if (activeTab !== 'scenarios') return;
    const mallId = currentMall?.id;
    const token = session?.access_token;
    const version = ++scenarioRequestVersion.current;
    setScenariosError(null);
    if (!mallId || !token) {
      setScenarios([]);
      setScenariosLoading(false);
      return;
    }
    setScenariosLoading(true);
    ApiService.getBigDataScenarios(mallId, token)
      .then((response) => {
        if (
          scenarioRequestVersion.current === version
          && currentMall?.id === mallId
        ) {
          setScenarios(response.data);
          setSelectedScenarioId((current) => (
            current && response.data.some((scenario) => scenario.id === current)
              ? current
              : response.data[0]?.id || null
          ));
        }
      })
      .catch((requestError: any) => {
        if (scenarioRequestVersion.current === version) {
          setScenarios([]);
          setScenariosError(
            requestError?.message || 'No se pudieron cargar los escenarios comerciales.',
          );
        }
      })
      .finally(() => {
        if (scenarioRequestVersion.current === version) {
          setScenariosLoading(false);
        }
      });
  }, [
    activeTab,
    currentMall?.id,
    session?.access_token,
    scenarioReloadKey,
  ]);

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

  const calendarLeadingSpaces = useMemo(
    () => visibleCalendar[0]?.weekday ?? 0,
    [visibleCalendar],
  );

  const selectedPrediction = useMemo(
    () => prediction?.horizons.find((item) => item.days === predictionHorizon) || null,
    [prediction?.horizons, predictionHorizon],
  );

  const visiblePredictionDays = useMemo(
    () => (prediction?.daily || []).slice(0, predictionHorizon),
    [prediction?.daily, predictionHorizon],
  );

  const predictionContextDays = useMemo(
    () => visiblePredictionDays.filter((item) => item.is_holiday || item.events.length),
    [visiblePredictionDays],
  );

  const selectedScenario = useMemo(
    () => scenarios.find((scenario) => scenario.id === selectedScenarioId) || null,
    [scenarios, selectedScenarioId],
  );

  const scenarioSummary = useMemo(() => {
    const open = scenarios.filter(
      (scenario) => !['COMPLETED', 'CANCELLED'].includes(scenario.status),
    );
    const actions = open.flatMap((scenario) => scenario.actions || []);
    return {
      open: open.length,
      potentialImpact: open.reduce(
        (total, scenario) => total + Number(scenario.incremental_sales || 0),
        0,
      ),
      pendingActions: actions.filter(
        (action) => !['DONE', 'CANCELLED'].includes(action.status),
      ).length,
    };
  }, [scenarios]);

  const anomalyRows = useMemo<AnomalyListRow[]>(() => {
    if (!data) return [];
    const pending: AnomalyListRow[] = data.anomalies.map((anomaly) => ({
      id: `pending-${anomaly.date}`,
      status: ['EXPLAINED', 'DISMISSED'].includes(anomaly.review?.status || '')
        ? 'explained'
        : 'pending',
      reviewStatus: anomaly.review?.status || 'OPEN',
      review: anomaly.review,
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
      status: movement.review?.status === 'IN_REVIEW' ? 'pending' : 'explained',
      reviewStatus: movement.review?.status || 'EXPLAINED',
      review: movement.review,
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
    diagnosticRequestVersion.current += 1;
    setSelectedAnomalyId(null);
    setDiagnosticLocalId(null);
    setDiagnostic(null);
    setDiagnosticError(null);
  }, [anomalyView, currentMall?.id]);

  useEffect(() => {
    if (!selectedAnomalyId && !diagnosticLocalId) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      if (diagnosticLocalId) {
        setDiagnosticLocalId(null);
        setDiagnostic(null);
        setDiagnosticError(null);
        return;
      }
      setSelectedAnomalyId(null);
    };
    window.addEventListener('keydown', closeOnEscape);
    return () => window.removeEventListener('keydown', closeOnEscape);
  }, [diagnosticLocalId, selectedAnomalyId]);

  const openDiagnostic = async (contributor: BigDataAnomalyContributor) => {
    if (!currentMall?.id || !session?.access_token || !selectedAnomaly) return;
    const localId = contributor.local_id;
    const version = ++diagnosticRequestVersion.current;
    setDiagnosticLocalId(localId);
    setDiagnostic(null);
    setDiagnosticError(null);
    setDiagnosticLoading(true);
    try {
      const response = await ApiService.getBigDataPhaseTwoDiagnostic(
        currentMall.id,
        localId,
        dates.start,
        dates.end,
        selectedAnomaly.date,
        session.access_token,
      );
      if (
        diagnosticRequestVersion.current === version
        &&
        currentMall?.id === response.mall_id
        && response.local.id === localId
      ) {
        setDiagnostic(response);
      }
    } catch (requestError: any) {
      if (diagnosticRequestVersion.current === version) {
        setDiagnosticError(
          requestError?.message || 'No se pudo construir el diagnóstico 360°.',
        );
      }
    } finally {
      if (diagnosticRequestVersion.current === version) {
        setDiagnosticLoading(false);
      }
    }
  };

  const closeDiagnostic = () => {
    diagnosticRequestVersion.current += 1;
    setDiagnosticLocalId(null);
    setDiagnostic(null);
    setDiagnosticError(null);
  };

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

  const openAnomalyReview = (anomaly: AnomalyListRow) => {
    const existing = anomaly.review;
    setAnomalyReviewError(null);
    setAnomalyReviewTarget(anomaly);
    setAnomalyReviewForm({
      status: existing?.status || 'IN_REVIEW',
      cause_type: existing?.cause_type || 'UNKNOWN',
      explanation: existing?.explanation || '',
      evidence: existing?.evidence || '',
      owner_name: existing?.owner_name || '',
      add_to_calendar: false,
      calendar_name: '',
      calendar_event_type: 'MALL_ACTIVITY',
    });
    setSelectedAnomalyId(null);
    setShowAnomalyReviewForm(true);
  };

  const saveAnomalyReview = async (event: React.FormEvent) => {
    event.preventDefault();
    if (
      !currentMall?.id
      || !session?.access_token
      || !anomalyReviewTarget
      || !data
    ) return;
    if (
      ['EXPLAINED', 'DISMISSED'].includes(anomalyReviewForm.status)
      && anomalyReviewForm.cause_type === 'UNKNOWN'
    ) {
      setAnomalyReviewError('Selecciona una causa antes de cerrar la investigación.');
      return;
    }
    if (
      anomalyReviewForm.add_to_calendar
      && anomalyReviewForm.cause_type !== 'COMMERCIAL_EVENT'
    ) {
      setAnomalyReviewError(
        'Solo las promociones o actividades comerciales se agregan al calendario.',
      );
      return;
    }
    setAnomalyReviewSaving(true);
    setAnomalyReviewError(null);
    let investigationSaved = false;
    try {
      await ApiService.upsertBigDataAnomalyReview(
        currentMall.id,
        anomalyReviewTarget.date,
        {
          status: anomalyReviewForm.status,
          cause_type: anomalyReviewForm.cause_type,
          explanation: anomalyReviewForm.explanation.trim(),
          evidence: anomalyReviewForm.evidence.trim() || undefined,
          owner_name: anomalyReviewForm.owner_name.trim() || undefined,
          snapshot: {
            direction: anomalyReviewTarget.direction,
            observed_sales: anomalyReviewTarget.observedSales,
            expected_sales: anomalyReviewTarget.expectedSales,
            impact: anomalyReviewTarget.impact,
            deviation_percent: anomalyReviewTarget.deviationPercent,
            confidence: anomalyReviewTarget.confidence,
            model_version: data.version,
          },
        },
        session.access_token,
      );
      investigationSaved = true;
      if (anomalyReviewForm.add_to_calendar) {
        await ApiService.createBigDataCalendarEvent(
          currentMall.id,
          {
            name: anomalyReviewForm.calendar_name.trim(),
            event_type: anomalyReviewForm.calendar_event_type,
            start_date: anomalyReviewTarget.date,
            end_date: anomalyReviewTarget.date,
            expected_impact: anomalyReviewTarget.direction,
            notes: [
              anomalyReviewForm.explanation.trim(),
              anomalyReviewForm.evidence.trim(),
            ].filter(Boolean).join('\n\n'),
          },
          session.access_token,
        );
      }
      setShowAnomalyReviewForm(false);
      setAnomalyReviewTarget(null);
      setReloadKey((value) => value + 1);
    } catch (saveError: any) {
      if (investigationSaved) {
        setReloadKey((value) => value + 1);
        setAnomalyReviewError(
          'La investigación quedó guardada, pero no se pudo agregar al calendario. Puedes intentarlo nuevamente.',
        );
      } else {
        setAnomalyReviewError(
          saveError?.message || 'No se pudo guardar la investigación.',
        );
      }
    } finally {
      setAnomalyReviewSaving(false);
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

  const resetScenarioDraft = () => {
    setScenarioForm(initialScenarioForm());
    setScenarioActions([{ title: '', owner_name: '', due_date: '', notes: '' }]);
    setScenarioSimulation(null);
    setScenarioFormError(null);
  };

  const updateScenarioForm = (patch: Partial<BigDataScenarioInput>) => {
    setScenarioForm((current) => ({ ...current, ...patch }));
    setScenarioSimulation(null);
    setScenarioFormError(null);
  };

  const simulateScenario = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!currentMall?.id || !session?.access_token) return;
    setScenarioSimulating(true);
    setScenarioSimulation(null);
    setScenarioFormError(null);
    try {
      const simulation = await ApiService.simulateBigDataScenario(
        currentMall.id,
        dates.start,
        dates.end,
        scenarioForm,
        session.access_token,
      );
      setScenarioSimulation(simulation);
    } catch (simulationError: any) {
      setScenarioFormError(
        simulationError?.message || 'No se pudo calcular el escenario.',
      );
    } finally {
      setScenarioSimulating(false);
    }
  };

  const saveScenario = async () => {
    if (
      !currentMall?.id
      || !session?.access_token
      || !scenarioSimulation
      || !(isAdmin || isTic)
    ) return;
    setScenarioSaving(true);
    setScenarioFormError(null);
    try {
      const saved = await ApiService.createBigDataScenario(
        currentMall.id,
        dates.start,
        dates.end,
        {
          ...scenarioForm,
          actions: scenarioActions
            .filter((action) => action.title.trim())
            .map((action) => ({
              title: action.title.trim(),
              owner_name: action.owner_name.trim() || undefined,
              due_date: action.due_date || undefined,
              notes: action.notes.trim() || undefined,
            })),
        },
        session.access_token,
      );
      setShowScenarioForm(false);
      resetScenarioDraft();
      setSelectedScenarioId(saved.id);
      setScenarioReloadKey((value) => value + 1);
    } catch (saveError: any) {
      setScenarioFormError(
        saveError?.message || 'No se pudo guardar el escenario.',
      );
    } finally {
      setScenarioSaving(false);
    }
  };

  const updateScenarioStatus = async (
    scenario: BigDataScenario,
    status: Exclude<BigDataScenarioStatus, 'DRAFT'>,
  ) => {
    if (!currentMall?.id || !session?.access_token || !(isAdmin || isTic)) return;
    if (
      status === 'CANCELLED'
      && !window.confirm(`¿Cancelar el escenario "${scenario.name}"?`)
    ) return;
    setScenarioWorkflowBusy(true);
    setScenariosError(null);
    try {
      await ApiService.updateBigDataScenarioStatus(
        currentMall.id,
        scenario.id,
        status,
        session.access_token,
      );
      setScenarioReloadKey((value) => value + 1);
    } catch (workflowError: any) {
      setScenariosError(
        workflowError?.message || 'No se pudo actualizar el escenario.',
      );
    } finally {
      setScenarioWorkflowBusy(false);
    }
  };

  const deleteScenario = async (scenario: BigDataScenario) => {
    if (!currentMall?.id || !session?.access_token || !(isAdmin || isTic)) return;
    if (!['DRAFT', 'CANCELLED'].includes(scenario.status)) return;
    const actionCount = scenario.actions?.length || 0;
    const actionWarning = actionCount
      ? ` También se eliminarán ${actionCount} tarea(s) asociada(s).`
      : '';
    if (!window.confirm(
      `¿Eliminar definitivamente el escenario "${scenario.name}"?${actionWarning} Esta acción no se puede deshacer.`,
    )) return;

    setScenarioWorkflowBusy(true);
    setScenariosError(null);
    try {
      await ApiService.deleteBigDataScenario(
        currentMall.id,
        scenario.id,
        session.access_token,
      );
      setSelectedScenarioId(null);
      setScenarios((current) => current.filter((item) => item.id !== scenario.id));
      setScenarioReloadKey((value) => value + 1);
    } catch (deleteError: any) {
      setScenariosError(
        deleteError?.message || 'No se pudo eliminar el escenario.',
      );
    } finally {
      setScenarioWorkflowBusy(false);
    }
  };

  const updateScenarioActionStatus = async (
    actionId: string,
    status: BigDataScenarioActionStatus,
  ) => {
    if (!currentMall?.id || !session?.access_token || !(isAdmin || isTic)) return;
    setScenarioWorkflowBusy(true);
    setScenariosError(null);
    try {
      await ApiService.updateBigDataScenarioActionStatus(
        currentMall.id,
        actionId,
        status,
        session.access_token,
      );
      setScenarioReloadKey((value) => value + 1);
    } catch (workflowError: any) {
      setScenariosError(
        workflowError?.message || 'No se pudo actualizar la acción.',
      );
    } finally {
      setScenarioWorkflowBusy(false);
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
  const statusLabel = activeTab === 'scenarios'
    ? `${scenarioSummary.open} escenario(s) abierto(s)`
    : activeTab === 'prediction'
    ? prediction
      ? `Confianza ${predictionConfidenceCopy[prediction.quality.confidence].label.toLowerCase()}`
      : 'Predicción explicable'
    : data?.general_status === 'DATA_INCOMPLETE'
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
                  Big Data · {activeTab === 'scenarios'
                    ? 'Fase 3B'
                    : activeTab === 'prediction'
                    ? 'Fase 3A'
                    : 'Fase 1'}
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
                {activeTab === 'scenarios'
                  ? 'Compara decisiones contra la predicción base, documenta los supuestos y convierte el escenario aprobado en un plan de ejecución medible.'
                  : activeTab === 'prediction'
                  ? 'Proyecta los próximos 7, 30 y 90 días con rangos de confianza, estacionalidad y contexto comercial verificable.'
                  : 'Descubre cuándo se repiten los patrones, qué fechas se salen de lo esperado, cuáles locales explican el movimiento y si los datos son confiables para actuar.'}
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
              : tab.id === 'scenarios'
              ? scenarioSummary.open
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

          {activeTab === 'prediction' && (
          <section role="tabpanel" className="space-y-3">
            {predictionError && (
              <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
                {predictionError}. Verifica que <code>BIG_DATA_FORECAST</code> esté habilitado para este mall.
              </div>
            )}

            {predictionLoading && (
              <div className="grid min-h-[360px] place-items-center rounded-2xl border border-slate-200 bg-white">
                <div className="text-center">
                  <Loader2 className="mx-auto animate-spin text-indigo-600" size={28} />
                  <p className="mt-3 text-sm font-bold text-slate-600">
                    Calculando estacionalidad, tendencia y contexto futuro…
                  </p>
                </div>
              </div>
            )}

            {!predictionLoading && prediction?.status === 'INSUFFICIENT_DATA' && (
              <div className="rounded-2xl border border-amber-200 bg-white p-5 shadow-sm">
                <div className="flex items-start gap-3">
                  <FileWarning className="mt-0.5 shrink-0 text-amber-500" size={22} />
                  <div>
                    <p className="font-black text-slate-900">Aún no emitimos una predicción</p>
                    <p className="mt-1 text-sm leading-6 text-slate-600">
                      {prediction.quality.reasons[0]
                        || 'Se requieren al menos 28 días históricos del mall.'}
                    </p>
                    <p className="mt-2 text-xs font-bold text-slate-400">
                      Disponibles: {prediction.quality.days_with_data} de {prediction.quality.expected_days} días del rango.
                    </p>
                  </div>
                </div>
              </div>
            )}

            {!predictionLoading && prediction?.status === 'OK' && selectedPrediction && (
              <>
                <div className="rounded-2xl border border-slate-200 bg-white p-3 shadow-sm">
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                    <div>
                      <p className="flex items-center gap-2 text-xs font-black uppercase tracking-[0.14em] text-indigo-600">
                        <TrendingUp size={16} /> Horizonte de predicción
                      </p>
                      <p className="mt-1 text-xs text-slate-500">
                        Corte {formatDate(prediction.period.as_of, { day: 'numeric', month: 'long', year: 'numeric' })}
                      </p>
                    </div>
                    <div className="flex rounded-xl bg-slate-100 p-1">
                      {([7, 30, 90] as PredictionHorizon[]).map((days) => (
                        <button
                          key={days}
                          type="button"
                          onClick={() => setPredictionHorizon(days)}
                          className={`rounded-lg px-4 py-2 text-xs font-black transition ${
                            predictionHorizon === days
                              ? 'bg-white text-indigo-700 shadow-sm'
                              : 'text-slate-500 hover:text-slate-800'
                          }`}
                        >
                          {days} días
                        </button>
                      ))}
                    </div>
                  </div>
                </div>

                <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                  <article className="rounded-2xl bg-slate-950 p-4 text-white shadow-sm">
                    <p className="text-[10px] font-black uppercase tracking-[0.14em] text-slate-400">
                      Venta proyectada
                    </p>
                    <p className="mt-2 truncate text-2xl font-black">
                      {format(selectedPrediction.expected_sales)}
                    </p>
                    <p className="mt-1 text-[10px] text-slate-400">
                      {formatDate(selectedPrediction.start_date, { day: '2-digit', month: 'short' })}
                      {' — '}
                      {formatDate(selectedPrediction.end_date, { day: '2-digit', month: 'short' })}
                    </p>
                  </article>
                  <article className="rounded-2xl border border-indigo-100 bg-indigo-50/60 p-4">
                    <p className="text-[10px] font-black uppercase tracking-[0.14em] text-indigo-500">
                      Rango esperado
                    </p>
                    <p className="mt-2 text-sm font-black text-slate-900">
                      {format(selectedPrediction.lower_bound)}
                    </p>
                    <p className="mt-0.5 text-xs font-bold text-slate-400">
                      hasta {format(selectedPrediction.upper_bound)}
                    </p>
                  </article>
                  <article className="rounded-2xl border border-slate-200 bg-white p-4">
                    <p className="text-[10px] font-black uppercase tracking-[0.14em] text-slate-400">
                      Promedio diario
                    </p>
                    <p className="mt-2 text-xl font-black text-slate-900">
                      {format(selectedPrediction.average_daily_sales)}
                    </p>
                    <p className={`mt-1 text-[10px] font-black ${
                      Number(selectedPrediction.comparison_recent_average_percent || 0) >= 0
                        ? 'text-emerald-600'
                        : 'text-rose-600'
                    }`}>
                      {Number(selectedPrediction.comparison_recent_average_percent || 0) > 0 ? '+' : ''}
                      {Number(selectedPrediction.comparison_recent_average_percent || 0).toFixed(1)}% vs. promedio reciente
                    </p>
                  </article>
                  <article className="rounded-2xl border border-slate-200 bg-white p-4">
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <p className="text-[10px] font-black uppercase tracking-[0.14em] text-slate-400">
                          Confianza
                        </p>
                        <p className="mt-2 text-xl font-black text-slate-900">
                          {prediction.quality.score}/100
                        </p>
                      </div>
                      <span className={`rounded-full border px-2.5 py-1 text-[10px] font-black ${
                        predictionConfidenceCopy[selectedPrediction.confidence].classes
                      }`}>
                        {predictionConfidenceCopy[selectedPrediction.confidence].label}
                      </span>
                    </div>
                    <p className="mt-1 text-[10px] text-slate-500">
                      Cobertura {prediction.quality.coverage_percent.toFixed(1)}%
                    </p>
                  </article>
                </div>

                <div className="grid gap-3 xl:grid-cols-[1.65fr_0.75fr]">
                  <article className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <p className="text-xs font-black uppercase tracking-[0.14em] text-indigo-600">
                          Trayectoria esperada
                        </p>
                        <h3 className="mt-1 text-lg font-black text-slate-900">
                          Venta diaria con límites de incertidumbre
                        </h3>
                      </div>
                      <div className="flex items-center gap-3 text-[10px] font-bold text-slate-400">
                        <span className="flex items-center gap-1.5">
                          <i className="h-0.5 w-4 bg-indigo-600" /> Esperado
                        </span>
                        <span className="flex items-center gap-1.5">
                          <i className="h-0.5 w-4 border-t border-dashed border-slate-400" /> Límites
                        </span>
                      </div>
                    </div>
                    <div className="mt-3 h-64">
                      <ResponsiveContainer width="100%" height="100%">
                        <LineChart
                          data={visiblePredictionDays}
                          margin={{ top: 8, right: 8, left: -18, bottom: 0 }}
                        >
                          <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
                          <XAxis
                            dataKey="date"
                            tick={{ fontSize: 9 }}
                            axisLine={false}
                            tickLine={false}
                            minTickGap={24}
                            tickFormatter={(value) => formatDate(String(value), { day: '2-digit', month: 'short' })}
                          />
                          <YAxis
                            tick={{ fontSize: 9 }}
                            axisLine={false}
                            tickLine={false}
                            tickFormatter={(value) => compactNumber.format(Number(value))}
                          />
                          <Tooltip
                            labelFormatter={(value) => formatDate(String(value), {
                              weekday: 'long',
                              day: 'numeric',
                              month: 'long',
                            })}
                            formatter={(value: number, name: string) => [
                              format(Number(value)),
                              name === 'expected_sales'
                                ? 'Venta esperada'
                                : name === 'lower_bound'
                                ? 'Límite inferior'
                                : 'Límite superior',
                            ]}
                          />
                          <Line
                            type="monotone"
                            dataKey="lower_bound"
                            stroke="#94a3b8"
                            strokeDasharray="4 4"
                            strokeWidth={1}
                            dot={false}
                          />
                          <Line
                            type="monotone"
                            dataKey="upper_bound"
                            stroke="#94a3b8"
                            strokeDasharray="4 4"
                            strokeWidth={1}
                            dot={false}
                          />
                          <Line
                            type="monotone"
                            dataKey="expected_sales"
                            stroke="#4f46e5"
                            strokeWidth={2.5}
                            dot={predictionHorizon === 7}
                            activeDot={{ r: 4 }}
                          />
                        </LineChart>
                      </ResponsiveContainer>
                    </div>
                  </article>

                  <aside className="space-y-3">
                    <article className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                      <p className="text-xs font-black uppercase tracking-[0.14em] text-indigo-600">
                        Motores del cálculo
                      </p>
                      <div className="mt-3 space-y-2">
                        <div className="flex items-center justify-between rounded-xl bg-slate-50 px-3 py-2.5">
                          <span className="text-xs font-bold text-slate-500">Tendencia 28 días</span>
                          <span className={`text-sm font-black ${
                            prediction.drivers.trend_percent >= 0 ? 'text-emerald-600' : 'text-rose-600'
                          }`}>
                            {prediction.drivers.trend_percent > 0 ? '+' : ''}
                            {prediction.drivers.trend_percent.toFixed(1)}%
                          </span>
                        </div>
                        <div className="flex items-center justify-between rounded-xl bg-slate-50 px-3 py-2.5">
                          <span className="text-xs font-bold text-slate-500">Días históricos</span>
                          <span className="text-sm font-black text-slate-800">
                            {prediction.quality.days_with_data}
                          </span>
                        </div>
                        <div className="flex items-center justify-between rounded-xl bg-slate-50 px-3 py-2.5">
                          <span className="text-xs font-bold text-slate-500">Contexto futuro</span>
                          <span className="text-sm font-black text-slate-800">
                            {selectedPrediction.known_context_days} día(s)
                          </span>
                        </div>
                        <div className="flex items-center justify-between rounded-xl bg-slate-50 px-3 py-2.5">
                          <span className="text-xs font-bold text-slate-500">Peso fin de semana</span>
                          <span className="text-sm font-black text-slate-800">
                            {selectedPrediction.weekend_share_percent.toFixed(1)}%
                          </span>
                        </div>
                      </div>
                    </article>

                    {prediction.quality.reasons.length > 0 && (
                      <article className="rounded-2xl border border-amber-100 bg-amber-50/70 p-4">
                        <p className="text-xs font-black text-amber-900">Límites de confianza</p>
                        <ul className="mt-2 space-y-1.5 text-[11px] leading-5 text-amber-800">
                          {prediction.quality.reasons.slice(0, 3).map((reason) => (
                            <li key={reason}>• {reason}</li>
                          ))}
                        </ul>
                      </article>
                    )}
                  </aside>
                </div>

                <div className="grid gap-3 lg:grid-cols-[1.2fr_0.8fr]">
                  <article className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                    <div>
                      <p className="text-xs font-black uppercase tracking-[0.14em] text-indigo-600">
                        Calendario incorporado
                      </p>
                      <h3 className="mt-1 text-base font-black text-slate-900">
                        Feriados y actividades dentro del horizonte
                      </h3>
                    </div>
                    {predictionContextDays.length ? (
                      <div className="mt-3 divide-y divide-slate-100 overflow-hidden rounded-xl border border-slate-100">
                        {predictionContextDays.slice(0, 8).map((item) => {
                          const unapplied = item.adjustments.some(
                            (adjustment) => adjustment.source !== 'RECENT_TREND' && !adjustment.applied,
                          );
                          return (
                            <div
                              key={item.date}
                              className="grid gap-2 px-3 py-3 sm:grid-cols-[110px_1fr_auto] sm:items-center"
                            >
                              <p className="text-xs font-black capitalize text-slate-800">
                                {formatDate(item.date, { day: '2-digit', month: 'short' })}
                              </p>
                              <div>
                                <p className="text-xs font-bold text-slate-700">
                                  {item.events.map((event) => event.name).join(', ')
                                    || item.holiday_name
                                    || 'Contexto comercial'}
                                </p>
                                <p className="mt-0.5 text-[10px] text-slate-400">
                                  {unapplied
                                    ? 'Registrado, sin ajuste por historial insuficiente'
                                    : `Ajuste total ${item.adjustment_percent > 0 ? '+' : ''}${item.adjustment_percent.toFixed(1)}%`}
                                </p>
                              </div>
                              <p className="text-xs font-black text-indigo-700">
                                {format(item.expected_sales)}
                              </p>
                            </div>
                          );
                        })}
                      </div>
                    ) : (
                      <div className="mt-3 rounded-xl bg-slate-50 p-4 text-sm text-slate-500">
                        No hay feriados ni actividades registradas dentro de este horizonte.
                      </div>
                    )}
                  </article>

                  <article className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                    <p className="text-xs font-black uppercase tracking-[0.14em] text-indigo-600">
                      Ajustes aprendidos
                    </p>
                    <div className="mt-3 space-y-2">
                      {prediction.drivers.event_adjustments.map((adjustment) => (
                        <div
                          key={adjustment.event_type}
                          className="flex items-center justify-between gap-3 rounded-xl border border-slate-100 px-3 py-2.5"
                        >
                          <div>
                            <p className="text-xs font-black text-slate-700">
                              {adjustment.event_type_label}
                            </p>
                            <p className="mt-0.5 text-[10px] text-slate-400">
                              {adjustment.observations} observación(es)
                            </p>
                          </div>
                          <span className={`text-xs font-black ${
                            adjustment.applied
                              ? adjustment.adjustment_percent >= 0
                                ? 'text-emerald-600'
                                : 'text-rose-600'
                              : 'text-slate-400'
                          }`}>
                            {adjustment.applied
                              ? `${adjustment.adjustment_percent > 0 ? '+' : ''}${adjustment.adjustment_percent.toFixed(1)}%`
                              : 'Sin aplicar'}
                          </span>
                        </div>
                      ))}
                      {!prediction.drivers.event_adjustments.length && (
                        <p className="rounded-xl bg-slate-50 p-4 text-xs leading-5 text-slate-500">
                          Todavía no existen actividades históricas suficientes para aprender un ajuste.
                        </p>
                      )}
                    </div>
                    <p className="mt-3 text-[10px] leading-4 text-slate-400">
                      {prediction.methodology}
                    </p>
                  </article>
                </div>
              </>
            )}
          </section>
          )}

          {activeTab === 'scenarios' && (
          <section role="tabpanel" className="space-y-3">
            <div className="grid gap-3 sm:grid-cols-3">
              <article className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                <p className="text-[10px] font-black uppercase tracking-[0.14em] text-slate-400">
                  Escenarios abiertos
                </p>
                <p className="mt-2 text-2xl font-black text-slate-900">
                  {scenarioSummary.open}
                </p>
                <p className="mt-1 text-[10px] text-slate-500">
                  Borradores, aprobados o en ejecución
                </p>
              </article>
              <article className="rounded-2xl border border-indigo-100 bg-indigo-50/60 p-4">
                <p className="text-[10px] font-black uppercase tracking-[0.14em] text-indigo-500">
                  Impacto potencial abierto
                </p>
                <p className={`mt-2 text-2xl font-black ${
                  scenarioSummary.potentialImpact >= 0 ? 'text-emerald-700' : 'text-rose-700'
                }`}>
                  {scenarioSummary.potentialImpact > 0 ? '+' : ''}
                  {format(scenarioSummary.potentialImpact)}
                </p>
                <p className="mt-1 text-[10px] text-indigo-500">
                  Supuestos acumulados; no es venta comprometida
                </p>
              </article>
              <article className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-[10px] font-black uppercase tracking-[0.14em] text-slate-400">
                      Acciones pendientes
                    </p>
                    <p className="mt-2 text-2xl font-black text-slate-900">
                      {scenarioSummary.pendingActions}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => {
                      resetScenarioDraft();
                      setShowScenarioForm(true);
                    }}
                    className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-3 py-2 text-xs font-black text-white shadow-sm hover:bg-indigo-700"
                  >
                    <Plus size={15} /> Simular
                  </button>
                </div>
                <p className="mt-1 text-[10px] text-slate-500">
                  Tareas del plan que aún requieren seguimiento
                </p>
              </article>
            </div>

            {scenariosError && (
              <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-xs leading-5 text-amber-900">
                {scenariosError}
              </div>
            )}

            <div className="grid gap-3 xl:grid-cols-[1.45fr_0.75fr]">
              <article className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
                <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-4 py-3">
                  <div>
                    <p className="flex items-center gap-2 text-xs font-black uppercase tracking-[0.14em] text-indigo-600">
                      <Target size={16} /> Escenarios comerciales
                    </p>
                    <p className="mt-1 text-xs text-slate-500">
                      Comparación contra la predicción vigente al momento de guardar.
                    </p>
                  </div>
                  <span className="rounded-full bg-slate-100 px-2.5 py-1 text-[10px] font-black text-slate-500">
                    Últimos {scenarios.length}
                  </span>
                </div>

                {scenariosLoading ? (
                  <div className="grid min-h-56 place-items-center">
                    <div className="flex items-center gap-2 text-sm font-bold text-slate-500">
                      <Loader2 size={18} className="animate-spin" /> Cargando escenarios…
                    </div>
                  </div>
                ) : scenarios.length ? (
                  <div className="overflow-x-auto">
                    <table className="min-w-full text-left">
                      <thead className="bg-slate-50 text-[9px] font-black uppercase tracking-wide text-slate-400">
                        <tr>
                          <th className="px-4 py-2.5">Escenario</th>
                          <th className="px-3 py-2.5">Período</th>
                          <th className="px-3 py-2.5">Supuesto</th>
                          <th className="px-3 py-2.5">Impacto potencial</th>
                          <th className="px-3 py-2.5">Estado</th>
                          <th className="px-3 py-2.5 text-right">Plan</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100">
                        {scenarios.map((scenario) => {
                          const doneActions = (scenario.actions || []).filter(
                            (action) => action.status === 'DONE',
                          ).length;
                          return (
                            <tr
                              key={scenario.id}
                              onClick={() => setSelectedScenarioId(scenario.id)}
                              className={`cursor-pointer text-xs transition ${
                                selectedScenarioId === scenario.id
                                  ? 'bg-indigo-50/60'
                                  : 'hover:bg-slate-50'
                              }`}
                            >
                              <td className="px-4 py-3">
                                <p className="max-w-52 truncate font-black text-slate-800">
                                  {scenario.name}
                                </p>
                                <p className="mt-0.5 text-[9px] text-slate-400">
                                  {SCENARIO_TYPES.find((item) => item.value === scenario.scenario_type)?.label
                                    || scenario.scenario_type}
                                </p>
                              </td>
                              <td className="whitespace-nowrap px-3 py-3 text-[10px] font-bold text-slate-500">
                                {formatDate(scenario.start_date, { day: '2-digit', month: 'short' })}
                                {' — '}
                                {formatDate(scenario.end_date, { day: '2-digit', month: 'short' })}
                              </td>
                              <td className={`whitespace-nowrap px-3 py-3 font-black ${
                                Number(scenario.adjustment_percent) >= 0
                                  ? 'text-emerald-600'
                                  : 'text-rose-600'
                              }`}>
                                {Number(scenario.adjustment_percent) > 0 ? '+' : ''}
                                {Number(scenario.adjustment_percent).toFixed(1)}%
                              </td>
                              <td className={`whitespace-nowrap px-3 py-3 font-black ${
                                Number(scenario.incremental_sales) >= 0
                                  ? 'text-emerald-600'
                                  : 'text-rose-600'
                              }`}>
                                {Number(scenario.incremental_sales) > 0 ? '+' : ''}
                                {format(Number(scenario.incremental_sales))}
                              </td>
                              <td className="px-3 py-3">
                                <span className={`rounded-full border px-2 py-1 text-[9px] font-black ${
                                  scenarioStatusCopy[scenario.status].classes
                                }`}>
                                  {scenarioStatusCopy[scenario.status].label}
                                </span>
                              </td>
                              <td className="whitespace-nowrap px-3 py-3 text-right text-[10px] font-bold text-slate-500">
                                {doneActions}/{scenario.actions?.length || 0}
                                <Eye size={14} className="ml-2 inline text-indigo-500" />
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <div className="grid min-h-56 place-items-center p-6 text-center">
                    <div>
                      <Target size={28} className="mx-auto text-slate-300" />
                      <p className="mt-3 text-sm font-black text-slate-700">
                        Aún no hay escenarios guardados
                      </p>
                      <p className="mt-1 max-w-sm text-xs leading-5 text-slate-500">
                        Simula una promoción, actividad o cambio operativo y compáralo
                        con la predicción base antes de aprobarlo.
                      </p>
                    </div>
                  </div>
                )}
              </article>

              <aside className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                {selectedScenario ? (
                  <>
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="text-[10px] font-black uppercase tracking-[0.14em] text-indigo-600">
                          Ficha del escenario
                        </p>
                        <h3 className="mt-1 truncate text-base font-black text-slate-900">
                          {selectedScenario.name}
                        </h3>
                      </div>
                      <span className={`shrink-0 rounded-full border px-2 py-1 text-[9px] font-black ${
                        scenarioStatusCopy[selectedScenario.status].classes
                      }`}>
                        {scenarioStatusCopy[selectedScenario.status].label}
                      </span>
                    </div>

                    <div className="mt-3 grid grid-cols-2 gap-2">
                      <div className="rounded-xl bg-slate-50 p-3">
                        <p className="text-[9px] font-black uppercase text-slate-400">Base</p>
                        <p className="mt-1 text-sm font-black text-slate-800">
                          {format(Number(selectedScenario.baseline_sales))}
                        </p>
                      </div>
                      <div className="rounded-xl bg-indigo-50 p-3">
                        <p className="text-[9px] font-black uppercase text-indigo-400">Escenario</p>
                        <p className="mt-1 text-sm font-black text-indigo-900">
                          {format(Number(selectedScenario.scenario_sales))}
                        </p>
                      </div>
                    </div>
                    <p className="mt-2 rounded-xl border border-slate-100 px-3 py-2 text-[10px] leading-4 text-slate-500">
                      Rango de planificación: {format(Number(selectedScenario.lower_bound))}
                      {' — '}
                      {format(Number(selectedScenario.upper_bound))}. Confianza{' '}
                      {predictionConfidenceCopy[selectedScenario.confidence].label.toLowerCase()}.
                    </p>

                    <div className="mt-4 flex items-center justify-between">
                      <p className="flex items-center gap-2 text-[10px] font-black uppercase tracking-wide text-slate-500">
                        <ClipboardList size={14} /> Plan de acción
                      </p>
                      <span className="text-[9px] font-bold text-slate-400">
                        {selectedScenario.actions?.length || 0} tarea(s)
                      </span>
                    </div>
                    <div className="mt-2 max-h-52 space-y-2 overflow-y-auto">
                      {(selectedScenario.actions || []).map((action) => (
                        <div key={action.id} className="rounded-xl border border-slate-100 p-2.5">
                          <div className="flex items-start justify-between gap-2">
                            <div className="min-w-0">
                              <p className={`text-xs font-black ${
                                action.status === 'DONE'
                                  ? 'text-slate-400 line-through'
                                  : 'text-slate-700'
                              }`}>
                                {action.title}
                              </p>
                              <p className="mt-0.5 text-[9px] text-slate-400">
                                {action.owner_name || 'Sin responsable'}
                                {action.due_date
                                  ? ` · ${formatDate(action.due_date, { day: '2-digit', month: 'short' })}`
                                  : ''}
                              </p>
                            </div>
                            {(isAdmin || isTic) ? (
                              <select
                                value={action.status}
                                disabled={
                                  scenarioWorkflowBusy
                                  || ['COMPLETED', 'CANCELLED'].includes(selectedScenario.status)
                                }
                                onChange={(event) => updateScenarioActionStatus(
                                  action.id,
                                  event.target.value as BigDataScenarioActionStatus,
                                )}
                                className="max-w-24 rounded-lg border border-slate-200 bg-white px-1.5 py-1 text-[9px] font-bold text-slate-600"
                              >
                                {(Object.keys(actionStatusCopy) as BigDataScenarioActionStatus[]).map((status) => (
                                  <option key={status} value={status}>{actionStatusCopy[status]}</option>
                                ))}
                              </select>
                            ) : (
                              <span className="text-[9px] font-bold text-slate-400">
                                {actionStatusCopy[action.status]}
                              </span>
                            )}
                          </div>
                        </div>
                      ))}
                      {!selectedScenario.actions?.length && (
                        <p className="rounded-xl bg-slate-50 p-3 text-xs leading-5 text-slate-500">
                          Este escenario no tiene acciones asignadas.
                        </p>
                      )}
                    </div>

                    {(isAdmin || isTic)
                      && !['COMPLETED', 'CANCELLED'].includes(selectedScenario.status) && (
                      <div className="mt-4 flex flex-wrap gap-2 border-t border-slate-100 pt-3">
                        {nextScenarioStatus[selectedScenario.status] && (
                          <button
                            type="button"
                            disabled={scenarioWorkflowBusy}
                            onClick={() => updateScenarioStatus(
                              selectedScenario,
                              nextScenarioStatus[selectedScenario.status]!,
                            )}
                            className="flex-1 rounded-xl bg-indigo-600 px-3 py-2 text-xs font-black text-white disabled:opacity-50"
                          >
                            {selectedScenario.status === 'DRAFT'
                              ? 'Aprobar'
                              : selectedScenario.status === 'APPROVED'
                              ? 'Iniciar'
                              : 'Completar'}
                          </button>
                        )}
                        <button
                          type="button"
                          disabled={scenarioWorkflowBusy}
                          onClick={() => updateScenarioStatus(selectedScenario, 'CANCELLED')}
                          className="rounded-xl border border-rose-200 px-3 py-2 text-xs font-black text-rose-600 disabled:opacity-50"
                        >
                          Cancelar
                        </button>
                      </div>
                    )}
                    {(isAdmin || isTic)
                      && ['DRAFT', 'CANCELLED'].includes(selectedScenario.status) && (
                      <div className="mt-3 border-t border-slate-100 pt-3">
                        <button
                          type="button"
                          disabled={scenarioWorkflowBusy}
                          onClick={() => deleteScenario(selectedScenario)}
                          className="flex w-full items-center justify-center gap-2 rounded-xl border border-rose-200 px-3 py-2 text-xs font-black text-rose-600 transition-colors hover:bg-rose-50 disabled:opacity-50"
                        >
                          <Trash2 size={14} />
                          Eliminar definitivamente
                        </button>
                        <p className="mt-1.5 text-center text-[9px] leading-4 text-slate-400">
                          Disponible solo para borradores o escenarios cancelados.
                        </p>
                      </div>
                    )}
                  </>
                ) : (
                  <div className="grid min-h-72 place-items-center text-center">
                    <div>
                      <ClipboardList size={28} className="mx-auto text-slate-300" />
                      <p className="mt-3 text-sm font-black text-slate-700">
                        Selecciona un escenario
                      </p>
                      <p className="mt-1 text-xs text-slate-500">
                        Aquí verás su supuesto, rango y plan de ejecución.
                      </p>
                    </div>
                  </div>
                )}
              </aside>
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
                Por investigar · {anomalyRows.filter((row) => row.status === 'pending').length}
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
                Revisadas · {anomalyRows.filter((row) => row.status === 'explained').length}
              </button>
            </div>
          )}

          {activeTab === 'anomalies' && (
            <section role="tabpanel" className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
              <div className="flex flex-col gap-3 border-b border-slate-100 p-4 xl:flex-row xl:items-end xl:justify-between">
                <div>
                  <p className="flex items-center gap-2 text-xs font-black uppercase tracking-[0.14em] text-indigo-600">
                    <AlertTriangle size={16} />
                    {anomalyView === 'pending' ? 'Anomalías por investigar' : 'Investigaciones revisadas'}
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
                    <table className="min-w-[980px] w-full table-fixed border-collapse text-left">
                      <caption className="sr-only">
                        La venta real, la referencia histórica y su diferencia corresponden
                        al mall; el principal local asociado es una atribución matemática,
                        no una causa comprobada.
                      </caption>
                      <thead className="bg-slate-50 text-[9px] font-black uppercase tracking-wide text-slate-400">
                        <tr>
                          {ANOMALY_TABLE_COLUMNS.map((column) => (
                            <th
                              key={column.key}
                              className={`${column.width} px-2 py-2.5 ${
                                column.key === 'action'
                                  ? 'sticky right-0 z-10 bg-slate-50'
                                  : ''
                              }`}
                            >
                              <span
                                className="inline-flex items-center gap-1 leading-tight"
                                title={'help' in column ? column.help : undefined}
                              >
                                {column.label}
                                {'help' in column && (
                                  <Info
                                    size={11}
                                    aria-label={`Ayuda: ${column.help}`}
                                    className="normal-case text-slate-300"
                                  />
                                )}
                              </span>
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100">
                        {visibleAnomalyRows.map((row) => {
                          const contributor = row.contributors[0];
                          return (
                            <tr key={row.id} className="group text-xs text-slate-600 hover:bg-indigo-50/30">
                              <td className="whitespace-nowrap px-2 py-2.5 font-black capitalize text-slate-800">
                                {formatDate(row.date, { day: '2-digit', month: 'short', year: 'numeric' })}
                              </td>
                              <td className="px-2 py-2.5">
                                <span className={`inline-block rounded-full px-1.5 py-1 text-[8px] font-black uppercase leading-tight ${
                                  anomalyReviewCopy[row.reviewStatus].classes
                                }`}>
                                  {anomalyReviewCopy[row.reviewStatus].label}
                                </span>
                              </td>
                              <td className="px-2 py-2.5">
                                <span className={`inline-flex items-center gap-1 font-black ${
                                  row.direction === 'UP' ? 'text-emerald-600' : 'text-rose-600'
                                }`}>
                                  {row.direction === 'UP' ? <TrendingUp size={14} /> : <TrendingDown size={14} />}
                                  {row.direction === 'UP' ? 'Pico' : 'Caída'}
                                </span>
                              </td>
                              <td className={`px-2 py-2.5 font-black ${
                                row.direction === 'UP' ? 'text-emerald-600' : 'text-rose-600'
                              }`}>
                                {row.deviationPercent > 0 ? '+' : ''}{row.deviationPercent.toFixed(1)}%
                              </td>
                              <td className="whitespace-nowrap px-2 py-2.5 font-bold text-slate-800">{format(row.observedSales)}</td>
                              <td className="whitespace-nowrap px-2 py-2.5">{format(row.expectedSales)}</td>
                              <td className={`whitespace-nowrap px-2 py-2.5 font-black ${
                                row.impact >= 0 ? 'text-emerald-600' : 'text-rose-600'
                              }`}>
                                {row.impact > 0 ? '+' : ''}{format(row.impact)}
                              </td>
                              <td className="px-2 py-2.5 font-bold">{(row.confidence * 100).toFixed(0)}%</td>
                              <td className="max-w-36 px-2 py-2.5">
                                {contributor ? (
                                  <>
                                    <p className="truncate font-black text-slate-700">
                                      {contributor.local_name}
                                    </p>
                                    <p className={`mt-0.5 whitespace-nowrap text-[10px] font-bold ${
                                      contributor.contribution >= 0
                                        ? 'text-emerald-600'
                                        : 'text-rose-600'
                                    }`}>
                                      Aporte {contributor.contribution > 0 ? '+' : ''}
                                      {format(contributor.contribution)}
                                      {' · '}
                                      {contributor.impact_share_percent.toFixed(1)}%
                                    </p>
                                  </>
                                ) : (
                                  <span className="font-bold text-slate-500">Sin atribución</span>
                                )}
                              </td>
                              <td className="sticky right-0 bg-white px-2 py-2.5 text-right group-hover:bg-indigo-50">
                                <button
                                  type="button"
                                  onClick={() => setSelectedAnomalyId(row.id)}
                                  className="inline-flex whitespace-nowrap items-center gap-1 rounded-lg border border-indigo-100 bg-white px-2 py-1.5 text-[9px] font-black text-indigo-600 hover:bg-indigo-50"
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
                            {row.contributors[0]
                              ? `${row.contributors[0].local_name} · aporte ${
                                row.contributors[0].contribution > 0 ? '+' : ''
                              }${format(row.contributors[0].contribution)}`
                              : row.context}
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
                    anomalyReviewCopy[selectedAnomaly.reviewStatus].classes
                  }`}>
                    {anomalyReviewCopy[selectedAnomaly.reviewStatus].label}
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
                    ['Venta real del mall', format(selectedAnomaly.observedSales)],
                    ['Referencia histórica', format(selectedAnomaly.expectedSales)],
                    ['Diferencia vs. referencia', `${selectedAnomaly.impact > 0 ? '+' : ''}${format(selectedAnomaly.impact)}`],
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
                {selectedAnomaly.review && (
                  <div className="mt-3 space-y-2 border-t border-sky-100 pt-3 text-xs text-sky-950">
                    <div className="flex flex-wrap gap-x-5 gap-y-1">
                      <p>
                        <span className="font-black">Causa:</span>{' '}
                        {ANOMALY_CAUSES.find(
                          (cause) => cause.value === selectedAnomaly.review?.cause_type,
                        )?.label || 'Por determinar'}
                      </p>
                      {selectedAnomaly.review.owner_name && (
                        <p>
                          <span className="font-black">Responsable:</span>{' '}
                          {selectedAnomaly.review.owner_name}
                        </p>
                      )}
                    </div>
                    <p className="leading-5">{selectedAnomaly.review.explanation}</p>
                    {selectedAnomaly.review.evidence && (
                      <p className="leading-5 text-sky-800">
                        <span className="font-black">Evidencia:</span>{' '}
                        {selectedAnomaly.review.evidence}
                      </p>
                    )}
                  </div>
                )}
                {(isAdmin || isTic) && (
                  <div className="mt-3 border-t border-sky-100 pt-3">
                    <button
                      type="button"
                      onClick={() => openAnomalyReview(selectedAnomaly)}
                      className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-sky-600 px-3 py-2.5 text-xs font-black text-white hover:bg-sky-700"
                    >
                      <ClipboardList size={15} />
                      {selectedAnomaly.review ? 'Editar investigación' : 'Investigar movimiento'}
                    </button>
                    <p className="mt-1.5 text-[10px] leading-4 text-sky-700">
                      Documenta causa, explicación, evidencia y responsable. El calendario es opcional.
                    </p>
                  </div>
                )}
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
                      <button
                        type="button"
                        key={contributor.local_id}
                        onClick={() => openDiagnostic(contributor)}
                        className="grid w-full grid-cols-[1fr_auto] gap-3 border-b border-slate-100 px-3 py-2.5 text-left transition hover:bg-indigo-50/60 last:border-0"
                      >
                        <div className="min-w-0">
                          <p className="truncate text-xs font-black text-slate-800">
                            {contributor.local_name}
                          </p>
                          <p className="mt-0.5 text-[10px] text-slate-400">
                            {contributor.impact_share_percent.toFixed(1)}% del impacto · {contributor.peer_days} días comparables
                          </p>
                          <p className="mt-1 inline-flex items-center gap-1 text-[10px] font-black text-indigo-600">
                            Abrir diagnóstico 360° <ChevronRight size={11} />
                          </p>
                        </div>
                        <p className={contributor.contribution >= 0
                          ? 'text-xs font-black text-emerald-600'
                          : 'text-xs font-black text-rose-600'}
                        >
                          {contributor.contribution > 0 ? '+' : ''}
                          {format(contributor.contribution)}
                        </p>
                      </button>
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

      {diagnosticLocalId && (
        <div className="fixed inset-0 z-[60] flex justify-end bg-slate-950/55 backdrop-blur-[3px]">
          <button
            type="button"
            aria-label="Cerrar diagnóstico"
            onClick={closeDiagnostic}
            className="absolute inset-0 cursor-default"
          />
          <aside
            role="dialog"
            aria-modal="true"
            aria-label="Diagnóstico 360 del local"
            className="relative h-full w-full max-w-3xl overflow-y-auto border-l border-slate-200 bg-slate-50 shadow-2xl"
          >
            <header className="sticky top-0 z-10 border-b border-slate-200 bg-white/95 px-5 py-4 backdrop-blur">
              <div className="flex items-start justify-between gap-4">
                <div className="flex items-start gap-3">
                  <button
                    type="button"
                    onClick={closeDiagnostic}
                    className="mt-0.5 rounded-lg border border-slate-200 p-2 text-slate-500 hover:bg-slate-50"
                    aria-label="Volver a la anomalía"
                  >
                    <ArrowLeft size={16} />
                  </button>
                  <div>
                    <p className="text-[10px] font-black uppercase tracking-[0.16em] text-indigo-500">
                      Big Data · Fase 2
                    </p>
                    <h2 className="mt-1 text-xl font-black text-slate-900">
                      Diagnóstico 360°
                    </h2>
                    <p className="mt-0.5 text-xs text-slate-500">
                      {diagnostic?.local.name || 'Construyendo diagnóstico del local…'}
                    </p>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={closeDiagnostic}
                  className="rounded-lg p-2 text-slate-400 hover:bg-slate-100"
                  aria-label="Cerrar"
                >
                  <X size={18} />
                </button>
              </div>
            </header>

            {diagnosticLoading && (
              <div className="grid min-h-[60vh] place-items-center p-8">
                <div className="text-center">
                  <Loader2 className="mx-auto animate-spin text-indigo-600" size={30} />
                  <p className="mt-3 text-sm font-bold text-slate-600">
                    Contrastando historial, pares e importaciones…
                  </p>
                </div>
              </div>
            )}

            {!diagnosticLoading && diagnosticError && (
              <div className="m-5 rounded-2xl border border-rose-200 bg-rose-50 p-5 text-sm text-rose-800">
                <p className="font-black">No fue posible completar el diagnóstico.</p>
                <p className="mt-1">{diagnosticError}</p>
              </div>
            )}

            {!diagnosticLoading && diagnostic && (
              <div className="space-y-4 p-5">
                <section className="rounded-2xl bg-slate-950 p-5 text-white shadow-sm">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <p className="text-xs font-black text-white">{diagnostic.local.name}</p>
                      <p className="mt-1 text-[11px] text-slate-400">
                        {diagnostic.local.category_name
                          || diagnostic.local.business_type
                          || 'Sin categoría homologada'}
                        {diagnostic.local.category_source === 'RUBRO_FALLBACK'
                          ? ' (rubro provisional)'
                          : ''}
                        {' · '}
                        {formatDate(diagnostic.period.target_date, {
                          day: 'numeric',
                          month: 'long',
                          year: 'numeric',
                        })}
                      </p>
                    </div>
                    <span className={`rounded-full border px-3 py-1 text-[10px] font-black ${
                      diagnosticCopy[diagnostic.diagnosis.classification].classes
                    }`}>
                      {diagnosticCopy[diagnostic.diagnosis.classification].label}
                    </span>
                  </div>
                  <div className="mt-5 grid grid-cols-2 gap-2 lg:grid-cols-4">
                    {[
                      ['Venta observada', format(diagnostic.headline.observed_sales)],
                      ['Referencia', format(diagnostic.headline.expected_sales)],
                      [
                        'Desviación',
                        diagnostic.headline.deviation_percent == null
                          ? 'Sin base'
                          : `${diagnostic.headline.deviation_percent > 0 ? '+' : ''}${diagnostic.headline.deviation_percent.toFixed(1)}%`,
                      ],
                      [
                        'Posición categoría',
                        diagnostic.benchmark.status === 'OK'
                          ? `${diagnostic.benchmark.rank}/${diagnostic.benchmark.comparable_stores}`
                          : 'Sin muestra',
                      ],
                    ].map(([label, value]) => (
                      <div key={label} className="rounded-xl bg-white/10 p-3">
                        <p className="text-[9px] font-bold uppercase text-slate-400">{label}</p>
                        <p className="mt-1 truncate text-sm font-black">{value}</p>
                      </div>
                    ))}
                  </div>
                </section>

                <section className="rounded-2xl border border-indigo-100 bg-white p-5 shadow-sm">
                  <div className="flex items-center justify-between gap-3">
                    <p className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.14em] text-indigo-500">
                      <BadgeCheck size={15} /> Conclusión analítica
                    </p>
                    <span className="text-[10px] font-bold text-slate-400">
                      Confianza {(diagnostic.diagnosis.confidence * 100).toFixed(0)}%
                    </span>
                  </div>
                  <p className="mt-3 text-base font-black leading-6 text-slate-900">
                    {diagnostic.diagnosis.summary}
                  </p>
                  <div className="mt-4 grid gap-2 md:grid-cols-2">
                    {diagnostic.diagnosis.factors.map((factor) => (
                      <div
                        key={factor.type}
                        className={`rounded-xl border p-3 ${toneClasses[factor.tone]}`}
                      >
                        <p className="text-[10px] font-black uppercase">{factor.label}</p>
                        <p className="mt-1 text-xs leading-5">{factor.detail}</p>
                      </div>
                    ))}
                  </div>
                  <div className="mt-4 rounded-xl bg-indigo-50 p-3">
                    <p className="text-[10px] font-black uppercase text-indigo-600">Siguiente acción</p>
                    <p className="mt-1 text-sm leading-6 text-indigo-950">
                      {diagnostic.diagnosis.recommendation}
                    </p>
                  </div>
                </section>

                <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <p className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.14em] text-slate-500">
                      <Activity size={15} /> Evolución del local
                    </p>
                    <span className="text-[10px] font-bold text-slate-400">
                      {diagnostic.headline.peer_days} días comparables
                    </span>
                  </div>
                  <div className="mt-4 h-56">
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={diagnostic.timeline} margin={{ top: 5, right: 8, left: -15, bottom: 0 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                        <XAxis
                          dataKey="date"
                          tick={{ fontSize: 9, fill: '#94a3b8' }}
                          tickFormatter={(value) => formatDate(value, { day: '2-digit', month: '2-digit' })}
                          minTickGap={24}
                        />
                        <YAxis tick={{ fontSize: 9, fill: '#94a3b8' }} tickFormatter={(value) => compactNumber.format(value)} />
                        <Tooltip
                          labelFormatter={(value) => formatDate(String(value), {
                            day: 'numeric',
                            month: 'long',
                          })}
                          formatter={(value: any, name: string) => [
                            format(Number(value)),
                            name === 'sales_net' ? 'Venta' : 'Referencia',
                          ]}
                        />
                        <Line type="monotone" dataKey="expected_sales" stroke="#94a3b8" strokeDasharray="5 4" dot={false} strokeWidth={2} />
                        <Line type="monotone" dataKey="sales_net" stroke="#4f46e5" dot={false} strokeWidth={2.5} />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                </section>

                <section className="grid gap-4 lg:grid-cols-2">
                  <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                    <p className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.14em] text-slate-500">
                      <BarChart3 size={15} /> Comparación de categoría
                    </p>
                    {diagnostic.benchmark.category_source === 'RUBRO_FALLBACK' && (
                      <p className="mt-2 text-[10px] font-bold text-amber-600">
                        Referencia provisional por rubro; pendiente de homologación comercial.
                      </p>
                    )}
                    {diagnostic.benchmark.status === 'OK' ? (
                      <>
                        <div className="mt-4 grid grid-cols-2 gap-2">
                          <div className="rounded-xl bg-indigo-50 p-3">
                            <p className="text-[9px] font-bold uppercase text-indigo-500">Percentil</p>
                            <p className="mt-1 text-xl font-black text-indigo-950">
                              {diagnostic.benchmark.percentile?.toFixed(0)}
                            </p>
                          </div>
                          <div className="rounded-xl bg-slate-50 p-3">
                            <p className="text-[9px] font-bold uppercase text-slate-500">Vs. mediana</p>
                            <p className={`mt-1 text-xl font-black ${
                              Number(diagnostic.benchmark.difference_vs_median_percent) >= 0
                                ? 'text-emerald-600'
                                : 'text-rose-600'
                            }`}>
                              {Number(diagnostic.benchmark.difference_vs_median_percent) > 0 ? '+' : ''}
                              {diagnostic.benchmark.difference_vs_median_percent?.toFixed(1)}%
                            </p>
                          </div>
                        </div>
                        <div className="mt-4 space-y-2">
                          {(diagnostic.benchmark.leaders || []).map((leader, index) => (
                            <div key={leader.local_id} className="flex items-center justify-between gap-3 text-xs">
                              <span className="min-w-0 truncate font-bold text-slate-600">
                                {index + 1}. {leader.local_name}
                              </span>
                              <span className="shrink-0 font-black text-slate-800">{format(leader.sales_net)}</span>
                            </div>
                          ))}
                        </div>
                      </>
                    ) : (
                      <p className="mt-4 text-sm leading-6 text-slate-500">
                        {diagnostic.benchmark.reason}
                      </p>
                    )}
                  </div>

                  <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                    <p className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.14em] text-slate-500">
                      <Database size={15} /> Cobertura
                    </p>
                    <p className="mt-4 text-3xl font-black text-slate-900">
                      {diagnostic.evidence.coverage.percent.toFixed(1)}%
                    </p>
                    <p className="mt-1 text-xs text-slate-500">
                      {diagnostic.evidence.coverage.days_with_data} de{' '}
                      {diagnostic.evidence.coverage.expected_days} días con datos
                    </p>
                    <div className="mt-4 h-2 overflow-hidden rounded-full bg-slate-100">
                      <div
                        className="h-full rounded-full bg-indigo-500"
                        style={{ width: `${Math.min(diagnostic.evidence.coverage.percent, 100)}%` }}
                      />
                    </div>
                    <p className="mt-3 text-xs font-bold text-slate-600">
                      Fecha analizada: {diagnostic.evidence.coverage.target_status}
                    </p>
                  </div>
                </section>

                <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <p className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.14em] text-slate-500">
                      <FileWarning size={15} /> Evidencia de importación
                    </p>
                    <span className={diagnostic.evidence.related_import_issue
                      ? 'rounded-full bg-rose-50 px-2 py-1 text-[10px] font-black text-rose-600'
                      : 'rounded-full bg-emerald-50 px-2 py-1 text-[10px] font-black text-emerald-600'}
                    >
                      {diagnostic.evidence.related_import_issue ? 'Requiere revisión' : 'Sin fallos relacionados'}
                    </span>
                  </div>
                  <div className="mt-4 overflow-hidden rounded-xl border border-slate-100">
                    {diagnostic.evidence.imports.length ? (
                      diagnostic.evidence.imports.map((item, index) => (
                        <div
                          key={`${item.date}-${item.filename}-${index}`}
                          className="grid gap-2 border-b border-slate-100 p-3 last:border-0 md:grid-cols-[1fr_auto]"
                        >
                          <div className="min-w-0">
                            <p className="truncate text-xs font-black text-slate-800">{item.filename}</p>
                            <p className="mt-1 text-[10px] text-slate-400">
                              {item.channel || 'Canal no identificado'} · {item.records_processed} registros · {item.error_count} errores
                            </p>
                            {item.message && <p className="mt-1 line-clamp-2 text-[10px] text-slate-500">{item.message}</p>}
                          </div>
                          <div className="flex items-start gap-2">
                            <span className="rounded-full bg-slate-100 px-2 py-1 text-[9px] font-bold text-slate-500">
                              {item.match === 'FILE_DATE'
                                ? 'Fecha en archivo'
                                : item.match === 'PROCESSING_DATE'
                                ? 'Fecha cercana'
                                : 'Dentro del período'}
                            </span>
                            <span className={item.has_issue
                              ? 'rounded-full bg-rose-50 px-2 py-1 text-[9px] font-black text-rose-600'
                              : 'rounded-full bg-emerald-50 px-2 py-1 text-[9px] font-black text-emerald-600'}
                            >
                              {item.status}
                            </span>
                          </div>
                        </div>
                      ))
                    ) : (
                      <p className="p-4 text-xs text-slate-500">
                        No hay logs de importación para este local dentro del período.
                      </p>
                    )}
                  </div>
                </section>

                <p className="px-1 text-[10px] leading-5 text-slate-400">
                  {diagnostic.methodology} Versión {diagnostic.version}.
                </p>
              </div>
            )}
          </aside>
        </div>
      )}

      {showScenarioForm && (
        <div className="fixed inset-0 z-[60] overflow-y-auto bg-slate-950/60 p-4 backdrop-blur-sm">
          <form
            onSubmit={simulateScenario}
            className="mx-auto my-4 w-full max-w-5xl overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-2xl"
          >
            <div className="flex items-start justify-between gap-4 border-b border-slate-100 px-5 py-4">
              <div>
                <p className="flex items-center gap-2 text-xs font-black uppercase tracking-[0.14em] text-indigo-600">
                  <Target size={16} /> Big Data · Fase 3B
                </p>
                <h3 className="mt-1 text-xl font-black text-slate-900">
                  Simular una decisión comercial
                </h3>
                <p className="mt-1 text-xs leading-5 text-slate-500">
                  Compara un supuesto explícito contra la predicción base antes de aprobar recursos o comprometer resultados.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setShowScenarioForm(false)}
                className="rounded-xl border border-slate-200 p-2 text-slate-400 hover:text-slate-700"
                aria-label="Cerrar simulador"
              >
                <X size={18} />
              </button>
            </div>

            <div className="grid lg:grid-cols-[1fr_0.9fr]">
              <div className="border-b border-slate-100 p-5 lg:border-b-0 lg:border-r">
                <div className="grid gap-3 sm:grid-cols-2">
                  <label className="sm:col-span-2">
                    <span className="text-xs font-bold text-slate-600">Nombre del escenario</span>
                    <input
                      required
                      minLength={2}
                      maxLength={160}
                      value={scenarioForm.name}
                      onChange={(event) => updateScenarioForm({ name: event.target.value })}
                      placeholder="Ej. Semana de moda agosto"
                      className="mt-1.5 w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm outline-none focus:border-indigo-400"
                    />
                  </label>
                  <label>
                    <span className="text-xs font-bold text-slate-600">Tipo</span>
                    <select
                      value={scenarioForm.scenario_type}
                      onChange={(event) => updateScenarioForm({
                        scenario_type: event.target.value as BigDataScenarioType,
                      })}
                      className="mt-1.5 w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm outline-none focus:border-indigo-400"
                    >
                      {SCENARIO_TYPES.map((option) => (
                        <option key={option.value} value={option.value}>{option.label}</option>
                      ))}
                    </select>
                  </label>
                  <label>
                    <span className="text-xs font-bold text-slate-600">
                      Supuesto de impacto
                    </span>
                    <div className="relative mt-1.5">
                      <input
                        required
                        type="number"
                        min={-60}
                        max={80}
                        step={0.5}
                        value={scenarioForm.adjustment_percent}
                        onChange={(event) => updateScenarioForm({
                          adjustment_percent: Number(event.target.value),
                        })}
                        className="w-full rounded-xl border border-slate-200 px-3 py-2.5 pr-8 text-sm outline-none focus:border-indigo-400"
                      />
                      <span className="absolute right-3 top-2.5 text-sm font-black text-slate-400">%</span>
                    </div>
                  </label>
                  <label>
                    <span className="text-xs font-bold text-slate-600">Desde</span>
                    <input
                      required
                      type="date"
                      value={scenarioForm.start_date}
                      min={initialScenarioForm().start_date}
                      max={scenarioForm.end_date}
                      onChange={(event) => updateScenarioForm({
                        start_date: event.target.value,
                        end_date: event.target.value > scenarioForm.end_date
                          ? event.target.value
                          : scenarioForm.end_date,
                      })}
                      className="mt-1.5 w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm outline-none focus:border-indigo-400"
                    />
                  </label>
                  <label>
                    <span className="text-xs font-bold text-slate-600">Hasta</span>
                    <input
                      required
                      type="date"
                      value={scenarioForm.end_date}
                      min={scenarioForm.start_date}
                      onChange={(event) => updateScenarioForm({ end_date: event.target.value })}
                      className="mt-1.5 w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm outline-none focus:border-indigo-400"
                    />
                  </label>
                  <label className="sm:col-span-2">
                    <span className="text-xs font-bold text-slate-600">Supuestos y notas</span>
                    <textarea
                      rows={2}
                      maxLength={2000}
                      value={scenarioForm.notes || ''}
                      onChange={(event) => updateScenarioForm({ notes: event.target.value })}
                      placeholder="Presupuesto, alcance, locales participantes u otra condición necesaria."
                      className="mt-1.5 w-full resize-none rounded-xl border border-slate-200 px-3 py-2.5 text-sm outline-none focus:border-indigo-400"
                    />
                  </label>
                </div>

                {(isAdmin || isTic) && (
                  <div className="mt-5 border-t border-slate-100 pt-4">
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <p className="flex items-center gap-2 text-xs font-black text-slate-700">
                          <ClipboardList size={15} /> Plan de acción inicial
                        </p>
                        <p className="mt-0.5 text-[10px] text-slate-400">
                          Opcional. Define responsables y fechas antes de aprobar.
                        </p>
                      </div>
                      <button
                        type="button"
                        onClick={() => setScenarioActions((current) => [
                          ...current,
                          { title: '', owner_name: '', due_date: '', notes: '' },
                        ])}
                        disabled={scenarioActions.length >= 20}
                        className="inline-flex items-center gap-1 rounded-lg border border-indigo-200 px-2.5 py-1.5 text-[10px] font-black text-indigo-600 disabled:opacity-40"
                      >
                        <Plus size={12} /> Acción
                      </button>
                    </div>
                    <div className="mt-3 max-h-52 space-y-2 overflow-y-auto pr-1">
                      {scenarioActions.map((action, index) => (
                        <div key={index} className="grid gap-2 rounded-xl bg-slate-50 p-2.5 sm:grid-cols-[1.3fr_0.8fr_0.75fr_auto]">
                          <input
                            maxLength={200}
                            value={action.title}
                            onChange={(event) => setScenarioActions((current) => current.map(
                              (item, position) => position === index
                                ? { ...item, title: event.target.value }
                                : item,
                            ))}
                            placeholder="Acción a ejecutar"
                            className="rounded-lg border border-slate-200 bg-white px-2.5 py-2 text-xs outline-none focus:border-indigo-400"
                          />
                          <input
                            maxLength={120}
                            value={action.owner_name}
                            onChange={(event) => setScenarioActions((current) => current.map(
                              (item, position) => position === index
                                ? { ...item, owner_name: event.target.value }
                                : item,
                            ))}
                            placeholder="Responsable"
                            className="rounded-lg border border-slate-200 bg-white px-2.5 py-2 text-xs outline-none focus:border-indigo-400"
                          />
                          <input
                            type="date"
                            value={action.due_date}
                            onChange={(event) => setScenarioActions((current) => current.map(
                              (item, position) => position === index
                                ? { ...item, due_date: event.target.value }
                                : item,
                            ))}
                            className="rounded-lg border border-slate-200 bg-white px-2 py-2 text-[10px] outline-none focus:border-indigo-400"
                          />
                          <button
                            type="button"
                            onClick={() => setScenarioActions((current) => (
                              current.length === 1
                                ? [{ title: '', owner_name: '', due_date: '', notes: '' }]
                                : current.filter((_, position) => position !== index)
                            ))}
                            className="rounded-lg p-2 text-slate-300 hover:bg-rose-50 hover:text-rose-500"
                            aria-label={`Eliminar acción ${index + 1}`}
                          >
                            <Trash2 size={14} />
                          </button>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              <div className="bg-slate-50/70 p-5">
                <p className="text-xs font-black uppercase tracking-[0.14em] text-indigo-600">
                  Comparación calculada
                </p>
                {!scenarioSimulation && !scenarioSimulating && (
                  <div className="mt-4 grid min-h-72 place-items-center rounded-2xl border border-dashed border-slate-200 bg-white p-6 text-center">
                    <div>
                      <Play size={28} className="mx-auto text-indigo-300" />
                      <p className="mt-3 text-sm font-black text-slate-700">
                        Define el supuesto y ejecuta la simulación
                      </p>
                      <p className="mt-1 text-xs leading-5 text-slate-500">
                        La base proviene de Fase 3A; este cálculo no modifica el calendario ni las ventas.
                      </p>
                    </div>
                  </div>
                )}
                {scenarioSimulating && (
                  <div className="mt-4 grid min-h-72 place-items-center rounded-2xl bg-white">
                    <div className="text-center text-sm font-bold text-slate-500">
                      <Loader2 size={24} className="mx-auto animate-spin text-indigo-500" />
                      <p className="mt-3">Comparando contra la predicción base…</p>
                    </div>
                  </div>
                )}
                {scenarioSimulation && (
                  <div className="mt-4 space-y-3">
                    <div className="grid grid-cols-2 gap-2">
                      <article className="rounded-xl border border-slate-200 bg-white p-3">
                        <p className="text-[9px] font-black uppercase text-slate-400">Predicción base</p>
                        <p className="mt-1 text-lg font-black text-slate-900">
                          {format(scenarioSimulation.result.baseline_sales)}
                        </p>
                      </article>
                      <article className="rounded-xl bg-slate-950 p-3 text-white">
                        <p className="text-[9px] font-black uppercase text-slate-400">Con escenario</p>
                        <p className="mt-1 text-lg font-black">
                          {format(scenarioSimulation.result.scenario_sales)}
                        </p>
                      </article>
                    </div>
                    <article className={`rounded-xl border p-3 ${
                      scenarioSimulation.result.incremental_sales >= 0
                        ? 'border-emerald-200 bg-emerald-50'
                        : 'border-rose-200 bg-rose-50'
                    }`}>
                      <p className="text-[9px] font-black uppercase text-slate-500">Impacto potencial</p>
                      <p className={`mt-1 text-2xl font-black ${
                        scenarioSimulation.result.incremental_sales >= 0
                          ? 'text-emerald-700'
                          : 'text-rose-700'
                      }`}>
                        {scenarioSimulation.result.incremental_sales > 0 ? '+' : ''}
                        {format(scenarioSimulation.result.incremental_sales)}
                      </p>
                      <p className="mt-1 text-[10px] text-slate-500">
                        {scenarioSimulation.period.affected_days} día(s) · rango{' '}
                        {format(scenarioSimulation.result.lower_bound)} —{' '}
                        {format(scenarioSimulation.result.upper_bound)}
                      </p>
                    </article>
                    {scenarioSimulation.assumption.historical_reference?.applied && (
                      <div className="rounded-xl border border-indigo-100 bg-indigo-50 p-3 text-xs leading-5 text-indigo-900">
                        Referencia histórica: {scenarioSimulation.assumption.historical_reference.observations}{' '}
                        observaciones comparables con ajuste mediano de{' '}
                        {scenarioSimulation.assumption.historical_reference.adjustment_percent > 0 ? '+' : ''}
                        {scenarioSimulation.assumption.historical_reference.adjustment_percent.toFixed(1)}%.
                      </div>
                    )}
                    {scenarioSimulation.warnings.map((warning) => (
                      <div key={warning} className="flex gap-2 rounded-xl border border-amber-100 bg-amber-50 p-3 text-[10px] leading-4 text-amber-800">
                        <AlertTriangle size={14} className="mt-0.5 shrink-0" />
                        {warning}
                      </div>
                    ))}
                    <p className="text-[9px] leading-4 text-slate-400">
                      {scenarioSimulation.methodology}
                    </p>
                  </div>
                )}

                {scenarioFormError && (
                  <p className="mt-3 rounded-xl border border-rose-100 bg-rose-50 p-3 text-xs leading-5 text-rose-700">
                    {scenarioFormError}
                  </p>
                )}
              </div>
            </div>

            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 px-5 py-4">
              <p className="text-[10px] text-slate-400">
                {(isAdmin || isTic)
                  ? 'Guardar crea un borrador; aprobarlo requiere una acción separada.'
                  : 'Puedes simular. Guardar y aprobar requiere rol administrador o IT.'}
              </p>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => setShowScenarioForm(false)}
                  className="rounded-xl border border-slate-200 px-4 py-2.5 text-sm font-bold text-slate-600"
                >
                  Cerrar
                </button>
                <button
                  type="submit"
                  disabled={scenarioSimulating || scenarioSaving}
                  className="inline-flex items-center gap-2 rounded-xl border border-indigo-200 bg-white px-4 py-2.5 text-sm font-black text-indigo-700 disabled:opacity-50"
                >
                  {scenarioSimulating
                    ? <Loader2 size={16} className="animate-spin" />
                    : <Play size={16} />}
                  Simular
                </button>
                {(isAdmin || isTic) && (
                  <button
                    type="button"
                    disabled={!scenarioSimulation || scenarioSaving || scenarioSimulating}
                    onClick={saveScenario}
                    className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-4 py-2.5 text-sm font-black text-white disabled:opacity-40"
                  >
                    {scenarioSaving
                      ? <Loader2 size={16} className="animate-spin" />
                      : <Save size={16} />}
                    Guardar borrador
                  </button>
                )}
              </div>
            </div>
          </form>
        </div>
      )}

      {showAnomalyReviewForm && anomalyReviewTarget && (
        <div className="fixed inset-0 z-[60] grid place-items-center overflow-y-auto bg-slate-950/55 p-4 backdrop-blur-sm">
          <form
            onSubmit={saveAnomalyReview}
            className="my-6 w-full max-w-2xl rounded-3xl border border-slate-200 bg-white p-6 shadow-2xl"
          >
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-xs font-black uppercase tracking-[0.14em] text-indigo-600">
                  Investigación de anomalía
                </p>
                <h3 className="mt-1 text-xl font-black capitalize text-slate-900">
                  {formatDate(anomalyReviewTarget.date, {
                    weekday: 'long',
                    day: 'numeric',
                    month: 'long',
                    year: 'numeric',
                  })}
                </h3>
                <p className="mt-1 text-xs leading-5 text-slate-500">
                  Documenta la conclusión sin depender de una actividad del calendario.
                </p>
              </div>
              <button
                type="button"
                onClick={() => {
                  setShowAnomalyReviewForm(false);
                  setAnomalyReviewTarget(null);
                }}
                className="rounded-xl border border-slate-200 p-2 text-slate-400 hover:text-slate-700"
                aria-label="Cerrar"
              >
                <X size={18} />
              </button>
            </div>

            <div className="mt-5 grid gap-4 sm:grid-cols-2">
              <label>
                <span className="text-xs font-bold text-slate-600">Estado</span>
                <select
                  value={anomalyReviewForm.status}
                  onChange={(event) => setAnomalyReviewForm({
                    ...anomalyReviewForm,
                    status: event.target.value as BigDataAnomalyReviewStatus,
                  })}
                  className="mt-1.5 w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm outline-none focus:border-indigo-400"
                >
                  <option value="IN_REVIEW">En revisión</option>
                  <option value="EXPLAINED">Explicada</option>
                  <option value="DISMISSED">Descartada</option>
                </select>
              </label>
              <label>
                <span className="text-xs font-bold text-slate-600">Causa</span>
                <select
                  value={anomalyReviewForm.cause_type}
                  onChange={(event) => {
                    const cause = event.target.value as BigDataAnomalyCauseType;
                    setAnomalyReviewForm({
                      ...anomalyReviewForm,
                      cause_type: cause,
                      add_to_calendar: cause === 'COMMERCIAL_EVENT'
                        ? anomalyReviewForm.add_to_calendar
                        : false,
                    });
                  }}
                  className="mt-1.5 w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm outline-none focus:border-indigo-400"
                >
                  {ANOMALY_CAUSES.map((cause) => (
                    <option key={cause.value} value={cause.value}>{cause.label}</option>
                  ))}
                </select>
              </label>
              <label className="sm:col-span-2">
                <span className="text-xs font-bold text-slate-600">Explicación</span>
                <textarea
                  required
                  minLength={5}
                  maxLength={2000}
                  rows={4}
                  value={anomalyReviewForm.explanation}
                  onChange={(event) => setAnomalyReviewForm({
                    ...anomalyReviewForm,
                    explanation: event.target.value,
                  })}
                  placeholder="Describe qué ocurrió, qué se verificó y cuál es la conclusión."
                  className="mt-1.5 w-full resize-y rounded-xl border border-slate-200 px-3 py-2.5 text-sm outline-none focus:border-indigo-400"
                />
              </label>
              <label>
                <span className="text-xs font-bold text-slate-600">Evidencia (opcional)</span>
                <textarea
                  minLength={2}
                  maxLength={2000}
                  rows={3}
                  value={anomalyReviewForm.evidence}
                  onChange={(event) => setAnomalyReviewForm({
                    ...anomalyReviewForm,
                    evidence: event.target.value,
                  })}
                  placeholder="Archivo, ticket, llamada o validación realizada."
                  className="mt-1.5 w-full resize-y rounded-xl border border-slate-200 px-3 py-2.5 text-sm outline-none focus:border-indigo-400"
                />
              </label>
              <label>
                <span className="text-xs font-bold text-slate-600">Responsable (opcional)</span>
                <input
                  minLength={2}
                  maxLength={120}
                  value={anomalyReviewForm.owner_name}
                  onChange={(event) => setAnomalyReviewForm({
                    ...anomalyReviewForm,
                    owner_name: event.target.value,
                  })}
                  placeholder="Nombre o equipo responsable"
                  className="mt-1.5 w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm outline-none focus:border-indigo-400"
                />
              </label>
            </div>

            {anomalyReviewForm.cause_type === 'COMMERCIAL_EVENT' && (
              <div className="mt-4 rounded-2xl border border-indigo-100 bg-indigo-50/60 p-4">
                <label className="flex cursor-pointer items-start gap-3">
                  <input
                    type="checkbox"
                    checked={anomalyReviewForm.add_to_calendar}
                    onChange={(event) => setAnomalyReviewForm({
                      ...anomalyReviewForm,
                      add_to_calendar: event.target.checked,
                    })}
                    className="mt-0.5 h-4 w-4 rounded border-slate-300 text-indigo-600"
                  />
                  <span>
                    <span className="block text-xs font-black text-indigo-900">
                      Agregar también al calendario comercial
                    </span>
                    <span className="mt-0.5 block text-[10px] leading-4 text-indigo-700">
                      Úsalo si fue una promoción o actividad que debe reconocerse en futuros análisis.
                    </span>
                  </span>
                </label>
                {anomalyReviewForm.add_to_calendar && (
                  <div className="mt-4 grid gap-3 sm:grid-cols-2">
                    <label>
                      <span className="text-xs font-bold text-slate-600">Nombre del evento</span>
                      <input
                        required
                        minLength={2}
                        maxLength={160}
                        value={anomalyReviewForm.calendar_name}
                        onChange={(event) => setAnomalyReviewForm({
                          ...anomalyReviewForm,
                          calendar_name: event.target.value,
                        })}
                        placeholder="Ej. Actividad de temporada"
                        className="mt-1.5 w-full rounded-xl border border-indigo-100 bg-white px-3 py-2.5 text-sm outline-none focus:border-indigo-400"
                      />
                    </label>
                    <label>
                      <span className="text-xs font-bold text-slate-600">Tipo</span>
                      <select
                        value={anomalyReviewForm.calendar_event_type}
                        onChange={(event) => setAnomalyReviewForm({
                          ...anomalyReviewForm,
                          calendar_event_type: event.target.value as BigDataCalendarEventType,
                        })}
                        className="mt-1.5 w-full rounded-xl border border-indigo-100 bg-white px-3 py-2.5 text-sm outline-none focus:border-indigo-400"
                      >
                        {EVENT_TYPES.map((option) => (
                          <option key={option.value} value={option.value}>{option.label}</option>
                        ))}
                      </select>
                    </label>
                  </div>
                )}
              </div>
            )}

            {anomalyReviewError && (
              <p className="mt-4 rounded-xl border border-rose-100 bg-rose-50 p-3 text-xs text-rose-700">
                {anomalyReviewError}
              </p>
            )}

            <div className="mt-5 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => {
                  setShowAnomalyReviewForm(false);
                  setAnomalyReviewTarget(null);
                }}
                className="rounded-xl border border-slate-200 px-4 py-2.5 text-sm font-bold text-slate-600"
              >
                Cancelar
              </button>
              <button
                type="submit"
                disabled={anomalyReviewSaving}
                className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-4 py-2.5 text-sm font-black text-white disabled:opacity-50"
              >
                {anomalyReviewSaving
                  ? <Loader2 size={16} className="animate-spin" />
                  : <Save size={16} />}
                {anomalyReviewSaving ? 'Guardando…' : 'Guardar investigación'}
              </button>
            </div>
          </form>
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
