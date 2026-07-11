import React, { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthProvider';
import { ApiService } from '../api';
import {
    TrendingUp, TrendingDown, Calendar,
    Download, Filter, ArrowRight, Activity,
    Store, Hash, CreditCard, Layers
} from 'lucide-react';

interface MetricCardProps {
    label: string;
    value: string | number;
    icon: React.ReactNode;
    color: string;
}

const MetricCard: React.FC<MetricCardProps> = ({ label, value, icon, color }) => (
    <div className="bg-white px-3 py-2.5 rounded-xl border border-slate-200 shadow-sm hover:shadow-md transition-shadow">
        <div className="flex items-center gap-3">
            <div className={`p-2 rounded-lg ${color}`}>
                {icon}
            </div>
            <div>
                <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">{label}</p>
                <p className="text-base font-bold text-slate-800 leading-tight">{value}</p>
            </div>
        </div>
    </div>
);

export const PeriodComparison: React.FC = () => {
    const { currentMall, session } = useAuth();
    const [loading, setLoading] = useState(true);
    const [data, setData] = useState<any>(null);
    const [error, setError] = useState<string | null>(null);
    const [tipo, setTipo] = useState<'MoM' | 'YoY' | 'WoW'>('MoM');
    const API_BASE = (import.meta.env.VITE_API_URL || '').trim();

    const buildEmptyData = () => ({
        mall_id: currentMall?.id || '',
        timezone: '',
        hoy_local: new Date().toISOString(),
        periodo_actual: {
            label: 'Periodo Actual',
            inicio: '-',
            fin: '-',
            datos: [],
            total_neto: 0,
            total_bruto: 0,
            transacciones: 0,
            ticket_promedio: 0
        },
        periodo_anterior: {
            label: 'Periodo Anterior',
            inicio: '-',
            fin: '-',
            datos: [],
            total_neto: 0,
            total_bruto: 0,
            transacciones: 0,
            ticket_promedio: 0
        },
        variacion_neto_porc: 0,
        tipo_comparativa: tipo
    });

    const getApiCandidates = () => {
        const normalized = API_BASE
            .replace(/\/+$/, '')
            .replace(/\/api\/v1$/i, '')
            .replace(/\/api$/i, '');
        const out = [];
        if (normalized) out.push(normalized);
        out.push(''); // relative fallback via Vercel rewrite
        return [...new Set(out)];
    };

    const fetchData = async () => {
        if (!currentMall?.id || !session?.access_token) {
            setLoading(false);
            setData(buildEmptyData());
            setError("No hay sesión o mall seleccionado para calcular comparativas.");
            return;
        }
        setLoading(true);
        setError(null);
        try {
            let loaded = false;
            let lastError = "No se pudo cargar la comparativa.";
            for (const base of getApiCandidates()) {
                const endpoint = `${base}/api/v1/comparisons/period-comparison?tipo=${tipo}`;
                const response = await fetch(endpoint, {
                    headers: {
                        'Authorization': `Bearer ${session.access_token}`,
                        'X-Mall-Id': currentMall.id,
                        'Accept': 'application/json'
                    },
                    cache: 'no-store'
                });

                const raw = await response.text();
                if (!response.ok) {
                    try {
                        const payload = JSON.parse(raw);
                        lastError = payload.detail || `Error ${response.status}`;
                    } catch {
                        lastError = `Error ${response.status}`;
                    }
                    continue;
                }

                if (!raw || raw.trim().startsWith('<')) {
                    lastError = "El endpoint devolvió HTML en lugar de JSON.";
                    continue;
                }

                let result: any = null;
                try {
                    result = JSON.parse(raw);
                } catch {
                    lastError = "Respuesta inválida del servidor (JSON malformado).";
                    continue;
                }

                if (!result?.periodo_actual || !result?.periodo_anterior) {
                    lastError = "El backend no devolvió estructura válida de comparativa.";
                    continue;
                }

                setData(result);
                loaded = true;
                break;
            }

            if (!loaded) {
                setData(buildEmptyData());
                setError(lastError);
            }
        } catch (error) {
            console.error("Error fetching comparison data:", error);
            setData(buildEmptyData());
            setError("No se pudo conectar con el backend de comparativas.");
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchData();
    }, [currentMall?.id, session?.access_token, tipo]);

    if (!currentMall?.id) {
        return (
            <div className="bg-white border border-slate-200 rounded-2xl p-4 text-slate-700">
                No hay mall asignado o seleccionado para mostrar comparativas.
            </div>
        );
    }

    const exportToCSV = () => {
        if (!data) return;

        const headers = ["Local", "Venta Actual (Neto)", "Venta Anterior (Neto)", "Diferencia $", "Variación %"];
        const rows = data.periodo_actual.datos.map((item: any) => {
            const prevItem = data.periodo_anterior.datos.find((p: any) => p.local_id === item.local_id) || { out_total_neto: 0 };
            const diff = (item.out_total_neto || 0) - (prevItem.out_total_neto || 0);
            const perc = (prevItem.out_total_neto || 0) > 0 ? (diff / prevItem.out_total_neto) * 100 : 100;

            return [
                item.local_nombre,
                (item.out_total_neto || 0).toFixed(2),
                (prevItem.out_total_neto || 0).toFixed(2),
                (diff || 0).toFixed(2),
                (perc || 0).toFixed(2) + "%"
            ];
        });

        const csvContent = [headers, ...rows].map(e => e.join(",")).join("\n");
        const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
        const link = document.createElement("a");
        const url = URL.createObjectURL(blob);
        link.setAttribute("href", url);
        link.setAttribute("download", `Comparativa_${tipo}_${new Date().toISOString().split('T')[0]}.csv`);
        link.style.visibility = 'hidden';
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
    };

    const formatCurrency = (val: number) => {
        const safeValue = Number.isFinite(val) ? val : 0;
        return `$${safeValue.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    };

    const formatInteger = (val: number) => {
        const safeValue = Number.isFinite(val) ? val : 0;
        return safeValue.toLocaleString('en-US', { maximumFractionDigits: 0 });
    };

    if (loading && !data) {
        return (
            <div className="flex flex-col items-center justify-center h-96">
                <Activity className="animate-spin text-indigo-600 mb-4" size={40} />
                <p className="text-slate-500 font-medium">Generando análisis comparativo...</p>
            </div>
        );
    }

    return (
        <div className="space-y-4 animate-in fade-in duration-500">
            {/* Header & Controls */}
            <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
                <div>
                    <h2 className="text-xl md:text-xl font-extrabold text-slate-900 tracking-tight">Comparativas de Rendimiento</h2>
                    <p className="text-slate-500 mt-0.5 text-sm">Análisis de crecimiento período vs período.</p>
                </div>

                <div className="w-full md:w-auto overflow-x-auto">
                    <div className="flex items-center gap-2 bg-white p-1 rounded-xl border border-slate-200 shadow-sm min-w-[560px] md:min-w-0">
                        <button
                            onClick={() => setTipo('WoW')}
                            className={`px-3 py-2 rounded-lg text-xs font-bold transition-all ${tipo === 'WoW' ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-200' : 'text-slate-400 hover:text-slate-600'}`}
                        >
                            Semana vs Semana (WoW)
                        </button>
                        <button
                            onClick={() => setTipo('MoM')}
                            className={`px-3 py-2 rounded-lg text-xs font-bold transition-all ${tipo === 'MoM' ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-200' : 'text-slate-400 hover:text-slate-600'}`}
                        >
                            Mes vs Mes (MoM)
                        </button>
                        <button
                            onClick={() => setTipo('YoY')}
                            className={`px-3 py-2 rounded-lg text-xs font-bold transition-all ${tipo === 'YoY' ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-200' : 'text-slate-400 hover:text-slate-600'}`}
                        >
                            Año vs Año (YoY)
                        </button>
                        <div className="w-px h-6 bg-slate-200 mx-1"></div>
                        <button
                            onClick={exportToCSV}
                            className="flex items-center gap-2 px-3 py-2 bg-indigo-600 text-white rounded-lg text-xs font-bold hover:bg-indigo-700 transition-all active:scale-95"
                        >
                            <Download size={14} /> Exportar
                        </button>
                    </div>
                </div>
            </div>
            {error && (
                <div className="bg-amber-50 border border-amber-200 text-amber-800 rounded-xl px-4 py-3 text-sm font-medium">
                    {error}
                </div>
            )}

            {/* Hero Stats */}
            {data && (
                <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                    <div className="bg-indigo-600 rounded-2xl p-4 text-white shadow-lg shadow-indigo-200 col-span-1 md:col-span-2 relative overflow-hidden group">
                        <div className="absolute -right-10 -top-10 w-40 h-40 bg-white/10 rounded-full blur-3xl group-hover:scale-150 transition-transform duration-700"></div>
                        <div className="relative z-10">
                            <div className="flex items-center gap-2 text-indigo-100/80 text-[10px] font-bold uppercase tracking-widest mb-4">
                                <Activity size={14} /> Variación Ventas Brutas (Neto)
                            </div>
                            <div className="flex items-baseline gap-3">
                                <h3 className="text-3xl font-black leading-none">{(data?.variacion_neto_porc || 0).toFixed(1)}%</h3>
                                {(data?.variacion_neto_porc || 0) >= 0 ?
                                    <TrendingUp className="text-emerald-400" size={32} /> :
                                    <TrendingDown className="text-rose-400" size={32} />
                                }
                            </div>
                            <p className="mt-3 text-indigo-100 text-xs leading-5 max-w-md">
                                {data.variacion_neto_porc >= 0
                                    ? "Excelente desempeño. El crecimiento refleja una tendencia positiva en el volumen de transacciones."
                                    : "Se detecta una contracción en el periodo. Se recomienda revisar el ticket promedio y rubros críticos."
                                }
                            </p>
                        </div>
                    </div>

                    <div className="col-span-1 md:col-span-2 grid grid-cols-1 sm:grid-cols-2 gap-4">
                        <MetricCard
                            label="Venta Bruta Actual"
                            value={formatCurrency(data?.periodo_actual?.total_neto || 0)}
                            icon={<CreditCard className="text-indigo-600" size={24} />}
                            color="bg-indigo-50"
                        />
                        <MetricCard
                            label="Venta Bruta Anterior"
                            value={formatCurrency(data?.periodo_anterior?.total_neto || 0)}
                            icon={<Layers className="text-slate-600" size={24} />}
                            color="bg-slate-100"
                        />
                        <MetricCard
                            label="Transacciones"
                            value={formatInteger(data?.periodo_actual?.transacciones || 0)}
                            icon={<Hash className="text-amber-600" size={24} />}
                            color="bg-amber-50"
                        />
                        <MetricCard
                            label="Ticket Promedio"
                            value={formatCurrency(data?.periodo_actual?.ticket_promedio || 0)}
                            icon={<Store className="text-emerald-600" size={24} />}
                            color="bg-emerald-50"
                        />
                    </div>
                </div>
            )}

            {/* Details Table */}
            {data && (
                <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
                    <div className="px-4 py-3 border-b border-slate-100 flex flex-col md:flex-row justify-between items-start md:items-center gap-3 bg-slate-50/50">
                        <div className="flex items-center gap-3">
                            <div className="p-2.5 bg-indigo-100 text-indigo-700 rounded-xl">
                                <Filter size={18} />
                            </div>
                            <h4 className="font-bold text-slate-800">Desglose por Local</h4>
                        </div>
                        <div className="text-[10px] font-bold text-slate-400 uppercase tracking-widest flex items-center gap-2">
                            <Calendar size={12} /> {data.periodo_actual.inicio} <ArrowRight size={10} /> {data.periodo_actual.fin}
                        </div>
                    </div>

                    <div className="max-h-[calc(100dvh-31rem)] min-h-[220px] overflow-auto">
                        <table className="w-full min-w-[760px] text-left">
                            <thead className="sticky top-0 z-10 bg-white">
                                <tr className="border-b border-slate-100">
                                    <th className="px-4 py-3 text-[10px] font-bold text-slate-400 uppercase tracking-widest">Local</th>
                                    <th className="px-4 py-3 text-[10px] font-bold text-slate-400 uppercase tracking-widest">Venta Actual</th>
                                    <th className="px-4 py-3 text-[10px] font-bold text-slate-400 uppercase tracking-widest">Venta Anterior</th>
                                    <th className="px-4 py-3 text-[10px] font-bold text-slate-400 uppercase tracking-widest text-right">Variación %</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-50">
                                {(data?.periodo_actual?.datos || []).map((item: any) => {
                                    const prevItem = (data?.periodo_anterior?.datos || []).find((p: any) => p.local_id === item.local_id) || { out_total_neto: 0 };
                                    const diff = (item.out_total_neto || 0) - (prevItem.out_total_neto || 0);
                                    const vPorc = (prevItem.out_total_neto || 0) > 0 ? (diff / prevItem.out_total_neto) * 100 : 100;

                                    return (
                                        <tr key={item.local_id} className="hover:bg-slate-50 transition-colors group">
                                            <td className="px-4 py-2.5">
                                                <div className="flex items-center gap-3">
                                                    <div className="w-8 h-8 rounded-full bg-indigo-50 flex items-center justify-center text-[10px] font-bold text-indigo-600 group-hover:bg-indigo-600 group-hover:text-white transition-all">
                                                        {item.local_nombre.substring(0, 2).toUpperCase()}
                                                    </div>
                                                    <div>
                                                        <p className="text-sm font-bold text-slate-800">{item.local_nombre}</p>
                                                        <p className="text-[10px] text-slate-400 font-medium uppercase tracking-tighter">{item.rubro || 'General'}</p>
                                                    </div>
                                                </div>
                                            </td>
                                            <td className="px-4 py-2.5 text-sm font-semibold text-slate-700">{formatCurrency(item.out_total_neto || 0)}</td>
                                            <td className="px-4 py-2.5 text-sm text-slate-400">{formatCurrency(prevItem.out_total_neto || 0)}</td>
                                            <td className="px-4 py-2.5 text-right">
                                                <div className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-[11px] font-bold ${vPorc >= 0 ? 'bg-emerald-50 text-emerald-600' : 'bg-rose-50 text-rose-600'}`}>
                                                    {vPorc >= 0 ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
                                                    {vPorc.toFixed(1)}%
                                                </div>
                                            </td>
                                        </tr>
                                    );
                                })}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}
        </div>
    );
};
