import React, { useEffect, useMemo, useState } from 'react';
import { useAuth } from '../context/AuthProvider';
import { ApiService } from '../api';
import { LoadLogEntry } from '../types';
import {
  describeLoadLog,
  getLoadLogErrorCount,
  getLoadLogProcessedCount,
  getLoadLogStatus,
} from '../utils/loadLogMessages';
import {
  AlertCircle,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Clock,
  FileText,
  RefreshCw,
  Search,
  Store,
  XCircle,
} from 'lucide-react';

type MonitorStatusFilter = 'all' | 'exito' | 'parcial' | 'error';
const LOAD_MONITOR_PAGE_SIZE = 20;

const StatCard = ({ title, count, icon: Icon, color, bgColor }: any) => (
  <div className="bg-white p-4 rounded-2xl border border-slate-100 shadow-sm flex items-center gap-4">
    <div className={`p-3 rounded-xl ${bgColor} ${color}`}>
      <Icon size={24} />
    </div>
    <div>
      <p className="text-slate-500 text-sm font-medium">{title}</p>
      <h3 className="text-xl font-bold text-slate-900">{count}</h3>
    </div>
  </div>
);

const safeDate = (value?: string | null): Date | null => {
  if (!value) return null;
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
};

const formatDate = (value?: string | null): string => {
  const parsed = safeDate(value);
  return parsed ? parsed.toLocaleDateString() : 'Sin fecha';
};

const toIsoDate = (value?: string | null): string => {
  const parsed = safeDate(value);
  return parsed ? parsed.toISOString().split('T')[0] : '';
};

const formatDateTime = (value?: string | null): string => {
  const parsed = safeDate(value);
  return parsed ? parsed.toLocaleString() : 'Sin fecha';
};

const truncateMiddle = (value?: string | null, left = 8, right = 6): string => {
  const text = String(value || '').trim();
  if (!text) return '—';
  if (text.length <= left + right + 3) return text;
  return `${text.slice(0, left)}...${text.slice(-right)}`;
};

const getErrorCount = getLoadLogErrorCount;
const getProcessedCount = getLoadLogProcessedCount;
const getNormalizedStatus = getLoadLogStatus;

const getDisplayChannel = (log: LoadLogEntry | null): string | null => {
  const raw = String(log?.canal || log?.metadata?.canal || '').trim();
  return raw || null;
};

const getDisplayLocalName = (log: LoadLogEntry | null): string => {
  if (!log) return 'Local desconocido';
  const direct = String(log.local_nombre || '').trim();
  if (direct) return direct;
  return truncateMiddle(log.local_id || '', 8, 4);
};

const getDisplayFileName = (log: LoadLogEntry | null): string => {
  const archivo = String(log?.archivo || '').trim();
  if (archivo && archivo.toUpperCase() !== 'N/A') return archivo;
  return 'Sin archivo';
};

const getReadableMessage = (log: LoadLogEntry | null): string => {
  return describeLoadLog(log).summary;
};

const getStatusBadge = (log: LoadLogEntry) => {
  const status = getNormalizedStatus(log);
  if (status === 'exito') {
    return <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-green-50 text-green-700 text-xs font-bold"><CheckCircle2 size={12} /> Éxito</span>;
  }
  if (status === 'parcial') {
    return <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-amber-50 text-amber-700 text-xs font-bold"><AlertCircle size={12} /> Parcial</span>;
  }
  if (status === 'no_encontrado') {
    return <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-amber-50 text-amber-700 text-xs font-bold"><AlertCircle size={12} /> No encontrado</span>;
  }
  return <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-red-50 text-red-700 text-xs font-bold"><XCircle size={12} /> Fallido</span>;
};

const SummaryTile = ({ label, value, subtle }: { label: string; value: React.ReactNode; subtle?: string }) => (
  <div className="p-4 rounded-2xl bg-slate-50 border border-slate-100">
    <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1">{label}</p>
    <div className="text-sm font-bold text-slate-700 break-words">{value}</div>
    {subtle && <div className="text-xs text-slate-500 mt-1 break-all">{subtle}</div>}
  </div>
);

