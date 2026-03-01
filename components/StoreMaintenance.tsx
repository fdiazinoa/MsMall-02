import React, { useEffect, useState } from 'react';
import { ApiService, Store, StoreCatalogOption } from '../api';
import { useAuth } from '../context/AuthProvider';
import {
  buildStoreCatalogValues,
  loadStoreCatalogOptions,
  normalizeStoreCatalogKey,
  normalizeStoreCatalogText,
  STORE_CATALOG_MIGRATION_FILE,
} from '../utils/storeCatalog';
import {
  Building2,
  FileText,
  MapPin,
  Maximize2,
  Percent,
  Plus,
  Search,
  Store as StoreIcon,
  Tag,
  User,
  X,
} from 'lucide-react';
import { SalesPurge } from './SalesPurge';

interface StoreMaintenanceProps {
  onOpenCatalogs?: () => void;
}

const createEmptyStore = (mallId = ''): Partial<Store> => ({
  nombre: '',
  codigo_interno: '',
  mall_id: mallId,
  responsable: '',
  contrato_no: '',
  piso: '',
  tipo_negocio: '',
  mts: '',
  porciento_renta: '',
  rubro: '',
});

export const StoreMaintenance: React.FC<StoreMaintenanceProps> = ({ onOpenCatalogs }) => {
  const { currentMall, isAdmin, isTic, session } = useAuth();
  const canManageStores = isAdmin || isTic;
  const [stores, setStores] = useState<Store[]>([]);
  const [catalogOptions, setCatalogOptions] = useState<StoreCatalogOption[]>([]);
  const [catalogTableAvailable, setCatalogTableAvailable] = useState<boolean | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [floorFilter, setFloorFilter] = useState('ALL');
  const [mtsFilter, setMtsFilter] = useState('ALL');
  const [businessTypeFilter, setBusinessTypeFilter] = useState('ALL');
  const [loading, setLoading] = useState(true);
  const [showFormDrawer, setShowFormDrawer] = useState(false);
  const [drawerMode, setDrawerMode] = useState<'create' | 'edit'>('create');
  const [newStore, setNewStore] = useState<Partial<Store>>(createEmptyStore());

  const normalizeText = normalizeStoreCatalogText;
  const normalizeSearch = normalizeStoreCatalogKey;

  const updateNewStoreField = (fieldName: 'tipo_negocio' | 'rubro', value: string) => {
    setNewStore((prev) => ({ ...prev, [fieldName]: value }));
  };

  const loadStores = async () => {
    if (!currentMall?.id) {
      setStores([]);
      setLoading(false);
      return;
    }

    setLoading(true);
    try {
      const data = await ApiService.getStores(currentMall.id);
      setStores(data);
    } catch (error) {
      console.error(error);
      alert('Error cargando locales.');
    } finally {
      setLoading(false);
    }
  };

  const loadCatalogs = async () => {
    if (!currentMall?.id) {
      setCatalogOptions([]);
      setCatalogTableAvailable(null);
      return;
    }

    try {
      const result = await loadStoreCatalogOptions(currentMall.id);
      setCatalogOptions(result.options);
      setCatalogTableAvailable(result.available);
    } catch (error: any) {
      console.error(error);
      alert(`Error cargando catalogos: ${error.message || error}`);
    }
  };

  const closeFormDrawer = () => {
    setShowFormDrawer(false);
    setDrawerMode('create');
    setNewStore(createEmptyStore(currentMall?.id || ''));
  };

  const openCreateDrawer = () => {
    setDrawerMode('create');
    setNewStore(createEmptyStore(currentMall?.id || ''));
    setShowFormDrawer(true);
  };

  const handleSaveStore = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!currentMall?.id) {
      alert('Error: No se ha seleccionado un Mall.');
      return;
    }

    const storeToSave = { ...newStore, mall_id: currentMall.id };

    try {
      if (storeToSave.id) {
        await ApiService.updateStore(storeToSave.id, storeToSave);
      } else {
        await ApiService.createStore(storeToSave);
      }
      closeFormDrawer();
      await loadStores();
    } catch (error: any) {
      console.error(error);
      alert('Error al guardar: ' + (error.message || error));
    }
  };

  const handleDelete = async (id: string, nombre: string) => {
    if (!confirm(`¿Está seguro de que desea eliminar el local "${nombre}"?\nEsta acción no se puede deshacer.`)) return;

    try {
      await ApiService.deleteStore(id);
      await loadStores();
    } catch (error: any) {
      console.error(error);
      alert('Error al eliminar: ' + (error.message || error));
    }
  };

  const handleEdit = (store: Store) => {
    setDrawerMode('edit');
    setNewStore({ ...createEmptyStore(currentMall?.id || ''), ...store });
    setShowFormDrawer(true);
  };

  useEffect(() => {
    if (!currentMall?.id) {
      setStores([]);
      setCatalogOptions([]);
      setCatalogTableAvailable(null);
      setLoading(false);
      setShowFormDrawer(false);
      setDrawerMode('create');
      setNewStore(createEmptyStore());
      return;
    }

    setShowFormDrawer(false);
    setDrawerMode('create');
    setNewStore((prev) => ({ ...prev, mall_id: currentMall.id }));
    loadStores();
    loadCatalogs();
  }, [currentMall?.id]);

  const catalogValuesByField = {
    tipo_negocio: buildStoreCatalogValues({
      fieldName: 'tipo_negocio',
      catalogOptions,
      catalogTableAvailable,
      stores,
      selectedValue: newStore.tipo_negocio || '',
    }),
    rubro: buildStoreCatalogValues({
      fieldName: 'rubro',
      catalogOptions,
      catalogTableAvailable,
      stores,
      selectedValue: newStore.rubro || '',
    }),
  };

  const storeFloorValue = (store: Store) => normalizeText(store.piso);
  const storeMtsValue = (store: Store) => normalizeText(store.mts);
  const storeBusinessTypeValue = (store: Store) => normalizeText(store.tipo_negocio) || 'General';

  const floorOptions: string[] = Array.from(
    new Set(
      stores
        .map((store) => storeFloorValue(store))
        .filter((value): value is string => Boolean(value))
    )
  ) as string[];
  floorOptions.sort((a, b) => a.localeCompare(b, undefined, { numeric: true, sensitivity: 'base' }));

  const mtsOptions: string[] = Array.from(
    new Set(
      stores
        .map((store) => storeMtsValue(store))
        .filter((value): value is string => Boolean(value))
    )
  ) as string[];
  mtsOptions.sort((a, b) => {
    const na = Number(a);
    const nb = Number(b);
    if (Number.isFinite(na) && Number.isFinite(nb)) return na - nb;
    return a.localeCompare(b, undefined, { numeric: true, sensitivity: 'base' });
  });

  const businessTypeOptions: string[] = Array.from(
    new Set(stores.map((store) => storeBusinessTypeValue(store)).filter((value): value is string => Boolean(value)))
  ) as string[];
  businessTypeOptions.sort((a, b) => a.localeCompare(b, undefined, { sensitivity: 'base' }));

  const filteredStores = stores.filter((store) => {
    const matchesSearch = !searchTerm || [
      store.nombre,
      store.codigo_interno,
      store.responsable,
      store.contrato_no,
      store.piso,
      store.tipo_negocio,
      store.rubro,
    ].some((value) => normalizeSearch(value).includes(normalizeSearch(searchTerm)));

    const matchesFloor = floorFilter === 'ALL' || storeFloorValue(store) === floorFilter;
    const matchesMts = mtsFilter === 'ALL' || storeMtsValue(store) === mtsFilter;
    const matchesBusinessType =
      businessTypeFilter === 'ALL' || storeBusinessTypeValue(store) === businessTypeFilter;

    return matchesSearch && matchesFloor && matchesMts && matchesBusinessType;
  });

  const sortedFilteredStores = [...filteredStores].sort((a, b) => {
    const byName = normalizeText(a.nombre).localeCompare(normalizeText(b.nombre), undefined, {
      sensitivity: 'base',
      numeric: true,
    });
    if (byName !== 0) return byName;
    return normalizeText(a.codigo_interno).localeCompare(normalizeText(b.codigo_interno), undefined, {
      sensitivity: 'base',
      numeric: true,
    });
  });

  const hasActiveFilters =
    Boolean(searchTerm.trim()) ||
    floorFilter !== 'ALL' ||
    mtsFilter !== 'ALL' ||
    businessTypeFilter !== 'ALL';

  const resetFilters = () => {
    setSearchTerm('');
    setFloorFilter('ALL');
    setMtsFilter('ALL');
    setBusinessTypeFilter('ALL');
  };

  if (!canManageStores) {
    return (
      <div className="bg-amber-50 border border-amber-200 text-amber-800 rounded-xl p-4 text-sm font-medium">
        Solo usuarios con rol IT o ADMIN pueden gestionar locales.
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
      <div className="flex flex-col xl:flex-row justify-between items-start xl:items-center gap-4">
        <div>
          <h2 className="text-2xl font-bold text-slate-800">Mantenimiento de Locales</h2>
          <p className="text-slate-500">Gestione la configuracion contractual y fisica de las tiendas.</p>
        </div>

        <div className="flex flex-col sm:flex-row gap-3 w-full xl:w-auto">
          {onOpenCatalogs && (
            <button
              type="button"
              onClick={onOpenCatalogs}
              className="px-4 py-2.5 rounded-xl border border-slate-200 bg-white text-slate-700 font-medium hover:bg-slate-50 transition-colors flex items-center justify-center gap-2"
            >
              <Tag size={16} className="text-indigo-500" />
              Gestionar Catalogos
            </button>
          )}
          <button
            onClick={() => (showFormDrawer ? closeFormDrawer() : openCreateDrawer())}
            className="bg-indigo-600 text-white px-5 py-2.5 rounded-xl flex items-center justify-center gap-2 hover:bg-indigo-700 transition-all shadow-md active:scale-95 font-medium"
          >
            {showFormDrawer ? <X size={18} /> : <Plus size={18} />}
            {showFormDrawer ? 'Cerrar Panel' : 'Registrar Nuevo Local'}
          </button>
        </div>
      </div>

      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-5">
        <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
          <div>
            <h3 className="text-sm font-bold text-slate-800 uppercase tracking-widest">Catalogos Separados</h3>
            <p className="text-sm text-slate-500 mt-1">
              Los tipos de negocio y rubros generales ahora se administran desde una seccion propia en el sidebar.
            </p>
          </div>
          {onOpenCatalogs && (
            <button
              type="button"
              onClick={onOpenCatalogs}
              className="px-4 py-2.5 rounded-xl bg-slate-900 text-white text-sm font-semibold hover:bg-slate-800 transition-colors"
            >
              Abrir Catalogos Locales
            </button>
          )}
        </div>

        {catalogTableAvailable === false && (
          <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
            Catalogo persistente pendiente. Ejecute <span className="font-mono">{STORE_CATALOG_MIGRATION_FILE}</span> en Supabase.
          </div>
        )}
      </div>

      {showFormDrawer && (
        <div className="fixed inset-0 z-[105] bg-black/40 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="absolute inset-0 flex justify-end" onClick={closeFormDrawer}>
            <div
              className="w-full lg:w-[760px] h-full bg-white border-l border-indigo-100 shadow-2xl animate-in slide-in-from-right duration-200 flex flex-col"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="bg-slate-50 border-b border-slate-100 p-6 flex justify-between items-center sticky top-0 z-10">
                <div>
                  <div className="text-[10px] font-bold text-indigo-600 uppercase tracking-widest mb-1">
                    {drawerMode === 'edit' ? 'Edicion de Local' : 'Nuevo Local'}
                  </div>
                  <h3 className="text-xl font-bold text-slate-800 flex items-center gap-2">
                    <StoreIcon className="text-indigo-600" size={20} />
                    {drawerMode === 'edit' ? (newStore.nombre || 'Editar Local') : 'Registrar Nuevo Local'}
                  </h3>
                  <p className="text-sm text-slate-500 mt-1">
                    {currentMall?.nombre || 'Mall sin seleccionar'}
                  </p>
                </div>
                <button onClick={closeFormDrawer} className="text-slate-400 hover:text-slate-600 transition-colors">
                  <X size={20} />
                </button>
              </div>

              <div className="flex-1 overflow-y-auto">
                <form id="store-maintenance-form" onSubmit={handleSaveStore} className="p-8 space-y-6">
                  <div className="bg-indigo-50/60 border border-indigo-100 rounded-2xl p-4">
                    <h4 className="text-[10px] font-bold text-indigo-600 uppercase tracking-widest mb-2">Contexto</h4>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
                      <div className="rounded-xl bg-white border border-indigo-100 px-4 py-3">
                        <div className="text-slate-400 text-[10px] uppercase tracking-widest mb-1">Mall</div>
                        <div className="font-semibold text-slate-800">{currentMall?.nombre || 'Sin mall'}</div>
                      </div>
                      <div className="rounded-xl bg-white border border-indigo-100 px-4 py-3">
                        <div className="text-slate-400 text-[10px] uppercase tracking-widest mb-1">Modo</div>
                        <div className="font-semibold text-slate-800">{drawerMode === 'edit' ? 'Editar existente' : 'Crear nuevo local'}</div>
                      </div>
                    </div>
                  </div>

                  <section className="rounded-2xl border border-slate-200 bg-white p-5 space-y-4">
                    <h4 className="text-xs font-bold text-slate-400 uppercase tracking-widest">Basico</h4>
                    <div>
                      <label className="block text-sm font-medium text-slate-700 mb-1">Nombre Comercial</label>
                      <input
                        type="text"
                        required
                        value={newStore.nombre}
                        onChange={(e) => setNewStore({ ...newStore, nombre: e.target.value })}
                        className="w-full px-4 py-2.5 rounded-xl border border-slate-200 focus:ring-2 focus:ring-indigo-500 outline-none"
                        placeholder="Ej. Adidas Store"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-slate-700 mb-1">Codigo Interno</label>
                      <input
                        type="text"
                        required
                        value={newStore.codigo_interno}
                        onChange={(e) => setNewStore({ ...newStore, codigo_interno: e.target.value })}
                        className="w-full px-4 py-2.5 rounded-xl border border-slate-200 focus:ring-2 focus:ring-indigo-500 outline-none"
                        placeholder="L001"
                      />
                    </div>
                    <div>
                      <div className="flex items-center justify-between gap-3 mb-1">
                        <label className="block text-sm font-medium text-slate-700">Tipo de Negocio</label>
                        <span className="text-[11px] font-medium text-slate-400">Catalogo por mall</span>
                      </div>
                      <select
                        value={newStore.tipo_negocio || ''}
                        onChange={(e) => updateNewStoreField('tipo_negocio', e.target.value)}
                        className="w-full px-4 py-2.5 rounded-xl border border-slate-200 focus:ring-2 focus:ring-indigo-500 outline-none bg-white"
                      >
                        <option value="">Seleccione un tipo</option>
                        {catalogValuesByField.tipo_negocio.map((option) => (
                          <option key={option} value={option}>{option}</option>
                        ))}
                      </select>
                      <p className="text-[11px] text-slate-400 mt-1">
                        Si falta una opcion, gestionela desde Catalogos Locales.
                      </p>
                    </div>
                  </section>

                  <section className="rounded-2xl border border-slate-200 bg-white p-5 space-y-4">
                    <h4 className="text-xs font-bold text-slate-400 uppercase tracking-widest">Contractual</h4>
                    <div>
                      <label className="block text-sm font-medium text-slate-700 mb-1">Responsable</label>
                      <input
                        type="text"
                        value={newStore.responsable}
                        onChange={(e) => setNewStore({ ...newStore, responsable: e.target.value })}
                        className="w-full px-4 py-2.5 rounded-xl border border-slate-200 focus:ring-2 focus:ring-indigo-500 outline-none"
                        placeholder="Nombre del encargado"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-slate-700 mb-1">Nº Contrato</label>
                      <input
                        type="text"
                        value={newStore.contrato_no}
                        onChange={(e) => setNewStore({ ...newStore, contrato_no: e.target.value })}
                        className="w-full px-4 py-2.5 rounded-xl border border-slate-200 focus:ring-2 focus:ring-indigo-500 outline-none"
                        placeholder="99-88-11"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-slate-700 mb-1">% Renta Variable</label>
                      <div className="relative">
                        <input
                          type="number"
                          step="0.01"
                          value={newStore.porciento_renta}
                          onChange={(e) => setNewStore({ ...newStore, porciento_renta: e.target.value })}
                          className="w-full px-4 py-2.5 rounded-xl border border-slate-200 focus:ring-2 focus:ring-indigo-500 outline-none pr-8"
                          placeholder="5.00"
                        />
                        <Percent size={14} className="absolute right-3 top-3.5 text-slate-400" />
                      </div>
                    </div>
                  </section>

                  <section className="rounded-2xl border border-slate-200 bg-white p-5 space-y-4">
                    <h4 className="text-xs font-bold text-slate-400 uppercase tracking-widest">Ubicacion y Espacio</h4>
                    <div>
                      <label className="block text-sm font-medium text-slate-700 mb-1">Piso / Ubicacion</label>
                      <input
                        type="text"
                        value={newStore.piso}
                        onChange={(e) => setNewStore({ ...newStore, piso: e.target.value })}
                        className="w-full px-4 py-2.5 rounded-xl border border-slate-200 focus:ring-2 focus:ring-indigo-500 outline-none"
                        placeholder="P2-L01"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-slate-700 mb-1">Metros Cuadrados (Mts2)</label>
                      <div className="relative">
                        <input
                          type="number"
                          step="0.01"
                          value={newStore.mts}
                          onChange={(e) => setNewStore({ ...newStore, mts: e.target.value })}
                          className="w-full px-4 py-2.5 rounded-xl border border-slate-200 focus:ring-2 focus:ring-indigo-500 outline-none pr-10"
                          placeholder="100.00"
                        />
                        <span className="absolute right-3 top-3 text-xs text-slate-400 font-bold">m²</span>
                      </div>
                    </div>
                    <div>
                      <div className="flex items-center justify-between gap-3 mb-1">
                        <label className="block text-sm font-medium text-slate-700">Rubro General</label>
                        <span className="text-[11px] font-medium text-slate-400">Catalogo por mall</span>
                      </div>
                      <select
                        value={newStore.rubro || ''}
                        onChange={(e) => updateNewStoreField('rubro', e.target.value)}
                        className="w-full px-4 py-2.5 rounded-xl border border-slate-200 focus:ring-2 focus:ring-indigo-500 outline-none bg-white"
                      >
                        <option value="">Seleccione un rubro</option>
                        {catalogValuesByField.rubro.map((option) => (
                          <option key={option} value={option}>{option}</option>
                        ))}
                      </select>
                      <p className="text-[11px] text-slate-400 mt-1">
                        Si falta una opcion, gestionela desde Catalogos Locales.
                      </p>
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
                      <p className="text-[10px] text-slate-400 mt-1 ml-13">Permite corregir facturas del mismo dia sobrescribiendo datos existentes.</p>
                    </div>
                  </section>
                </form>
              </div>

              <div className="border-t border-slate-100 flex justify-end gap-3 px-8 py-5 bg-white">
                <button
                  type="button"
                  onClick={closeFormDrawer}
                  className="px-6 py-2.5 text-slate-500 font-medium hover:text-slate-800 transition-colors"
                >
                  Cerrar
                </button>
                <button
                  type="submit"
                  form="store-maintenance-form"
                  className="bg-indigo-600 text-white px-10 py-2.5 rounded-xl font-bold shadow-lg shadow-indigo-600/20 hover:bg-indigo-700 active:scale-95 transition-all"
                >
                  {drawerMode === 'edit' ? 'Guardar Cambios' : 'Guardar Local'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="p-4 border-b border-slate-100 bg-slate-50/50 space-y-3">
          <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-3">
            <div className="flex items-center gap-3 flex-1 min-w-0 lg:max-w-xl bg-white border border-slate-200 rounded-xl px-3 py-2.5">
              <Search size={18} className="text-slate-400 shrink-0" />
              <input
                type="text"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                placeholder="Buscar local por nombre, codigo, responsable o rubro..."
                className="bg-transparent border-none outline-none text-sm w-full"
              />
            </div>
            <div className="flex items-center gap-2">
              <div className="text-xs text-slate-500 font-medium whitespace-nowrap">
                Mostrando {sortedFilteredStores.length} de {stores.length} locales
              </div>
              {hasActiveFilters && (
                <button
                  type="button"
                  onClick={resetFilters}
                  className="px-3 py-1.5 rounded-lg border border-slate-200 text-slate-600 text-xs font-semibold hover:bg-white transition-colors"
                >
                  Limpiar filtros
                </button>
              )}
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div>
              <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1.5">Piso</label>
              <select
                value={floorFilter}
                onChange={(e) => setFloorFilter(e.target.value)}
                className="w-full px-3 py-2 rounded-xl border border-slate-200 bg-white text-sm outline-none focus:ring-2 focus:ring-indigo-500"
              >
                <option value="ALL">Todos los pisos</option>
                {floorOptions.map((option) => (
                  <option key={option} value={option}>{option}</option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1.5">Mts²</label>
              <select
                value={mtsFilter}
                onChange={(e) => setMtsFilter(e.target.value)}
                className="w-full px-3 py-2 rounded-xl border border-slate-200 bg-white text-sm outline-none focus:ring-2 focus:ring-indigo-500"
              >
                <option value="ALL">Todos los metrajes</option>
                {mtsOptions.map((option) => (
                  <option key={option} value={option}>{option}</option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1.5">Tipo de Negocio</label>
              <select
                value={businessTypeFilter}
                onChange={(e) => setBusinessTypeFilter(e.target.value)}
                className="w-full px-3 py-2 rounded-xl border border-slate-200 bg-white text-sm outline-none focus:ring-2 focus:ring-indigo-500"
              >
                <option value="ALL">Todos los tipos</option>
                {businessTypeOptions.map((option) => (
                  <option key={option} value={option}>{option}</option>
                ))}
              </select>
            </div>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left">
            <thead className="bg-slate-50/50 text-slate-500 text-[10px] uppercase font-bold tracking-widest border-b border-slate-100">
              <tr>
                <th className="px-6 py-4">Informacion Local</th>
                <th className="px-6 py-4">Responsable</th>
                <th className="px-6 py-4">Ubicacion (Piso)</th>
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
              ) : sortedFilteredStores.length > 0 ? (
                sortedFilteredStores.map((store) => (
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
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="text-[10px] font-mono bg-slate-100 px-1.5 py-0.5 rounded text-slate-500">ID: {store.codigo_interno}</span>
                            <span className="text-[10px] text-slate-400 flex items-center gap-1"><Tag size={8} /> {store.tipo_negocio || 'General'}</span>
                            <span className="text-[10px] text-slate-400 flex items-center gap-1"><Building2 size={8} /> {store.rubro || 'Sin rubro'}</span>
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
                              if (confirm('¿Reactivar este local? Se restablecera el contador de fallos.')) {
                                try {
                                  await ApiService.reactivateStore(store.id, session?.access_token);
                                  await loadStores();
                                } catch (error) {
                                  alert('Error: ' + error);
                                }
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

      <div className="mt-8 animate-in fade-in slide-in-from-bottom-8 duration-700 delay-150">
        <SalesPurge />
      </div>
    </div>
  );
};
