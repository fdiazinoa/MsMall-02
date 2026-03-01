import React, { useEffect, useState } from 'react';
import {
  ApiService,
  DEFAULT_STORE_CATALOG_VALUES,
  Store,
  StoreCatalogFieldName,
  StoreCatalogOption,
} from '../api';
import { useAuth } from '../context/AuthProvider';
import {
  Store as StoreIcon,
  Plus,
  Search,
  Building2,
  User,
  FileText,
  MapPin,
  Tag,
  Maximize2,
  Percent,
  X,
  Pencil,
  Trash2,
  Save,
  Loader2,
} from 'lucide-react';
import { SalesPurge } from './SalesPurge';

const STORE_CATALOG_MIGRATION_FILE = '20260301_store_field_options.sql';

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

const CATALOG_META: Record<StoreCatalogFieldName, {
  title: string;
  description: string;
  label: string;
  placeholder: string;
  emptyMessage: string;
}> = {
  tipo_negocio: {
    title: 'Tipos de Negocio',
    description: 'Lista maestra por mall para clasificar el modelo comercial del local.',
    label: 'Tipo de Negocio',
    placeholder: 'Ej. RETAIL',
    emptyMessage: 'No hay tipos de negocio configurados todavía.',
  },
  rubro: {
    title: 'Rubros Generales',
    description: 'Lista maestra por mall para clasificar la categoría principal del local.',
    label: 'Rubro General',
    placeholder: 'Ej. ZAPATERIA',
    emptyMessage: 'No hay rubros configurados todavía.',
  },
};

const INITIAL_CATALOG_DRAFTS: Record<StoreCatalogFieldName, string> = {
  tipo_negocio: '',
  rubro: '',
};

const INITIAL_CATALOG_EDITING: Record<StoreCatalogFieldName, { original: string | null; draft: string }> = {
  tipo_negocio: { original: null, draft: '' },
  rubro: { original: null, draft: '' },
};

