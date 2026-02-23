
import React, { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthProvider';
import { ApiService } from '../api';
import { queueImportConnectionOpenRequest } from '../utils/importNavigation';
import {
    CheckCircle2, XCircle, AlertCircle, Clock,
    Search, RefreshCw, FileText, Store, Filter
} from 'lucide-react';

interface LoadLog {
    id: string;
    fecha_hora: string;
    local_nombre: string;
    local_id?: string;
    archivo: string;
    estado: 'exito' | 'error' | 'no_encontrado';
    mensaje: string;
    batch_id?: string;
    detalles?: { linea: number, error: string }[];
}

const StatCard = ({ title, count, icon: Icon, color, bgColor }: any) => (
    <div className={`bg-white p-6 rounded-2xl border border-slate-100 shadow-sm flex items-center gap-4`}>
        <div className={`p-3 rounded-xl ${bgColor} ${color}`}>
            <Icon size={24} />
        </div>
        <div>
            <p className="text-slate-500 text-sm font-medium">{title}</p>
            <h3 className="text-2xl font-bold text-slate-900">{count}</h3>
        </div>
    </div>
);

export const LoadMonitor: React.FC = () => {
    const { currentMall, session } = useAuth();
    const [logs, setLogs] = useState<LoadLog[]>([]);
    const [loading, setLoading] = useState(true);
    const [searchTerm, setSearchTerm] = useState('');
    const [selectedLog, setSelectedLog] = useState<LoadLog | null>(null);
    const [dateRange, setDateRange] = useState({ start: '', end: '' });
    const [statusFilter, setStatusFilter] = useState<'all' | 'exito' | 'parcial' | 'error'>('all');

    const loadData = async () => {
        if (!currentMall?.id) return;
        setLoading(true);
        try {
            const data = await ApiService.getLoadLogs(currentMall.id);
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
            alert('Sesión inválida. Inicia sesión nuevamente para continuar.');
            return;
        }

        if (window.confirm(`¿Estás seguro de que deseas limpiar el historial de cargas de ${currentMall.nombre}? Esta acción no se puede deshacer.`)) {
            try {
                await ApiService.clearLoadLogs(currentMall.id, session.access_token);
                await loadData();
                alert('Historial limpiado correctamente.');
            } catch (e) {
                alert('Error al limpiar el historial.');
            }
        }
    };

    useEffect(() => {
        if (currentMall) {
            loadData();
            // Refresh every 30 seconds
            const interval = setInterval(loadData, 30000);
            return () => clearInterval(interval);
        }
    }, [currentMall]);

    const stats = {
        exito: logs.filter(l => l.estado === 'exito' && (!l.detalles || l.detalles.length === 0)).length,
        parcial: logs.filter(l => l.estado === 'exito' && l.detalles && l.detalles.length > 0).length,
        error: logs.filter(l => l.estado === 'error').length,
        total: logs.length
    };

    const filteredLogs = React.useMemo(() => {
        const result: any[] = [];
        let lastLog: any = null;
        let repeatCount = 1;

        // First filter by search/date
        const rawFiltered = logs.filter(log => {
            const matchesSearch = log.local_nombre.toLowerCase().includes(searchTerm.toLowerCase()) ||
                log.archivo.toLowerCase().includes(searchTerm.toLowerCase()) ||
                log.mensaje.toLowerCase().includes(searchTerm.toLowerCase());

            const logDate = new Date(log.fecha_hora).toISOString().split('T')[0];
            const matchesStart = !dateRange.start || logDate >= dateRange.start;
            const matchesEnd = !dateRange.end || logDate <= dateRange.end;

            const hasErrors = log.detalles && log.detalles.length > 0;
            let matchesStatus = true;
            if (statusFilter === 'exito') matchesStatus = log.estado === 'exito' && !hasErrors;
            else if (statusFilter === 'parcial') matchesStatus = log.estado === 'exito' && hasErrors;
            else if (statusFilter === 'error') matchesStatus = log.estado === 'error';

            return matchesSearch && matchesStart && matchesEnd && matchesStatus;
        });

        // Then Group Repetitive Errors
        // Assuming logs are sorted by date desc
        for (const log of rawFiltered) {
            const isRepetitive = lastLog &&
                lastLog.local_nombre === log.local_nombre &&
                lastLog.mensaje === log.mensaje &&
                lastLog.estado === log.estado &&
                new Date(lastLog.fecha_hora).toDateString() === new Date(log.fecha_hora).toDateString(); // Same day

            if (isRepetitive) {
                lastLog.repeatCount = (lastLog.repeatCount || 1) + 1;
                // Keep the latest timestamp visible? Or range?
                // lastLog is the newest one if we iterate desc? 
                // Using API ordering... usually newest first.
                // If newest first, lastLog is the newer one. 
                // We just extend the count.
            } else {
                result.push({ ...log, repeatCount: 1 });
                lastLog = result[result.length - 1];
            }
        }
        return result;
    }, [logs, searchTerm, dateRange, statusFilter]);

    const getStatusBadge = (log: LoadLog) => {
        const hasErrors = log.detalles && log.detalles.length > 0;

        if (log.estado === 'exito' && !hasErrors) {
            return <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-green-50 text-green-700 text-xs font-bold"><CheckCircle2 size={12} /> Éxito</span>;
        }
        if (log.estado === 'exito' && hasErrors) {
            return <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-amber-50 text-amber-700 text-xs font-bold"><AlertCircle size={12} /> Parcial ({log.detalles?.length} err)</span>;
        }
        if (log.estado === 'error') {
            return <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-red-50 text-red-700 text-xs font-bold"><XCircle size={12} /> Fallido</span>;
        }
        if (log.estado === 'no_encontrado') {
            return <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-amber-50 text-amber-700 text-xs font-bold"><AlertCircle size={12} /> No Encontrado</span>;
        }
        return <span className="px-2.5 py-0.5 rounded-full bg-slate-50 text-slate-700 text-xs font-bold">{log.estado}</span>;
    };

    const canOpenConnectionFromLog = (log: LoadLog | null) => {
        if (!log) return false;
        if (!(log.estado === 'error' || log.estado === 'no_encontrado')) return false;
        return Boolean((log as any).local_id || log.local_nombre);
    };

    const handleOpenConnectionFromLog = (log: LoadLog) => {
        const localId = (log as any).local_id || (log as any).localId || undefined;
        const localName = (log.local_nombre || '').trim() || undefined;

        if (!localId && !localName) {
            alert('No se pudo identificar el local asociado a este registro.');
            return;
        }

        queueImportConnectionOpenRequest({
            localId,
            localName,
            logId: log.id
        });
        setSelectedLog(null);
    };

    const inferFailureKind = (log: LoadLog | null) => {
        if (!log) return 'Fallo de ejecución';
        const msg = String(log.mensaje || '').toLowerCase();
        if (msg.includes('conexión') || msg.includes('conexion') || msg.includes('ftp') || msg.includes('sftp')) {
            return 'Fallo de Conexión';
        }
        if (msg.includes('no se pudo descargar') || msg.includes('no encontrado') || msg.includes('not found')) {
            return 'Archivo no Encontrado';
        }
        if (msg.includes('vacío') || msg.includes('vacio') || msg.includes('sin datos') || msg.includes('solo encabezado') || msg.includes('no contiene filas')) {
            return 'Archivo sin Datos';
        }
        return 'Fallo de ejecución';
    };

    return (
        <div className="space-y-8 animate-in fade-in duration-500">
            <div className="flex justify-between items-center">
                <div>
                    <h2 className="text-2xl font-bold text-slate-800">Monitor de Cargas (TIC)</h2>
                    <p className="text-slate-500">Auditoría en tiempo real de la ingesta de datos.</p>
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

            {/* Summary Cards */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                <StatCard
                    title="Cargas Exitosas"
                    count={stats.exito}
                    icon={CheckCircle2}
                    color="text-green-600"
                    bgColor="bg-green-50"
                />
                <StatCard
                    title="Cargas con Errores"
                    count={stats.parcial + stats.error}
                    icon={AlertCircle}
                    color="text-amber-600"
                    bgColor="bg-amber-50"
                />
                <StatCard
                    title="Total Archivos"
                    count={stats.total}
                    icon={FileText}
                    color="text-indigo-600"
                    bgColor="bg-indigo-50"
                />
                <StatCard
                    title="Última Actualización"
                    count={new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    icon={Clock}
                    color="text-slate-600"
                    bgColor="bg-slate-50"
                />
            </div>

            {/* Filters Bar */}
            <div className="bg-white p-4 rounded-2xl border border-slate-200 shadow-sm flex flex-wrap items-center gap-4">
                <div className="flex items-center gap-3 flex-1 min-w-[250px] bg-slate-50 px-3 py-2 rounded-xl border border-slate-100">
                    <Search size={18} className="text-slate-400" />
                    <input
                        type="text"
                        placeholder="Buscar por local, archivo..."
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
                        onChange={(e) => setStatusFilter(e.target.value as any)}
                    >
                        <option value="all">Todos los Estados</option>
                        <option value="exito">Solo Éxito</option>
                        <option value="parcial">Solo Parcial</option>
                        <option value="error">Solo Fallidos</option>
                    </select>
                </div>
            </div>

            {/* Audit Table */}
            <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
                <div className="overflow-x-auto">
                    <table className="w-full text-left">
                        <thead className="bg-slate-50/50 text-slate-500 text-[10px] uppercase font-bold tracking-widest border-b border-slate-100">
                            <tr>
                                <th className="px-6 py-4">Fecha / Hora</th>
                                <th className="px-6 py-4">Local</th>
                                <th className="px-6 py-4">Archivo</th>
                                <th className="px-6 py-4">Estado</th>
                                <th className="px-6 py-4">Mensaje</th>
                                <th className="px-6 py-4 text-right">Acción</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100">
                            {loading && logs.length === 0 ? (
                                <tr>
                                    <td colSpan={6} className="px-6 py-20 text-center">
                                        <div className="flex flex-col items-center gap-2">
                                            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600"></div>
                                            <span className="text-slate-500 text-sm">Cargando logs de auditoría...</span>
                                        </div>
                                    </td>
                                </tr>
                            ) : filteredLogs.length > 0 ? (
                                filteredLogs.map((log) => (
                                    <tr key={log.id} className="hover:bg-slate-50/80 transition-colors group">
                                        <td className="px-6 py-4 whitespace-nowrap">
                                            <div className="text-sm font-medium text-slate-700">
                                                {new Date(log.fecha_hora).toLocaleDateString()}
                                            </div>
                                            <div className="text-[10px] text-slate-400">
                                                {new Date(log.fecha_hora).toLocaleTimeString()}
                                                {log.repeatCount > 1 && (
                                                    <span className="ml-2 px-1.5 py-0.5 bg-slate-200 text-slate-600 rounded-md text-[10px] font-bold">
                                                        x{log.repeatCount}
                                                    </span>
                                                )}
                                            </div>
                                        </td>
                                        <td className="px-6 py-4">
                                            <div className="flex items-center gap-2 text-sm font-bold text-slate-800">
                                                <Store size={14} className="text-slate-400" />
                                                {log.local_nombre}
                                            </div>
                                        </td>
                                        <td className="px-6 py-4">
                                            <div className="flex items-center gap-2 text-sm text-slate-600">
                                                <FileText size={14} className="text-indigo-400" />
                                                {log.archivo}
                                            </div>
                                        </td>
                                        <td className="px-6 py-4">
                                            {getStatusBadge(log)}
                                        </td>
                                        <td className="px-6 py-4">
                                            <div className="text-xs text-slate-500 max-w-xs truncate" title={log.mensaje}>
                                                {log.mensaje}
                                            </div>
                                        </td>
                                        <td className="px-6 py-4 text-right">
                                            <div className="inline-flex items-center gap-3">
                                                {canOpenConnectionFromLog(log) && (
                                                    <button
                                                        onClick={() => handleOpenConnectionFromLog(log)}
                                                        className="text-xs font-bold text-indigo-600 hover:text-indigo-800 underline"
                                                    >
                                                        Ir a Conexión
                                                    </button>
                                                )}
                                                <button
                                                    onClick={() => setSelectedLog(log)}
                                                    className="text-xs font-bold text-indigo-600 hover:text-indigo-800 underline"
                                                >
                                                    Ver Detalle
                                                </button>
                                            </div>
                                        </td>
                                    </tr>
                                ))
                            ) : (
                                <tr>
                                    <td colSpan={6} className="px-6 py-20 text-center text-slate-400 italic">
                                        No se encontraron registros de carga.
                                    </td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                </div>
            </div>

            {/* Detail Modal */}
            {selectedLog && (
                (() => {
                    const lineErrors = selectedLog.detalles || [];
                    const hasLineErrors = lineErrors.length > 0;
                    const isExecutionFailure = (selectedLog.estado === 'error' || selectedLog.estado === 'no_encontrado') && !hasLineErrors;
                    const detailTitle = hasLineErrors
                        ? `Errores por Línea (${lineErrors.length})`
                        : isExecutionFailure
                            ? inferFailureKind(selectedLog)
                            : 'Resultado de Validación';

                    return (
                <div className="fixed inset-0 bg-slate-900/50 backdrop-blur-sm flex items-center justify-center z-50 p-4">
                    <div className="bg-white rounded-3xl shadow-2xl max-w-2xl w-full max-h-[80vh] flex flex-col overflow-hidden animate-in zoom-in-95 duration-200">
                        <div className="p-6 border-b border-slate-100 flex justify-between items-center bg-slate-50/50">
                            <div>
                                <h3 className="text-xl font-bold text-slate-800">Detalle de Carga</h3>
                                <p className="text-sm text-slate-500">{selectedLog.archivo} - {selectedLog.local_nombre}</p>
                            </div>
                            <button
                                onClick={() => setSelectedLog(null)}
                                className="p-2 hover:bg-slate-200 rounded-full transition-colors"
                            >
                                <XCircle size={24} className="text-slate-400" />
                            </button>
                        </div>

                        <div className="p-6 overflow-y-auto flex-1 space-y-6">
                            <div className="grid grid-cols-2 gap-4">
                                <div className="p-4 rounded-2xl bg-slate-50 border border-slate-100">
                                    <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1">Estado Final</p>
                                    {getStatusBadge(selectedLog)}
                                </div>
                                <div className="p-4 rounded-2xl bg-slate-50 border border-slate-100">
                                    <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1">Fecha y Hora</p>
                                    <p className="text-sm font-bold text-slate-700">{new Date(selectedLog.fecha_hora).toLocaleString()}</p>
                                </div>
                            </div>

                            <div>
                                <h4 className="text-sm font-bold text-slate-800 mb-3 flex items-center gap-2">
                                    <AlertCircle size={16} className={isExecutionFailure ? "text-red-500" : "text-amber-500"} />
                                    {detailTitle}
                                </h4>

                                {hasLineErrors ? (
                                    <div className="space-y-2">
                                        {lineErrors.map((err: any, idx: number) => (
                                            <div key={idx} className="flex items-start gap-3 p-3 rounded-xl bg-red-50 border border-red-100">
                                                <span className="text-[10px] font-mono font-bold bg-red-200 text-red-700 px-1.5 py-0.5 rounded">L{err.linea}</span>
                                                <p className="text-xs text-red-700 font-medium">{err.error}</p>
                                            </div>
                                        ))}
                                    </div>
                                ) : isExecutionFailure ? (
                                    <div className="p-5 rounded-2xl bg-red-50 border border-red-100 space-y-2">
                                        <p className="text-sm font-bold text-red-700">La carga falló antes de procesar líneas del archivo.</p>
                                        <p className="text-xs text-red-700/90">{selectedLog.mensaje || 'Sin detalle adicional.'}</p>
                                        <p className="text-[11px] text-red-600/80">
                                            No hay errores por línea porque el fallo ocurrió en conexión, descarga, ubicación del archivo o validación inicial.
                                        </p>
                                    </div>
                                ) : (
                                    <div className="p-8 text-center bg-green-50 rounded-2xl border border-green-100">
                                        <CheckCircle2 size={32} className="text-green-500 mx-auto mb-2" />
                                        <p className="text-sm text-green-700 font-medium">No se encontraron errores por línea en el archivo.</p>
                                    </div>
                                )}
                            </div>
                        </div>

                        <div className="p-6 border-t border-slate-100 bg-slate-50/50 flex justify-end gap-3">
                            {canOpenConnectionFromLog(selectedLog) && (
                                <button
                                    onClick={() => handleOpenConnectionFromLog(selectedLog)}
                                    className="px-6 py-2 rounded-xl border border-indigo-200 bg-white text-indigo-700 font-bold hover:bg-indigo-50 transition-all active:scale-95"
                                >
                                    Ir a Conexión
                                </button>
                            )}
                            <button
                                onClick={() => setSelectedLog(null)}
                                className="px-6 py-2 rounded-xl bg-slate-800 text-white font-bold hover:bg-slate-900 transition-all active:scale-95"
                            >
                                Cerrar
                            </button>
                        </div>
                    </div>
                </div>
                    );
                })()
            )}
        </div>
    );
};
