import React, { useEffect, useState } from 'react';
import {
    Bar,
    BarChart,
    CartesianGrid,
    Cell,
    ReferenceLine,
    ResponsiveContainer,
    Tooltip,
    XAxis,
    YAxis
} from 'recharts';
import {
    AlertCircle,
    ArrowRight,
    Calendar,
    DollarSign,
    FileSpreadsheet,
    FileText,
    Info,
    Loader2,
    PieChart,
    Target,
    TrendingUp
} from 'lucide-react';

import { ApiService } from '../api';
import { useAuth } from '../context/AuthProvider';
import { useFormatCurrency } from '../hooks/useFormatCurrency';

const DAY_MS = 24 * 60 * 60 * 1000;

const parseDateInput = (value: string): Date => new Date(`${value}T12:00:00`);

const diffDaysInclusive = (start: Date, end: Date): number => {
    if (end < start) return 0;
    return Math.floor((end.getTime() - start.getTime()) / DAY_MS) + 1;
};

const getRiskMeta = (ocr: number) => {
    if (ocr > 20) {
        return {
            label: 'Riesgo',
            color: '#ef4444',
            badge: 'bg-rose-100 text-rose-700',
            panel: 'border-rose-200 bg-rose-50/70'
        };
    }
    if (ocr >= 12) {
        return {
            label: 'Vigilancia',
            color: '#f59e0b',
            badge: 'bg-amber-100 text-amber-700',
            panel: 'border-amber-200 bg-amber-50/70'
        };
    }
    return {
        label: 'Saludable',
        color: '#4f46e5',
        badge: 'bg-indigo-100 text-indigo-700',
        panel: 'border-indigo-200 bg-indigo-50/70'
    };
};

