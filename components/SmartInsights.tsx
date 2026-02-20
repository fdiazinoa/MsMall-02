
import React, { useState, useEffect, useMemo } from 'react';
import { ApiService } from '../api';
import {
    AlertTriangle, TrendingUp, BarChart3,
    Calendar, Info, Zap, Activity, Home,
    DollarSign, Users, Clock, X, ChevronRight, Trophy
} from 'lucide-react';
import {
    BarChart, Bar, XAxis, YAxis, CartesianGrid,
    Tooltip, ResponsiveContainer, Cell, LineChart, Line
} from 'recharts';

import { useAuth } from '../context/AuthProvider';

export const SmartInsights: React.FC<{ localId?: string }> = ({ localId: initialLocalId }) => {
    const { currentMall } = useAuth();
    const [selectedLocalId, setSelectedLocalId] = useState<string>(initialLocalId || '');
    const [availableStores, setAvailableStores] = useState<any[]>([]);
    const [alerts, setAlerts] = useState<any[]>([]);
    const [alertsStatus, setAlertsStatus] = useState<'ok' | 'error'>('ok');
    const [benchmarking, setBenchmarking] = useState<any>(null);
    const [efficiency, setEfficiency] = useState<any>(null);
    const [heatmap, setHeatmap] = useState<any[]>([]);
    const [loading, setLoading] = useState(true);

    // Modal state
    const [showModal, setShowModal] = useState(false);
    const [modalConfig, setModalConfig] = useState<{ title: string, metric: string, data: any[] }>({ title: '', metric: '', data: [] });
    const [loadingModal, setLoadingModal] = useState(false);
    const heatmapBySlot = useMemo(() => {
        const map = new Map<string, number>();
        for (const cell of heatmap) {
            map.set(`${cell.dia}|${cell.hora}`, Number(cell.valor) || 0);
        }
        return map;
    }, [heatmap]);

    useEffect(() => {
        const fetchStores = async () => {
            if (!currentMall?.id) {
                setAvailableStores([]);
                setSelectedLocalId('');
                setLoading(false);
                return;
            }
            const stores = await ApiService.getStores(currentMall.id);
            setAvailableStores(stores);
            if (!selectedLocalId && stores.length > 0) {
                setSelectedLocalId(stores[0].id);
            }
            if (stores.length === 0) {
                setLoading(false);
            }
        };
        fetchStores();
    }, [currentMall]);

    useEffect(() => {
        if (!selectedLocalId) {
            setLoading(false);
            return;
        }
        const loadData = async () => {
            setLoading(true);
            try {
                const [alertsData, benchData, heatmapData, efficiencyData] = await Promise.all([
                    ApiService.getAIAlerts(selectedLocalId),
                    ApiService.getBenchmarking(selectedLocalId),
                    ApiService.getHeatmap(selectedLocalId),
                    ApiService.getEfficiency(selectedLocalId)
                ]);
                setAlerts(alertsData.alerts || []);
                setAlertsStatus(alertsData.status);
                setBenchmarking(benchData);
                setHeatmap(heatmapData);
                setEfficiency(efficiencyData);
            } catch (error) {
                console.error("Error loading insights:", error);
                setAlerts([]);
                setAlertsStatus('error');
            } finally {
                setLoading(false);
            }
        };
        loadData();
    }, [selectedLocalId]);

    const handleCardClick = async (metric: string, title: string) => {
        setShowModal(true);
        setLoadingModal(true);
        setModalConfig({ title, metric, data: [] });
        try {
            const ranking = await ApiService.getRanking(metric, currentMall?.id);
            setModalConfig(prev => ({ ...prev, data: ranking }));
        } catch (error) {
            console.error("Error loading ranking:", error);
        } finally {
            setLoadingModal(false);
        }
    };

    if (loading) {
        return (
            <div className="flex items-center justify-center h-64">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600"></div>
            </div>
        );
    }

    const relevantAlerts = alerts.filter(a => a.nivel_riesgo === 'ALTO' || a.nivel_riesgo === 'MEDIO');
    const hasHighRisk = relevantAlerts.some(a => a.nivel_riesgo === 'ALTO');
    const hasMediumRisk = !hasHighRisk && relevantAlerts.some(a => a.nivel_riesgo === 'MEDIO');
    const riskState: 'HIGH' | 'MEDIUM' | 'NORMAL' | 'NO_DATA' =
        alertsStatus === 'error'
            ? 'NO_DATA'
            : hasHighRisk
                ? 'HIGH'
                : hasMediumRisk
                    ? 'MEDIUM'
                    : 'NORMAL';

    const riskCardStyles =
        riskState === 'HIGH'
            ? 'bg-red-50 border-red-200 shadow-lg shadow-red-100'
            : riskState === 'MEDIUM'
                ? 'bg-amber-50 border-amber-200 shadow-lg shadow-amber-100'
                : riskState === 'NO_DATA'
                    ? 'bg-slate-50 border-slate-200'
                    : 'bg-green-50 border-green-200';

    const riskIconStyles =
        riskState === 'HIGH'
            ? 'bg-red-500 text-white animate-pulse'
            : riskState === 'MEDIUM'
                ? 'bg-amber-500 text-white'
                : riskState === 'NO_DATA'
                    ? 'bg-slate-400 text-white'
                    : 'bg-green-500 text-white';

    const riskBadgeStyles =
        riskState === 'HIGH'
            ? 'bg-red-100 text-red-600'
            : riskState === 'MEDIUM'
                ? 'bg-amber-100 text-amber-700'
                : riskState === 'NO_DATA'
                    ? 'bg-slate-200 text-slate-600'
                    : 'bg-green-100 text-green-600';

    const riskBadgeText =
        riskState === 'HIGH'
            ? 'Riesgo Alto'
            : riskState === 'MEDIUM'
                ? 'Riesgo Medio'
                : riskState === 'NO_DATA'
                    ? 'Sin Datos'
                    : 'Operación Normal';

    return (
        <div className="space-y-6 animate-in fade-in duration-500 pb-12">
            <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
                <div>
                    <h2 className="text-2xl font-bold text-slate-800 flex items-center gap-2">
                        <Zap className="text-amber-500 fill-amber-500" size={24} />
                        Inteligencia de Negocio & IA
                    </h2>
                    <p className="text-slate-500 text-sm">Análisis avanzado de comportamiento y eficiencia para locales.</p>
                </div>

                <div className="flex items-center gap-2 bg-white p-2 rounded-2xl shadow-sm border border-slate-100 w-full md:w-auto">
                    <Home size={18} className="text-slate-400 ml-2" />
                    <select
                        className="bg-transparent border-none focus:ring-0 text-sm font-semibold text-slate-700 outline-none pr-8 cursor-pointer w-full"
                        value={selectedLocalId}
                        onChange={(e) => setSelectedLocalId(e.target.value)}
                    >
                        <option value="">-- Seleccionar Local --</option>
                        {availableStores.map(store => (
                            <option key={store.id} value={store.id}>{store.nombre}</option>
                        ))}
                    </select>
                </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* Risk Traffic Light */}
                <div className={`p-6 rounded-3xl border-2 transition-all ${riskCardStyles}`}>
                    <div className="flex items-center justify-between mb-4">
                        <div className={`p-3 rounded-2xl ${riskIconStyles}`}>
                            <AlertTriangle size={24} />
                        </div>
                        <span className={`text-xs font-bold uppercase tracking-widest px-3 py-1 rounded-full ${riskBadgeStyles}`}>
                            {riskBadgeText}
                        </span>
                    </div>
                    <h3 className="text-lg font-bold text-slate-800 mb-2">Semáforo de Riesgo</h3>
                    {(riskState === 'HIGH' || riskState === 'MEDIUM') ? (
                        <div className="space-y-3">
                            {relevantAlerts.map((alert, idx) => (
                                <div key={idx} className="bg-white/60 p-3 rounded-xl border border-red-100">
                                    <div className="flex items-center gap-2 mb-1">
                                        <span className={`text-[10px] font-bold px-2 py-0.5 rounded-md ${alert.tipo_alerta === 'CAJA_APAGADA' ? 'bg-red-600 text-white' : alert.tipo_alerta === 'FACTURA_PLANA' ? 'bg-orange-500 text-white' : 'bg-red-100 text-red-600'}`}>
                                            {alert.tipo_alerta.replace('_', ' ')}
                                        </span>
                                        <span className="text-[10px] font-bold text-slate-400">{alert.fecha}</span>
                                    </div>
                                    <p className="text-red-800 text-xs font-medium leading-relaxed">
                                        {alert.mensaje}
                                    </p>
                                </div>
                            ))}
                        </div>
                    ) : riskState === 'NO_DATA' ? (
                        <p className="text-slate-700 text-sm font-medium">
                            No se pudo validar alertas IA en este momento. Verifica conexión o servicio de alertas.
                        </p>
                    ) : (
                        <p className="text-green-700 text-sm font-medium">
                            No se han detectado anomalías significativas en los últimos 7 días.
                        </p>
                    )}
                </div>

                {/* Efficiency Metrics */}
                <div className="lg:col-span-2 grid grid-cols-1 md:grid-cols-2 gap-6">
                    <div
                        onClick={() => handleCardClick('sales_per_m2', 'Ranking: Ventas por m²')}
                        className="bg-white p-6 rounded-3xl border border-slate-200 shadow-sm hover:shadow-md hover:border-indigo-300 transition-all cursor-pointer group"
                    >
                        <div className="flex items-center justify-between mb-4">
                            <div className="flex items-center gap-3">
                                <div className="p-2 bg-indigo-50 text-indigo-600 rounded-xl group-hover:bg-indigo-600 group-hover:text-white transition-colors">
                                    <Home size={20} />
                                </div>
                                <h3 className="font-bold text-slate-800">Ventas por m²</h3>
                            </div>
                            <ChevronRight size={18} className="text-slate-300 group-hover:text-indigo-500 transition-colors" />
                        </div>
                        <p className="text-3xl font-bold text-slate-800">${efficiency?.sales_per_m2?.toLocaleString()}</p>
                        <p className="text-xs text-slate-400 mt-2">Eficiencia de uso de espacio físico. <span className="text-indigo-500 font-medium">Ver ranking →</span></p>
                    </div>

                    <div
                        onClick={() => handleCardClick('occupancy_cost', 'Salud del Locatario: Ranking OCR')}
                        className={`p-6 rounded-3xl border shadow-sm hover:shadow-md transition-all cursor-pointer group ${efficiency?.is_healthy ? 'bg-white border-slate-200 hover:border-indigo-300' : 'bg-amber-50 border-amber-200 hover:border-amber-300'}`}
                    >
                        <div className="flex items-center justify-between mb-4">
                            <div className="flex items-center gap-3">
                                <div className={`p-2 rounded-xl transition-colors ${efficiency?.is_healthy ? 'bg-indigo-50 text-indigo-600 group-hover:bg-indigo-600 group-hover:text-white' : 'bg-amber-100 text-amber-600 group-hover:bg-amber-600 group-hover:text-white'}`}>
                                    <Activity size={20} />
                                </div>
                                <h3 className="font-bold text-slate-800">Salud del Locatario</h3>
                            </div>
                            <ChevronRight size={18} className="text-slate-300 group-hover:text-indigo-500 transition-colors" />
                        </div>
                        <div className="flex items-end justify-between">
                            <div>
                                <p className="text-3xl font-bold text-slate-800">{efficiency?.occupancy_cost_ratio}%</p>
                                <p className="text-[10px] font-bold uppercase text-slate-400 mt-1">Occupancy Cost Ratio</p>
                            </div>
                            <span className={`text-[10px] font-bold px-2 py-1 rounded-lg ${efficiency?.is_healthy ? 'bg-green-100 text-green-600' : 'bg-red-100 text-red-600'}`}>
                                {efficiency?.risk_level} RIESGO
                            </span>
                        </div>
                    </div>
                </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Benchmarking & ATV */}
                <div className="bg-white p-4 sm:p-8 rounded-3xl border border-slate-200 shadow-sm">
                    <div className="flex items-center justify-between mb-8">
                        <h3 className="text-lg font-bold text-slate-800 flex items-center gap-2">
                            <BarChart3 className="text-indigo-500" size={20} />
                            Benchmarking & Ticket Promedio
                        </h3>
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 sm:gap-8 mb-8">
                        <div className="p-4 bg-slate-50 rounded-2xl">
                            <p className="text-[10px] font-bold text-slate-400 uppercase mb-1">Ticket Promedio (ATV)</p>
                            <p className="text-2xl font-bold text-slate-800">${benchmarking?.atv_local}</p>
                            <span className="text-[10px] font-bold text-green-600">{benchmarking?.atv_growth} vs mes anterior</span>
                        </div>
                        <div className="p-4 bg-slate-50 rounded-2xl">
                            <p className="text-[10px] font-bold text-slate-400 uppercase mb-1">Promedio Rubro</p>
                            <p className="text-2xl font-bold text-slate-500">${benchmarking?.atv_category}</p>
                            <span className="text-[10px] font-bold text-slate-400">Referencia mercado</span>
                        </div>
                    </div>

                    <div className="h-48 w-full">
                        <ResponsiveContainer width="100%" height="100%">
                            <BarChart data={[
                                { name: 'Tu Local', value: benchmarking?.local_value },
                                { name: 'Promedio Rubro', value: benchmarking?.category_avg }
                            ]}>
                                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                                <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{ fontSize: 12, fontWeight: 600, fill: '#64748b' }} />
                                <YAxis hide />
                                <Tooltip
                                    cursor={{ fill: '#f8fafc' }}
                                    contentStyle={{ borderRadius: '12px', border: 'none', boxShadow: '0 10px 15px -3px rgb(0 0 0 / 0.1)' }}
                                />
                                <Bar dataKey="value" radius={[8, 8, 0, 0]} barSize={60}>
                                    <Cell fill="#4f46e5" />
                                    <Cell fill="#cbd5e1" />
                                </Bar>
                            </BarChart>
                        </ResponsiveContainer>
                    </div>
                </div>

                {/* Heatmap Section */}
                <div className="bg-white p-4 sm:p-8 rounded-3xl border border-slate-200 shadow-sm">
                    <div className="flex items-center justify-between mb-8">
                        <div>
                            <h3 className="text-lg font-bold text-slate-800 flex items-center gap-2">
                                <Clock className="text-indigo-500" size={20} />
                                Intensidad Horaria
                            </h3>
                            <p className="text-slate-400 text-xs">Vital para planificación de seguridad y limpieza.</p>
                        </div>
                        <div className="flex items-center gap-4">
                            <div className="flex items-center gap-1.5">
                                <div className="w-3 h-3 rounded bg-indigo-50"></div>
                                <span className="text-[10px] font-bold text-slate-400 uppercase">Bajo</span>
                            </div>
                            <div className="flex items-center gap-1.5">
                                <div className="w-3 h-3 rounded bg-indigo-600"></div>
                                <span className="text-[10px] font-bold text-slate-400 uppercase">Pico</span>
                            </div>
                        </div>
                    </div>

                    <div className="overflow-x-auto">
                        <div className="min-w-[500px]">
                            <div className="grid grid-cols-8 gap-2 mb-2">
                                <div className="h-8"></div>
                                {["10am", "12pm", "2pm", "4pm", "6pm", "8pm", "10pm"].map(h => (
                                    <div key={h} className="text-[10px] font-bold text-slate-400 text-center uppercase">{h}</div>
                                ))}
                            </div>

                            {["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"].map(day => (
                                <div key={day} className="grid grid-cols-8 gap-2 mb-2">
                                    <div className="text-[10px] font-bold text-slate-600 flex items-center">{day}</div>
                                    {[0, 1, 2, 3, 4, 5, 6].map(i => {
                                        const slot = `${day}|${(10 + i * 2).toString().padStart(2, '0')}:00`;
                                        const val = heatmapBySlot.get(slot) || 0;
                                        return (
                                            <div
                                                key={i}
                                                className="h-8 rounded-lg transition-all hover:scale-110 cursor-pointer"
                                                style={{
                                                    backgroundColor: `rgba(79, 70, 229, ${val / 100})`,
                                                    border: '1px solid rgba(79, 70, 229, 0.1)'
                                                }}
                                                title={`${day} ${10 + i * 2}:00 - Intensidad: ${Math.round(val)}%`}
                                            ></div>
                                        );
                                    })}
                                </div>
                            ))}
                        </div>
                    </div>
                </div>
            </div>

            {/* Drill-down Modal */}
            {showModal && (
                <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm animate-in fade-in duration-200">
                    <div className="bg-white w-full max-w-2xl rounded-3xl shadow-2xl overflow-hidden animate-in zoom-in-95 duration-200">
                        <div className="p-6 border-b border-slate-100 flex items-center justify-between bg-slate-50/50">
                            <div className="flex items-center gap-3">
                                <div className="p-2 bg-indigo-600 text-white rounded-xl shadow-lg shadow-indigo-200">
                                    <Trophy size={20} />
                                </div>
                                <h3 className="text-xl font-bold text-slate-800">{modalConfig.title}</h3>
                            </div>
                            <button
                                onClick={() => setShowModal(false)}
                                className="p-2 hover:bg-slate-200 rounded-full transition-colors text-slate-400"
                            >
                                <X size={24} />
                            </button>
                        </div>

                        <div className="p-6 max-h-[70vh] overflow-y-auto">
                            {loadingModal ? (
                                <div className="flex flex-col items-center justify-center py-20 gap-4">
                                    <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-indigo-600"></div>
                                    <p className="text-slate-400 text-sm font-medium">Cargando ranking de locales...</p>
                                </div>
                            ) : (
                                <div className="space-y-3">
                                    {modalConfig.data.map((item, index) => (
                                        <div
                                            key={item.id}
                                            className={`flex items-center justify-between p-4 rounded-2xl border transition-all ${item.id === selectedLocalId ? 'bg-indigo-50 border-indigo-200 ring-1 ring-indigo-500/20' : 'bg-white border-slate-100 hover:border-slate-300'}`}
                                        >
                                            <div className="flex items-center gap-4">
                                                <div className={`w-8 h-8 rounded-full flex items-center justify-center font-bold text-sm ${index === 0 ? 'bg-amber-100 text-amber-600' : index === 1 ? 'bg-slate-100 text-slate-600' : index === 2 ? 'bg-orange-100 text-orange-600' : 'bg-slate-50 text-slate-400'}`}>
                                                    {index + 1}
                                                </div>
                                                <div>
                                                    <p className="font-bold text-slate-800">{item.nombre}</p>
                                                    <p className="text-[10px] font-bold uppercase text-slate-400 tracking-wider">{item.extra}</p>
                                                </div>
                                            </div>
                                            <div className="text-right">
                                                <p className="text-lg font-mono font-bold text-slate-700">
                                                    {modalConfig.metric === 'sales_per_m2' ? `$${item.valor.toLocaleString()}` : `${item.valor}%`}
                                                </p>
                                                {item.id === selectedLocalId && <span className="text-[10px] font-bold text-indigo-600 uppercase">Local Seleccionado</span>}
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>

                        <div className="p-6 bg-slate-50 border-t border-slate-100 flex justify-end">
                            <button
                                onClick={() => setShowModal(false)}
                                className="px-6 py-2.5 bg-slate-800 text-white rounded-xl font-bold text-sm hover:bg-slate-700 transition-all shadow-lg shadow-slate-200"
                            >
                                Entendido
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};
