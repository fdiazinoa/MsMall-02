import React, { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthProvider';
import {
    ScatterChart, Scatter, XAxis, YAxis, ZAxis,
    CartesianGrid, Tooltip, ResponsiveContainer,
    ReferenceLine, Label, Cell
} from 'recharts';
import {
    TrendingUp, AlertCircle, DollarSign,
    ArrowUpRight, PieChart, Users, Info,
    FileSpreadsheet, FileText, Loader2, Calendar, ArrowRight
} from 'lucide-react';
import { ApiService } from '../api';
import { useFormatCurrency } from '../hooks/useFormatCurrency';

export const FinancialDashboard: React.FC = () => {
    const { currentMall, session } = useAuth();
    const { format } = useFormatCurrency();
    const [data, setData] = useState<any[]>([]);
    const [loading, setLoading] = useState(true);
    const [isExporting, setIsExporting] = useState(false);

    // Date state
    const [dates, setDates] = useState<{ startDate: string, endDate: string }>(() => {
        const now = new Date();
        const start = new Date(now.getFullYear(), now.getMonth(), 1).toISOString().split('T')[0];
        const end = new Date(now.getFullYear(), now.getMonth() + 1, 0).toISOString().split('T')[0];
        return { startDate: start, endDate: end };
    });

    const fetchFinancialData = async () => {
        if (!currentMall || !session?.access_token) {
            setData([]);
            setLoading(false);
            return;
        }
        setLoading(true);
        try {
            const [stores, kpiData] = await Promise.all([
                ApiService.getStores(currentMall.id),
                ApiService.getKPIs({ startDate: dates.startDate, endDate: dates.endDate, mallId: currentMall.id }, session.access_token)
            ]);
            const salesMap = kpiData.ventas_por_tienda_completo || {};

            const parseNum = (value: any): number => {
                if (value === null || value === undefined) return 0;
                if (typeof value === 'number') return Number.isFinite(value) ? value : 0;

                let raw = String(value).trim();
                if (!raw) return 0;

                // Remove currency/percent/letters, keep separators and sign.
                raw = raw.replace(/[^\d.,-]/g, '');
                if (!raw) return 0;

                const hasDot = raw.includes('.');
                const hasComma = raw.includes(',');

                let normalized = raw;
                if (hasDot && hasComma) {
                    // Decide decimal separator by the last symbol.
                    if (raw.lastIndexOf(',') > raw.lastIndexOf('.')) {
                        // 1.234.567,89 => 1234567.89
                        normalized = raw.replace(/\./g, '').replace(',', '.');
                    } else {
                        // 1,234,567.89 => 1234567.89
                        normalized = raw.replace(/,/g, '');
                    }
                } else if (hasComma) {
                    // 2,50 or 1,234,567
                    const commaGroups = raw.split(',');
                    const looksThousands = commaGroups.length > 1 && commaGroups.slice(1).every(g => g.length === 3);
                    normalized = looksThousands ? raw.replace(/,/g, '') : raw.replace(',', '.');
                }

                const n = Number(normalized);
                return Number.isFinite(n) ? n : 0;
            };

            const processed = stores.map(s => {
                const ventaActual = salesMap[s.nombre] || 0;

                // Simple projection (keep as is for now, or improve)
                const proyeccion = ventaActual;
                const rentaFija = parseNum(s.renta_fija);
                const breakpoint = parseNum(s.breakpoint_venta);
                const pctVar = parseNum(s.porcentaje_variable ?? s.porciento_renta);

                // If fixed rent is missing, estimate occupancy using variable % as proxy.
                const ocr = ventaActual > 0
                    ? ((rentaFija > 0 ? rentaFija : (ventaActual * pctVar / 100)) / ventaActual) * 100
                    : 0;

                let rentaVariable = 0;
                if (pctVar > 0) {
                    const aplicaVariable = breakpoint <= 0 || proyeccion > breakpoint;
                    if (aplicaVariable) {
                        const rentaTeorica = (proyeccion * pctVar) / 100;
                        // If fixed rent exists, variable is the excess. Otherwise show theoretical variable.
                        rentaVariable = rentaFija > 0
                            ? Math.max(0, rentaTeorica - rentaFija)
                            : Math.max(0, rentaTeorica);
                    }
                }

                return {
                    id: s.id,
                    name: s.nombre,
                    venta: ventaActual,
                    proyeccion,
                    ocr,
                    rentaVariable,
                    pctVar,
                    breakpoint,
                    m2: Number(s.mts) || 1
                };
            });
            setData(processed);
        } catch (error) {
            console.error("Error loading financial data:", error);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchFinancialData();
    }, [dates, currentMall?.id, session?.access_token]); // Refetch when dates/auth context change

    if (!currentMall?.id) {
        return (
            <div className="bg-white border border-slate-200 rounded-2xl p-6 text-slate-700">
                No hay mall asignado o seleccionado para ver salud financiera.
            </div>
        );
    }

    const handleExport = async (type: 'excel' | 'pdf') => {
        if (!currentMall) return;
        setIsExporting(true);
        try {
            const endpoint = type === 'excel' ? 'excel' : 'pdf';
            const ext = type === 'excel' ? 'xlsx' : 'pdf';
            const params = new URLSearchParams({
                fecha_inicio: dates.startDate,
                fecha_fin: dates.endDate
            });

            const token = session?.access_token;
            const headers: HeadersInit = {
                'X-Mall-Id': currentMall.id
            };
            if (token) headers['Authorization'] = `Bearer ${token}`;

            const response = await fetch(`${import.meta.env.VITE_API_URL || ''}/api/v1/export/financial-dashboard/${endpoint}?${params.toString()}`, {
                headers
            });

            if (!response.ok) throw new Error("Export failed");

            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `salud_cartera_${dates.startDate}_${dates.endDate}.${ext}`;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);
        } catch (e) {
            console.error(e);
            alert("Error al exportar");
        } finally {
            setIsExporting(false);
        }
    };

    if (loading && !data.length) return <div className="h-64 flex items-center justify-center"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600"></div></div>;

    const avgSalesM2 = data.length > 0
        ? data.reduce((acc, curr) => acc + (curr.venta / curr.m2), 0) / data.length
        : 0;
    const storesAtRisk = data.filter(s => s.ocr > 20).length;
    const projectionRows = [...data]
        .filter(s => (s.venta > 0) || (s.proyeccion > 0) || (s.rentaVariable > 0))
        .sort((a, b) => (b.rentaVariable - a.rentaVariable) || (b.proyeccion - a.proyeccion));
    const hasProjectedVariable = projectionRows.some(row => row.rentaVariable > 0);

    return (
        <div className="space-y-8 animate-in fade-in duration-500">
            {/* Header with Filters & Exports */}
            <div className="bg-white p-6 rounded-3xl border border-slate-100 shadow-sm flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
                <div>
                    <h2 className="text-xl font-bold text-slate-800">Salud Financiera</h2>
                    <p className="text-slate-500 text-sm">Análisis de OCR y Proyecciones</p>
                </div>
                <div className="flex flex-wrap items-center gap-3 w-full md:w-auto">
                    <div className="flex flex-col sm:flex-row sm:items-center gap-2 bg-slate-50 p-2 rounded-xl border border-slate-200 w-full md:w-auto">
                        <Calendar size={16} className="text-slate-400" />
                        <input
                            type="date"
                            className="bg-transparent border-none text-sm outline-none w-full sm:w-32 text-slate-600"
                            value={dates.startDate}
                            onChange={(e) => setDates({ ...dates, startDate: e.target.value })}
                        />
                        <ArrowRight size={14} className="text-slate-300 hidden sm:block" />
                        <input
                            type="date"
                            className="bg-transparent border-none text-sm outline-none w-full sm:w-32 text-slate-600"
                            value={dates.endDate}
                            onChange={(e) => setDates({ ...dates, endDate: e.target.value })}
                        />
                    </div>

                    <button
                        onClick={() => handleExport('excel')}
                        disabled={isExporting}
                        className="flex items-center gap-2 px-3 py-2 bg-emerald-600 text-white rounded-lg text-sm font-medium hover:bg-emerald-700 transition-colors disabled:opacity-50"
                        title="Exportar Excel"
                    >
                        {isExporting ? <Loader2 size={16} className="animate-spin" /> : <FileSpreadsheet size={16} />}
                    </button>
                    <button
                        onClick={() => handleExport('pdf')}
                        disabled={isExporting}
                        className="flex items-center gap-2 px-3 py-2 bg-rose-600 text-white rounded-lg text-sm font-medium hover:bg-rose-700 transition-colors disabled:opacity-50"
                        title="Exportar PDF"
                    >
                        {isExporting ? <Loader2 size={16} className="animate-spin" /> : <FileText size={16} />}
                    </button>
                </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                <div className="bg-white p-6 rounded-3xl border border-slate-100 shadow-sm relative group">
                    <div className="absolute top-6 right-6 text-slate-300 hover:text-indigo-500 transition-colors cursor-help">
                        <Info size={16} />
                        <div className="absolute right-0 w-64 p-3 mt-2 text-xs text-white bg-slate-800 rounded-lg opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-10 shadow-lg top-full">
                            Fórmula: Σ(Ventas Locales) / Σ(Metros Cuadrados). Indica la eficiencia promedio de generación de ingresos por espacio físico.
                        </div>
                    </div>
                    <div className="p-2 bg-indigo-50 text-indigo-600 w-fit rounded-xl mb-4"><DollarSign size={20} /></div>
                    <p className="text-slate-500 text-sm font-medium">Venta Prom m² Mall</p>
                    <h3 className="text-2xl font-bold text-slate-900 mt-1">{format(avgSalesM2)}</h3>
                </div>
                <div className="bg-white p-6 rounded-3xl border border-slate-100 shadow-sm relative group">
                    <div className="absolute top-6 right-6 text-slate-300 hover:text-red-500 transition-colors cursor-help">
                        <Info size={16} />
                        <div className="absolute right-0 w-64 p-3 mt-2 text-xs text-white bg-slate-800 rounded-lg opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-10 shadow-lg top-full">
                            Fórmula OCR: (Renta Fija / Ventas) * 100. Un OCR {'>'} 20% indica alto esfuerzo financiero.
                        </div>
                    </div>
                    <div className="p-2 bg-red-50 text-red-600 w-fit rounded-xl mb-4"><AlertCircle size={20} /></div>
                    <p className="text-slate-500 text-sm font-medium">Locales en Riesgo (OCR {'>'} 20%)</p>
                    <h3 className="text-2xl font-bold text-slate-900 mt-1">{storesAtRisk} Locales</h3>
                </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
                {/* Scatter Plot: Salud de Cartera */}
                <div className="bg-white p-8 rounded-3xl border border-slate-100 shadow-sm">
                    <h3 className="text-lg font-bold text-slate-800 mb-6 flex items-center gap-2">
                        <PieChart className="text-indigo-500" size={20} />
                        Salud de Cartera (Ventas vs OCR)
                    </h3>
                    <div className="bg-slate-50/50 rounded-2xl p-6 border border-slate-100 flex flex-col">
                        {/* HTML Legend to confirm data is present */}
                        <div className="flex flex-wrap gap-2 mb-6">
                            {data.map((d, i) => (
                                <div key={i} className="flex items-center gap-1.5 bg-white px-3 py-1 rounded-full border border-slate-200 shadow-sm">
                                    <div className={`w-2 h-2 rounded-full ${d.ocr > 20 ? 'bg-rose-500' : 'bg-indigo-600'}`} />
                                    <span className="text-[10px] font-bold text-slate-700">{d.name}</span>
                                    <span className="text-[10px] text-indigo-600 font-bold font-mono ml-1">{d.ocr.toFixed(1)}%</span>
                                </div>
                            ))}
                        </div>

                        <div className="h-[300px] w-full">
                            <ResponsiveContainer width="100%" height="100%">
                                <ScatterChart margin={{ top: 10, right: 30, bottom: 40, left: 10 }}>
                                    <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
                                    <XAxis
                                        type="number"
                                        dataKey="venta"
                                        name="Ventas"
                                        tickFormatter={(val) => `$${(val / 1000).toFixed(0)}k`}
                                        domain={['auto', 'auto']}
                                        axisLine={{ stroke: '#cbd5e1' }}
                                        tick={{ fontSize: 10, fill: '#475569', fontWeight: 600 }}
                                        tickLine={{ stroke: '#cbd5e1' }}
                                    />
                                    <YAxis
                                        type="number"
                                        dataKey="ocr"
                                        name="OCR"
                                        unit="%"
                                        domain={[0, 25]}
                                        axisLine={{ stroke: '#cbd5e1' }}
                                        tick={{ fontSize: 10, fill: '#475569', fontWeight: 600 }}
                                        tickLine={{ stroke: '#cbd5e1' }}
                                    />
                                    <ZAxis type="number" range={[100, 100]} />
                                    <Tooltip
                                        cursor={{ strokeDasharray: '3 3' }}
                                        content={({ active, payload }) => {
                                            if (active && payload && payload.length) {
                                                const item = payload[0].payload;
                                                return (
                                                    <div className="bg-white p-3 border border-slate-200 shadow-xl rounded-xl text-xs">
                                                        <p className="font-bold text-slate-900 border-b border-slate-100 pb-1 mb-1">{item.name}</p>
                                                        <p className="text-slate-600">Venta: <span className="font-mono text-indigo-600 font-bold">{format(item.venta)}</span></p>
                                                        <p className="text-slate-600">OCR: <span className="font-mono text-indigo-600 font-bold">{item.ocr.toFixed(2)}%</span></p>
                                                    </div>
                                                );
                                            }
                                            return null;
                                        }}
                                    />
                                    <ReferenceLine y={20} stroke="#f43f5e" strokeDasharray="5 5" strokeWidth={2}>
                                        <Label value="RIESGO 20%" position="insideTopRight" fill="#f43f5e" fontSize={10} fontWeight="bold" />
                                    </ReferenceLine>
                                    <Scatter name="Locales" data={data}>
                                        {data.map((entry, index) => (
                                            <Cell
                                                key={`cell-${index}`}
                                                fill={entry.ocr > 20 ? '#f43f5e' : '#4f46e5'}
                                                stroke="#fff"
                                                strokeWidth={2}
                                            />
                                        ))}
                                    </Scatter>
                                </ScatterChart>
                            </ResponsiveContainer>
                        </div>
                    </div>
                </div>

                {/* Table: Proyección de Recaudación */}
                <div className="bg-white p-4 sm:p-8 rounded-3xl border border-slate-100 shadow-sm overflow-hidden">
                    <h3 className="text-lg font-bold text-slate-800 mb-6 flex items-center gap-2">
                        <TrendingUp className="text-indigo-500" size={20} />
                        Proyección de Recaudación (Variable)
                    </h3>
                    <div className="overflow-x-auto">
                        <table className="w-full min-w-[620px] text-left">
                            <thead>
                                <tr className="text-xs font-bold text-slate-400 uppercase tracking-wider border-b border-slate-50">
                                    <th className="pb-4">Local</th>
                                    <th className="pb-4">Venta Actual</th>
                                    <th className="pb-4">Proyección</th>
                                    <th className="pb-4 text-right">Renta Var. Est.</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-50">
                                {projectionRows.map((row) => (
                                    <tr key={row.id} className="text-sm hover:bg-slate-50/50 transition-colors">
                                        <td className="py-4 font-semibold text-slate-700">{row.name}</td>
                                        <td className="py-4 text-slate-500">{format(row.venta)}</td>
                                        <td className="py-4 text-slate-500">{format(row.proyeccion)}</td>
                                        <td className={`py-4 text-right font-bold ${row.rentaVariable > 0 ? 'text-indigo-600' : 'text-slate-400'}`}>
                                            {format(row.rentaVariable)}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                    {projectionRows.length === 0 && (
                        <p className="text-center text-slate-400 text-sm py-8">No hay ventas en el periodo para calcular proyecciones.</p>
                    )}
                    {projectionRows.length > 0 && !hasProjectedVariable && (
                        <p className="text-center text-slate-400 text-sm py-8">Hay ventas registradas, pero la renta variable estimada es 0 para los locales en este periodo.</p>
                    )}
                </div>
            </div>
        </div>
    );
};
