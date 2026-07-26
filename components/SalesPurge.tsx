import React, { useState, useEffect, useRef } from 'react';
import { ApiService, Store } from '../api';
import { useAuth } from '../context/AuthProvider';
import { AlertTriangle, Trash2, Calendar, Building, X, ShieldAlert, Check, Search, ChevronRight, Store as StoreIcon } from 'lucide-react';

export const SalesPurge: React.FC = () => {
    const { currentMall, session } = useAuth();
    const [stores, setStores] = useState<Store[]>([]);
    const [loading, setLoading] = useState(false);
    const [fetchingStores, setFetchingStores] = useState(true);

    // Form state
    const [selectedStoreId, setSelectedStoreId] = useState('');
    const [searchTerm, setSearchTerm] = useState('');
    const [isRangeEnabled, setIsRangeEnabled] = useState(false);
    const [startDate, setStartDate] = useState('');
    const [endDate, setEndDate] = useState('');

    // Modal state
    const [showConfirmModal, setShowConfirmModal] = useState(false);
    const [confirmKeyword, setConfirmKeyword] = useState('');

    // Status
    const [message, setMessage] = useState<{ type: 'success' | 'error', text: string } | null>(null);

    useEffect(() => {
        const loadStores = async () => {
            if (!currentMall?.id) return;
            setFetchingStores(true);
            try {
                const data = await ApiService.getStores(currentMall.id);
                setStores(data);
            } catch (err) {
                console.error("Error loading stores for purge:", err);
            } finally {
                setFetchingStores(false);
            }
        };
        loadStores();
    }, [currentMall]);

    const filteredStores = stores.filter(s =>
        s.nombre.toLowerCase().includes(searchTerm.toLowerCase()) ||
        s.codigo_interno.toLowerCase().includes(searchTerm.toLowerCase())
    );

    const selectedStore = stores.find(s => s.id === selectedStoreId);

    const handlePurgeClick = async () => {
        if (!selectedStoreId) {
            setMessage({ type: 'error', text: 'Por favor selecciona un local.' });
            return;
        }
        if (isRangeEnabled && (!startDate || !endDate)) {
            setMessage({ type: 'error', text: 'Por favor selecciona ambas fechas para el rango.' });
            return;
        }

        // Use native confirm for reliability
        const isConfirmed = window.confirm(
            `PROTOCOLO DE SEGURIDAD\n\nVAS A BORRAR VENTAS DE: ${selectedStore?.nombre}\n\n¿Estás SEGURO? Esto no se puede deshacer.`
        );

        if (!isConfirmed) return;

        const secondConfirm = window.prompt("Para confirmar, escribe BORRAR:");
        if (secondConfirm?.trim() !== 'BORRAR') {
            alert("Operación cancelada. La clave no coincide.");
            return;
        }

        setLoading(true);
        try {
            const res = await ApiService.purgeSales(
                selectedStoreId,
                isRangeEnabled ? startDate : undefined,
                isRangeEnabled ? endDate : undefined,
                'BORRAR',
                currentMall?.id,
                session?.access_token || undefined
            );

            if (res.success) {
                alert(`✅ ÉXITO: ${res.message}`);
                setStartDate('');
                setEndDate('');
                setIsRangeEnabled(false);
                setConfirmKeyword('');
            } else {
                alert(`❌ ERROR: ${res.message}`);
            }
        } catch (err: any) {
            console.error(err);
            alert(`❌ ERROR CRÍTICO: ${err.message}`);
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="bg-white border border-red-100 rounded-2xl overflow-hidden shadow-xl shadow-red-500/5 group transition-all hover:shadow-red-500/10 active:scale-[0.998]">
            {/* Red Stripe Header */}
            <div className="h-2 bg-gradient-to-r from-red-500 via-rose-500 to-red-400" />

            <div className="p-4">
                {/* Section Title */}
                <div className="flex items-center justify-between mb-8">
                    <div className="flex items-center gap-4">
                        <div className="w-14 h-14 bg-red-50 rounded-2xl flex items-center justify-center text-red-600 shadow-sm border border-red-100/50">
                            <ShieldAlert size={28} />
                        </div>
                        <div>
                            <h3 className="text-xl font-black text-slate-800 tracking-tight">Zona de Depuración Administrativa</h3>
                            <p className="text-slate-400 text-xs font-semibold uppercase tracking-widest mt-1">TIC & Admin Only Flow</p>
                        </div>
                    </div>
                    <div className="hidden lg:flex items-center gap-1.5 px-4 py-2 bg-red-50 rounded-full border border-red-100/50">
                        <div className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />
                        <span className="text-[10px] font-black text-red-700 uppercase tracking-tighter">Acceso de Alto Privilegio</span>
                    </div>
                </div>

                <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
                    {/* LEFT: Store Selection (7 cols) */}
                    <div className="lg:col-span-7 space-y-4">
                        <div className="flex items-center justify-between px-1">
                            <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest flex items-center gap-2">
                                <Building size={14} className="text-red-500/50" /> Seleccionar Local para Depurar
                            </label>
                            {selectedStoreId && (
                                <button
                                    onClick={() => setSelectedStoreId('')}
                                    className="text-[10px] font-bold text-red-500 hover:underline transition-all"
                                >
                                    Limpiar Selección
                                </button>
                            )}
                        </div>

                        {/* Search & List Container */}
                        <div className="relative bg-slate-50 border border-slate-200 rounded-2xl overflow-hidden focus-within:border-red-500 focus-within:ring-4 focus-within:ring-red-500/5 transition-all">
                            {/* Search Sticky Top */}
                            <div className="relative border-b border-slate-200">
                                <Search className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" size={18} />
                                <input
                                    type="text"
                                    placeholder="Buscar por nombre o código de local..."
                                    value={searchTerm}
                                    onChange={(e) => setSearchTerm(e.target.value)}
                                    className="w-full bg-transparent pl-12 pr-4 py-4 text-sm font-bold text-slate-700 placeholder:text-slate-400 placeholder:font-medium outline-none"
                                />
                            </div>

                            {/* Custom Scrollable List */}
                            <div className="max-h-[320px] overflow-y-auto scrollbar-thin scrollbar-thumb-slate-200 scrollbar-track-transparent">
                                {fetchingStores ? (
                                    <div className="p-12 flex flex-col items-center justify-center gap-3">
                                        <div className="w-8 h-8 rounded-full border-4 border-slate-200 border-t-red-500 animate-spin" />
                                        <span className="text-xs font-bold text-slate-400">Cargando locales...</span>
                                    </div>
                                ) : filteredStores.length === 0 ? (
                                    <div className="p-12 text-center">
                                        <p className="text-sm font-bold text-slate-400 italic">No se encontraron locales para "{searchTerm}"</p>
                                    </div>
                                ) : (
                                    <div className="p-2 space-y-1">
                                        {filteredStores.map(store => (
                                            <button
                                                key={store.id}
                                                onClick={() => setSelectedStoreId(store.id)}
                                                className={`w-full flex items-center justify-between p-3.5 rounded-xl transition-all group/item ${selectedStoreId === store.id
                                                    ? 'bg-red-600 text-white shadow-lg shadow-red-200'
                                                    : 'hover:bg-white hover:shadow-md hover:border-slate-100 text-slate-700'
                                                    }`}
                                            >
                                                <div className="flex items-center gap-3">
                                                    <div className={`w-10 h-10 rounded-lg flex items-center justify-center transition-colors ${selectedStoreId === store.id ? 'bg-white/20' : 'bg-slate-200/50 group-hover/item:bg-red-50'
                                                        }`}>
                                                        <StoreIcon size={18} className={selectedStoreId === store.id ? 'text-white' : 'text-slate-400 group-hover/item:text-red-500'} />
                                                    </div>
                                                    <div className="text-left">
                                                        <p className="text-sm font-black tracking-tight">{store.nombre}</p>
                                                        <p className={`text-[10px] font-bold ${selectedStoreId === store.id ? 'text-white/70' : 'text-slate-400'}`}>
                                                            {store.codigo_interno} • {store.tipo_negocio || 'General'}
                                                        </p>
                                                    </div>
                                                </div>
                                                {selectedStoreId === store.id ? (
                                                    <Check size={20} className="text-white" />
                                                ) : (
                                                    <ChevronRight size={16} className="text-slate-300 opacity-0 group-hover/item:opacity-100 transition-all -translate-x-2 group-hover/item:translate-x-0" />
                                                )}
                                            </button>
                                        ))}
                                    </div>
                                )}
                            </div>
                        </div>
                    </div>

                    {/* RIGHT: Filters & Action (5 cols) */}
                    <div className="lg:col-span-5 flex flex-col h-full">
                        <div className="flex-1 space-y-4 bg-slate-50/50 p-4 rounded-2xl border border-slate-100">
                            {/* Toggle Range */}
                            <div className="bg-white p-5 border border-slate-100 rounded-2xl shadow-sm">
                                <label className="flex items-center justify-between cursor-pointer group">
                                    <div className="flex items-center gap-3">
                                        <div className={`w-10 h-10 rounded-xl flex items-center justify-center transition-all ${isRangeEnabled ? 'bg-indigo-50 text-indigo-600' : 'bg-slate-100 text-slate-400'}`}>
                                            <Calendar size={18} />
                                        </div>
                                        <div>
                                            <p className="text-xs font-black text-slate-800">Filtrar por Rango</p>
                                            <p className="text-[10px] font-bold text-slate-400 tracking-tight">Depuración parcial de fechas</p>
                                        </div>
                                    </div>
                                    <input
                                        type="checkbox"
                                        checked={isRangeEnabled}
                                        onChange={(e) => setIsRangeEnabled(e.target.checked)}
                                        className="sr-only peer"
                                    />
                                    <div className="w-11 h-6 bg-slate-200 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-red-600"></div>
                                </label>

                                {isRangeEnabled && (
                                    <div className="mt-5 grid grid-cols-2 gap-3 pt-4 border-t border-slate-100 animate-in slide-in-from-top-4 duration-300">
                                        <div className="space-y-1.5">
                                            <span className="text-[9px] font-black text-slate-400 uppercase tracking-widest block ml-1">Desde</span>
                                            <input
                                                type="date"
                                                value={startDate}
                                                onChange={(e) => setStartDate(e.target.value)}
                                                className="w-full bg-white border border-slate-200 rounded-xl px-3 py-3 text-sm font-bold text-slate-700 focus:ring-4 focus:ring-red-500/5 focus:border-red-500 outline-none transition-all"
                                            />
                                        </div>
                                        <div className="space-y-1.5">
                                            <span className="text-[9px] font-black text-slate-400 uppercase tracking-widest block ml-1">Hasta</span>
                                            <input
                                                type="date"
                                                value={endDate}
                                                onChange={(e) => setEndDate(e.target.value)}
                                                className="w-full bg-white border border-slate-200 rounded-xl px-3 py-3 text-sm font-bold text-slate-700 focus:ring-4 focus:ring-red-500/5 focus:border-red-500 outline-none transition-all"
                                            />
                                        </div>
                                    </div>
                                )}
                            </div>

                            {/* Warning or Info */}
                            {!isRangeEnabled ? (
                                <div className="bg-red-50 border border-red-100 rounded-2xl p-5 flex items-start gap-4">
                                    <div className="w-10 h-10 bg-red-100 rounded-xl flex items-center justify-center text-red-600 shrink-0">
                                        <AlertTriangle size={20} />
                                    </div>
                                    <div>
                                        <p className="text-xs font-black text-red-900 uppercase">Borrado Total de Local</p>
                                        <p className="text-red-700/70 text-[11px] font-medium leading-relaxed mt-1">
                                            Estás a punto de borrar <span className="underline font-black">TODO</span> el historial de ventas del local seleccionado sin restricciones de fecha.
                                        </p>
                                    </div>
                                </div>
                            ) : (
                                <div className="bg-emerald-50 border border-emerald-100 rounded-2xl p-5 flex items-start gap-4">
                                    <div className="w-10 h-10 bg-emerald-100 rounded-xl flex items-center justify-center text-emerald-600 shrink-0">
                                        <Check size={20} />
                                    </div>
                                    <div>
                                        <p className="text-xs font-black text-emerald-900 uppercase">Borrado Granular</p>
                                        <p className="text-emerald-700/70 text-[11px] font-medium leading-relaxed mt-1">
                                            Solo se eliminarán las facturas comprendidas entre las fechas seleccionadas arriba.
                                        </p>
                                    </div>
                                </div>
                            )}
                        </div>

                        {/* Action CTA */}
                        <div className="mt-8">
                            <button
                                onClick={handlePurgeClick}
                                disabled={loading || !selectedStoreId}
                                className={`w-full group relative overflow-hidden px-8 py-5 rounded-2xl text-sm font-black tracking-widest uppercase transition-all flex items-center justify-center gap-3 shadow-2xl ${loading || !selectedStoreId
                                    ? 'bg-slate-100 text-slate-300 border border-slate-200 cursor-not-allowed'
                                    : 'bg-red-600 text-white shadow-red-500/20 hover:bg-red-700 hover:-translate-y-1 active:scale-95'
                                    }`}
                            >
                                <div className="absolute inset-0 bg-gradient-to-r from-white/0 via-white/10 to-white/0 -translate-x-full group-hover:translate-x-full transition-transform duration-1000" />
                                {loading ? (
                                    <div className="w-5 h-5 rounded-full border-2 border-white/30 border-t-white animate-spin" />
                                ) : (
                                    <>
                                        <Trash2 size={20} />
                                        Ejecutar Purga Definitiva
                                    </>
                                )}
                            </button>
                        </div>
                    </div>
                </div>

                {/* Status Feedback */}
                {message && (
                    <div className={`mt-8 p-4 rounded-2xl flex items-start gap-4 border-2 animate-in slide-in-from-bottom-4 duration-500 ${message.type === 'success'
                        ? 'bg-emerald-50/50 border-emerald-100 text-emerald-800'
                        : 'bg-red-50 border-red-100 text-red-800'
                        }`}>
                        <div className={`w-10 h-10 rounded-xl flex items-center justify-center shrink-0 ${message.type === 'success' ? 'bg-emerald-100 text-emerald-600' : 'bg-red-100 text-red-600'
                            }`}>
                            {message.type === 'success' ? <Check size={20} /> : <AlertTriangle size={20} />}
                        </div>
                        <div className="flex-1">
                            <p className="text-xs font-black uppercase tracking-wider mb-0.5">Resultado del Sistema</p>
                            <p className="text-sm font-bold opacity-80">{message.text}</p>
                        </div>
                        <button onClick={() => setMessage(null)} className="text-slate-400 hover:text-slate-600 bg-white p-1.5 rounded-lg shadow-sm">
                            <X size={16} />
                        </button>
                    </div>
                )}
            </div>
        </div>
    );
};
