import React, { useState, useEffect } from 'react';
import { AlertTriangle, ChevronDown, ChevronUp, CheckCircle, SearchX, ServerCrash, BarChart2, Eye } from 'lucide-react';
import { useAuth } from '../context/AuthProvider';
import { supabase } from '../api';

interface AuditDetail {
    fecha: string;
    causa: string;
    log_id?: number;
}

interface GlobalSummaryItem {
    local_id: string;
    nombre: string;
    rubro: string;
    dias_faltantes_count: number;
    dias_totales_periodo: number;
    porcentaje_cumplimiento: number;
    estado: string;
    lista_dias: string[];
}

interface GapAnalysisResult {
    modo?: 'global' | 'individual';
    total_dias_faltantes?: number;
    detalle?: AuditDetail[];
    resumen?: GlobalSummaryItem[];
}

interface Props {
    localId: string | null;
    startDate: string;
    endDate: string;
    onSelectLocal?: (localId: string) => void;
}

export const MissingDaysAlert: React.FC<Props> = ({ localId, startDate, endDate, onSelectLocal }) => {
    const { currentMall, session } = useAuth();
    const [analysis, setAnalysis] = useState<GapAnalysisResult | null>(null);
    const [loading, setLoading] = useState(false);
    const [expanded, setExpanded] = useState(false);
    const [matrixPage, setMatrixPage] = useState(1);
    const MATRIX_PAGE_SIZE = 10;

    useEffect(() => {
        if (!startDate || !endDate || !currentMall) return;
        setMatrixPage(1);

        const fetchAnalysis = async () => {
            setLoading(true);
            try {
                const token = session?.access_token;

                if (!token) {
                    console.warn("No auth token available for analysis audit");
                    return;
                }

                const params: any = {
                    fecha_inicio: startDate,
                    fecha_fin: endDate
                };
                if (localId) params.local_id = localId;
                else params.local_id = 'ALL';

                const query = new URLSearchParams(params);
                const rawBase = String(import.meta.env.VITE_API_URL || '').trim();
                let apiBase = rawBase.replace(/\/+$/, '');
                if (apiBase && !/^https?:\/\//i.test(apiBase) && !apiBase.startsWith('/')) {
                    apiBase = `https://${apiBase}`;
                }

                let endpoint = `/api/v1/auditoria/brechas-ventas?${query.toString()}`;
                if (apiBase) {
                    const lower = apiBase.toLowerCase();
                    let path = '/api/v1/auditoria/brechas-ventas';
                    if (lower.endsWith('/api/v1')) path = '/auditoria/brechas-ventas';
                    else if (lower.endsWith('/api')) path = '/v1/auditoria/brechas-ventas';
                    endpoint = `${apiBase}${path}?${query.toString()}`;
                }

                const requestHeaders = {
                    'Authorization': `Bearer ${token}`,
                    'X-Mall-Id': currentMall.id,
                    'Accept': 'application/json'
                };

                let res: Response;
                try {
                    res = await fetch(endpoint, { headers: requestHeaders });
                } catch (firstError) {
                    console.warn(`Gap analysis primary URL failed (${endpoint}), retrying with relative path`, firstError);
                    const fallbackEndpoint = `/api/v1/auditoria/brechas-ventas?${query.toString()}`;
                    res = await fetch(fallbackEndpoint, { headers: requestHeaders });
                }

                if (res.ok) {
                    const contentType = res.headers.get('content-type') || '';
                    if (!contentType.includes('application/json')) {
                        const raw = await res.text();
                        throw new Error(`Respuesta no JSON en gap analysis (${res.status}). Primeros chars: ${raw.slice(0, 120)}`);
                    }
                    const data = await res.json();
                    setAnalysis(data);
                } else {
                    const errorBody = await res.text();
                    console.error("Error fetching analysis:", errorBody);
                }
            } catch (err) {
                console.error("Error fetching gap analysis:", err);
            } finally {
                setLoading(false);
            }
        };

        fetchAnalysis();
    }, [localId, startDate, endDate, currentMall, session]);

    if (loading) return null;
    if (!analysis) return null;

    // --- MODO GLOBAL (MATRIX VIEW) ---
    if (analysis.modo === 'global' && analysis.resumen) {
        const criticalItems = analysis.resumen.filter(i => i.dias_faltantes_count > 0);
        const completeCount = analysis.resumen.length - criticalItems.length;
        const totalMatrixPages = Math.max(1, Math.ceil(criticalItems.length / MATRIX_PAGE_SIZE));
        const currentMatrixPage = Math.min(matrixPage, totalMatrixPages);
        const pageStart = (currentMatrixPage - 1) * MATRIX_PAGE_SIZE;
        const paginatedCriticalItems = criticalItems.slice(pageStart, pageStart + MATRIX_PAGE_SIZE);

        if (criticalItems.length === 0) return null; // Todo perfecto (o mostrar banner verde global)

        return (
            <div className="mb-6 bg-white border border-slate-200 rounded-xl overflow-hidden shadow-sm animate-in fade-in slide-in-from-top-2">
                <div className="p-4 bg-slate-50 border-b border-slate-200 flex items-center justify-between">
                    <div className="flex items-center gap-2">
                        <BarChart2 className="text-slate-500" size={20} />
                        <h4 className="font-bold text-slate-700">Matriz de Cumplimiento de Ventas</h4>
                    </div>
                    <span className="text-xs bg-slate-200 text-slate-600 px-2 py-1 rounded-full font-medium">
                        {criticalItems.length} locales con brechas
                    </span>
                </div>

                <div className="overflow-x-auto">
                    <table className="w-full text-left text-sm">
                        <thead className="bg-slate-50 text-slate-500 font-semibold uppercase text-xs border-b border-slate-200">
                            <tr>
                                <th className="px-4 py-3">Local</th>
                                <th className="px-4 py-3 text-center">Estado</th>
                                <th className="px-4 py-3 text-center">Días Faltantes</th>
                                <th className="px-4 py-3 text-center">Cumplimiento</th>
                                <th className="px-4 py-3 text-right">Acción</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100">
                            {paginatedCriticalItems.map((item) => {
                                const totalDays = item.dias_totales_periodo || 0;
                                const missingDays = item.dias_faltantes_count || 0;
                                const reportedDays = Math.max(0, totalDays - missingDays);
                                const compliance = Number.isFinite(item.porcentaje_cumplimiento) ? item.porcentaje_cumplimiento : 0;

                                return (
                                    <tr key={item.local_id} className="hover:bg-slate-50 transition-colors">
                                        <td className="px-4 py-3">
                                            <div className="font-medium text-slate-800">{item.nombre}</div>
                                            <div className="text-xs text-slate-400">{item.rubro}</div>
                                        </td>
                                        <td className="px-4 py-3 text-center">
                                            <span className={`inline-flex items-center px-2 py-1 rounded-full text-xs font-bold ${item.estado === 'Crítico' ? 'bg-rose-100 text-rose-700' :
                                                item.estado === 'Alerta' ? 'bg-amber-100 text-amber-700' : 'bg-emerald-100 text-emerald-700'
                                                }`}>
                                                {item.estado === 'Crítico' && <AlertTriangle size={12} className="mr-1" />}
                                                {item.estado}
                                            </span>
                                        </td>
                                        <td className="px-4 py-3 text-center">
                                            <div className="font-mono font-bold text-slate-700">
                                                {missingDays} / {totalDays}
                                            </div>
                                            <div className="text-[11px] text-slate-400">
                                                {reportedDays} días con venta
                                            </div>
                                        </td>
                                        <td className="px-4 py-3 text-center">
                                            <div className="flex items-center gap-2 justify-center">
                                                <div className="w-24 h-2 bg-slate-100 rounded-full overflow-hidden">
                                                    <div
                                                        className={`h-full ${compliance < 80 ? 'bg-rose-500' : compliance < 95 ? 'bg-amber-500' : 'bg-emerald-500'}`}
                                                        style={{ width: `${compliance}%` }}
                                                    ></div>
                                                </div>
                                                <span className="text-xs font-medium text-slate-500">{compliance}%</span>
                                            </div>
                                            <div className="mt-1 text-[11px] text-slate-400">
                                                {missingDays > 0 ? `${(100 - compliance).toFixed(1)}% de brecha` : '0% de brecha'}
                                            </div>
                                        </td>
                                        <td className="px-4 py-3 text-right">
                                            <button
                                                onClick={() => onSelectLocal && onSelectLocal(item.local_id)}
                                                className="inline-flex items-center gap-1 px-3 py-1.5 bg-white border border-slate-300 text-slate-700 rounded-lg hover:bg-slate-50 text-xs font-medium shadow-sm transition-all hover:border-indigo-300 hover:text-indigo-600"
                                            >
                                                <Eye size={14} /> Auditar
                                            </button>
                                        </td>
                                    </tr>
                                );
                            })}

                            {completeCount > 0 && (
                                <tr className="bg-slate-50/50">
                                    <td colSpan={5} className="px-4 py-3 text-center text-slate-400 text-xs italic">
                                        ... y {completeCount} locales con cumplimiento perfecto (100%)
                                    </td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                </div>

                {totalMatrixPages > 1 && (
                    <div className="flex flex-col gap-3 border-t border-slate-100 bg-white px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
                        <p className="text-xs text-slate-500">
                            Mostrando {pageStart + 1}-{Math.min(pageStart + MATRIX_PAGE_SIZE, criticalItems.length)} de {criticalItems.length} locales con brechas
                        </p>
                        <div className="flex items-center gap-2">
                            <button
                                type="button"
                                onClick={() => setMatrixPage((page) => Math.max(1, page - 1))}
                                disabled={currentMatrixPage === 1}
                                className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-semibold text-slate-600 transition-colors hover:border-indigo-300 hover:text-indigo-600 disabled:cursor-not-allowed disabled:opacity-40"
                            >
                                Anterior
                            </button>
                            <span className="text-xs font-medium text-slate-500">
                                Página {currentMatrixPage} de {totalMatrixPages}
                            </span>
                            <button
                                type="button"
                                onClick={() => setMatrixPage((page) => Math.min(totalMatrixPages, page + 1))}
                                disabled={currentMatrixPage === totalMatrixPages}
                                className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-semibold text-slate-600 transition-colors hover:border-indigo-300 hover:text-indigo-600 disabled:cursor-not-allowed disabled:opacity-40"
                            >
                                Siguiente
                            </button>
                        </div>
                    </div>
                )}
            </div>
        );
    }

    // --- MODO INDIVIDUAL (EXISTENTE) ---
    if (analysis.total_dias_faltantes === 0) {
        return (
            <div className="mb-4 bg-emerald-50 border border-emerald-100 p-3 rounded-lg flex items-center gap-2 text-emerald-700 text-sm">
                <CheckCircle size={16} />
                <span className="font-medium">Auditoría Completa:</span> No faltan días de venta en este periodo.
            </div>
        );
    }

    return (
        <div className="mb-6 bg-amber-50 border border-amber-200 rounded-xl overflow-hidden shadow-sm animate-in fade-in slide-in-from-top-2">
            <div className="p-4 flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
                <div className="flex items-start gap-3">
                    <div className="p-2 bg-amber-100 rounded-full text-amber-600 mt-1 md:mt-0">
                        <AlertTriangle size={20} />
                    </div>
                    <div>
                        <h4 className="font-bold text-amber-900 text-lg">
                            Atención: Faltan ventas para {analysis.total_dias_faltantes} días
                        </h4>
                        <p className="text-amber-700 text-sm mt-1">
                            Se detectaron días sin transacciones registradas en el periodo seleccionado.
                        </p>
                    </div>
                </div>

                <button
                    onClick={() => setExpanded(!expanded)}
                    className="flex items-center gap-2 px-4 py-2 bg-amber-100 hover:bg-amber-200 text-amber-800 rounded-lg text-sm font-semibold transition-colors whitespace-nowrap"
                >
                    {expanded ? 'Ocultar Causas' : 'Ver Causas Probables'}
                    {expanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                </button>
            </div>

            {expanded && (
                <div className="bg-amber-100/30 border-t border-amber-200 p-4">
                    <p className="text-xs font-bold text-amber-500 uppercase tracking-wider mb-3">
                        Detalle de Días Faltantes y Auditoría de Logs
                    </p>
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                        {analysis.detalle?.map((item, idx) => (
                            <div key={idx} className="bg-white/80 p-3 rounded-lg border border-amber-100 flex items-start gap-3">
                                {/* Icon based on cause */}
                                <div className="mt-0.5">
                                    {item.causa.includes("Fallo Técnico") ? (
                                        <ServerCrash size={16} className="text-rose-500" />
                                    ) : item.causa.includes("Archivo no disponible") ? (
                                        <SearchX size={16} className="text-orange-500" />
                                    ) : (
                                        <AlertTriangle size={16} className="text-slate-400" />
                                    )}
                                </div>
                                <div>
                                    <div className="text-sm font-bold text-slate-700">{item.fecha}</div>
                                    <div className={`text-xs font-medium mt-0.5 ${item.causa.includes("Fallo Técnico") ? "text-rose-600" :
                                        item.causa.includes("Archivo no disponible") ? "text-orange-600" :
                                            "text-slate-500"
                                        }`}>
                                        {item.causa}
                                    </div>
                                    {item.log_id && (
                                        <div className="text-[10px] text-slate-400 mt-1">
                                            Log ID: #{item.log_id}
                                        </div>
                                    )}
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
};
