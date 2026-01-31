import React, { useState } from 'react';
import { ApiService } from '../api';
import {
    Calendar, Filter, TrendingUp, DollarSign,
    ArrowRight, Loader2, Download, Archive
} from 'lucide-react';
import { DateRange } from '../types';

export const SalesCube: React.FC = () => {
    const [loading, setLoading] = useState(false);
    const [cubeData, setCubeData] = useState<any>(null);
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

    const [error, setError] = useState<string | null>(null);

    const generateCube = async () => {
        setLoading(true);
        setError(null);
        try {
            const data = await ApiService.getSalesCube({
                fecha_inicio: dates.startDate,
                fecha_fin: dates.endDate,
                agrupacion: grouping,
                metrica: metric
            });
            setCubeData(data);
        } catch (err: any) {
            console.error("Error generating cube:", err);
            setError("No se pudo conectar con el servidor. Verifica que el backend esté corriendo.");
        } finally {
            setLoading(false);
        }
    };

    const formatValue = (val: number) => {
        if (metric === 'transacciones') return val.toLocaleString();
        return `$ ${val.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    };

    return (
        <div className="space-y-6 animate-in fade-in duration-500">
            {/* Control Bar */}
            <div className="bg-white p-6 rounded-3xl border border-slate-100 shadow-sm flex flex-wrap gap-6 items-end">
                <div>
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

                <button
                    onClick={generateCube}
                    className="ml-auto bg-indigo-600 hover:bg-indigo-700 text-white font-bold py-3 px-6 rounded-xl flex items-center gap-2 transition-colors disabled:opacity-50"
                    disabled={loading}
                >
                    {loading ? <Loader2 className="animate-spin" size={20} /> : <TrendingUp size={20} />}
                    Generar Cubo
                </button>
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
                                <span className="font-bold text-slate-800 text-lg">{formatValue(Object.values(cubeData.grand_totals).reduce((a: any, b: any) => a + (typeof b === 'number' ? b : 0), 0) as number)}</span>
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
