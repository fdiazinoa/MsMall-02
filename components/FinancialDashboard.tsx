import React, { useState, useEffect } from 'react';
import {
    ScatterChart, Scatter, XAxis, YAxis, ZAxis,
    CartesianGrid, Tooltip, ResponsiveContainer,
    ReferenceLine, Label, Cell
} from 'recharts';
import {
    TrendingUp, AlertCircle, DollarSign,
    ArrowUpRight, PieChart, Users, Info
} from 'lucide-react';
import { ApiService } from '../api';

export const FinancialDashboard: React.FC = () => {
    const [data, setData] = useState<any[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const fetchFinancialData = async () => {
            setLoading(true);
            try {
                // Mocking the behavior of analytics.py integration
                // In a real scenario, this would call a new backend endpoint
                const stores = await ApiService.getStores();

                // Fetch real sales data for the current month
                const now = new Date();
                const startDate = new Date(now.getFullYear(), now.getMonth(), 1).toISOString().split('T')[0];
                const endDate = new Date(now.getFullYear(), now.getMonth() + 1, 0).toISOString().split('T')[0];

                const kpiData = await ApiService.getKPIs({ startDate, endDate });
                const salesMap = kpiData.ventas_por_tienda_completo || {};

                const processed = stores.map(s => {
                    const ventaActual = salesMap[s.nombre] || 0; // Use real data or 0

                    // Simple projection: If we are not at end of month, extrapolate
                    // const dayOfMonth = now.getDate();
                    // const daysInMonth = new Date(now.getFullYear(), now.getMonth() + 1, 0).getDate();
                    // const factor = dayOfMonth > 0 ? (daysInMonth / dayOfMonth) : 1;
                    // For now, let's keep it simple: Sale * 1.0 (assuming import is full month or simple view)
                    // Or keep the 1.2 projection if desired by user, but based on REAL data.
                    const proyeccion = ventaActual;

                    const rentaFija = Number(s.renta_fija) || 0; // Default to 0 if not set, to avoid NaN

                    // Avoid division by zero
                    const ocr = ventaActual > 0 ? (rentaFija / ventaActual) * 100 : 0;

                    const breakpoint = Number(s.breakpoint_venta) || 0;
                    const pctVar = Number(s.porcentaje_variable || s.porciento_renta) || 0;

                    let rentaVariable = 0;
                    if (proyeccion > breakpoint && breakpoint > 0) {
                        rentaVariable = Math.max(0, (proyeccion * pctVar / 100) - rentaFija);
                    }

                    return {
                        id: s.id,
                        name: s.nombre,
                        venta: ventaActual,
                        proyeccion,
                        ocr,
                        rentaVariable,
                        m2: Number(s.mts) || 1 // Avoid division by zero in Avg Calc
                    };
                });
                setData(processed.filter(d => d.venta > 0 || d.name === 'Skechers')); // Optional: filter out 0 sales if desired, but user likely wants to see all. Let's keep all.
                // Actually, let's keep all stores so they see who has 0 sales (like Pollo Victorina)
                setData(processed);
            } catch (error) {
                console.error("Error loading financial data:", error);
            } finally {
                setLoading(false);
            }
        };
        fetchFinancialData();
    }, []);

    if (loading) return <div className="h-64 flex items-center justify-center"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600"></div></div>;

    const avgSalesM2 = data.length > 0
        ? data.reduce((acc, curr) => acc + (curr.venta / curr.m2), 0) / data.length
        : 0;
    const storesAtRisk = data.filter(s => s.ocr > 20).length;

    console.log("Financial Data Sample:", data.length > 0 ? JSON.stringify(data[0]) : "No data");
    console.log("Avg Sales M2:", avgSalesM2);

    return (
        <div className="space-y-8 animate-in fade-in duration-500">
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
                    <h3 className="text-2xl font-bold text-slate-900 mt-1">${avgSalesM2.toFixed(2)}</h3>
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
                    <div className="w-full flex justify-center">
                        <ScatterChart width={600} height={300} margin={{ top: 20, right: 20, bottom: 20, left: 20 }}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                            <XAxis type="number" dataKey="venta" name="Ventas" unit="$" axisLine={false} tick={{ fontSize: 12, fill: '#94a3b8' }} domain={['auto', 'auto']} />
                            <YAxis type="number" dataKey="ocr" name="OCR" unit="%" axisLine={false} tick={{ fontSize: 12, fill: '#94a3b8' }} domain={[0, 100]} />
                            <Tooltip cursor={{ strokeDasharray: '3 3' }} />
                            <ReferenceLine y={20} stroke="red" strokeDasharray="3 3">
                                <Label value="Zona de Riesgo (20%)" position="top" fill="red" fontSize={10} />
                            </ReferenceLine>
                            <Scatter name="Locales" data={data} fill="#6366f1">
                                {data.map((entry, index) => (
                                    <Cell key={`cell-${index}`} fill={entry.ocr > 20 ? '#ef4444' : '#6366f1'} />
                                ))}
                            </Scatter>
                        </ScatterChart>
                    </div>
                </div>

                {/* Table: Proyección de Recaudación */}
                <div className="bg-white p-8 rounded-3xl border border-slate-100 shadow-sm overflow-hidden">
                    <h3 className="text-lg font-bold text-slate-800 mb-6 flex items-center gap-2">
                        <TrendingUp className="text-indigo-500" size={20} />
                        Proyección de Recaudación (Variable)
                    </h3>
                    <div className="overflow-x-auto">
                        <table className="w-full text-left">
                            <thead>
                                <tr className="text-xs font-bold text-slate-400 uppercase tracking-wider border-b border-slate-50">
                                    <th className="pb-4">Local</th>
                                    <th className="pb-4">Venta Actual</th>
                                    <th className="pb-4">Proyección</th>
                                    <th className="pb-4 text-right">Renta Var. Est.</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-50">
                                {data.filter(s => s.rentaVariable > 0).map((row) => (
                                    <tr key={row.id} className="text-sm hover:bg-slate-50/50 transition-colors">
                                        <td className="py-4 font-semibold text-slate-700">{row.name}</td>
                                        <td className="py-4 text-slate-500">${row.venta.toLocaleString(undefined, { maximumFractionDigits: 0 })}</td>
                                        <td className="py-4 text-slate-500">${row.proyeccion.toLocaleString(undefined, { maximumFractionDigits: 0 })}</td>
                                        <td className="py-4 text-right text-indigo-600 font-bold">
                                            ${row.rentaVariable.toLocaleString(undefined, { maximumFractionDigits: 2 })}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                    {data.filter(s => s.rentaVariable > 0).length === 0 && (
                        <p className="text-center text-slate-400 text-sm py-8">No se proyecta cobro de renta variable este mes.</p>
                    )}
                </div>
            </div>
        </div>
    );
};
