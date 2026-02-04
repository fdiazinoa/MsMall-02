
import React, { useState, useEffect } from 'react';
import { Store, ApiService } from '../api';
import { useAuth } from '../context/AuthProvider';
import {
  Store as StoreIcon, Plus, Search, Building2,
  User, FileText, MapPin, Tag, Maximize2, Percent, X
} from 'lucide-react';

export const StoreMaintenance: React.FC = () => {
  const { currentMall } = useAuth();
  const [stores, setStores] = useState<Store[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [isResetting, setIsResetting] = useState(false);

  const handleResetSales = async () => {
    if (!confirm("⚠️ ALERTA CRÍTICA ⚠️\n\nEstá a punto de BORRAR TODAS LAS VENTAS de la base de datos.\n\nEsta acción es irreversible y dejará los reportes vacíos.\n¿Desea continuar?")) {
      return;
    }

    // Doble confirmación
    if (!confirm("Confirmación Final:\n\n¿Realmente desea eliminar permanentemente el historial de ventas completo?")) {
      return;
    }

    setIsResetting(true);
    try {
      const result = await ApiService.resetAllSales();
      if (result.success) {
        alert("✅ Operación Exitosa:\nLa tabla de ventas ha sido vaciada.");
      } else {
        alert("❌ Error:\n" + result.message);
      }
    } catch (e: any) {
      alert("❌ Error de comunicación:\n" + (e.message || String(e)));
    } finally {
      setIsResetting(false);
    }
  };

  const [newStore, setNewStore] = useState<Partial<Store>>({
    nombre: '',
    codigo_interno: '',
    mall_id: '',
    responsable: '',
    contrato_no: '',
    piso: '',
    tipo_negocio: '',
    mts: '',
    porciento_renta: '',
    rubro: ''
  });

  const loadStores = async () => {
    if (!currentMall?.id) return;
    setLoading(true);
    try {
      const data = await ApiService.getStores(currentMall.id);
      setStores(data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!currentMall?.id) {
      alert("Error: No se ha seleccionado un Mall.");
      return;
    }

    // Ensure mall_id is set
    const storeToSave = { ...newStore, mall_id: currentMall.id };

    try {
      if (storeToSave.id) {
        await ApiService.updateStore(storeToSave.id, storeToSave);
      } else {
        await ApiService.createStore(storeToSave);
      }
      setShowForm(false);
      setNewStore({
        nombre: '',
        codigo_interno: '',
        mall_id: currentMall.id,
        responsable: '',
        contrato_no: '',
        piso: '',
        tipo_negocio: '',
        mts: '',
        porciento_renta: '',
        rubro: ''
      });
      loadStores();
    } catch (e: any) {
      console.error(e);
      alert("Error al guardar: " + (e.message || e));
    }
  };

  const handleDelete = async (id: string, nombre: string) => {
    if (!confirm(`¿Está seguro de que desea eliminar el local "${nombre}"?\nEsta acción no se puede deshacer.`)) return;
    try {
      await ApiService.deleteStore(id);
      loadStores();
    } catch (e: any) {
      console.error(e);
      alert("Error al eliminar: " + (e.message || e));
    }
  };

  const handleEdit = (store: Store) => {
    setNewStore({ ...store });
    setShowForm(true);
  };

  useEffect(() => {
    loadStores();
  }, [currentMall]);

  return (
    <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
        <div>
          <h2 className="text-2xl font-bold text-slate-800">Mantenimiento de Locales</h2>
          <p className="text-slate-500">Gestione la configuración contractual y física de las tiendas.</p>
        </div>
        <button
          onClick={() => setShowForm(!showForm)}
          className="bg-indigo-600 text-white px-5 py-2.5 rounded-xl flex items-center gap-2 hover:bg-indigo-700 transition-all shadow-md active:scale-95 font-medium"
        >
          {showForm ? <X size={18} /> : <Plus size={18} />}
          {showForm ? 'Cancelar Registro' : 'Registrar Nuevo Local'}
        </button>
      </div>

      {showForm && (
        <div className="bg-white p-8 rounded-2xl border border-indigo-100 shadow-xl animate-in zoom-in-95 duration-200">
          <h3 className="text-lg font-bold text-slate-800 mb-6 flex items-center gap-2">
            <StoreIcon className="text-indigo-600" size={20} />
            Información del Nuevo Local
          </h3>
          <form onSubmit={handleCreate} className="space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              {/* Información Básica */}
              <div className="space-y-4">
                <h4 className="text-xs font-bold text-slate-400 uppercase tracking-widest">Básico</h4>
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">Nombre Comercial</label>
                  <input
                    type="text" required
                    value={newStore.nombre}
                    onChange={(e) => setNewStore({ ...newStore, nombre: e.target.value })}
                    className="w-full px-4 py-2 rounded-lg border border-slate-200 focus:ring-2 focus:ring-indigo-500 outline-none"
                    placeholder="Ej. Adidas Store"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">Código Interno</label>
                  <input
                    type="text" required
                    value={newStore.codigo_interno}
                    onChange={(e) => setNewStore({ ...newStore, codigo_interno: e.target.value })}
                    className="w-full px-4 py-2 rounded-lg border border-slate-200 focus:ring-2 focus:ring-indigo-500 outline-none"
                    placeholder="L001"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">Tipo de Negocio</label>
                  <input
                    type="text"
                    value={newStore.tipo_negocio}
                    onChange={(e) => setNewStore({ ...newStore, tipo_negocio: e.target.value })}
                    className="w-full px-4 py-2 rounded-lg border border-slate-200 focus:ring-2 focus:ring-indigo-500 outline-none"
                    placeholder="Ropa, Restaurante..."
                  />
                </div>
              </div>

              {/* Información Contractual */}
              <div className="space-y-4">
                <h4 className="text-xs font-bold text-slate-400 uppercase tracking-widest">Contractual</h4>
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">Responsable</label>
                  <input
                    type="text"
                    value={newStore.responsable}
                    onChange={(e) => setNewStore({ ...newStore, responsable: e.target.value })}
                    className="w-full px-4 py-2 rounded-lg border border-slate-200 focus:ring-2 focus:ring-indigo-500 outline-none"
                    placeholder="Nombre del encargado"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">Nº Contrato</label>
                  <input
                    type="text"
                    value={newStore.contrato_no}
                    onChange={(e) => setNewStore({ ...newStore, contrato_no: e.target.value })}
                    className="w-full px-4 py-2 rounded-lg border border-slate-200 focus:ring-2 focus:ring-indigo-500 outline-none"
                    placeholder="99-88-11"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">% Renta Variable</label>
                  <div className="relative">
                    <input
                      type="number" step="0.01"
                      value={newStore.porciento_renta}
                      onChange={(e) => setNewStore({ ...newStore, porciento_renta: e.target.value })}
                      className="w-full px-4 py-2 rounded-lg border border-slate-200 focus:ring-2 focus:ring-indigo-500 outline-none pr-8"
                      placeholder="5.00"
                    />
                    <Percent size={14} className="absolute right-3 top-3 text-slate-400" />
                  </div>
                </div>
              </div>

              {/* Información Física */}
              <div className="space-y-4">
                <h4 className="text-xs font-bold text-slate-400 uppercase tracking-widest">Ubicación y Espacio</h4>
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">Piso / Ubicación</label>
                  <input
                    type="text"
                    value={newStore.piso}
                    onChange={(e) => setNewStore({ ...newStore, piso: e.target.value })}
                    className="w-full px-4 py-2 rounded-lg border border-slate-200 focus:ring-2 focus:ring-indigo-500 outline-none"
                    placeholder="P2-L01"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">Metros Cuadrados (Mts2)</label>
                  <div className="relative">
                    <input
                      type="number" step="0.01"
                      value={newStore.mts}
                      onChange={(e) => setNewStore({ ...newStore, mts: e.target.value })}
                      className="w-full px-4 py-2 rounded-lg border border-slate-200 focus:ring-2 focus:ring-indigo-500 outline-none pr-10"
                      placeholder="100.00"
                    />
                    <span className="absolute right-3 top-2.5 text-xs text-slate-400 font-bold">m²</span>
                  </div>
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">Rubro General</label>
                  <input
                    type="text"
                    value={newStore.rubro || ''}
                    onChange={(e) => setNewStore({ ...newStore, rubro: e.target.value })}
                    className="w-full px-4 py-2 rounded-lg border border-slate-200 focus:ring-2 focus:ring-indigo-500 outline-none"
                    placeholder="Vestuario, Comida..."
                  />
                </div>
                <div className="pt-2">
                  <label className="flex items-center gap-3 cursor-pointer group">
                    <div className="relative">
                      <input
                        type="checkbox"
                        checked={newStore.upsert_activo}
                        onChange={(e) => setNewStore({ ...newStore, upsert_activo: e.target.checked })}
                        className="sr-only peer"
                      />
                      <div className="w-10 h-5 bg-slate-200 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-indigo-600"></div>
                    </div>
                    <span className="text-sm font-medium text-slate-700 group-hover:text-indigo-600 transition-colors">Activar Sobrescritura (Upsert)</span>
                  </label>
                  <p className="text-[10px] text-slate-400 mt-1 ml-13">Permite corregir facturas del mismo día sobrescribiendo datos existentes.</p>
                </div>
              </div>
            </div>

            <div className="pt-6 border-t border-slate-100 flex justify-end gap-3">
              <button type="button" onClick={() => setShowForm(false)} className="px-6 py-2.5 rounded-xl border border-slate-200 text-slate-600 font-medium hover:bg-slate-50 transition-colors">Cancelar</button>
              <button type="submit" className="px-10 py-2.5 rounded-xl bg-indigo-600 text-white font-bold hover:bg-indigo-700 shadow-lg shadow-indigo-600/20 active:scale-95 transition-all">Guardar Local</button>
            </div>
          </form>
        </div>
      )}

      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="p-4 border-b border-slate-100 bg-slate-50/50 flex items-center justify-between">
          <div className="flex items-center gap-3 flex-1 max-w-md">
            <Search size={18} className="text-slate-400" />
            <input type="text" placeholder="Buscar por nombre, responsable o código..." className="bg-transparent border-none outline-none text-sm w-full" />
          </div>
          <div className="text-xs text-slate-400 font-medium">
            Mostrando {stores.length} locales registrados
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left">
            <thead className="bg-slate-50/50 text-slate-500 text-[10px] uppercase font-bold tracking-widest border-b border-slate-100">
              <tr>
                <th className="px-6 py-4">Información Local</th>
                <th className="px-6 py-4">Responsable</th>
                <th className="px-6 py-4">Ubicación (Piso)</th>
                <th className="px-6 py-4 text-center">Metraje (Mts²)</th>
                <th className="px-6 py-4 text-center">Renta %</th>
                <th className="px-6 py-4 text-right">Acciones</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {loading ? (
                <tr>
                  <td colSpan={6} className="px-6 py-12 text-center text-slate-400">
                    <div className="flex flex-col items-center gap-2">
                      <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-indigo-600"></div>
                      <span className="text-sm">Cargando datos de locales...</span>
                    </div>
                  </td>
                </tr>
              ) : stores.length > 0 ? (
                stores.map((store) => (
                  <tr key={store.id} className="hover:bg-slate-50/80 transition-colors group">
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-3">
                        <div className="p-2 bg-indigo-50 text-indigo-600 rounded-lg group-hover:bg-indigo-100 transition-colors">
                          <StoreIcon size={18} />
                        </div>
                        <div>
                          <div className="font-bold text-slate-800 text-sm leading-none mb-1 flex items-center gap-2">
                            {store.nombre}
                            {store.processing_status === 'SUSPENDED_AUTH_ERROR' && (
                              <span className="px-1.5 py-0.5 rounded-full bg-red-100 text-red-600 text-[9px] uppercase font-extrabold tracking-wider border border-red-200">
                                Suspendido
                              </span>
                            )}
                          </div>
                          <div className="flex items-center gap-2">
                            <span className="text-[10px] font-mono bg-slate-100 px-1.5 py-0.5 rounded text-slate-500">ID: {store.codigo_interno}</span>
                            <span className="text-[10px] text-slate-400 flex items-center gap-1"><Tag size={8} /> {store.tipo_negocio || 'General'}</span>
                          </div>
                        </div>
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <div className="text-sm font-medium text-slate-700 flex items-center gap-2">
                        <User size={14} className="text-slate-400" />
                        {store.responsable}
                      </div>
                      <div className="text-[10px] text-slate-400 flex items-center gap-1 mt-0.5 ml-5">
                        <FileText size={10} /> {store.contrato_no}
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-2 text-slate-600 text-sm font-medium">
                        <MapPin size={14} className="text-indigo-400" />
                        {store.piso}
                      </div>
                      <div className="text-[10px] text-slate-400 ml-5 mt-0.5 flex items-center gap-1">
                        <Building2 size={10} /> {store.mall_nombre || 'Mall Plaza'}
                      </div>
                    </td>
                    <td className="px-6 py-4 text-center">
                      <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-slate-100 text-slate-700 text-xs font-bold">
                        <Maximize2 size={12} className="text-slate-400" />
                        {store.mts}
                      </div>
                    </td>
                    <td className="px-6 py-4 text-center">
                      <div className="text-sm font-bold text-indigo-600">
                        {store.porciento_renta}%
                      </div>
                    </td>
                    <td className="px-6 py-4 text-right">
                      <div className="flex items-center justify-end gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                        {store.processing_status === 'SUSPENDED_AUTH_ERROR' ? (
                          <button
                            onClick={async () => {
                              if (confirm('¿Reactivar este local? Se restablecerá el contador de fallos.')) {
                                try {
                                  await ApiService.reactivateStore(store.id);
                                  loadStores();
                                } catch (e) { alert('Error: ' + e); }
                              }
                            }}
                            className="bg-red-100 text-red-700 px-3 py-1 rounded-lg text-xs font-bold hover:bg-red-200 transition-colors flex items-center gap-1"
                          >
                            <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><path d="M2 12a10 10 0 1 0 20 0 10 10 0 1 0-20 0" /><path d="m16 10-4 4-4-4" /></svg>
                            Reactivar
                          </button>
                        ) : (
                          <>
                            <button
                              onClick={() => handleEdit(store)}
                              className="p-2 text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 rounded-lg transition-all"
                              title="Editar"
                            >
                              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z" /><path d="m15 5 4 4" /></svg>
                            </button>
                            <button
                              onClick={() => handleDelete(store.id, store.nombre)}
                              className="p-2 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-all"
                              title="Eliminar"
                            >
                              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 6h18" /><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6" /><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2" /><line x1="10" x2="10" y1="11" y2="17" /><line x1="14" x2="14" y1="11" y2="17" /></svg>
                            </button>
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={6} className="px-6 py-20 text-center">
                    <div className="flex flex-col items-center gap-3 text-slate-300">
                      <StoreIcon size={48} strokeWidth={1} />
                      <p className="text-slate-500 font-medium italic">No se encontraron locales registrados con estos criterios.</p>
                    </div>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Danger Zone */}
      <div className="mt-8 border-t border-red-200 pt-8 animate-in fade-in slide-in-from-bottom-8 duration-700 delay-150">
        <h3 className="text-lg font-bold text-red-700 flex items-center gap-2 mb-4">
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path></svg>
          Zona de Peligro (Admin)
        </h3>
        <div className="bg-red-50 border border-red-200 rounded-xl p-6 flex flex-col md:flex-row items-center justify-between gap-6 hover:shadow-lg transition-shadow">
          <div>
            <h4 className="font-bold text-red-800 text-sm">Reiniciar Base de Datos de Ventas</h4>
            <p className="text-red-600/80 text-xs mt-1 max-w-lg leading-relaxed">
              Esta acción eliminará <strong>TODOS</strong> los registros de la tabla de ventas de forma permanente.
              Utilice esta función solo para limpiar datos de prueba una vez concluidas las validaciones.
            </p>
          </div>
          <button
            onClick={handleResetSales}
            disabled={isResetting}
            className={`px-6 py-3 rounded-xl bg-red-600 text-white font-bold text-sm shadow-lg shadow-red-600/20 hover:bg-red-700 active:scale-95 transition-all flex items-center gap-2 border border-red-500 hover:border-red-400 ${isResetting ? 'opacity-70 cursor-not-allowed' : ''}`}
          >
            {isResetting ? (
              <><div className="animate-spin h-4 w-4 border-2 border-white/30 border-t-white rounded-full"></div> Limpiando Base de Datos...</>
            ) : (
              <><span className="text-lg">🗑️</span> Borrar Todas las Ventas</>
            )}
          </button>
        </div>
      </div>
    </div>
  );
};