export const StoreMaintenance: React.FC = () => {
  const { currentMall, isAdmin, isTic, session } = useAuth();
  const canManageStores = isAdmin || isTic;
  const [stores, setStores] = useState<Store[]>([]);
  const [catalogOptions, setCatalogOptions] = useState<StoreCatalogOption[]>([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [floorFilter, setFloorFilter] = useState('ALL');
  const [mtsFilter, setMtsFilter] = useState('ALL');
  const [businessTypeFilter, setBusinessTypeFilter] = useState('ALL');
  const [loading, setLoading] = useState(true);
  const [catalogLoading, setCatalogLoading] = useState(true);
  const [catalogTableAvailable, setCatalogTableAvailable] = useState<boolean | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [newStore, setNewStore] = useState<Partial<Store>>(createEmptyStore());
  const [catalogDrafts, setCatalogDrafts] = useState(INITIAL_CATALOG_DRAFTS);
  const [catalogEditing, setCatalogEditing] = useState(INITIAL_CATALOG_EDITING);
  const [catalogBusyKey, setCatalogBusyKey] = useState<string | null>(null);

  const normalizeText = (value: any) => String(value || '').trim().replace(/\s+/g, ' ');
  const normalizeSearch = (value: any) =>
    normalizeText(value)
      .toLowerCase()
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '');

  const catalogKey = (value: any) => normalizeSearch(value);

  const getStoreFieldValue = (store: Partial<Store>, fieldName: StoreCatalogFieldName) =>
    normalizeText(fieldName === 'tipo_negocio' ? store.tipo_negocio : store.rubro);

  const updateNewStoreField = (fieldName: StoreCatalogFieldName, value: string) => {
    setNewStore((prev) => ({ ...prev, [fieldName]: value }));
  };

  const resetCatalogEditing = (fieldName?: StoreCatalogFieldName) => {
    if (fieldName) {
      setCatalogEditing((prev) => ({
        ...prev,
        [fieldName]: INITIAL_CATALOG_EDITING[fieldName],
      }));
      return;
    }
    setCatalogEditing(INITIAL_CATALOG_EDITING);
  };

  const getCatalogOptionRow = (fieldName: StoreCatalogFieldName, value: string) =>
    catalogOptions.find(
      (option) => option.field_name === fieldName && catalogKey(option.value) === catalogKey(value)
    );

  const buildCatalogValues = (fieldName: StoreCatalogFieldName) => {
    const ordered = new Map<string, string>();
    const sources = [
      ...(catalogTableAvailable === true ? [] : DEFAULT_STORE_CATALOG_VALUES[fieldName]),
      ...catalogOptions
        .filter((option) => option.field_name === fieldName)
        .map((option) => option.value),
      ...stores.map((store) => getStoreFieldValue(store, fieldName)),
      getStoreFieldValue(newStore, fieldName),
    ];

    sources.forEach((value) => {
      const cleanValue = normalizeText(value);
      const key = catalogKey(cleanValue);
      if (!cleanValue || !key || ordered.has(key)) return;
      ordered.set(key, cleanValue);
    });

    return Array.from(ordered.values()).sort((a, b) =>
      a.localeCompare(b, undefined, { sensitivity: 'base', numeric: true })
    );
  };

  const buildUsageMap = (fieldName: StoreCatalogFieldName) => {
    const usageMap = new Map<string, number>();
    stores.forEach((store) => {
      const value = getStoreFieldValue(store, fieldName);
      const key = catalogKey(value);
      if (!key) return;
      usageMap.set(key, (usageMap.get(key) || 0) + 1);
    });
    return usageMap;
  };

  const catalogValuesByField = {
    tipo_negocio: buildCatalogValues('tipo_negocio'),
    rubro: buildCatalogValues('rubro'),
  };

  const catalogUsageByField = {
    tipo_negocio: buildUsageMap('tipo_negocio'),
    rubro: buildUsageMap('rubro'),
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
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const loadCatalogs = async () => {
    if (!currentMall?.id) {
      setCatalogOptions([]);
      setCatalogTableAvailable(null);
      setCatalogLoading(false);
      return;
    }

    setCatalogLoading(true);
    try {
      const result = await ApiService.getStoreCatalogOptions(currentMall.id);

      if (!result.available) {
        setCatalogOptions([]);
        setCatalogTableAvailable(false);
        return;
      }

      setCatalogTableAvailable(true);

      if (result.options.length === 0) {
        await ApiService.seedStoreCatalogDefaults(currentMall.id);
        const seededResult = await ApiService.getStoreCatalogOptions(currentMall.id);
        setCatalogOptions(seededResult.options);
        return;
      }

      setCatalogOptions(result.options);
    } catch (e: any) {
      console.error(e);
      alert(`Error cargando catálogos: ${e.message || e}`);
    } finally {
      setCatalogLoading(false);
    }
  };

  const reloadStoresAndCatalogs = async () => {
    await Promise.all([loadStores(), loadCatalogs()]);
  };

  const handleCreate = async (e: React.FormEvent) => {
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
      setShowForm(false);
      setNewStore(createEmptyStore(currentMall.id));
      await loadStores();
    } catch (e: any) {
      console.error(e);
      alert('Error al guardar: ' + (e.message || e));
    }
  };

  const handleDelete = async (id: string, nombre: string) => {
    if (!confirm(`¿Está seguro de que desea eliminar el local "${nombre}"?\nEsta acción no se puede deshacer.`)) return;
    try {
      await ApiService.deleteStore(id);
      await loadStores();
    } catch (e: any) {
      console.error(e);
      alert('Error al eliminar: ' + (e.message || e));
    }
  };

  const handleEdit = (store: Store) => {
    setNewStore({ ...createEmptyStore(currentMall?.id || ''), ...store });
    setShowForm(true);
  };

  const handleToggleForm = () => {
    if (showForm) {
      setShowForm(false);
      setNewStore(createEmptyStore(currentMall?.id || ''));
      return;
    }
    setNewStore(createEmptyStore(currentMall?.id || ''));
    setShowForm(true);
  };

  const handleAddCatalogOption = async (fieldName: StoreCatalogFieldName) => {
    if (!currentMall?.id) {
      alert('Seleccione un mall antes de editar catálogos.');
      return;
    }

    if (!catalogTableAvailable) {
      alert(`Para guardar catálogos editables debe ejecutar el script SQL ${STORE_CATALOG_MIGRATION_FILE}.`);
      return;
    }

    const newValue = normalizeText(catalogDrafts[fieldName]);
    if (!newValue) {
      alert(`Ingrese un valor para ${CATALOG_META[fieldName].label}.`);
      return;
    }

    if (catalogValuesByField[fieldName].some((option) => catalogKey(option) === catalogKey(newValue))) {
      alert('Ese valor ya existe en la lista.');
      return;
    }

    setCatalogBusyKey(`create:${fieldName}`);
    try {
      await ApiService.createStoreCatalogOption({
        mall_id: currentMall.id,
        field_name: fieldName,
        value: newValue,
        sort_order: catalogValuesByField[fieldName].length + 1,
      });
      setCatalogDrafts((prev) => ({ ...prev, [fieldName]: '' }));
      await loadCatalogs();
    } catch (e: any) {
      console.error(e);
      alert(`Error guardando ${CATALOG_META[fieldName].label}: ${e.message || e}`);
    } finally {
      setCatalogBusyKey(null);
    }
  };

  const handleStartCatalogEdit = (fieldName: StoreCatalogFieldName, value: string) => {
    setCatalogEditing((prev) => ({
      ...prev,
      [fieldName]: { original: value, draft: value },
    }));
  };

  const handleSaveCatalogEdit = async (fieldName: StoreCatalogFieldName) => {
    if (!currentMall?.id) {
      alert('Seleccione un mall antes de editar catálogos.');
      return;
    }

    if (!catalogTableAvailable) {
      alert(`Para guardar catálogos editables debe ejecutar el script SQL ${STORE_CATALOG_MIGRATION_FILE}.`);
      return;
    }

    const { original, draft } = catalogEditing[fieldName];
    const previousValue = normalizeText(original);
    const nextValue = normalizeText(draft);

    if (!previousValue) return;
    if (!nextValue) {
      alert(`Ingrese un valor para ${CATALOG_META[fieldName].label}.`);
      return;
    }

    const sourceOption = getCatalogOptionRow(fieldName, previousValue);
    const targetOption = getCatalogOptionRow(fieldName, nextValue);
    const operationKey = `edit:${fieldName}:${catalogKey(previousValue)}`;

    setCatalogBusyKey(operationKey);
    try {
      if (previousValue !== nextValue) {
        await ApiService.bulkReplaceStoreFieldValue(currentMall.id, fieldName, previousValue, nextValue);
      }

      if (sourceOption) {
        if (targetOption && targetOption.id !== sourceOption.id) {
          await ApiService.deleteStoreCatalogOption(sourceOption.id);
        } else if (sourceOption.value !== nextValue) {
          await ApiService.updateStoreCatalogOption(sourceOption.id, { value: nextValue });
        }
      } else if (!targetOption) {
        await ApiService.createStoreCatalogOption({
          mall_id: currentMall.id,
          field_name: fieldName,
          value: nextValue,
          sort_order: catalogValuesByField[fieldName].length + 1,
        });
      }

      const currentSelectedValue = getStoreFieldValue(newStore, fieldName);
      if (catalogKey(currentSelectedValue) === catalogKey(previousValue)) {
        updateNewStoreField(fieldName, nextValue);
      }

      resetCatalogEditing(fieldName);
      await reloadStoresAndCatalogs();
    } catch (e: any) {
      console.error(e);
      alert(`Error actualizando ${CATALOG_META[fieldName].label}: ${e.message || e}`);
    } finally {
      setCatalogBusyKey(null);
    }
  };

  const handleDeleteCatalogOption = async (fieldName: StoreCatalogFieldName, value: string) => {
    if (!catalogTableAvailable) {
      alert(`Para guardar catálogos editables debe ejecutar el script SQL ${STORE_CATALOG_MIGRATION_FILE}.`);
      return;
    }

    const usageCount = catalogUsageByField[fieldName].get(catalogKey(value)) || 0;
    if (usageCount > 0) {
      alert(`No se puede eliminar "${value}" porque ${usageCount} local(es) lo usan actualmente.`);
      return;
    }

    const option = getCatalogOptionRow(fieldName, value);
    if (!option) return;

    if (!confirm(`¿Eliminar "${value}" de ${CATALOG_META[fieldName].title}?`)) return;

    setCatalogBusyKey(`delete:${fieldName}:${catalogKey(value)}`);
    try {
      await ApiService.deleteStoreCatalogOption(option.id);

      const currentSelectedValue = getStoreFieldValue(newStore, fieldName);
      if (catalogKey(currentSelectedValue) === catalogKey(value)) {
        updateNewStoreField(fieldName, '');
      }

      await loadCatalogs();
    } catch (e: any) {
      console.error(e);
      alert(`Error eliminando ${CATALOG_META[fieldName].label}: ${e.message || e}`);
    } finally {
      setCatalogBusyKey(null);
    }
  };

  useEffect(() => {
    if (!currentMall?.id) {
      setStores([]);
      setCatalogOptions([]);
      setCatalogTableAvailable(null);
      setLoading(false);
      setCatalogLoading(false);
      setNewStore(createEmptyStore());
      return;
    }

    setNewStore((prev) => ({ ...prev, mall_id: currentMall.id }));
    loadStores();
    loadCatalogs();
    setCatalogDrafts(INITIAL_CATALOG_DRAFTS);
    resetCatalogEditing();
  }, [currentMall?.id]);

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

  const renderCatalogCard = (fieldName: StoreCatalogFieldName) => {
    const options = catalogValuesByField[fieldName];
    const usageMap = catalogUsageByField[fieldName];
    const editingState = catalogEditing[fieldName];
    const hasPersistedCatalog = catalogTableAvailable === true;

    return (
      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="px-5 py-4 border-b border-slate-100 bg-slate-50/70">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h3 className="text-base font-bold text-slate-800">{CATALOG_META[fieldName].title}</h3>
              <p className="text-sm text-slate-500">{CATALOG_META[fieldName].description}</p>
            </div>
            {catalogLoading && <Loader2 size={18} className="animate-spin text-indigo-500 shrink-0 mt-0.5" />}
          </div>
          {catalogTableAvailable === false && (
            <div className="mt-3 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
              Catálogo persistente pendiente. Ejecuta <span className="font-mono">{STORE_CATALOG_MIGRATION_FILE}</span>.
              Mientras tanto se usan valores por defecto y valores ya presentes en los locales.
            </div>
          )}
        </div>

        <div className="p-5 space-y-4">
          <div className="flex flex-col sm:flex-row gap-2">
            <input
              type="text"
              value={catalogDrafts[fieldName]}
              onChange={(e) => setCatalogDrafts((prev) => ({ ...prev, [fieldName]: e.target.value }))}
              className="flex-1 px-4 py-2.5 rounded-xl border border-slate-200 focus:ring-2 focus:ring-indigo-500 outline-none disabled:bg-slate-100 disabled:text-slate-400"
              placeholder={CATALOG_META[fieldName].placeholder}
              disabled={!hasPersistedCatalog || catalogLoading || Boolean(catalogBusyKey)}
            />
            <button
              type="button"
              onClick={() => handleAddCatalogOption(fieldName)}
              disabled={!hasPersistedCatalog || catalogLoading || Boolean(catalogBusyKey)}
              className="px-4 py-2.5 rounded-xl bg-indigo-600 text-white text-sm font-semibold hover:bg-indigo-700 disabled:bg-slate-300 disabled:cursor-not-allowed transition-colors"
            >
              Agregar
            </button>
          </div>

          <div className="space-y-2 max-h-80 overflow-y-auto pr-1">
            {options.length === 0 ? (
              <div className="rounded-xl border border-dashed border-slate-200 px-4 py-6 text-sm text-slate-400 text-center">
                {CATALOG_META[fieldName].emptyMessage}
              </div>
            ) : (
              options.map((option) => {
                const optionRow = getCatalogOptionRow(fieldName, option);
                const usageCount = usageMap.get(catalogKey(option)) || 0;
                const optionBusyPrefix = `${fieldName}:${catalogKey(option)}`;
                const isEditing =
                  editingState.original !== null &&
                  catalogKey(editingState.original) === catalogKey(option);
                const isBusy =
                  catalogBusyKey === `edit:${optionBusyPrefix}` ||
                  catalogBusyKey === `delete:${optionBusyPrefix}`;

                return (
                  <div
                    key={`${fieldName}:${catalogKey(option)}`}
                    className="rounded-xl border border-slate-200 px-3 py-3 bg-white"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <div className="min-w-0 flex-1">
                        {isEditing ? (
                          <input
                            type="text"
                            value={editingState.draft}
                            onChange={(e) =>
                              setCatalogEditing((prev) => ({
                                ...prev,
                                [fieldName]: { original: option, draft: e.target.value },
                              }))
                            }
                            className="w-full px-3 py-2 rounded-lg border border-slate-200 focus:ring-2 focus:ring-indigo-500 outline-none"
                            disabled={isBusy}
                          />
                        ) : (
                          <div className="text-sm font-semibold text-slate-800 truncate">{option}</div>
                        )}

                        <div className="mt-1 flex items-center gap-2 text-[11px] text-slate-500">
                          <span className="px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 font-semibold">
                            {usageCount} local(es)
                          </span>
                          <span className={`px-2 py-0.5 rounded-full font-semibold ${optionRow ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-500'}`}>
                            {optionRow ? 'Catalogo' : 'Heredado'}
                          </span>
                        </div>
                      </div>

                      <div className="flex items-center gap-1 shrink-0">
                        {isEditing ? (
                          <>
                            <button
                              type="button"
                              onClick={() => handleSaveCatalogEdit(fieldName)}
                              disabled={isBusy}
                              className="p-2 text-indigo-600 hover:bg-indigo-50 rounded-lg transition-colors disabled:opacity-50"
                              title="Guardar"
                            >
                              <Save size={16} />
                            </button>
                            <button
                              type="button"
                              onClick={() => resetCatalogEditing(fieldName)}
                              disabled={isBusy}
                              className="p-2 text-slate-500 hover:bg-slate-100 rounded-lg transition-colors disabled:opacity-50"
                              title="Cancelar"
                            >
                              <X size={16} />
                            </button>
                          </>
                        ) : (
                          <>
                            <button
                              type="button"
                              onClick={() => handleStartCatalogEdit(fieldName, option)}
                              disabled={!hasPersistedCatalog || isBusy || catalogLoading}
                              className="p-2 text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                              title="Editar"
                            >
                              <Pencil size={16} />
                            </button>
                            <button
                              type="button"
                              onClick={() => handleDeleteCatalogOption(fieldName, option)}
                              disabled={!hasPersistedCatalog || isBusy || catalogLoading}
                              className="p-2 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                              title="Eliminar"
                            >
                              <Trash2 size={16} />
                            </button>
                          </>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>
      </div>
    );
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
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
        <div>
          <h2 className="text-2xl font-bold text-slate-800">Mantenimiento de Locales</h2>
          <p className="text-slate-500">Gestione la configuración contractual, física y catálogos maestros de las tiendas.</p>
        </div>
        <button
          onClick={handleToggleForm}
          className="bg-indigo-600 text-white px-5 py-2.5 rounded-xl flex items-center gap-2 hover:bg-indigo-700 transition-all shadow-md active:scale-95 font-medium"
        >
          {showForm ? <X size={18} /> : <Plus size={18} />}
          {showForm ? 'Cancelar Registro' : 'Registrar Nuevo Local'}
        </button>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        {renderCatalogCard('tipo_negocio')}
        {renderCatalogCard('rubro')}
      </div>

      {showForm && (
        <div className="bg-white p-8 rounded-2xl border border-indigo-100 shadow-xl animate-in zoom-in-95 duration-200">
          <h3 className="text-lg font-bold text-slate-800 mb-6 flex items-center gap-2">
            <StoreIcon className="text-indigo-600" size={20} />
            {newStore.id ? 'Editar Local' : 'Información del Nuevo Local'}
          </h3>
          <form onSubmit={handleCreate} className="space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              <div className="space-y-4">
                <h4 className="text-xs font-bold text-slate-400 uppercase tracking-widest">Básico</h4>
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">Nombre Comercial</label>
                  <input
                    type="text"
                    required
                    value={newStore.nombre}
                    onChange={(e) => setNewStore({ ...newStore, nombre: e.target.value })}
                    className="w-full px-4 py-2 rounded-lg border border-slate-200 focus:ring-2 focus:ring-indigo-500 outline-none"
                    placeholder="Ej. Adidas Store"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">Código Interno</label>
                  <input
                    type="text"
                    required
                    value={newStore.codigo_interno}
                    onChange={(e) => setNewStore({ ...newStore, codigo_interno: e.target.value })}
                    className="w-full px-4 py-2 rounded-lg border border-slate-200 focus:ring-2 focus:ring-indigo-500 outline-none"
                    placeholder="L001"
                  />
                </div>
                <div>
                  <div className="flex items-center justify-between gap-3 mb-1">
                    <label className="block text-sm font-medium text-slate-700">Tipo de Negocio</label>
                    <span className="text-[11px] font-medium text-slate-400">Catálogo por mall</span>
                  </div>
                  <select
                    value={newStore.tipo_negocio || ''}
                    onChange={(e) => updateNewStoreField('tipo_negocio', e.target.value)}
                    className="w-full px-4 py-2 rounded-lg border border-slate-200 focus:ring-2 focus:ring-indigo-500 outline-none bg-white"
                  >
                    <option value="">Seleccione un tipo</option>
                    {catalogValuesByField.tipo_negocio.map((option) => (
                      <option key={option} value={option}>{option}</option>
                    ))}
                  </select>
                  <p className="text-[11px] text-slate-400 mt-1">
                    Si falta una opción, agréguela en el catálogo superior antes de guardar.
                  </p>
                </div>
              </div>

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
                      type="number"
                      step="0.01"
                      value={newStore.porciento_renta}
                      onChange={(e) => setNewStore({ ...newStore, porciento_renta: e.target.value })}
                      className="w-full px-4 py-2 rounded-lg border border-slate-200 focus:ring-2 focus:ring-indigo-500 outline-none pr-8"
                      placeholder="5.00"
                    />
                    <Percent size={14} className="absolute right-3 top-3 text-slate-400" />
                  </div>
                </div>
              </div>

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
                      type="number"
                      step="0.01"
                      value={newStore.mts}
                      onChange={(e) => setNewStore({ ...newStore, mts: e.target.value })}
                      className="w-full px-4 py-2 rounded-lg border border-slate-200 focus:ring-2 focus:ring-indigo-500 outline-none pr-10"
                      placeholder="100.00"
                    />
                    <span className="absolute right-3 top-2.5 text-xs text-slate-400 font-bold">m²</span>
                  </div>
                </div>
                <div>
                  <div className="flex items-center justify-between gap-3 mb-1">
                    <label className="block text-sm font-medium text-slate-700">Rubro General</label>
                    <span className="text-[11px] font-medium text-slate-400">Catálogo por mall</span>
                  </div>
                  <select
                    value={newStore.rubro || ''}
                    onChange={(e) => updateNewStoreField('rubro', e.target.value)}
                    className="w-full px-4 py-2 rounded-lg border border-slate-200 focus:ring-2 focus:ring-indigo-500 outline-none bg-white"
                  >
                    <option value="">Seleccione un rubro</option>
                    {catalogValuesByField.rubro.map((option) => (
                      <option key={option} value={option}>{option}</option>
                    ))}
                  </select>
                  <p className="text-[11px] text-slate-400 mt-1">
                    Si falta una opción, agréguela en el catálogo superior antes de guardar.
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
                  <p className="text-[10px] text-slate-400 mt-1 ml-13">Permite corregir facturas del mismo día sobrescribiendo datos existentes.</p>
                </div>
              </div>
            </div>

            <div className="pt-6 border-t border-slate-100 flex justify-end gap-3">
              <button
                type="button"
                onClick={handleToggleForm}
                className="px-6 py-2.5 rounded-xl border border-slate-200 text-slate-600 font-medium hover:bg-slate-50 transition-colors"
              >
                Cancelar
              </button>
              <button
                type="submit"
                className="px-10 py-2.5 rounded-xl bg-indigo-600 text-white font-bold hover:bg-indigo-700 shadow-lg shadow-indigo-600/20 active:scale-95 transition-all"
              >
                Guardar Local
              </button>
            </div>
          </form>
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
                placeholder="Buscar local por nombre, código, responsable o rubro..."
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
                              if (confirm('¿Reactivar este local? Se restablecerá el contador de fallos.')) {
                                try {
                                  await ApiService.reactivateStore(store.id, session?.access_token);
                                  await loadStores();
                                } catch (e) {
                                  alert('Error: ' + e);
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
