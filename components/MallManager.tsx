import React, { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthProvider';
import { ApiService } from '../api';
import { Plus, Edit2, Trash2, Building, Loader2, X } from 'lucide-react';

export const MallManager: React.FC = () => {
    const { session, refreshMalls } = useAuth();
    const [malls, setMalls] = useState<any[]>([]);
    const [loading, setLoading] = useState(true);
    const [modalOpen, setModalOpen] = useState(false);
    const [editingMall, setEditingMall] = useState<any>(null);
    const [formData, setFormData] = useState({ nombre: '', conf_locale: 'es-CL', conf_moneda: 'CLP' });
    const [error, setError] = useState<string | null>(null);

    const loadMalls = async () => {
        setLoading(true);
        if (session?.access_token) {
            const data = await ApiService.getMalls(session.access_token);
            setMalls(data);
        }
        setLoading(false);
    };

    useEffect(() => {
        loadMalls();
    }, [session]);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError(null);
        if (!session?.access_token) return;

        try {
            if (editingMall) {
                await ApiService.updateMall(editingMall.id, formData, session.access_token);
            } else {
                await ApiService.createMall(formData, session.access_token);
            }
            setModalOpen(false);
            setEditingMall(null);
            setFormData({ nombre: '', conf_locale: 'es-CL', conf_moneda: 'CLP' });
            loadMalls();
            if (refreshMalls) refreshMalls();
        } catch (err: any) {
            setError(err.message);
        }
    };

    const handleDelete = async (id: string) => {
        if (!window.confirm("¿Seguro que deseas eliminar este Mall?")) return;
        if (!session?.access_token) return;
        try {
            await ApiService.deleteMall(id, session.access_token);
            loadMalls();
            if (refreshMalls) refreshMalls();
        } catch (err: any) {
            alert(err.message);
        }
    };

    const openModal = (mall?: any) => {
        setError(null);
        if (mall) {
            setEditingMall(mall);
            setFormData({
                nombre: mall.nombre,
                conf_locale: mall.conf_locale || 'es-CL',
                conf_moneda: mall.conf_moneda || 'CLP'
            });
        } else {
            setEditingMall(null);
            setFormData({ nombre: '', conf_locale: 'es-CL', conf_moneda: 'CLP' });
        }
        setModalOpen(true);
    };

    if (loading) return <div className="flex justify-center p-10"><Loader2 className="animate-spin text-indigo-600" /></div>;

    return (
        <div className="space-y-4">
            <div className="flex justify-between items-center">
                <div>
                    <h2 className="text-xl font-bold text-slate-800">Gestión de Malls</h2>
                    <p className="text-slate-500">Administra los centros comerciales del sistema.</p>
                </div>
                <button
                    onClick={() => openModal()}
                    className="bg-indigo-600 hover:bg-indigo-700 text-white px-4 py-2 rounded-lg flex items-center gap-2 font-medium transition-colors"
                >
                    <Plus size={18} /> Nuevo Mall
                </button>
            </div>

            <div className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
                <table className="w-full text-left">
                    <thead className="bg-slate-50 border-b border-slate-200 text-slate-500 font-medium text-xs uppercase">
                        <tr>
                            <th className="px-3 py-2.5">Nombre</th>
                            <th className="px-3 py-2.5">ID</th>
                            <th className="px-3 py-2.5 text-right">Acciones</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                        {malls.length === 0 ? (
                            <tr><td colSpan={3} className="px-6 py-8 text-center text-slate-400">No hay malls registrados.</td></tr>
                        ) : (
                            malls.map(mall => (
                                <tr key={mall.id} className="hover:bg-slate-50 transition-colors">
                                    <td className="px-3 py-2.5 font-medium text-slate-800 flex items-center gap-3">
                                        <div className="p-2 bg-indigo-50 text-indigo-600 rounded-lg">
                                            <Building size={18} />
                                        </div>
                                        {mall.nombre}
                                    </td>
                                    <td className="px-3 py-2.5 text-slate-500 font-mono text-xs">{mall.id}</td>
                                    <td className="px-3 py-2.5 text-right space-x-2">
                                        <button
                                            onClick={() => openModal(mall)}
                                            className="p-2 text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 rounded-lg transition-colors"
                                            title="Editar"
                                        >
                                            <Edit2 size={16} />
                                        </button>
                                        <button
                                            onClick={() => handleDelete(mall.id)}
                                            className="p-2 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                                            title="Eliminar"
                                        >
                                            <Trash2 size={16} />
                                        </button>
                                    </td>
                                </tr>
                            ))
                        )}
                    </tbody>
                </table>
            </div>

            {/* Modal */}
            {modalOpen && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm animate-in fade-in">
                    <div className="bg-white rounded-xl shadow-xl w-full max-w-md p-4">
                        <div className="flex justify-between items-center mb-6">
                            <h3 className="text-lg font-bold text-slate-800">{editingMall ? 'Editar Mall' : 'Nuevo Mall'}</h3>
                            <button onClick={() => setModalOpen(false)} className="text-slate-400 hover:text-slate-600">
                                <X size={20} />
                            </button>
                        </div>

                        {error && <div className="mb-4 p-3 bg-red-50 text-red-600 rounded-lg text-sm">{error}</div>}

                        <form onSubmit={handleSubmit} className="space-y-4">
                            <div>
                                <label className="block text-sm font-medium text-slate-700 mb-1">Nombre del Mall</label>
                                <input
                                    type="text"
                                    value={formData.nombre}
                                    onChange={e => setFormData({ ...formData, nombre: e.target.value })}
                                    className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                                    placeholder="Ej: Mall Plaza Norte"
                                    required
                                />
                            </div>

                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <label className="block text-sm font-medium text-slate-700 mb-1">Formato Regional</label>
                                    <select
                                        value={formData.conf_locale}
                                        onChange={e => setFormData({ ...formData, conf_locale: e.target.value })}
                                        className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:outline-none text-sm"
                                    >
                                        <option value="es-CL">Chile (1.234,56)</option>
                                        <option value="es-ES">España (1.234,56)</option>
                                        <option value="en-US">EE.UU. (1,234.56)</option>
                                        <option value="es-MX">México (1,234.56)</option>
                                    </select>
                                </div>
                                <div>
                                    <label className="block text-sm font-medium text-slate-700 mb-1">Moneda</label>
                                    <select
                                        value={formData.conf_moneda}
                                        onChange={e => setFormData({ ...formData, conf_moneda: e.target.value })}
                                        className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:outline-none text-sm"
                                    >
                                        <option value="CLP">CLP ($)</option>
                                        <option value="USD">USD ($)</option>
                                        <option value="EUR">EUR (€)</option>
                                        <option value="MXN">MXN ($)</option>
                                    </select>
                                </div>
                            </div>
                            <div className="flex justify-end gap-3 pt-4">
                                <button
                                    type="button"
                                    onClick={() => setModalOpen(false)}
                                    className="px-4 py-2 text-slate-600 hover:bg-slate-100 rounded-lg transition-colors"
                                >
                                    Cancelar
                                </button>
                                <button
                                    type="submit"
                                    className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg transition-colors"
                                >
                                    Guardar
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}
        </div>
    );
};