export const LoadMonitor: React.FC = () => {
  const { currentMall, session } = useAuth();
  const [logs, setLogs] = useState<LoadLogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedLog, setSelectedLog] = useState<LoadLogEntry | null>(null);
  const [dateRange, setDateRange] = useState({ start: '', end: '' });
  const [statusFilter, setStatusFilter] = useState<MonitorStatusFilter>('all');
  const [currentPage, setCurrentPage] = useState(1);

  const loadData = async () => {
    if (!currentMall?.id) return;
    setLoading(true);
    try {
      const data = await ApiService.getLoadLogs(currentMall.id, session?.access_token);
      setLogs(data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const handleClearLogs = async () => {
    if (!currentMall?.id) {
      alert('No hay mall seleccionado.');
      return;
    }
    if (!session?.access_token) {
      alert('Sesion invalida. Inicia sesion nuevamente para continuar.');
      return;
    }

    if (window.confirm(`Estas seguro de que deseas limpiar el historial de cargas de ${currentMall.nombre}? Esta accion no se puede deshacer.`)) {
      try {
        await ApiService.clearLoadLogs(currentMall.id, session.access_token);
        await loadData();
        alert('Historial limpiado correctamente.');
      } catch {
        alert('Error al limpiar el historial.');
      }
    }
  };

  useEffect(() => {
    if (!currentMall) return;
    loadData();
    const interval = setInterval(loadData, 30000);
    return () => clearInterval(interval);
  }, [currentMall]);

  const stats = useMemo(() => ({
    exito: logs.filter((log) => getNormalizedStatus(log) === 'exito').length,
    parcial: logs.filter((log) => getNormalizedStatus(log) === 'parcial').length,
    error: logs.filter((log) => getNormalizedStatus(log) === 'error').length,
    total: logs.length,
  }), [logs]);

  const filteredLogs = useMemo(() => {
    const result: Array<LoadLogEntry & { repeatCount: number }> = [];
    let lastLog: (LoadLogEntry & { repeatCount: number }) | null = null;

    const rawFiltered = logs.filter((log) => {
      const searchHaystack = [
        getDisplayLocalName(log),
        getDisplayChannel(log) || '',
        getDisplayFileName(log),
        log.batch_id || '',
        getReadableMessage(log),
      ].join(' ').toLowerCase();

      const matchesSearch = searchHaystack.includes(searchTerm.toLowerCase());
      const logDate = toIsoDate(log.fecha_hora);
      const matchesStart = !dateRange.start || logDate >= dateRange.start;
      const matchesEnd = !dateRange.end || logDate <= dateRange.end;

      const normalizedStatus = getNormalizedStatus(log);
      let matchesStatus = true;
      if (statusFilter === 'exito') matchesStatus = normalizedStatus === 'exito';
      else if (statusFilter === 'parcial') matchesStatus = normalizedStatus === 'parcial';
      else if (statusFilter === 'error') matchesStatus = normalizedStatus === 'error';

      return matchesSearch && matchesStart && matchesEnd && matchesStatus;
    });

    for (const log of rawFiltered) {
      const repetitive = lastLog
        && getDisplayLocalName(lastLog) === getDisplayLocalName(log)
        && getReadableMessage(lastLog) === getReadableMessage(log)
        && getNormalizedStatus(lastLog) === getNormalizedStatus(log)
        && formatDate(lastLog.fecha_hora) === formatDate(log.fecha_hora);

      if (repetitive && lastLog) {
        lastLog.repeatCount += 1;
        continue;
      }

      const current = { ...log, repeatCount: 1 };
      result.push(current);
      lastLog = current;
    }

    return result;
  }, [logs, searchTerm, dateRange, statusFilter]);

  useEffect(() => {
    setCurrentPage(1);
  }, [searchTerm, dateRange.start, dateRange.end, statusFilter, currentMall?.id]);

  const totalPages = Math.max(1, Math.ceil(filteredLogs.length / LOAD_MONITOR_PAGE_SIZE));
  const safeCurrentPage = Math.min(Math.max(currentPage, 1), totalPages);
  const pageStart = (safeCurrentPage - 1) * LOAD_MONITOR_PAGE_SIZE;
  const paginatedLogs = filteredLogs.slice(pageStart, pageStart + LOAD_MONITOR_PAGE_SIZE);
  const pageEnd = filteredLogs.length > 0 ? pageStart + paginatedLogs.length : 0;

  useEffect(() => {
    if (currentPage !== safeCurrentPage) {
      setCurrentPage(safeCurrentPage);
    }
  }, [currentPage, safeCurrentPage]);

  const selectedLogErrors = Array.isArray(selectedLog?.detalles) ? selectedLog.detalles : [];
  const selectedLogStatus = getNormalizedStatus(selectedLog);
  const hasLineErrors = selectedLogErrors.length > 0;
  const isExecutionFailure = selectedLogStatus === 'error' && !hasLineErrors;
  const selectedOperationalMessage = describeLoadLog(selectedLog);

  const selectedSummaryItems = [
    { label: 'Estado Final', value: getStatusBadge(selectedLog as LoadLogEntry) },
    { label: 'Local', value: getDisplayLocalName(selectedLog), subtle: selectedLog?.local_id || undefined },
    { label: 'Registros Procesados', value: `${getProcessedCount(selectedLog)} registros` },
    { label: 'Errores', value: `${getErrorCount(selectedLog)} errores` },
    { label: 'Fecha y Hora', value: formatDateTime(selectedLog?.fecha_hora) },
    ...(selectedLog?.batch_id ? [{ label: 'Batch ID', value: selectedLog.batch_id, subtle: selectedLog.batch_id }] : []),
    ...(getDisplayChannel(selectedLog) ? [{ label: 'Vía de Carga', value: getDisplayChannel(selectedLog) as string }] : []),
  ];

  return (
    <div className="space-y-4 animate-in fade-in duration-500">
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-xl font-bold text-slate-800">Monitor de Cargas (TIC)</h2>
          <p className="text-slate-500">Auditoría en tiempo real de la ingesta de datos. Por defecto muestra hasta los últimos 5 días.</p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={handleClearLogs}
            className="flex items-center gap-2 px-4 py-2 bg-red-50 text-red-600 hover:bg-red-100 rounded-xl text-sm font-bold transition-all border border-red-200"
          >
            <XCircle size={18} /> Limpiar Historial
          </button>
          <button
            onClick={loadData}
            className="p-2 text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 rounded-xl transition-all"
            title="Actualizar"
          >
            <RefreshCw size={20} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard title="Cargas Exitosas" count={stats.exito} icon={CheckCircle2} color="text-green-600" bgColor="bg-green-50" />
        <StatCard title="Cargas con Errores" count={stats.parcial + stats.error} icon={AlertCircle} color="text-amber-600" bgColor="bg-amber-50" />
        <StatCard title="Cargas últimos 5 días" count={stats.total} icon={FileText} color="text-indigo-600" bgColor="bg-indigo-50" />
        <StatCard title="Ultima Actualizacion" count={new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} icon={Clock} color="text-slate-600" bgColor="bg-slate-50" />
      </div>

      <div className="bg-white p-4 rounded-2xl border border-slate-200 shadow-sm flex flex-wrap items-center gap-4">
        <div className="flex items-center gap-3 flex-1 min-w-[250px] bg-slate-50 px-3 py-2 rounded-xl border border-slate-100">
          <Search size={18} className="text-slate-400" />
          <input
            type="text"
            placeholder="Buscar por local, archivo o batch..."
            className="bg-transparent border-none outline-none text-sm w-full"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
        </div>

        <div className="flex items-center gap-2 bg-slate-50 px-3 py-2 rounded-xl border border-slate-100">
          <Clock size={16} className="text-slate-400" />
          <input
            type="date"
            className="bg-transparent border-none outline-none text-xs text-slate-600"
            value={dateRange.start}
            onChange={(e) => setDateRange({ ...dateRange, start: e.target.value })}
          />
          <span className="text-slate-300">|</span>
          <input
            type="date"
            className="bg-transparent border-none outline-none text-xs text-slate-600"
            value={dateRange.end}
            onChange={(e) => setDateRange({ ...dateRange, end: e.target.value })}
          />
        </div>

        <div className="flex items-center gap-2">
          <select
            className="bg-slate-50 border border-slate-100 rounded-xl px-3 py-2 text-xs font-bold text-slate-600 outline-none focus:ring-2 focus:ring-indigo-500/20"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as MonitorStatusFilter)}
          >
            <option value="all">Todos los Estados</option>
            <option value="exito">Solo Éxito</option>
            <option value="parcial">Solo Parcial</option>
            <option value="error">Solo Fallidos</option>
          </select>
        </div>
      </div>

      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="max-h-[calc(100dvh-19rem)] min-h-[260px] overflow-auto">
          <table className="w-full text-left">
            <thead className="sticky top-0 z-10 bg-slate-50/95 text-slate-500 text-[10px] uppercase font-bold tracking-widest border-b border-slate-100">
              <tr>
                <th className="px-3 py-2.5">Fecha / Hora</th>
                <th className="px-3 py-2.5">Local</th>
                <th className="px-3 py-2.5">Archivo</th>
                <th className="px-3 py-2.5">Estado</th>
                <th className="px-3 py-2.5">Mensaje</th>
                <th className="px-3 py-2.5 text-right">Accion</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {loading && logs.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-6 py-10 text-center">
                    <div className="flex flex-col items-center gap-2">
                      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600"></div>
                      <span className="text-slate-500 text-sm">Cargando logs de auditoría...</span>
                    </div>
                  </td>
                </tr>
              ) : filteredLogs.length > 0 ? (
                paginatedLogs.map((log) => (
                  <tr key={String(log.id)} className="hover:bg-slate-50/80 transition-colors group">
                    <td className="px-3 py-2.5 whitespace-nowrap">
                      <div className="text-sm font-medium text-slate-700">{formatDate(log.fecha_hora)}</div>
                      <div className="text-[10px] text-slate-400">
                        {safeDate(log.fecha_hora)?.toLocaleTimeString() || 'Sin hora'}
                        {log.repeatCount > 1 && (
                          <span className="ml-2 px-1.5 py-0.5 bg-slate-200 text-slate-600 rounded-md text-[10px] font-bold">
                            x{log.repeatCount}
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-3 py-2.5">
                      <div className="flex items-center gap-2 text-sm font-bold text-slate-800">
                        <Store size={14} className="text-slate-400" />
                        {getDisplayLocalName(log)}
                      </div>
                    </td>
                    <td className="px-3 py-2.5">
                      <div className="text-sm text-slate-700">{getDisplayFileName(log)}</div>
                      <div className="flex flex-wrap items-center gap-2 mt-1 text-xs text-slate-500">
                        {getDisplayChannel(log) && (
                          <span className="inline-flex items-center rounded-full bg-slate-100 text-slate-700 px-2 py-0.5 font-semibold">
                            {getDisplayChannel(log)}
                          </span>
                        )}
                        {log.batch_id && <span>Batch: {truncateMiddle(log.batch_id, 8, 6)}</span>}
                      </div>
                    </td>
                    <td className="px-3 py-2.5">
                      {getStatusBadge(log)}
                    </td>
                    <td className="px-3 py-2.5">
                      <div className="max-w-sm" title={getReadableMessage(log)}>
                        <div className="text-xs font-bold text-slate-700">{describeLoadLog(log).title}</div>
                        <div className="text-xs text-slate-500 line-clamp-2">{describeLoadLog(log).summary}</div>
                      </div>
                    </td>
                    <td className="px-3 py-2.5 text-right">
                      <button
                        onClick={() => setSelectedLog(log)}
                        className="text-xs font-bold text-indigo-600 hover:text-indigo-800 underline"
                      >
                        Ver Detalle
                      </button>
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={6} className="px-6 py-10 text-center text-slate-400 italic">
                    No se encontraron registros de carga.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        <div className="flex flex-col gap-3 border-t border-slate-100 bg-slate-50/70 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="text-xs font-medium text-slate-500">
            {filteredLogs.length > 0
              ? `Mostrando ${pageStart + 1}-${pageEnd} de ${filteredLogs.length} registros`
              : 'Sin registros para mostrar'}
          </div>
          <div className="flex items-center justify-between gap-3 sm:justify-end">
            <button
              type="button"
              onClick={() => setCurrentPage((page) => Math.max(1, page - 1))}
              disabled={safeCurrentPage <= 1}
              className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2 text-xs font-bold text-slate-600 transition-all hover:border-indigo-200 hover:text-indigo-600 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:border-slate-200 disabled:hover:text-slate-600"
            >
              <ChevronLeft size={16} />
              Retroceder
            </button>
            <span className="min-w-[88px] text-center text-xs font-bold text-slate-500">
              Pagina {safeCurrentPage} de {totalPages}
            </span>
            <button
              type="button"
              onClick={() => setCurrentPage((page) => Math.min(totalPages, page + 1))}
              disabled={safeCurrentPage >= totalPages}
              className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2 text-xs font-bold text-slate-600 transition-all hover:border-indigo-200 hover:text-indigo-600 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:border-slate-200 disabled:hover:text-slate-600"
            >
              Siguiente
              <ChevronRight size={16} />
            </button>
          </div>
        </div>
      </div>

      {selectedLog && (
        <div className="fixed inset-0 bg-slate-900/50 backdrop-blur-sm flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl shadow-2xl max-w-3xl w-full max-h-[85vh] flex flex-col overflow-hidden animate-in zoom-in-95 duration-200">
            <div className="p-4 border-b border-slate-100 flex justify-between items-center bg-slate-50/50">
              <div>
                <h3 className="text-xl font-bold text-slate-800">Detalle de Carga</h3>
                <p className="text-sm text-slate-500">{getDisplayFileName(selectedLog)} - {getDisplayLocalName(selectedLog)}</p>
              </div>
              <button
                onClick={() => setSelectedLog(null)}
                className="p-2 hover:bg-slate-200 rounded-full transition-colors"
              >
                <XCircle size={24} className="text-slate-400" />
              </button>
            </div>

            <div className="p-4 overflow-y-auto flex-1 space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                {selectedSummaryItems.map((item) => (
                  <SummaryTile key={item.label} label={item.label} value={item.value} subtle={item.subtle} />
                ))}
              </div>

              <div className="p-5 rounded-2xl bg-indigo-50 border border-indigo-100">
                <p className="text-[10px] font-bold text-indigo-500 uppercase tracking-widest mb-2">
                  Mensaje operativo · {selectedOperationalMessage.category}
                </p>
                <p className="text-sm font-bold text-slate-800">{selectedOperationalMessage.title}</p>
                <p className="text-sm text-slate-700 leading-relaxed mt-1">{selectedOperationalMessage.summary}</p>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-4">
                  <div className="rounded-xl bg-white/70 border border-indigo-100 p-3">
                    <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1">Causa probable</p>
                    <p className="text-xs text-slate-700 leading-relaxed">{selectedOperationalMessage.cause}</p>
                  </div>
                  <div className="rounded-xl bg-white/70 border border-indigo-100 p-3">
                    <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1">Accion recomendada</p>
                    <p className="text-xs text-slate-700 leading-relaxed">{selectedOperationalMessage.action}</p>
                  </div>
                </div>
              </div>

              <div>
                <h4 className="text-sm font-bold text-slate-800 mb-3 flex items-center gap-2">
                  <AlertCircle size={16} className={isExecutionFailure ? 'text-red-500' : 'text-amber-500'} />
                  {hasLineErrors
                    ? `Resultado de Validación (${selectedLogErrors.length} errores)`
                    : isExecutionFailure
                      ? selectedOperationalMessage.title
                      : 'Resultado de Validación'}
                </h4>

                {hasLineErrors ? (
                  <div className="space-y-2">
                    {selectedLogErrors.map((err, idx) => (
                      <div key={`${idx}-${err.linea || 0}`} className="flex items-start gap-3 p-3 rounded-xl bg-red-50 border border-red-100">
                        <span className="text-[10px] font-mono font-bold bg-red-200 text-red-700 px-1.5 py-0.5 rounded">
                          L{err.linea || idx + 1}
                        </span>
                        <p className="text-xs text-red-700 font-medium">{String(err.error || 'Error sin detalle')}</p>
                      </div>
                    ))}
                  </div>
                ) : isExecutionFailure ? (
                  <div className="p-5 rounded-2xl bg-red-50 border border-red-100 space-y-2">
                    <p className="text-sm font-bold text-red-700">{selectedOperationalMessage.title}</p>
                    <p className="text-xs text-red-700/90">{selectedOperationalMessage.summary}</p>
                    <p className="text-xs text-red-700/90">Causa probable: {selectedOperationalMessage.cause}</p>
                    <p className="text-[11px] text-red-600/80">
                      No hay errores por linea porque el fallo ocurrio en conexion, descarga, validacion inicial o persistencia.
                    </p>
                  </div>
                ) : (
                  <div className="p-4 text-center bg-green-50 rounded-2xl border border-green-100">
                    <CheckCircle2 size={32} className="text-green-500 mx-auto mb-2" />
                    <p className="text-sm text-green-700 font-medium">No se encontraron errores en las líneas del archivo.</p>
                  </div>
                )}
              </div>
            </div>

            <div className="p-4 border-t border-slate-100 bg-slate-50/50 flex justify-end">
              <button
                onClick={() => setSelectedLog(null)}
                className="px-6 py-2 rounded-xl bg-slate-800 text-white font-bold hover:bg-slate-900 transition-all active:scale-95"
              >
                Cerrar
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
