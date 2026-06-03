import React, { useEffect, useMemo, useState } from 'react';
import { useAuth } from '../context/AuthProvider';
import { ApiService } from '../api';
import { LoadLogEntry } from '../types';
import {
  AlertCircle,
  Building2,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Clock,
  FileText,
  Hash,
  RefreshCw,
  Search,
  Store,
  Waypoints,
  XCircle,
} from 'lucide-react';

type MonitorStatusFilter = 'all' | 'exito' | 'parcial' | 'error';
const LOAD_MONITOR_PAGE_SIZE = 20;

const StatCard = ({ title, count, icon: Icon, color, bgColor }: any) => (
  <div className="bg-white p-6 rounded-2xl border border-slate-100 shadow-sm flex items-center gap-4">
    <div className={`p-3 rounded-xl ${bgColor} ${color}`}>
      <Icon size={24} />
    </div>
    <div>
      <p className="text-slate-500 text-sm font-medium">{title}</p>
      <h3 className="text-2xl font-bold text-slate-900">{count}</h3>
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

const truncateMiddle = (value?: string | null, left = 10, right = 6): string => {
  const text = String(value || '').trim();
  if (!text) return '—';
  if (text.length <= left + right + 3) return text;
  return `${text.slice(0, left)}...${text.slice(-right)}`;
};

const getErrorCount = (log: LoadLogEntry | null): number => {
  if (!log) return 0;
  const explicit = Number(log.error_count);
  if (Number.isFinite(explicit)) return explicit;
  return Array.isArray(log.detalles) ? log.detalles.length : 0;
};

const getProcessedCount = (log: LoadLogEntry | null): number => {
  if (!log) return 0;
  const explicit = Number(log.records_processed);
  return Number.isFinite(explicit) ? explicit : 0;
};

const getNormalizedStatus = (log: LoadLogEntry | null): string => {
  if (!log) return 'error';
  const status = String(log.estado || '').trim().toLowerCase();
  if (status === 'parcial') return 'parcial';
  if (status === 'exito' && getErrorCount(log) > 0) return 'parcial';
  return status || 'error';
};

const getDisplayChannel = (log: LoadLogEntry | null): string => {
  const raw = String(log?.canal || log?.metadata?.canal || '').trim();
  if (!raw) return 'Sin canal';
  return raw;
};

const getDisplayMallName = (log: LoadLogEntry | null, currentMall: any): string => {
  if (!log) return 'Mall desconocido';
  const direct = String(log.mall_nombre || '').trim();
  if (direct) return direct;
  if (currentMall?.id && (!log.mall_id || log.mall_id === currentMall.id)) {
    return currentMall.nombre || 'Mall actual';
  }
  return truncateMiddle(log.mall_id || '', 8, 4);
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
  if (log?.batch_id) return `Batch ${log.batch_id}`;
  return 'Sin archivo';
};

const getReadableMessage = (log: LoadLogEntry | null): string => {
  const message = String(log?.mensaje || '').trim();
  if (message) return message;
  const processed = getProcessedCount(log);
  const errors = getErrorCount(log);
  if (getNormalizedStatus(log) === 'exito') {
    return `Carga completada. ${processed} registros procesados.`;
  }
  if (getNormalizedStatus(log) === 'parcial') {
    return `Carga parcial. ${processed} registros procesados y ${errors} errores.`;
  }
  return 'Sin detalle adicional.';
};

const getStatusBadge = (log: LoadLogEntry) => {
  const status = getNormalizedStatus(log);
  if (status === 'exito') {
    return <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-green-50 text-green-700 text-xs font-bold"><CheckCircle2 size={12} /> Exito</span>;
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
        getDisplayMallName(log, currentMall),
        getDisplayLocalName(log),
        getDisplayChannel(log),
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
  }, [logs, searchTerm, dateRange, statusFilter, currentMall]);

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

  const inferFailureKind = (log: LoadLogEntry | null) => {
    if (!log) return 'Fallo de ejecucion';
    const msg = getReadableMessage(log).toLowerCase();
    const channel = getDisplayChannel(log).toLowerCase();
    if (msg.includes('conexion') || channel === 'ftp' || channel === 'sftp') {
      return 'Fallo de conexion';
    }
    if (msg.includes('no se pudo descargar') || msg.includes('no encontrado') || msg.includes('not found')) {
      return 'Archivo no encontrado';
    }
    if (msg.includes('vacio') || msg.includes('sin datos') || msg.includes('solo encabezado') || msg.includes('no contiene registros')) {
      return 'Archivo sin datos';
    }
    if (channel === 'webservice') {
      return 'Fallo de validacion WebService';
    }
    return 'Fallo de ejecucion';
  };

  const selectedLogErrors = Array.isArray(selectedLog?.detalles) ? selectedLog.detalles : [];
  const selectedLogStatus = getNormalizedStatus(selectedLog);
  const hasLineErrors = selectedLogErrors.length > 0;
  const isExecutionFailure = selectedLogStatus === 'error' && !hasLineErrors;

  return (
    <div className="space-y-8 animate-in fade-in duration-500">
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-2xl font-bold text-slate-800">Monitor de Cargas (TIC)</h2>
          <p className="text-slate-500">Auditoria en tiempo real de la ingesta de datos.</p>
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

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <StatCard title="Cargas Exitosas" count={stats.exito} icon={CheckCircle2} color="text-green-600" bgColor="bg-green-50" />
        <StatCard title="Cargas Parciales" count={stats.parcial} icon={AlertCircle} color="text-amber-600" bgColor="bg-amber-50" />
        <StatCard title="Cargas Fallidas" count={stats.error} icon={XCircle} color="text-red-600" bgColor="bg-red-50" />
        <StatCard title="Ultima Actualizacion" count={new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} icon={Clock} color="text-slate-600" bgColor="bg-slate-50" />
      </div>

      <div className="bg-white p-4 rounded-2xl border border-slate-200 shadow-sm flex flex-wrap items-center gap-4">
        <div className="flex items-center gap-3 flex-1 min-w-[250px] bg-slate-50 px-3 py-2 rounded-xl border border-slate-100">
          <Search size={18} className="text-slate-400" />
          <input
            type="text"
            placeholder="Buscar por mall, local, via, archivo o batch..."
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
            <option value="exito">Solo Exito</option>
            <option value="parcial">Solo Parcial</option>
            <option value="error">Solo Fallidos</option>
          </select>
        </div>
      </div>

      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left min-w-[1200px]">
            <thead className="bg-slate-50/50 text-slate-500 text-[10px] uppercase font-bold tracking-widest border-b border-slate-100">
              <tr>
                <th className="px-6 py-4">Fecha / Hora</th>
                <th className="px-6 py-4">Mall / Local</th>
                <th className="px-6 py-4">Via</th>
                <th className="px-6 py-4">Archivo / Batch</th>
                <th className="px-6 py-4">Estado</th>
                <th className="px-6 py-4">Registros</th>
                <th className="px-6 py-4">Mensaje</th>
                <th className="px-6 py-4 text-right">Accion</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {loading && logs.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-6 py-20 text-center">
                    <div className="flex flex-col items-center gap-2">
                      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600"></div>
                      <span className="text-slate-500 text-sm">Cargando logs de auditoria...</span>
                    </div>
                  </td>
                </tr>
              ) : filteredLogs.length > 0 ? (
                paginatedLogs.map((log) => (
                  <tr key={String(log.id)} className="hover:bg-slate-50/80 transition-colors group">
                    <td className="px-6 py-4 whitespace-nowrap">
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
                    <td className="px-6 py-4">
                      <div className="flex items-start gap-3">
                        <Building2 size={15} className="text-slate-400 mt-0.5" />
                        <div>
                          <div className="text-sm font-bold text-slate-800">{getDisplayMallName(log, currentMall)}</div>
                          <div className="text-xs text-slate-500 flex items-center gap-1.5 mt-1">
                            <Store size={12} />
                            <span>{getDisplayLocalName(log)}</span>
                          </div>
                        </div>
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-slate-100 text-slate-700 text-xs font-semibold">
                        <Waypoints size={12} />
                        {getDisplayChannel(log)}
                      </span>
                    </td>
                    <td className="px-6 py-4">
                      <div className="text-sm font-medium text-slate-700">{getDisplayFileName(log)}</div>
                      <div className="text-xs text-slate-500 flex items-center gap-1.5 mt-1">
                        <Hash size={12} />
                        <span>{log.batch_id ? truncateMiddle(log.batch_id, 8, 6) : 'Sin batch_id'}</span>
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      {getStatusBadge(log)}
                    </td>
                    <td className="px-6 py-4">
                      <div className="text-sm font-bold text-slate-800">{getProcessedCount(log)} registros</div>
                      <div className="text-xs text-slate-500">{getErrorCount(log)} errores</div>
                    </td>
                    <td className="px-6 py-4">
                      <div className="text-xs text-slate-500 max-w-sm line-clamp-2" title={getReadableMessage(log)}>
                        {getReadableMessage(log)}
                      </div>
                    </td>
                    <td className="px-6 py-4 text-right">
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
                  <td colSpan={8} className="px-6 py-20 text-center text-slate-400 italic">
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
          <div className="bg-white rounded-3xl shadow-2xl max-w-4xl w-full max-h-[85vh] flex flex-col overflow-hidden animate-in zoom-in-95 duration-200">
            <div className="p-6 border-b border-slate-100 flex justify-between items-center bg-slate-50/50">
              <div>
                <h3 className="text-xl font-bold text-slate-800">Detalle de Carga</h3>
                <p className="text-sm text-slate-500">
                  {getDisplayFileName(selectedLog)} · {getDisplayLocalName(selectedLog)}
                </p>
              </div>
              <button
                onClick={() => setSelectedLog(null)}
                className="p-2 hover:bg-slate-200 rounded-full transition-colors"
              >
                <XCircle size={24} className="text-slate-400" />
              </button>
            </div>

            <div className="p-6 overflow-y-auto flex-1 space-y-6">
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
                <SummaryTile label="Estado Final" value={getStatusBadge(selectedLog)} />
                <SummaryTile label="Mall" value={getDisplayMallName(selectedLog, currentMall)} subtle={selectedLog.mall_id || undefined} />
                <SummaryTile label="Local" value={getDisplayLocalName(selectedLog)} subtle={selectedLog.local_id || undefined} />
                <SummaryTile label="Via de Carga" value={getDisplayChannel(selectedLog)} />
                <SummaryTile label="Archivo" value={getDisplayFileName(selectedLog)} />
                <SummaryTile label="Batch ID" value={selectedLog.batch_id || 'No aplica'} subtle={selectedLog.batch_id || undefined} />
                <SummaryTile label="Registros Procesados" value={`${getProcessedCount(selectedLog)} registros`} />
                <SummaryTile label="Errores" value={`${getErrorCount(selectedLog)} errores`} />
                <SummaryTile label="Fecha y Hora" value={formatDateTime(selectedLog.fecha_hora)} />
              </div>

              <div className="p-5 rounded-2xl bg-indigo-50 border border-indigo-100">
                <p className="text-[10px] font-bold text-indigo-500 uppercase tracking-widest mb-2">Mensaje</p>
                <p className="text-sm text-slate-700 leading-relaxed">{getReadableMessage(selectedLog)}</p>
              </div>

              <div>
                <h4 className="text-sm font-bold text-slate-800 mb-3 flex items-center gap-2">
                  <AlertCircle size={16} className={isExecutionFailure ? 'text-red-500' : 'text-amber-500'} />
                  {hasLineErrors
                    ? `Resultado de Validacion (${selectedLogErrors.length} errores)`
                    : isExecutionFailure
                      ? inferFailureKind(selectedLog)
                      : 'Resultado de Validacion'}
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
                    <p className="text-sm font-bold text-red-700">La carga fallo antes de completar el procesamiento.</p>
                    <p className="text-xs text-red-700/90">{getReadableMessage(selectedLog)}</p>
                    <p className="text-[11px] text-red-600/80">
                      No hay errores por linea porque el fallo ocurrio en conexion, descarga, validacion inicial o persistencia.
                    </p>
                  </div>
                ) : (
                  <div className="p-8 text-center bg-green-50 rounded-2xl border border-green-100">
                    <CheckCircle2 size={32} className="text-green-500 mx-auto mb-2" />
                    <p className="text-sm text-green-700 font-medium">No se encontraron errores en la validacion del archivo o batch.</p>
                  </div>
                )}
              </div>
            </div>

            <div className="p-6 border-t border-slate-100 bg-slate-50/50 flex justify-end">
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
