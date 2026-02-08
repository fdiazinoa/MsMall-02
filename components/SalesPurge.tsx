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

    const handlePurgeClick = () => {
        if (!selectedStoreId) {
            setMessage({ type: 'error', text: 'Por favor selecciona un local de la lista.' });
            return;
        }
        if (isRangeEnabled && (!startDate || !endDate)) {
            setMessage({ type: 'error', text: 'Por favor selecciona ambas fechas para el rango.' });
            return;
        }
        setMessage(null);
        setShowConfirmModal(true);
    };

    const handlePurgeConfirm = async () => {
        if (confirmKeyword !== 'BORRAR') return;

        setLoading(true);
        setShowConfirmModal(false);
        setConfirmKeyword('');

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
                setMessage({ type: 'success', text: res.message });
                // Reset form
                setStartDate('');
                setEndDate('');
                setIsRangeEnabled(false);
            } else {
                setMessage({ type: 'error', text: res.message });
            }
        } catch (err: any) {
            setMessage({ type: 'error', text: err.message || 'Error al procesar la solicitud' });
        } finally {
            setLoading(false);
        }
    };

    const selectedStore = stores.find(s => s.id === selectedStoreId);

    return (
        <div className="bg-white border border-red-100 rounded-3xl overflow-hidden shadow-xl shadow-red-500/5 group transition-all hover:shadow-red-500/10 active:scale-[0.998]">
            {/* Red Stripe Header */}
            <div className="h-2 bg-gradient-to-r from-red-500 via-rose-500 to-red-400" />

            <div className="p-8">
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

                <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
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
                        <div className="flex-1 space-y-6 bg-slate-50/50 p-6 rounded-3xl border border-slate-100">
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
                                className={`w-full group relative overflow-hidden px-8 py-5 rounded-3xl text-sm font-black tracking-widest uppercase transition-all flex items-center justify-center gap-3 shadow-2xl ${loading || !selectedStoreId
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
                    <div className={`mt-8 p-6 rounded-3xl flex items-start gap-4 border-2 animate-in slide-in-from-bottom-4 duration-500 ${message.type === 'success'
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

            {/* Security Modal (Refined) */}
            {showConfirmModal && (
                <div className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-900/90 backdrop-blur-xl p-4 animate-in fade-in duration-300">
                    <div className="bg-white rounded-[40px] shadow-[0_32px_128px_-15px_rgba(220,38,38,0.5)] w-full max-w-lg border border-slate-100 overflow-hidden animate-in zoom-in-95 duration-500">
                        {/* Modal Top Branding */}
                        <div className="bg-red-600 p-12 text-white text-center relative overflow-hidden">
                            {/* SVG Background Pattern */}
                            <div className="absolute inset-0 opacity-10 pointer-events-none">
                                <svg width="100%" height="100%" xmlns="http://www.w3.org/2000/svg">
                                    <defs>
                                        <pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">
                                            <path d="M 40 0 L 0 0 0 40" fill="none" stroke="white" strokeWidth="1" />
                                        </pattern>
                                    </defs>
                                    <rect width="100%" height="100%" fill="url(#grid)" />
                                </svg>
                            </div>

                            <div className="relative z-10">
                                <div className="absolute -top-4 -right-4 m-8 text-white/50 hover:text-white transition-colors cursor-pointer" onClick={() => setShowConfirmModal(false)}>
                                    <X size={32} strokeWidth={3} />
                                </div>
                                <div className="w-24 h-24 bg-white rounded-[32px] flex items-center justify-center mx-auto mb-6 shadow-2xl rotate-3">
                                    <Trash2 size={48} className="text-red-600" />
                                </div>
                                <h3 className="text-4xl font-black uppercase tracking-tighter leading-none mb-2">Protocolo de<br />Seguridad</h3>
                                <p className="text-red-100/60 text-xs font-bold uppercase tracking-widest">Confirmación de Acción Destructiva</p>
                            </div>
                        </div>

                        <div className="p-12 space-y-8">
                            <div className="bg-slate-50 rounded-[32px] p-8 border border-slate-100 relative overflow-hidden">
                                <div className="relative z-10 items-center justify-center flex flex-col text-center">
                                    <p className="text-slate-400 text-xs font-black uppercase tracking-widest mb-3">Local Impactado</p>
                                    <h4 className="text-2xl font-black text-slate-900 leading-tight">"{selectedStore?.nombre}"</h4>

                                    <div className="mt-6 inline-flex items-center gap-3 px-6 py-2.5 bg-red-600 text-white rounded-2xl shadow-lg shadow-red-200">
                                        <div className="w-2.5 h-2.5 bg-white rounded-full animate-pulse shadow-[0_0_8px_white]" />
                                        <span className="text-sm font-black uppercase tracking-tighter">
                                            {isRangeEnabled ? `Del ${startDate} al ${endDate}` : 'Historial Definitivo'}
                                        </span>
                                    </div>
                                </div>
                            </div>

                            <div className="space-y-4">
                                <label className="block text-[10px] font-black text-red-500 uppercase tracking-[0.4em] text-center">Para proceder, escribe la clave maestra:</label>
                                <input
                                    type="text"
                                    value={confirmKeyword}
                                    onChange={(e) => setConfirmKeyword(e.target.value.toUpperCase())}
                                    placeholder="BORRAR"
                                    className="w-full bg-slate-50 border-4 border-slate-100 rounded-[32px] px-8 py-6 text-center text-5xl font-black tracking-[0.5em] focus:border-red-600 focus:bg-white focus:ring-8 focus:ring-red-600/5 transition-all text-red-600 placeholder:text-slate-200 placeholder:font-black placeholder:tracking-tight placeholder:text-lg"
                                    autoFocus
                                />
                                <p className="text-[10px] text-slate-400 font-bold text-center italic mt-2 opacity-60">Esta acción no se puede deshacer una vez confirmada.</p>
                            </div>

                            <div className="flex flex-col gap-4 pt-4">
                                <button
                                    onClick={handlePurgeConfirm}
                                    disabled={confirmKeyword !== 'BORRAR'}
                                    className={`w-full py-6 rounded-[32px] text-sm font-black tracking-[0.2em] uppercase transition-all shadow-2xl active:scale-95 flex items-center justify-center gap-3 ${confirmKeyword === 'BORRAR'
                                            ? 'bg-red-600 text-white shadow-red-500/40 hover:bg-red-700'
                                            : 'bg-slate-100 text-slate-300 pointer-events-none'
                                        }`}
                                >
                                    Confirmar Ejecución
                                </button>
                                <button
                                    onClick={() => { setShowConfirmModal(false); setConfirmKeyword(''); }}
                                    className="w-full py-4 text-xs font-black text-slate-400 hover:text-red-500 transition-all uppercase tracking-widest"
                                >
                                    Abortar Operación
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};