export const FinancialDashboard: React.FC = () => {
    const { currentMall, session } = useAuth();
    const { format } = useFormatCurrency();
    const [data, setData] = useState<any[]>([]);
    const [loading, setLoading] = useState(true);
    const [isExporting, setIsExporting] = useState(false);
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

                raw = raw.replace(/[^\d.,-]/g, '');
                if (!raw) return 0;

                const hasDot = raw.includes('.');
                const hasComma = raw.includes(',');

                let normalized = raw;
                if (hasDot && hasComma) {
                    if (raw.lastIndexOf(',') > raw.lastIndexOf('.')) {
                        normalized = raw.replace(/\./g, '').replace(',', '.');
                    } else {
                        normalized = raw.replace(/,/g, '');
                    }
                } else if (hasComma) {
                    const commaGroups = raw.split(',');
                    const looksThousands = commaGroups.length > 1 && commaGroups.slice(1).every(g => g.length === 3);
                    normalized = looksThousands ? raw.replace(/,/g, '') : raw.replace(',', '.');
                }

                const n = Number(normalized);
                return Number.isFinite(n) ? n : 0;
            };

            const start = parseDateInput(dates.startDate);
            const end = parseDateInput(dates.endDate);
            const today = new Date();
            const totalDays = Math.max(diffDaysInclusive(start, end), 1);
            const effectiveEnd = today < start ? start : (today > end ? end : today);
            const elapsedDays = today < start ? 0 : Math.max(diffDaysInclusive(start, effectiveEnd), 1);
            const isProjectionActive = today >= start && today < end && elapsedDays < totalDays;
            const projectionFactor = isProjectionActive ? totalDays / elapsedDays : 1;

            const processed = stores.map(s => {
                const ventaActual = salesMap[s.nombre] || 0;
                const rentaFija = parseNum(s.renta_fija);
                const breakpoint = parseNum(s.breakpoint_venta);
                const pctVarDirect = parseNum(s.porcentaje_variable);
                const pctVarLegacy = parseNum(s.porciento_renta);
                const pctVar = pctVarDirect > 0 ? pctVarDirect : pctVarLegacy;
                const m2 = Number(s.mts) || 1;
                const proyeccion = ventaActual > 0 ? ventaActual * projectionFactor : ventaActual;
                const projectionDelta = proyeccion - ventaActual;
                const ocr = ventaActual > 0
                    ? ((rentaFija > 0 ? rentaFija : (ventaActual * pctVar / 100)) / ventaActual) * 100
                    : 0;

                let rentaVariable = 0;
                if (pctVar > 0) {
                    const aplicaVariable = breakpoint <= 0 || proyeccion > breakpoint;
                    if (aplicaVariable) {
                        const rentaTeorica = (proyeccion * pctVar) / 100;
                        rentaVariable = rentaFija > 0
                            ? Math.max(0, rentaTeorica - rentaFija)
                            : Math.max(0, rentaTeorica);
                    }
                }

                const breakpointGap = breakpoint > 0 ? proyeccion - breakpoint : null;
                const riskMeta = getRiskMeta(ocr);
                const projectionStatus = pctVar <= 0
                    ? 'Sin variable'
                    : breakpoint <= 0
                        ? (rentaVariable > 0 ? 'Variable activa' : 'Sin trigger')
                        : (breakpointGap ?? 0) >= 0
                            ? (rentaVariable > 0 ? 'Generando variable' : 'Sobre breakpoint')
                            : 'Por activar';

                return {
                    id: s.id,
                    name: s.nombre,
                    venta: ventaActual,
                    proyeccion,
                    projectionDelta,
                    ocr,
                    rentaVariable,
                    pctVar,
                    breakpoint,
                    breakpointGap,
                    m2,
                    riskMeta,
                    projectionStatus
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
    }, [dates, currentMall?.id, session?.access_token]);

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

    if (loading && !data.length) {
        return (
            <div className="h-64 flex items-center justify-center">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600"></div>
            </div>
        );
    }

    const start = parseDateInput(dates.startDate);
    const end = parseDateInput(dates.endDate);
    const today = new Date();
    const totalDays = Math.max(diffDaysInclusive(start, end), 1);
    const effectiveEnd = today < start ? start : (today > end ? end : today);
    const elapsedDays = today < start ? 0 : Math.max(diffDaysInclusive(start, effectiveEnd), 1);
    const isProjectionActive = today >= start && today < end && elapsedDays < totalDays;
    const projectionBasis = isProjectionActive
        ? `Ritmo de ${elapsedDays}/${totalDays} dias`
        : today > end
            ? 'Periodo cerrado'
            : 'Periodo futuro';

    const avgSalesM2 = data.length > 0
        ? data.reduce((acc, curr) => acc + (curr.venta / Math.max(curr.m2, 1)), 0) / data.length
        : 0;
    const storesAtRisk = data.filter(s => s.ocr > 20).length;
    const activeStores = data.filter(s => s.venta > 0 || s.ocr > 0);
    const rankedPortfolio = [...activeStores].sort((a, b) => (b.ocr - a.ocr) || (b.venta - a.venta));
    const topPortfolioRows = rankedPortfolio.slice(0, 12);
    const maxOcr = topPortfolioRows.length > 0
        ? Math.max(25, Math.ceil(Math.max(...topPortfolioRows.map(row => row.ocr || 0), 0) / 5) * 5)
        : 25;

    const healthBuckets = [
        {
            label: 'Saludable',
            helper: 'OCR menor a 12%',
            count: activeStores.filter(s => s.ocr < 12).length,
            tone: 'bg-indigo-50 border-indigo-200 text-indigo-700'
        },
        {
            label: 'Vigilancia',
            helper: 'OCR entre 12% y 20%',
            count: activeStores.filter(s => s.ocr >= 12 && s.ocr <= 20).length,
            tone: 'bg-amber-50 border-amber-200 text-amber-700'
        },
        {
            label: 'Riesgo',
            helper: 'OCR mayor a 20%',
            count: activeStores.filter(s => s.ocr > 20).length,
            tone: 'bg-rose-50 border-rose-200 text-rose-700'
        }
    ];

    const projectionRows = [...data]
        .filter(s => s.venta > 0 || s.proyeccion > 0 || s.breakpoint > 0 || s.rentaVariable > 0)
        .sort((a, b) => (
            (b.rentaVariable - a.rentaVariable)
            || ((b.breakpointGap ?? Number.NEGATIVE_INFINITY) - (a.breakpointGap ?? Number.NEGATIVE_INFINITY))
            || (b.proyeccion - a.proyeccion)
        ));

    const totalProjectedSales = projectionRows.reduce((acc, row) => acc + row.proyeccion, 0);
    const totalProjectedVariable = projectionRows.reduce((acc, row) => acc + row.rentaVariable, 0);
    const storesAboveBreakpoint = projectionRows.filter(row => row.breakpoint > 0 && (row.breakpointGap ?? -1) >= 0).length;
    const hasProjectedVariable = projectionRows.some(row => row.rentaVariable > 0);

    const formatSignedCurrency = (value: number) => {
        const absValue = Math.abs(value);
        return `${value >= 0 ? '+' : '-'}${format(absValue)}`;
    };

    return (
        <div className="space-y-8 animate-in fade-in duration-500">
            <div className="bg-white p-6 rounded-3xl border border-slate-100 shadow-sm flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
                <div>
                    <h2 className="text-xl font-bold text-slate-800">Salud Financiera</h2>
                    <p className="text-slate-500 text-sm">Análisis de OCR y proyecciones con mayor claridad operativa.</p>
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
                            Fórmula OCR: (Renta Fija / Ventas) * 100. Un OCR mayor a 20% indica alto esfuerzo financiero.
                        </div>
                    </div>
                    <div className="p-2 bg-red-50 text-red-600 w-fit rounded-xl mb-4"><AlertCircle size={20} /></div>
                    <p className="text-slate-500 text-sm font-medium">Locales en Riesgo (OCR {'>'} 20%)</p>
                    <h3 className="text-2xl font-bold text-slate-900 mt-1">{storesAtRisk} Locales</h3>
                </div>

                <div className="bg-white p-6 rounded-3xl border border-slate-100 shadow-sm">
                    <div className="p-2 bg-emerald-50 text-emerald-600 w-fit rounded-xl mb-4"><TrendingUp size={20} /></div>
                    <p className="text-slate-500 text-sm font-medium">Venta Proyectada Mall</p>
                    <h3 className="text-2xl font-bold text-slate-900 mt-1">{format(totalProjectedSales)}</h3>
                    <p className="text-xs text-slate-400 mt-2">{projectionBasis}</p>
                </div>

                <div className="bg-white p-6 rounded-3xl border border-slate-100 shadow-sm">
                    <div className="p-2 bg-amber-50 text-amber-600 w-fit rounded-xl mb-4"><Target size={20} /></div>
                    <p className="text-slate-500 text-sm font-medium">Locales sobre Breakpoint</p>
                    <h3 className="text-2xl font-bold text-slate-900 mt-1">{storesAboveBreakpoint}</h3>
                    <p className="text-xs text-slate-400 mt-2">Con opción real de activar renta variable</p>
                </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1.25fr)_minmax(320px,0.75fr)] gap-8">
                <div className="bg-white p-6 sm:p-8 rounded-3xl border border-slate-100 shadow-sm">
                    <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 mb-6">
                        <div>
                            <h3 className="text-lg font-bold text-slate-800 flex items-center gap-2">
                                <PieChart className="text-indigo-500" size={20} />
                                Salud de Cartera por OCR
                            </h3>
                            <p className="text-sm text-slate-500 mt-1">
                                Se priorizan los locales con mayor presión financiera. Mostrar todo en un scatter deja de ser legible cuando el mall crece.
                            </p>
                        </div>
                        <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3">
                            <p className="text-[11px] font-bold uppercase tracking-[0.2em] text-slate-400">Foco</p>
                            <p className="text-sm font-semibold text-slate-700">Top {topPortfolioRows.length} de {rankedPortfolio.length} locales con ventas</p>
                        </div>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-6">
                        {healthBuckets.map((bucket) => (
                            <div key={bucket.label} className={`rounded-2xl border px-4 py-4 ${bucket.tone}`}>
                                <p className="text-[11px] font-bold uppercase tracking-[0.18em]">{bucket.label}</p>
                                <p className="text-3xl font-bold mt-2">{bucket.count}</p>
                                <p className="text-xs mt-2 opacity-80">{bucket.helper}</p>
                            </div>
                        ))}
                    </div>

                    <div className="rounded-3xl border border-slate-200 bg-slate-50/70 p-4 sm:p-6">
                        {topPortfolioRows.length > 0 ? (
                            <div className="h-[420px]">
                                <ResponsiveContainer width="100%" height="100%">
                                    <BarChart
                                        data={[...topPortfolioRows].reverse()}
                                        layout="vertical"
                                        margin={{ top: 8, right: 24, bottom: 8, left: 24 }}
                                    >
                                        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" horizontal={true} vertical={false} />
                                        <XAxis
                                            type="number"
                                            domain={[0, maxOcr]}
                                            tickFormatter={(value) => `${value}%`}
                                            axisLine={{ stroke: '#cbd5e1' }}
                                            tick={{ fontSize: 11, fill: '#64748b', fontWeight: 600 }}
                                            tickLine={{ stroke: '#cbd5e1' }}
                                        />
                                        <YAxis
                                            type="category"
                                            dataKey="name"
                                            width={110}
                                            axisLine={false}
                                            tickLine={false}
                                            tick={{ fontSize: 11, fill: '#334155', fontWeight: 600 }}
                                        />
                                        <Tooltip
                                            cursor={{ fill: '#eef2ff' }}
                                            content={({ active, payload }) => {
                                                if (!active || !payload?.length) return null;
                                                const item = payload[0].payload;
                                                return (
                                                    <div className="bg-white p-3 border border-slate-200 shadow-xl rounded-2xl text-xs min-w-[200px]">
                                                        <p className="font-bold text-slate-900">{item.name}</p>
                                                        <p className="mt-2 text-slate-600">Ventas: <span className="font-mono font-bold text-slate-900">{format(item.venta)}</span></p>
                                                        <p className="text-slate-600">OCR: <span className="font-mono font-bold text-slate-900">{item.ocr.toFixed(2)}%</span></p>
                                                        <p className="text-slate-600">Estado: <span className="font-semibold text-slate-900">{item.riskMeta.label}</span></p>
                                                    </div>
                                                );
                                            }}
                                        />
                                        <ReferenceLine x={20} stroke="#ef4444" strokeDasharray="5 5" strokeWidth={2} />
                                        <Bar dataKey="ocr" radius={[0, 10, 10, 0]} barSize={18}>
                                            {topPortfolioRows.slice().reverse().map((entry) => (
                                                <Cell key={entry.id} fill={entry.riskMeta.color} />
                                            ))}
                                        </Bar>
                                    </BarChart>
                                </ResponsiveContainer>
                            </div>
                        ) : (
                            <p className="text-center text-slate-400 text-sm py-16">No hay ventas en el periodo para evaluar OCR.</p>
                        )}
                    </div>
                </div>

                <div className="bg-white p-6 sm:p-8 rounded-3xl border border-slate-100 shadow-sm">
                    <h3 className="text-lg font-bold text-slate-800 mb-2">Watchlist de cartera</h3>
                    <p className="text-sm text-slate-500 mb-6">Lista corta para seguimiento semanal. Se ordena por OCR y peso comercial.</p>

                    <div className="space-y-3 max-h-[520px] overflow-y-auto pr-1">
                        {topPortfolioRows.map((row) => {
                            const widthPct = `${Math.min((row.ocr / Math.max(maxOcr, 1)) * 100, 100)}%`;
                            return (
                                <div key={row.id} className={`rounded-2xl border px-4 py-4 ${row.riskMeta.panel}`}>
                                    <div className="flex items-start justify-between gap-3">
                                        <div className="min-w-0">
                                            <p className="font-semibold text-slate-800 truncate">{row.name}</p>
                                            <p className="text-xs text-slate-500 mt-1">Ventas del periodo: {format(row.venta)}</p>
                                        </div>
                                        <span className={`px-2.5 py-1 rounded-full text-[11px] font-bold uppercase tracking-wide ${row.riskMeta.badge}`}>
                                            {row.riskMeta.label}
                                        </span>
                                    </div>
                                    <div className="mt-4 h-2.5 rounded-full bg-white/80 overflow-hidden">
                                        <div className="h-full rounded-full" style={{ width: widthPct, backgroundColor: row.riskMeta.color }} />
                                    </div>
                                    <div className="mt-3 flex items-center justify-between text-xs">
                                        <span className="text-slate-500">OCR</span>
                                        <span className="font-mono font-bold text-slate-800">{row.ocr.toFixed(2)}%</span>
                                    </div>
                                </div>
                            );
                        })}

                        {topPortfolioRows.length === 0 && (
                            <p className="text-center text-slate-400 text-sm py-12">No hay locales con ventas para construir la watchlist.</p>
                        )}
                    </div>
                </div>
            </div>

            <div className="bg-white p-4 sm:p-8 rounded-3xl border border-slate-100 shadow-sm overflow-hidden">
                <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-4 mb-6">
                    <div>
                        <h3 className="text-lg font-bold text-slate-800 flex items-center gap-2">
                            <TrendingUp className="text-indigo-500" size={20} />
                            Potencial de Recaudación Variable
                        </h3>
                        <p className="text-sm text-slate-500 mt-1">
                            La proyección ya no replica la venta actual: estima cierre al ritmo del periodo y muestra qué tan lejos está cada local de activar variable.
                        </p>
                    </div>
                    <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3">
                        <p className="text-[11px] font-bold uppercase tracking-[0.2em] text-slate-400">Base de cálculo</p>
                        <p className="text-sm font-semibold text-slate-700">{projectionBasis}</p>
                    </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
                    <div className="rounded-2xl border border-indigo-200 bg-indigo-50/70 px-4 py-4">
                        <p className="text-[11px] font-bold uppercase tracking-[0.18em] text-indigo-500">Cierre estimado mall</p>
                        <p className="text-2xl font-bold text-slate-900 mt-2">{format(totalProjectedSales)}</p>
                        <p className="text-xs text-slate-500 mt-2">Con el ritmo actual del periodo seleccionado.</p>
                    </div>
                    <div className="rounded-2xl border border-emerald-200 bg-emerald-50/70 px-4 py-4">
                        <p className="text-[11px] font-bold uppercase tracking-[0.18em] text-emerald-500">Renta variable estimada</p>
                        <p className="text-2xl font-bold text-slate-900 mt-2">{format(totalProjectedVariable)}</p>
                        <p className="text-xs text-slate-500 mt-2">Suma estimada si el mall mantiene el mismo run-rate.</p>
                    </div>
                    <div className="rounded-2xl border border-amber-200 bg-amber-50/70 px-4 py-4">
                        <p className="text-[11px] font-bold uppercase tracking-[0.18em] text-amber-500">Locales sobre breakpoint</p>
                        <p className="text-2xl font-bold text-slate-900 mt-2">{storesAboveBreakpoint}</p>
                        <p className="text-xs text-slate-500 mt-2">Locales que ya cruzan el umbral contractual proyectado.</p>
                    </div>
                </div>

                <div className="overflow-x-auto max-h-[520px] overflow-y-auto">
                    <table className="w-full min-w-[920px] text-left">
                        <thead className="sticky top-0 bg-white z-10">
                            <tr className="text-xs font-bold text-slate-400 uppercase tracking-wider border-b border-slate-100">
                                <th className="pb-4">Local</th>
                                <th className="pb-4">Venta Actual</th>
                                <th className="pb-4">Cierre Est.</th>
                                <th className="pb-4">Gap vs Breakpoint</th>
                                <th className="pb-4 text-right">Renta Var. Est.</th>
                                <th className="pb-4 text-right">Estado</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-50">
                            {projectionRows.map((row) => {
                                const gapPositive = (row.breakpointGap ?? 0) >= 0;
                                const statusTone = row.projectionStatus === 'Generando variable'
                                    ? 'bg-emerald-100 text-emerald-700'
                                    : row.projectionStatus === 'Sobre breakpoint'
                                        ? 'bg-indigo-100 text-indigo-700'
                                        : row.projectionStatus === 'Por activar'
                                            ? 'bg-amber-100 text-amber-700'
                                            : 'bg-slate-100 text-slate-600';

                                return (
                                    <tr key={row.id} className="text-sm hover:bg-slate-50/60 transition-colors align-top">
                                        <td className="py-4">
                                            <div className="min-w-0">
                                                <p className="font-semibold text-slate-800">{row.name}</p>
                                                <p className="text-xs text-slate-400 mt-1">OCR {row.ocr.toFixed(2)}% · % variable {row.pctVar.toFixed(2)}%</p>
                                            </div>
                                        </td>
                                        <td className="py-4 text-slate-600 font-medium">{format(row.venta)}</td>
                                        <td className="py-4">
                                            <p className="text-slate-800 font-semibold">{format(row.proyeccion)}</p>
                                            <p className={`text-xs mt-1 font-semibold ${row.projectionDelta >= 0 ? 'text-emerald-600' : 'text-rose-600'}`}>
                                                {formatSignedCurrency(row.projectionDelta)} vs actual
                                            </p>
                                        </td>
                                        <td className="py-4">
                                            {row.breakpoint > 0 ? (
                                                <div>
                                                    <p className={`font-semibold ${gapPositive ? 'text-emerald-600' : 'text-amber-700'}`}>
                                                        {formatSignedCurrency(row.breakpointGap || 0)}
                                                    </p>
                                                    <p className="text-xs text-slate-400 mt-1">Breakpoint {format(row.breakpoint)}</p>
                                                </div>
                                            ) : (
                                                <span className="text-slate-400 text-sm">Sin breakpoint</span>
                                            )}
                                        </td>
                                        <td className={`py-4 text-right font-bold ${row.rentaVariable > 0 ? 'text-indigo-600' : 'text-slate-400'}`}>
                                            {format(row.rentaVariable)}
                                        </td>
                                        <td className="py-4 text-right">
                                            <span className={`inline-flex px-2.5 py-1 rounded-full text-[11px] font-bold uppercase tracking-wide ${statusTone}`}>
                                                {row.projectionStatus}
                                            </span>
                                        </td>
                                    </tr>
                                );
                            })}
                        </tbody>
                    </table>
                </div>

                {projectionRows.length === 0 && (
                    <p className="text-center text-slate-400 text-sm py-8">No hay ventas en el periodo para calcular proyecciones.</p>
                )}
                {projectionRows.length > 0 && !hasProjectedVariable && (
                    <p className="text-center text-slate-400 text-sm py-8">
                        El ritmo actual permite analizar breakpoints, aunque todavía no se proyecta renta variable positiva para ningún local.
                    </p>
                )}
            </div>
        </div>
    );
};
