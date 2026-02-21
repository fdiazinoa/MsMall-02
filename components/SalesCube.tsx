import React, { useEffect, useState } from 'react';
import { useAuth } from '../context/AuthProvider';
import { ApiService } from '../api';
import {
    Calendar, Filter, TrendingUp, DollarSign,
    ArrowRight, Loader2, Download, Archive, FileSpreadsheet
} from 'lucide-react';
import { DateRange } from '../types';
import { useFormatCurrency } from '../hooks/useFormatCurrency';

const DEFAULT_RAILWAY_BASE_URL = 'https://msmall-02-production.up.railway.app';

const normalizeBase = (value: string): string => {
    const trimmed = (value || '').trim();
    if (!trimmed) return '';
    return trimmed.replace(/\/+$/, '').replace(/\/api\/v1$/i, '').replace(/\/api$/i, '');
};

export const SalesCube: React.FC = () => {
    const { currentMall, session } = useAuth();
    const { format } = useFormatCurrency();
    const [loading, setLoading] = useState(false);
    const [cubeData, setCubeData] = useState<any>(null);
    const [isExporting, setIsExporting] = useState(false);
    const [dates, setDates] = useState<DateRange>(() => {
        const now = new Date();
        const firstDay = new Date(now.getFullYear(), now.getMonth(), 1);
        return {
            startDate: firstDay.toISOString().split('T')[0],
            endDate: now.toISOString().split('T')[0]
        };
    });
    const [grouping, setGrouping] = useState<'DIA' | 'SEMANA' | 'MES'>('DIA');
    const [metric, setMetric] = useState<'total_neto' | 'total_bruto' | 'transacciones'>('total_neto');
    const [stores, setStores] = useState<any[]>([]);
    const [selectedLocal, setSelectedLocal] = useState<string>('');

    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        const loadStores = async () => {
            if (!currentMall?.id) {
                setStores([]);
                setSelectedLocal('');
                return;
            }
            try {
                const locals = await ApiService.getStores(currentMall.id);
                setStores(locals || []);
                // Keep selected value only if still present in current mall.
                if (selectedLocal && !(locals || []).some((s: any) => s.id === selectedLocal)) {
                    setSelectedLocal('');
                }
            } catch (e) {
                console.error("Error loading stores for SalesCube:", e);
                setStores([]);
            }
        };
        loadStores();
    }, [currentMall?.id]);

    const generateCube = async () => {
        if (!currentMall?.id || !session?.access_token) return;
        setLoading(true);
        setError(null);
        try {
            const data = await ApiService.getSalesCube({
                fecha_inicio: dates.startDate,
                fecha_fin: dates.endDate,
                agrupacion: grouping,
                metrica: metric,
                local_id: selectedLocal || null,
                mallId: currentMall.id
            }, session.access_token);
            setCubeData(data);
        } catch (err: any) {
            console.error("Error generating cube:", err);
            setError("No se pudo conectar con el servidor. Verifica que el backend esté corriendo.");
        } finally {
            setLoading(false);
        }
    };

    const handleExportExcel = async () => {
        if (!currentMall) return;
        setIsExporting(true);
        try {
            const params = new URLSearchParams({
                fecha_inicio: dates.startDate,
                fecha_fin: dates.endDate,
                agrupacion: grouping.toLowerCase(),
                metrica: metric
            });
            if (selectedLocal) {
                params.append('local_id', selectedLocal);
            }

            const token = session?.access_token;
            const headers: HeadersInit = { 'X-Mall-Id': currentMall.id };
            if (token) headers['Authorization'] = `Bearer ${token}`;

            const configuredApiBase = normalizeBase(import.meta.env.VITE_API_URL || '');
            const directApiBase = normalizeBase(import.meta.env.VITE_DIRECT_BACKEND_BASE_URL || '');
            const isVercelHost = typeof window !== 'undefined' && window.location.hostname.endsWith('vercel.app');

            const baseCandidates = Array.from(new Set([
                configuredApiBase,
                directApiBase,
                ...(isVercelHost ? [DEFAULT_RAILWAY_BASE_URL] : []),
                '' // relative fallback
            ]));

            let downloadedBlob: Blob | null = null;
            let lastError = 'No se pudo exportar el archivo Excel del cubo.';

            for (const base of baseCandidates) {
                const endpoint = `${base}/api/v1/export/sales-cube/excel?${params.toString()}`;
                try {
                    const response = await fetch(endpoint, { headers });
                    if (!response.ok) {
                        lastError = `Export failed (${response.status})`;
                        continue;
                    }

                    const contentType = (response.headers.get('content-type') || '').toLowerCase();
                    const blob = await response.blob();

                    const looksLikeExcel =
                        contentType.includes('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet') ||
                        contentType.includes('application/octet-stream');

                    if (!looksLikeExcel) {
                        const rawText = (await blob.text()).slice(0, 200).toLowerCase();
                        if (rawText.includes('<!doctype html') || rawText.includes('<html')) {
                            lastError = 'El servidor devolvió HTML en lugar de Excel. Verifica la URL del backend.';
                            continue;
                        }
                    }

                    downloadedBlob = blob;
                    break;
                } catch (err: any) {
                    lastError = err?.message || lastError;
                }
            }

            if (!downloadedBlob) {
                throw new Error(lastError);
            }

            const url = window.URL.createObjectURL(downloadedBlob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `matriz_ventas_${dates.startDate}_${dates.endDate}.xlsx`;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);
        } catch (e) {
            console.error(e);
            alert(`Error al exportar: ${e instanceof Error ? e.message : 'fallo desconocido'}`);
        } finally {
            setIsExporting(false);
        }
    };

    const formatValue = (val: number) => {
        if (metric === 'transacciones') return val.toLocaleString();
        return format(val);
    };

    const totalPeriodo = (() => {
        if (!cubeData?.grand_totals) return 0;
        if (typeof cubeData.grand_totals.TOTAL_FILA === 'number') {
            return cubeData.grand_totals.TOTAL_FILA;
        }
        return Object.entries(cubeData.grand_totals).reduce((acc: number, [key, value]: [string, any]) => {
            if (key === 'TOTAL_FILA') return acc;
            return acc + (typeof value === 'number' ? value : 0);
        }, 0);
    })();

    return (
        <div className="space-y-6 animate-in fade-in duration-500">
            {/* Control Bar */}
            <div className="bg-white p-6 rounded-3xl border border-slate-100 shadow-sm flex flex-wrap gap-6 items-end">
                <div>
                    {/* ... existing date inputs ... */}
                    <label className="block text-xs font-bold text-slate-400 mb-2 uppercase">Rango de Fechas</label>
                    <div className="flex items-center gap-2 bg-slate-50 p-2 rounded-xl border border-slate-200">
                        <Calendar size={16} className="text-slate-400" />
                        <input
                            type="date"
                            className="bg-transparent border-none text-sm outline-none w-32 text-slate-600"
                            value={dates.startDate}
                            onChange={(e) => setDates({ ...dates, startDate: e.target.value })}
                        />
                        <ArrowRight size={14} className="text-slate-300" />
                        <input
                            type="date"
                            className="bg-transparent border-none text-sm outline-none w-32 text-slate-600"
                            value={dates.endDate}
                            onChange={(e) => setDates({ ...dates, endDate: e.target.value })}
                        />
                    </div>
                </div>

                <div>
                    <label className="block text-xs font-bold text-slate-400 mb-2 uppercase">Agrupación</label>
                    <div className="flex p-1 bg-slate-100 rounded-xl">
                        {['DIA', 'SEMANA', 'MES'].map((g) => (
                            <button
                                key={g}
                                onClick={() => setGrouping(g as any)}
                                className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${grouping === g ? 'bg-white text-indigo-600 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}
                            >
                                {g}
                            </button>
                        ))}
                    </div>
                </div>

                <div>
                    <label className="block text-xs font-bold text-slate-400 mb-2 uppercase">Métrica</label>
                    <select
                        value={metric}
                        onChange={(e) => setMetric(e.target.value as any)}
                        className="bg-slate-50 border border-slate-200 text-slate-700 text-sm rounded-xl focus:ring-indigo-500 focus:border-indigo-500 block w-full p-2.5 outline-none"
                    >
                        <option value="total_neto">Venta Bruta (Base)</option>
                        <option value="total_bruto">Venta Neta (Total)</option>
                        <option value="transacciones">Transacciones</option>
                    </select>
                </div>

                <div>
                    <label className="block text-xs font-bold text-slate-400 mb-2 uppercase">Cliente</label>
                    <select
                        value={selectedLocal}
                        onChange={(e) => setSelectedLocal(e.target.value)}
                        className="bg-slate-50 border border-slate-200 text-slate-700 text-sm rounded-xl focus:ring-indigo-500 focus:border-indigo-500 block w-full p-2.5 outline-none min-w-[220px]"
                    >
                        <option value="">Todos los Clientes</option>
                        {stores.map((store) => (
                            <option key={store.id} value={store.id}>
                                {store.nombre}
                            </option>
                        ))}
                    </select>
                </div>

                <div className="ml-auto flex gap-2">
                    <button
                        onClick={handleExportExcel}
                        disabled={isExporting}
                        className="bg-emerald-600 hover:bg-emerald-700 text-white font-bold py-3 px-4 rounded-xl flex items-center gap-2 transition-colors disabled:opacity-50"
                        title="Exportar Excel"
                    >
                        {isExporting ? <Loader2 className="animate-spin" size={20} /> : <FileSpreadsheet size={20} />}
                    </button>

                    <button
                        onClick={generateCube}
                        className="bg-indigo-600 hover:bg-indigo-700 text-white font-bold py-3 px-6 rounded-xl flex items-center gap-2 transition-colors disabled:opacity-50"
                        disabled={loading}
                    >
                        {loading ? <Loader2 className="animate-spin" size={20} /> : <TrendingUp size={20} />}
                        Generar Cubo
                    </button>
                </div>
            </div>

            {error && (
                <div className="bg-red-50 text-red-600 p-4 rounded-xl border border-red-100 flex items-center gap-2">
                    <span className="font-bold">Error:</span> {error}
                </div>
            )}

            {/* Matrix View */}
            {cubeData && (
                <div className="bg-white rounded-3xl border border-slate-100 shadow-sm overflow-hidden flex flex-col h-[600px]">
                    <div className="p-6 border-b border-slate-50 flex justify-between items-center">
                        <div className="flex items-center gap-3">
                            <div className="p-2 bg-emerald-50 text-emerald-600 rounded-lg">
                                <Archive size={20} />
                            </div>
                            <div>
                                <h3 className="font-bold text-slate-800 text-lg">Matriz de Ventas</h3>
                                <p className="text-slate-500 text-xs">Vista dinámica pivotada</p>
                            </div>
                        </div>
                        <div className="flex gap-4 text-sm">
                            <div className="flex flex-col items-end">
                                <span className="text-slate-400 text-xs uppercase font-bold">Total Periodo</span>
                                <span className="font-bold text-slate-800 text-lg">{formatValue(totalPeriodo as number)}</span>
                            </div>
                        </div>
                    </div>

                    <div className="flex-1 overflow-auto relative">
                        <table className="w-full text-left border-collapse">
                            <thead className="bg-slate-50 sticky top-0 z-20 shadow-sm">
                                <tr>
                                    {cubeData.columns.map((col: string, idx: number) => (
                                        <th
                                            key={idx}
                                            className={`p-4 text-xs font-bold text-slate-500 uppercase tracking-wider border-b border-slate-200 whitespace-nowrap ${idx === 0 ? 'sticky left-0 bg-slate-50 z-30 border-r' : 'text-right'}`}
                                        >
                                            {col === 'local_nombre' ? 'Local' : col.replace('TOTAL_FILA', 'Total')}
                                        </th>
                                    ))}
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-50">
                                {cubeData.data.map((row: any, rIdx: number) => (
                                    <tr key={rIdx} className="hover:bg-indigo-50/30 transition-colors">
                                        {cubeData.columns.map((col: string, cIdx: number) => {
                                            const val = row[col];
                                            const isZero = val === 0 || !val;
                                            const isTotal = col === 'TOTAL_FILA';
                                            const isSticky = cIdx === 0;

                                            return (
                                                <td
                                                    key={cIdx}
                                                    className={`p-4 text-sm whitespace-nowrap border-b border-slate-50
                                                        ${isSticky ? 'sticky left-0 bg-white font-bold text-slate-700 z-10 border-r border-slate-100' : 'text-right'}
                                                        ${isTotal ? 'bg-slate-50 font-bold text-indigo-700' : ''}
                                                    `}
                                                >
                                                    {isSticky ? val : (
                                                        <span className={isZero ? 'text-slate-300 font-light' : 'text-slate-600 font-medium'}>
                                                            {isZero ? '-' : formatValue(val)}
                                                        </span>
                                                    )}
                                                </td>
                                            );
                                        })}
                                    </tr>
                                ))}
                            </tbody>
                            <tfoot className="bg-slate-100 sticky bottom-0 z-20 shadow-[0_-4px_6px_-1px_rgba(0,0,0,0.1)]">
                                <tr>
                                    {cubeData.columns.map((col: string, idx: number) => (
                                        <td
                                            key={col}
                                            className={`p-4 text-sm font-bold text-slate-800 border-t border-slate-300
                                                ${idx === 0 ? 'sticky left-0 bg-slate-100 z-30 border-r' : 'text-right'}
                                            `}
                                        >
                                            {idx === 0 ? 'TOTAL GENERAL' : formatValue(cubeData.grand_totals[col] || 0)}
                                        </td>
                                    ))}
                                </tr>
                            </tfoot>
                        </table>
                    </div>
                </div>
            )}
        </div>
    );
};
