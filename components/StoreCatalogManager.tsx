import React, { useEffect, useState } from 'react';
import { ApiService, Store, StoreCatalogFieldName, StoreCatalogOption } from '../api';
import { useAuth } from '../context/AuthProvider';
import {
  buildStoreCatalogUsageMap,
  buildStoreCatalogValues,
  getStoreCatalogOptionRow,
  loadStoreCatalogOptions,
  normalizeStoreCatalogKey,
  normalizeStoreCatalogText,
  STORE_CATALOG_MIGRATION_FILE,
} from '../utils/storeCatalog';
import { Loader2, Pencil, Save, Store as StoreIcon, Tag, Trash2, X } from 'lucide-react';

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
    emptyMessage: 'No hay tipos de negocio configurados todavia.',
  },
  rubro: {
    title: 'Rubros Generales',
    description: 'Lista maestra por mall para clasificar la categoria principal del local.',
    label: 'Rubro General',
    placeholder: 'Ej. ZAPATERIA',
    emptyMessage: 'No hay rubros configurados todavia.',
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

export const StoreCatalogManager: React.FC = () => {
  const { currentMall, isAdmin, isTic } = useAuth();
  const canManageStores = isAdmin || isTic;
  const [stores, setStores] = useState<Store[]>([]);
  const [catalogOptions, setCatalogOptions] = useState<StoreCatalogOption[]>([]);
  const [catalogLoading, setCatalogLoading] = useState(true);
  const [catalogTableAvailable, setCatalogTableAvailable] = useState<boolean | null>(null);
  const [catalogDrafts, setCatalogDrafts] = useState(INITIAL_CATALOG_DRAFTS);
  const [catalogEditing, setCatalogEditing] = useState(INITIAL_CATALOG_EDITING);
  const [catalogBusyKey, setCatalogBusyKey] = useState<string | null>(null);

  const catalogValuesByField = {
    tipo_negocio: buildStoreCatalogValues({
      fieldName: 'tipo_negocio',
      catalogOptions,
      catalogTableAvailable,
      stores,
    }),
    rubro: buildStoreCatalogValues({
      fieldName: 'rubro',
      catalogOptions,
      catalogTableAvailable,
      stores,
    }),
  };

  const catalogUsageByField = {
    tipo_negocio: buildStoreCatalogUsageMap(stores, 'tipo_negocio'),
    rubro: buildStoreCatalogUsageMap(stores, 'rubro'),
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

  const loadStores = async () => {
    if (!currentMall?.id) {
      setStores([]);
      return;
    }

    try {
      const data = await ApiService.getStores(currentMall.id);
      setStores(data);
    } catch (error) {
      console.error(error);
      alert('Error cargando locales del mall.');
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
      const result = await loadStoreCatalogOptions(currentMall.id);
      setCatalogOptions(result.options);
      setCatalogTableAvailable(result.available);
    } catch (error: any) {
      console.error(error);
      alert(`Error cargando catalogos: ${error.message || error}`);
    } finally {
      setCatalogLoading(false);
    }
  };

  const reloadStoresAndCatalogs = async () => {
    await Promise.all([loadStores(), loadCatalogs()]);
  };

  const handleAddCatalogOption = async (fieldName: StoreCatalogFieldName) => {
    if (!currentMall?.id) {
      alert('Seleccione un mall antes de editar catalogos.');
      return;
    }

    if (!catalogTableAvailable) {
      alert(`Para guardar catalogos editables debe ejecutar el script SQL ${STORE_CATALOG_MIGRATION_FILE}.`);
      return;
    }

    const newValue = normalizeStoreCatalogText(catalogDrafts[fieldName]);
    if (!newValue) {
      alert(`Ingrese un valor para ${CATALOG_META[fieldName].label}.`);
      return;
    }

    if (catalogValuesByField[fieldName].some((option) => normalizeStoreCatalogKey(option) === normalizeStoreCatalogKey(newValue))) {
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
    } catch (error: any) {
      console.error(error);
      alert(`Error guardando ${CATALOG_META[fieldName].label}: ${error.message || error}`);
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
      alert('Seleccione un mall antes de editar catalogos.');
      return;
    }

    if (!catalogTableAvailable) {
      alert(`Para guardar catalogos editables debe ejecutar el script SQL ${STORE_CATALOG_MIGRATION_FILE}.`);
      return;
    }

    const { original, draft } = catalogEditing[fieldName];
    const previousValue = normalizeStoreCatalogText(original);
    const nextValue = normalizeStoreCatalogText(draft);

    if (!previousValue) return;
    if (!nextValue) {
      alert(`Ingrese un valor para ${CATALOG_META[fieldName].label}.`);
      return;
    }

    const sourceOption = getStoreCatalogOptionRow(catalogOptions, fieldName, previousValue);
    const targetOption = getStoreCatalogOptionRow(catalogOptions, fieldName, nextValue);
    const operationKey = `edit:${fieldName}:${normalizeStoreCatalogKey(previousValue)}`;

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

      resetCatalogEditing(fieldName);
      await reloadStoresAndCatalogs();
    } catch (error: any) {
      console.error(error);
      alert(`Error actualizando ${CATALOG_META[fieldName].label}: ${error.message || error}`);
    } finally {
      setCatalogBusyKey(null);
    }
  };

  const handleDeleteCatalogOption = async (fieldName: StoreCatalogFieldName, value: string) => {
    if (!catalogTableAvailable) {
      alert(`Para guardar catalogos editables debe ejecutar el script SQL ${STORE_CATALOG_MIGRATION_FILE}.`);
      return;
    }

    const usageCount = catalogUsageByField[fieldName].get(normalizeStoreCatalogKey(value)) || 0;
    if (usageCount > 0) {
      alert(`No se puede eliminar "${value}" porque ${usageCount} local(es) lo usan actualmente.`);
      return;
    }

    const option = getStoreCatalogOptionRow(catalogOptions, fieldName, value);
    if (!option) return;

    if (!confirm(`¿Eliminar "${value}" de ${CATALOG_META[fieldName].title}?`)) return;

    setCatalogBusyKey(`delete:${fieldName}:${normalizeStoreCatalogKey(value)}`);
    try {
      await ApiService.deleteStoreCatalogOption(option.id);
      await loadCatalogs();
    } catch (error: any) {
      console.error(error);
      alert(`Error eliminando ${CATALOG_META[fieldName].label}: ${error.message || error}`);
    } finally {
      setCatalogBusyKey(null);
    }
  };

  useEffect(() => {
    if (!currentMall?.id) {
      setStores([]);
      setCatalogOptions([]);
      setCatalogTableAvailable(null);
      setCatalogLoading(false);
      return;
    }

    setCatalogDrafts(INITIAL_CATALOG_DRAFTS);
    resetCatalogEditing();
    loadStores();
    loadCatalogs();
  }, [currentMall?.id]);

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
              Catalogo persistente pendiente. Ejecuta <span className="font-mono">{STORE_CATALOG_MIGRATION_FILE}</span>.
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

          <div className="space-y-2 max-h-[460px] overflow-y-auto pr-1">
            {options.length === 0 ? (
              <div className="rounded-xl border border-dashed border-slate-200 px-4 py-6 text-sm text-slate-400 text-center">
                {CATALOG_META[fieldName].emptyMessage}
              </div>
            ) : (
              options.map((option) => {
                const optionRow = getStoreCatalogOptionRow(catalogOptions, fieldName, option);
                const usageCount = usageMap.get(normalizeStoreCatalogKey(option)) || 0;
                const optionBusyPrefix = `${fieldName}:${normalizeStoreCatalogKey(option)}`;
                const isEditing =
                  editingState.original !== null &&
                  normalizeStoreCatalogKey(editingState.original) === normalizeStoreCatalogKey(option);
                const isBusy =
                  catalogBusyKey === `edit:${optionBusyPrefix}` ||
                  catalogBusyKey === `delete:${optionBusyPrefix}`;

                return (
                  <div
                    key={`${fieldName}:${normalizeStoreCatalogKey(option)}`}
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
        Solo usuarios con rol IT o ADMIN pueden gestionar catalogos de locales.
      </div>
    );
  }

  return (
    <div className="space-y-4 animate-in fade-in slide-in-from-bottom-4 duration-500">
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
        <div>
          <h2 className="text-xl font-bold text-slate-800 flex items-center gap-2">
            <Tag className="text-indigo-600" size={22} />
            Catalogos de Locales
          </h2>
          <p className="text-slate-500">
            Administre por separado las listas maestras de tipos de negocio y rubros generales.
          </p>
        </div>
        <div className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm text-slate-600 shadow-sm">
          <StoreIcon size={16} className="text-indigo-500" />
          Mall activo: <span className="font-semibold text-slate-800">{currentMall?.nombre || 'Sin seleccionar'}</span>
        </div>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        {renderCatalogCard('tipo_negocio')}
        {renderCatalogCard('rubro')}
      </div>

      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-5">
        <h3 className="text-sm font-bold text-slate-700 uppercase tracking-widest mb-3">Uso actual</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm text-slate-600">
          <div className="rounded-xl bg-slate-50 border border-slate-200 px-4 py-3">
            <div className="text-xs text-slate-400 uppercase tracking-widest mb-1">Locales cargados</div>
            <div className="text-xl font-bold text-slate-800">{stores.length}</div>
          </div>
          <div className="rounded-xl bg-slate-50 border border-slate-200 px-4 py-3">
            <div className="text-xs text-slate-400 uppercase tracking-widest mb-1">Catalogos persistentes</div>
            <div className="text-xl font-bold text-slate-800">
              {catalogTableAvailable ? catalogOptions.length : 0}
            </div>
          </div>
        </div>
        {!catalogTableAvailable && (
          <p className="mt-4 text-xs text-amber-700">
            Ejecute <span className="font-mono">{STORE_CATALOG_MIGRATION_FILE}</span> para persistir los cambios del catalogo.
          </p>
        )}
      </div>
    </div>
  );
};
