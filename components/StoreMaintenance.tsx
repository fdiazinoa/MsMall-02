import React, { useEffect, useMemo, useState } from 'react';
import {
  ApiService,
  LocalCustomFieldDefinition,
  LocalCustomFieldOption,
  LocalCustomFieldValue,
  Store,
  StoreCatalogOption,
} from '../api';
import { useAuth } from '../context/AuthProvider';
import {
  loadStoreCatalogOptions,
  normalizeStoreCatalogKey,
  STORE_CATALOG_MIGRATION_FILE,
} from '../utils/storeCatalog';
import {
  Store as StoreIcon, Plus, Search, Building2,
  User, FileText, MapPin, Tag, Maximize2, Percent, Settings2, Layers3, Mail, Trash2
} from 'lucide-react';
import { SalesPurge } from './SalesPurge';

interface StoreMaintenanceProps {
  onOpenCatalogs?: () => void;
}

type FieldValueState = {
  field_definition_id: string;
  value_text?: string | null;
  value_number?: number | null;
  value_date?: string | null;
  selected_option_id?: string | null;
};

const emptyStore = (mallId?: string): Partial<Store> => ({
  nombre: '',
  codigo_interno: '',
  email: '',
  email_secundario: '',
  mall_id: mallId || '',
  responsable: '',
  contrato_no: '',
  piso: '',
  tipo_negocio: '',
  mts: '',
  porciento_renta: '',
  renta_fija: '',
  breakpoint_venta: '',
  porcentaje_variable: '',
  rubro: '',
  upsert_activo: false,
  fecha_corte_importacion: '',
});

const parseOptionalNumber = (value: unknown): number | null => {
  if (value === null || value === undefined || value === '') return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
};

const emptyFieldDraft = (mallId?: string): Partial<LocalCustomFieldDefinition> => ({
  mall_id: mallId || '',
  key: '',
  label: '',
  data_type: 'text',
  widget_type: 'textbox',
  required: false,
  active: true,
  sort_order: 0,
  parent_field_id: null,
  options: [],
});

const buildValueMap = (values: LocalCustomFieldValue[]): Record<string, FieldValueState> => {
  return values.reduce<Record<string, FieldValueState>>((acc, value) => {
    acc[value.field_definition_id] = {
      field_definition_id: value.field_definition_id,
      value_text: value.value_text ?? '',
      value_number: value.value_number ?? null,
      value_date: value.value_date ?? '',
      selected_option_id: value.selected_option_id ?? null,
    };
    return acc;
  }, {});
};

const serializeFieldValues = (
  definitions: LocalCustomFieldDefinition[],
  valueMap: Record<string, FieldValueState>
): LocalCustomFieldValue[] => {
  return definitions.map((definition) => {
    const value = valueMap[definition.id] || { field_definition_id: definition.id };
    return {
      field_definition_id: definition.id,
      value_text: definition.data_type === 'text' ? (value.value_text ?? '') : null,
      value_number: definition.data_type === 'number' ? (value.value_number ?? null) : null,
      value_date: definition.data_type === 'date' ? (value.value_date ?? '') : null,
      selected_option_id: definition.data_type === 'select' ? (value.selected_option_id ?? null) : null,
    };
  });
};

const getFilteredOptions = (
  definition: LocalCustomFieldDefinition,
  definitions: LocalCustomFieldDefinition[],
  valueMap: Record<string, FieldValueState>
) => {
  const options = definition.options || [];
  if (definition.widget_type !== 'drilldown' || !definition.parent_field_id) {
    return options.filter((option) => option.active !== false);
  }
  const parentValue = valueMap[definition.parent_field_id]?.selected_option_id;
  if (!parentValue) return [];
  return options.filter((option) => option.active !== false && option.parent_option_id === parentValue);
};

const formatFieldValue = (
  definition: LocalCustomFieldDefinition,
  value: FieldValueState | undefined
) => {
  if (!value) return 'Sin valor';
  if (definition.data_type === 'text') return value.value_text || 'Sin valor';
  if (definition.data_type === 'number') return value.value_number ?? 'Sin valor';
  if (definition.data_type === 'date') return value.value_date || 'Sin valor';
  const option = definition.options.find((row) => row.id === value.selected_option_id);
  return option?.label || 'Sin valor';
};

const DefinitionOptionsEditor: React.FC<{
  definition: Partial<LocalCustomFieldDefinition>;
  definitions: LocalCustomFieldDefinition[];
  onChange: (options: LocalCustomFieldOption[]) => void;
}> = ({ definition, definitions, onChange }) => {
  const options = definition.options || [];
  const parentDefinition = definitions.find((field) => field.id === definition.parent_field_id);
  const parentOptions = parentDefinition?.options || [];

  const updateOption = (index: number, patch: Partial<LocalCustomFieldOption>) => {
    const next = options.map((option, idx) => idx === index ? { ...option, ...patch } : option);
    onChange(next);
  };

  const addOption = () => {
    onChange([
      ...options,
      {
        label: '',
        value: '',
        sort_order: options.length,
        active: true,
        parent_option_id: definition.widget_type === 'drilldown' ? (parentOptions[0]?.id || null) : null,
      }
    ]);
  };

  const removeOption = (index: number) => {
    onChange(options.filter((_, idx) => idx !== index));
  };

  if (!['select', 'drilldown'].includes(definition.widget_type || '')) {
    return null;
  }

  return (
    <div className="space-y-3 rounded-xl border border-slate-200 bg-slate-50/60 p-4">
      <div className="flex items-center justify-between">
        <div>
          <h4 className="text-sm font-bold text-slate-700">Opciones</h4>
          <p className="text-xs text-slate-500">
            {definition.widget_type === 'drilldown'
              ? 'Cada opción hija debe apuntar a una opción del campo padre.'
              : 'Estas opciones aparecerán en el selector del local y del cubo.'}
          </p>
        </div>
        <button type="button" onClick={addOption} className="rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-bold text-white hover:bg-indigo-700">
          Agregar opción
        </button>
      </div>

      {options.length === 0 ? (
        <div className="rounded-lg border border-dashed border-slate-300 p-4 text-xs text-slate-500">
          No hay opciones configuradas.
        </div>
      ) : (
        <div className="space-y-2">
          {options.map((option, index) => (
            <div key={option.id || `new-${index}`} className="grid gap-2 rounded-lg border border-slate-200 bg-white p-3 md:grid-cols-[1.2fr_1fr_1fr_auto]">
              <input
                type="text"
                value={option.label}
                onChange={(e) => updateOption(index, { label: e.target.value })}
                placeholder="Etiqueta visible"
                className="rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-indigo-500"
              />
              <input
                type="text"
                value={option.value}
                onChange={(e) => updateOption(index, { value: e.target.value })}
                placeholder="Valor técnico"
                className="rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-indigo-500"
              />
              {definition.widget_type === 'drilldown' ? (
                <select
                  value={option.parent_option_id || ''}
                  onChange={(e) => updateOption(index, { parent_option_id: e.target.value || null })}
                  className="rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-indigo-500"
                >
                  <option value="">Opción padre</option>
                  {parentOptions.map((parentOption) => (
                    <option key={parentOption.id} value={parentOption.id}>
                      {parentOption.label}
                    </option>
                  ))}
                </select>
              ) : (
                <label className="flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-600">
                  <input
                    type="checkbox"
                    checked={option.active !== false}
                    onChange={(e) => updateOption(index, { active: e.target.checked })}
                  />
                  Activa
                </label>
              )}
              <button type="button" onClick={() => removeOption(index)} className="rounded-lg border border-red-200 px-3 py-2 text-xs font-bold text-red-600 hover:bg-red-50">
                Quitar
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export const StoreMaintenance: React.FC<StoreMaintenanceProps> = ({ onOpenCatalogs }) => {
  const { currentMall, isAdmin, isTic, session } = useAuth();
  const canManageStores = isAdmin || isTic;
  const authToken = session?.access_token;

  const [stores, setStores] = useState<Store[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [showCustomFieldsManager, setShowCustomFieldsManager] = useState(false);
  const [showSalesPurge, setShowSalesPurge] = useState(false);
  const [savingStore, setSavingStore] = useState(false);
  const [savingFieldDefinition, setSavingFieldDefinition] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const [newStore, setNewStore] = useState<Partial<Store>>(emptyStore());
  const [customFieldDefinitions, setCustomFieldDefinitions] = useState<LocalCustomFieldDefinition[]>([]);
  const [customFieldValues, setCustomFieldValues] = useState<Record<string, FieldValueState>>({});
  const [editingFieldId, setEditingFieldId] = useState<string | null>(null);
  const [fieldDraft, setFieldDraft] = useState<Partial<LocalCustomFieldDefinition>>(emptyFieldDraft());
  const [catalogOptions, setCatalogOptions] = useState<StoreCatalogOption[]>([]);
  const [catalogTableAvailable, setCatalogTableAvailable] = useState<boolean | null>(null);
  const [catalogLoading, setCatalogLoading] = useState(false);

  const activeFieldDefinitions = useMemo(
    () => customFieldDefinitions.filter((field) => field.active).sort((a, b) => (a.sort_order || 0) - (b.sort_order || 0)),
    [customFieldDefinitions]
  );
  const catalogValuesByField = useMemo(() => ({
    tipo_negocio: catalogOptions
      .filter((option) => option.field_name === 'tipo_negocio')
      .map((option) => option.value)
      .filter(Boolean),
    rubro: catalogOptions
      .filter((option) => option.field_name === 'rubro')
      .map((option) => option.value)
      .filter(Boolean),
  }), [catalogOptions]);

  const isCatalogValue = (fieldName: 'tipo_negocio' | 'rubro', value: any) => {
    const valueKey = normalizeStoreCatalogKey(value);
    if (!valueKey) return false;
    return catalogValuesByField[fieldName].some((option) => normalizeStoreCatalogKey(option) === valueKey);
  };

  const hasUncataloguedValue = (fieldName: 'tipo_negocio' | 'rubro') => {
    const value = fieldName === 'tipo_negocio' ? newStore.tipo_negocio : newStore.rubro;
    return Boolean(value) && !isCatalogValue(fieldName, value);
  };

  const filteredStores = useMemo(() => {
    const query = searchTerm.trim().toLowerCase();
    if (!query) return stores;
    return stores.filter((store) => {
      return [
        store.nombre,
        store.codigo_interno,
        store.email,
        store.email_secundario,
        store.responsable,
        store.tipo_negocio,
        store.rubro,
      ].some((value) => String(value || '').toLowerCase().includes(query));
    });
  }, [stores, searchTerm]);

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

  const loadCustomFieldDefinitions = async () => {
    if (!currentMall?.id || !authToken || !canManageStores) {
      setCustomFieldDefinitions([]);
      return;
    }
    try {
      const data = await ApiService.getLocalCustomFieldDefinitions(currentMall.id, authToken, true);
      setCustomFieldDefinitions(data || []);
    } catch (error) {
      console.error('Error loading custom field definitions:', error);
      setCustomFieldDefinitions([]);
    }
  };

  const loadStoreCatalogs = async () => {
    if (!currentMall?.id) {
      setCatalogOptions([]);
      setCatalogTableAvailable(null);
      return;
    }
    setCatalogLoading(true);
    try {
      const result = await loadStoreCatalogOptions(currentMall.id);
      setCatalogOptions(result.options);
      setCatalogTableAvailable(result.available);
    } catch (error) {
      console.error('Error loading store catalogs:', error);
      setCatalogOptions([]);
      setCatalogTableAvailable(false);
    } finally {
      setCatalogLoading(false);
    }
  };

  const loadStoreCustomFieldValues = async (storeId: string) => {
    if (!authToken || !storeId) {
      setCustomFieldValues({});
      return;
    }
    try {
      const bundle = await ApiService.getStoreCustomFields(storeId, authToken, true);
      setCustomFieldValues(buildValueMap(bundle.values || []));
    } catch (error) {
      console.error('Error loading store custom fields:', error);
      setCustomFieldValues({});
    }
  };

  const resetStoreForm = () => {
    setNewStore(emptyStore(currentMall?.id));
    setCustomFieldValues({});
  };

  const resetFieldDraft = () => {
    setEditingFieldId(null);
    setFieldDraft(emptyFieldDraft(currentMall?.id));
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!currentMall?.id) {
      alert("Error: No se ha seleccionado un Mall.");
      return;
    }
    if (!authToken && activeFieldDefinitions.length > 0) {
      alert("Error: se requiere sesión válida para guardar campos libres.");
      return;
    }
    if (!catalogTableAvailable) {
      alert(`Para guardar locales debe configurar Catálogos Locales. Ejecute ${STORE_CATALOG_MIGRATION_FILE} o agregue las opciones desde Catálogos Locales.`);
      return;
    }
    if (!isCatalogValue('tipo_negocio', newStore.tipo_negocio)) {
      alert('Seleccione un Tipo de Negocio válido desde Catálogos Locales.');
      return;
    }
    if (!isCatalogValue('rubro', newStore.rubro)) {
      alert('Seleccione un Rubro General válido desde Catálogos Locales.');
      return;
    }

    const storeToSave = {
      ...newStore,
      mall_id: currentMall.id,
      mts: parseOptionalNumber(newStore.mts),
      porciento_renta: parseOptionalNumber(newStore.porciento_renta),
      renta_fija: parseOptionalNumber(newStore.renta_fija),
      breakpoint_venta: parseOptionalNumber(newStore.breakpoint_venta),
      porcentaje_variable: parseOptionalNumber(newStore.porcentaje_variable),
      fecha_corte_importacion: newStore.fecha_corte_importacion || null,
    };
    const customValuesPayload = serializeFieldValues(activeFieldDefinitions, customFieldValues);

    setSavingStore(true);
    try {
      const savedStore = storeToSave.id
        ? await ApiService.updateStore(storeToSave.id, storeToSave, authToken)
        : await ApiService.createStore(storeToSave, authToken);

      if (activeFieldDefinitions.length > 0) {
        await ApiService.saveStoreCustomFields(savedStore.id, customValuesPayload, authToken);
      }

      setShowForm(false);
      resetStoreForm();
      await loadStores();
    } catch (e: any) {
      console.error(e);
      if (storeToSave.id) {
        setNewStore({ ...storeToSave });
      }
      alert("Error al guardar: " + (e.message || e));
    } finally {
      setSavingStore(false);
    }
  };

  const handleDelete = async (id: string, nombre: string) => {
    if (!confirm(`¿Está seguro de que desea eliminar el local "${nombre}"?\nEsta acción no se puede deshacer.`)) return;
    try {
      await ApiService.deleteStore(id, authToken);
      loadStores();
    } catch (e: any) {
      console.error(e);
      alert("Error al eliminar: " + (e.message || e));
    }
  };

  const handleEdit = async (store: Store) => {
    setNewStore({ ...store });
    setShowForm(true);
    await loadStoreCustomFieldValues(store.id);
  };

  const handleNewStore = () => {
    resetStoreForm();
    setShowForm(true);
  };

  const handleSaveFieldDefinition = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!currentMall?.id || !authToken) {
      alert('No se pudo autenticar la gestión de campos libres.');
      return;
    }
    setSavingFieldDefinition(true);
    try {
      const payload = {
        ...fieldDraft,
        mall_id: currentMall.id,
        parent_field_id: fieldDraft.widget_type === 'drilldown' ? fieldDraft.parent_field_id || null : null,
        options: fieldDraft.options || [],
      };
      if (editingFieldId) {
        await ApiService.updateLocalCustomFieldDefinition(editingFieldId, payload, authToken);
      } else {
        await ApiService.createLocalCustomFieldDefinition(payload, authToken);
      }
      resetFieldDraft();
      await loadCustomFieldDefinitions();
    } catch (error: any) {
      console.error(error);
      alert(error?.message || 'No se pudo guardar el campo libre.');
    } finally {
      setSavingFieldDefinition(false);
    }
  };

  const handleEditFieldDefinition = (definition: LocalCustomFieldDefinition) => {
    setEditingFieldId(definition.id);
    setFieldDraft({
      ...definition,
      options: definition.options.map((option) => ({ ...option })),
    });
  };

  const updateCustomFieldValue = (fieldId: string, patch: Partial<FieldValueState>) => {
    setCustomFieldValues((prev) => {
      const current = prev[fieldId] || { field_definition_id: fieldId };
      return { ...prev, [fieldId]: { ...current, ...patch } };
    });
  };

  useEffect(() => {
    loadStores();
    loadStoreCatalogs();
    loadCustomFieldDefinitions();
    resetStoreForm();
    resetFieldDraft();
  }, [currentMall?.id, authToken, canManageStores]);

  if (!canManageStores) {
    return (
      <div className="bg-amber-50 border border-amber-200 text-amber-800 rounded-xl p-4 text-sm font-medium">
        Solo usuarios con rol IT o ADMIN pueden gestionar locales.
      </div>
    );
  }

  return (
    <div className="flex min-h-0 flex-col gap-4 animate-in fade-in slide-in-from-bottom-4 duration-500 lg:h-[calc(100dvh-8rem)] lg:overflow-hidden">
      <div className="flex shrink-0 flex-col items-start justify-between gap-3 md:flex-row md:items-center">
        <div>
          <h2 className="text-2xl font-bold text-slate-800">Mantenimiento de Locales</h2>
          <p className="text-sm text-slate-500">Configuración contractual, física y campos libres por mall.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {onOpenCatalogs && (
            <button
              type="button"
              onClick={onOpenCatalogs}
              className="flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 shadow-sm transition-all hover:bg-slate-50"
            >
              <Tag size={16} />
              Catálogos
            </button>
          )}
          <button
            onClick={() => setShowCustomFieldsManager(true)}
            className="flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 shadow-sm transition-all hover:bg-slate-50"
          >
            <Settings2 size={16} />
            Campos libres
          </button>
          <button
            type="button"
            onClick={() => setShowSalesPurge(true)}
            className="flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm font-medium text-red-600 transition-all hover:bg-red-100"
          >
            <Trash2 size={16} />
            Depurar ventas
          </button>
          <button
            onClick={handleNewStore}
            className="flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white shadow-md transition-all hover:bg-indigo-700 active:scale-95"
          >
            <Plus size={16} />
            Nuevo local
          </button>
        </div>
      </div>

      {showForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-3 backdrop-blur-sm sm:p-4">
          <div data-testid="store-maintenance-form-modal" className="flex max-h-[92vh] w-full max-w-6xl flex-col overflow-hidden rounded-2xl border border-indigo-100 bg-white shadow-2xl animate-in zoom-in-95 duration-200">
            <div className="flex shrink-0 items-center justify-between gap-4 border-b border-slate-100 px-5 py-3 sm:px-6">
            <h3 className="text-lg font-bold text-slate-800 flex items-center gap-2">
              <StoreIcon className="text-indigo-600" size={20} />
              {newStore.id ? 'Editar Local' : 'Información del Nuevo Local'}
            </h3>
            <button type="button" onClick={() => { setShowForm(false); resetStoreForm(); }} className="rounded-lg border border-slate-200 px-3 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50">
              Cerrar
            </button>
          </div>

          <form onSubmit={handleCreate} className="flex-1 space-y-5 overflow-y-auto p-5 sm:p-6">
            <div className="grid grid-cols-1 gap-5 md:grid-cols-3">
              <div className="space-y-4">
                <h4 className="text-xs font-bold text-slate-400 uppercase tracking-widest">Básico</h4>
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">Nombre Comercial</label>
                  <input type="text" required value={newStore.nombre} onChange={(e) => setNewStore({ ...newStore, nombre: e.target.value })} className="w-full px-4 py-2 rounded-lg border border-slate-200 focus:ring-2 focus:ring-indigo-500 outline-none" placeholder="Ej. Adidas Store" />
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">Código Interno</label>
                  <input type="text" required value={newStore.codigo_interno} onChange={(e) => setNewStore({ ...newStore, codigo_interno: e.target.value })} className="w-full px-4 py-2 rounded-lg border border-slate-200 focus:ring-2 focus:ring-indigo-500 outline-none" placeholder="L001" />
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">Email de Notificaciones</label>
                  <div className="relative">
                    <input
                      type="email"
                      value={newStore.email || ''}
                      onChange={(e) => setNewStore({ ...newStore, email: e.target.value })}
                      className="w-full px-4 py-2 rounded-lg border border-slate-200 focus:ring-2 focus:ring-indigo-500 outline-none pr-10"
                      placeholder="contacto@local.com"
                    />
                    <Mail size={14} className="absolute right-3 top-3 text-slate-400" />
                  </div>
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">Email secundario de Notificaciones</label>
                  <div className="relative">
                    <input
                      type="email"
                      value={newStore.email_secundario || ''}
                      onChange={(e) => setNewStore({ ...newStore, email_secundario: e.target.value })}
                      className="w-full px-4 py-2 rounded-lg border border-slate-200 focus:ring-2 focus:ring-indigo-500 outline-none pr-10"
                      placeholder="respaldo@local.com"
                    />
                    <Mail size={14} className="absolute right-3 top-3 text-slate-400" />
                  </div>
                  <p className="mt-1 text-xs text-slate-400">Recibirá en copia los avisos automáticos del local.</p>
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">Tipo de Negocio</label>
                  <select
                    required
                    value={newStore.tipo_negocio || ''}
                    disabled={catalogLoading || catalogValuesByField.tipo_negocio.length === 0}
                    onChange={(e) => setNewStore({ ...newStore, tipo_negocio: e.target.value })}
                    className="w-full px-4 py-2 rounded-lg border border-slate-200 focus:ring-2 focus:ring-indigo-500 outline-none disabled:bg-slate-50 disabled:text-slate-400"
                  >
                    <option value="">{catalogLoading ? 'Cargando catalogo...' : 'Seleccione tipo de negocio'}</option>
                    {hasUncataloguedValue('tipo_negocio') && (
                      <option value={newStore.tipo_negocio}>
                        Actual no catalogado: {newStore.tipo_negocio}
                      </option>
                    )}
                    {catalogValuesByField.tipo_negocio.map((value) => (
                      <option key={value} value={value}>{value}</option>
                    ))}
                  </select>
                  {hasUncataloguedValue('tipo_negocio') && (
                    <p className="mt-1 text-[10px] font-medium text-amber-600">Normalice este valor seleccionando una opción de Catálogos Locales.</p>
                  )}
                </div>
              </div>

              <div className="space-y-4">
                <h4 className="text-xs font-bold text-slate-400 uppercase tracking-widest">Contractual</h4>
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">Responsable</label>
                  <input type="text" value={newStore.responsable} onChange={(e) => setNewStore({ ...newStore, responsable: e.target.value })} className="w-full px-4 py-2 rounded-lg border border-slate-200 focus:ring-2 focus:ring-indigo-500 outline-none" placeholder="Nombre del encargado" />
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">Nº Contrato</label>
                  <input type="text" value={newStore.contrato_no} onChange={(e) => setNewStore({ ...newStore, contrato_no: e.target.value })} className="w-full px-4 py-2 rounded-lg border border-slate-200 focus:ring-2 focus:ring-indigo-500 outline-none" placeholder="99-88-11" />
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">% Renta Variable</label>
                  <div className="relative">
                    <input type="number" step="0.01" value={newStore.porciento_renta} onChange={(e) => setNewStore({ ...newStore, porciento_renta: e.target.value })} className="w-full px-4 py-2 rounded-lg border border-slate-200 focus:ring-2 focus:ring-indigo-500 outline-none pr-8" placeholder="5.00" />
                    <Percent size={14} className="absolute right-3 top-3 text-slate-400" />
                  </div>
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">Renta Fija</label>
                  <input type="number" step="0.01" value={newStore.renta_fija ?? ''} onChange={(e) => setNewStore({ ...newStore, renta_fija: e.target.value })} className="w-full px-4 py-2 rounded-lg border border-slate-200 focus:ring-2 focus:ring-indigo-500 outline-none" placeholder="0.00" />
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">Breakpoint de Venta</label>
                  <input type="number" step="0.01" value={newStore.breakpoint_venta ?? ''} onChange={(e) => setNewStore({ ...newStore, breakpoint_venta: e.target.value })} className="w-full px-4 py-2 rounded-lg border border-slate-200 focus:ring-2 focus:ring-indigo-500 outline-none" placeholder="0.00" />
                  <p className="mt-1 text-[10px] text-slate-400">Umbral contractual. Si el contrato no usa breakpoint, dejelo vacio.</p>
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">% Variable sobre Breakpoint</label>
                  <input type="number" step="0.01" value={newStore.porcentaje_variable ?? ''} onChange={(e) => setNewStore({ ...newStore, porcentaje_variable: e.target.value })} className="w-full px-4 py-2 rounded-lg border border-slate-200 focus:ring-2 focus:ring-indigo-500 outline-none" placeholder="0.00" />
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">Cierre de ventas hasta</label>
                  <input
                    type="date"
                    value={newStore.fecha_corte_importacion || ''}
                    onChange={(e) => setNewStore({ ...newStore, fecha_corte_importacion: e.target.value })}
                    className="w-full px-4 py-2 rounded-lg border border-slate-200 focus:ring-2 focus:ring-indigo-500 outline-none"
                  />
                  <p className="mt-1 text-[10px] text-slate-400">Bloquea importaciones con fecha igual o anterior.</p>
                </div>
              </div>

              <div className="space-y-4">
                <h4 className="text-xs font-bold text-slate-400 uppercase tracking-widest">Ubicación y Espacio</h4>
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">Piso / Ubicación</label>
                  <input type="text" value={newStore.piso} onChange={(e) => setNewStore({ ...newStore, piso: e.target.value })} className="w-full px-4 py-2 rounded-lg border border-slate-200 focus:ring-2 focus:ring-indigo-500 outline-none" placeholder="P2-L01" />
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">Metros Cuadrados (Mts2)</label>
                  <div className="relative">
                    <input type="number" step="0.01" value={newStore.mts} onChange={(e) => setNewStore({ ...newStore, mts: e.target.value })} className="w-full px-4 py-2 rounded-lg border border-slate-200 focus:ring-2 focus:ring-indigo-500 outline-none pr-10" placeholder="100.00" />
                    <span className="absolute right-3 top-2.5 text-xs text-slate-400 font-bold">m²</span>
                  </div>
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">Rubro General</label>
                  <select
                    required
                    value={newStore.rubro || ''}
                    disabled={catalogLoading || catalogValuesByField.rubro.length === 0}
                    onChange={(e) => setNewStore({ ...newStore, rubro: e.target.value })}
                    className="w-full px-4 py-2 rounded-lg border border-slate-200 focus:ring-2 focus:ring-indigo-500 outline-none disabled:bg-slate-50 disabled:text-slate-400"
                  >
                    <option value="">{catalogLoading ? 'Cargando catalogo...' : 'Seleccione rubro general'}</option>
                    {hasUncataloguedValue('rubro') && (
                      <option value={newStore.rubro || ''}>
                        Actual no catalogado: {newStore.rubro}
                      </option>
                    )}
                    {catalogValuesByField.rubro.map((value) => (
                      <option key={value} value={value}>{value}</option>
                    ))}
                  </select>
                  {hasUncataloguedValue('rubro') && (
                    <p className="mt-1 text-[10px] font-medium text-amber-600">Normalice este valor seleccionando una opción de Catálogos Locales.</p>
                  )}
                </div>
                <div className="pt-2">
                  <label className="flex items-center gap-3 cursor-pointer group">
                    <div className="relative">
                      <input type="checkbox" checked={!!newStore.upsert_activo} onChange={(e) => setNewStore({ ...newStore, upsert_activo: e.target.checked })} className="sr-only peer" />
                      <div className="w-10 h-5 bg-slate-200 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-indigo-600" />
                    </div>
                    <span className="text-sm font-medium text-slate-700 group-hover:text-indigo-600 transition-colors">Activar Sobrescritura (Upsert)</span>
                  </label>
                  <p className="text-[10px] text-slate-400 mt-1 ml-13">Permite corregir facturas del mismo día sobrescribiendo datos existentes.</p>
                </div>
              </div>
            </div>

            <div className="rounded-2xl border border-slate-200 bg-slate-50/60 p-5">
              <div className="flex items-center gap-3 mb-4">
                <div className="rounded-lg bg-indigo-100 p-2 text-indigo-600">
                  <Layers3 size={18} />
                </div>
                <div>
                  <h4 className="text-sm font-bold text-slate-800">Campos Libres</h4>
                  <p className="text-xs text-slate-500">Se configuran por mall y se usan también como dimensión opcional en el cubo.</p>
                </div>
              </div>

              {activeFieldDefinitions.length === 0 ? (
                <div className="rounded-xl border border-dashed border-slate-300 bg-white px-4 py-5 text-sm text-slate-500">
                  Este mall todavía no tiene campos libres configurados.
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {activeFieldDefinitions.map((definition) => {
                    const value = customFieldValues[definition.id];
                    const options = getFilteredOptions(definition, activeFieldDefinitions, customFieldValues);
                    return (
                      <div key={definition.id} className="rounded-xl border border-slate-200 bg-white p-4 space-y-2">
                        <div className="flex items-center justify-between gap-2">
                          <label className="text-sm font-semibold text-slate-700">
                            {definition.label}
                            {definition.required && <span className="ml-1 text-red-500">*</span>}
                          </label>
                          <span className="rounded-full bg-slate-100 px-2 py-1 text-[10px] font-bold uppercase tracking-wide text-slate-500">
                            {definition.widget_type}
                          </span>
                        </div>

                        {definition.data_type === 'text' && (
                          <input
                            type="text"
                            required={definition.required}
                            value={value?.value_text || ''}
                            onChange={(e) => updateCustomFieldValue(definition.id, { value_text: e.target.value })}
                            className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-indigo-500"
                          />
                        )}

                        {definition.data_type === 'number' && (
                          <input
                            type="number"
                            required={definition.required}
                            value={value?.value_number ?? ''}
                            onChange={(e) => updateCustomFieldValue(definition.id, { value_number: e.target.value ? Number(e.target.value) : null })}
                            className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-indigo-500"
                          />
                        )}

                        {definition.data_type === 'date' && (
                          <input
                            type="date"
                            required={definition.required}
                            value={value?.value_date || ''}
                            onChange={(e) => updateCustomFieldValue(definition.id, { value_date: e.target.value })}
                            className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-indigo-500"
                          />
                        )}

                        {definition.data_type === 'select' && (
                          <select
                            required={definition.required}
                            value={value?.selected_option_id || ''}
                            disabled={definition.widget_type === 'drilldown' && options.length === 0}
                            onChange={(e) => updateCustomFieldValue(definition.id, { selected_option_id: e.target.value || null })}
                            className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-indigo-500"
                          >
                            <option value="">{definition.widget_type === 'drilldown' ? 'Seleccione una opción hija' : 'Seleccione una opción'}</option>
                            {options.map((option) => (
                              <option key={option.id} value={option.id}>
                                {option.label}
                              </option>
                            ))}
                          </select>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            <div className="sticky bottom-0 flex justify-end gap-3 border-t border-slate-100 bg-white/95 pt-4 backdrop-blur">
              <button type="button" onClick={() => { setShowForm(false); resetStoreForm(); }} className="px-6 py-2.5 rounded-xl border border-slate-200 text-slate-600 font-medium hover:bg-slate-50 transition-colors">Cancelar</button>
              <button type="submit" disabled={savingStore} className="px-10 py-2.5 rounded-xl bg-indigo-600 text-white font-bold hover:bg-indigo-700 shadow-lg shadow-indigo-600/20 active:scale-95 transition-all disabled:opacity-60">
                {savingStore ? 'Guardando...' : 'Guardar Local'}
              </button>
            </div>
            </form>
          </div>
        </div>
      )}

      {showCustomFieldsManager && (
        <div className="fixed inset-0 z-50 bg-slate-950/40 backdrop-blur-sm flex items-center justify-center px-4">
          <div className="w-full max-w-6xl max-h-[90vh] overflow-auto rounded-3xl bg-white shadow-2xl border border-slate-200">
            <div className="sticky top-0 z-10 flex items-center justify-between border-b border-slate-100 bg-white px-6 py-4">
              <div>
                <h3 className="text-lg font-bold text-slate-800">Configurar Campos Libres</h3>
                <p className="text-sm text-slate-500">Defina campos dinámicos por mall y sus opciones para mantenimiento y cubo.</p>
              </div>
              <button onClick={() => { setShowCustomFieldsManager(false); resetFieldDraft(); }} className="rounded-lg border border-slate-200 px-3 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50">
                Cerrar
              </button>
            </div>

            <div className="grid gap-6 p-6 lg:grid-cols-[1.1fr_1.4fr]">
              <div className="space-y-4">
                <h4 className="text-sm font-bold text-slate-700">Campos existentes</h4>
                <div className="space-y-3">
                  {customFieldDefinitions.length === 0 ? (
                    <div className="rounded-xl border border-dashed border-slate-300 p-5 text-sm text-slate-500">
                      No hay campos libres configurados para este mall.
                    </div>
                  ) : (
                    customFieldDefinitions.map((definition) => (
                      <button
                        key={definition.id}
                        type="button"
                        onClick={() => handleEditFieldDefinition(definition)}
                        className="w-full rounded-xl border border-slate-200 bg-slate-50/70 p-4 text-left hover:border-indigo-300 hover:bg-indigo-50/40"
                      >
                        <div className="flex items-center justify-between gap-3">
                          <div>
                            <div className="font-bold text-slate-800">{definition.label}</div>
                            <div className="text-xs text-slate-500">
                              <span className="font-mono">{definition.key}</span> · {definition.data_type} · {definition.widget_type}
                            </div>
                          </div>
                          <div className="flex flex-col items-end gap-1 text-[10px] font-bold uppercase tracking-wide">
                            {!definition.active && <span className="rounded-full bg-red-100 px-2 py-1 text-red-600">Inactivo</span>}
                            {definition.required && <span className="rounded-full bg-amber-100 px-2 py-1 text-amber-700">Requerido</span>}
                          </div>
                        </div>
                      </button>
                    ))
                  )}
                </div>
              </div>

              <form onSubmit={handleSaveFieldDefinition} className="space-y-4 rounded-2xl border border-slate-200 bg-slate-50/60 p-5">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <h4 className="text-sm font-bold text-slate-700">{editingFieldId ? 'Editar campo libre' : 'Nuevo campo libre'}</h4>
                    <p className="text-xs text-slate-500">La clave técnica debe ser estable porque se usará en filtros y dimensión del cubo.</p>
                  </div>
                  {editingFieldId && (
                    <button type="button" onClick={resetFieldDraft} className="rounded-lg border border-slate-200 px-3 py-2 text-xs font-bold text-slate-600 hover:bg-white">
                      Nuevo campo
                    </button>
                  )}
                </div>

                <div className="grid gap-4 md:grid-cols-2">
                  <div>
                    <label className="mb-1 block text-sm font-medium text-slate-700">Etiqueta</label>
                    <input type="text" required value={fieldDraft.label || ''} onChange={(e) => setFieldDraft((prev) => ({ ...prev, label: e.target.value }))} className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-indigo-500" />
                  </div>
                  <div>
                    <label className="mb-1 block text-sm font-medium text-slate-700">Clave técnica</label>
                    <input type="text" required value={fieldDraft.key || ''} onChange={(e) => setFieldDraft((prev) => ({ ...prev, key: e.target.value.trim().toLowerCase().replace(/\s+/g, '_') }))} className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-indigo-500" />
                  </div>
                  <div>
                    <label className="mb-1 block text-sm font-medium text-slate-700">Tipo de dato</label>
                    <select value={fieldDraft.data_type || 'text'} onChange={(e) => setFieldDraft((prev) => ({ ...prev, data_type: e.target.value as LocalCustomFieldDefinition['data_type'], widget_type: e.target.value === 'select' ? 'select' : 'textbox', parent_field_id: null }))} className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-indigo-500">
                      <option value="text">Texto</option>
                      <option value="number">Numérico</option>
                      <option value="date">Fecha</option>
                      <option value="select">Selección</option>
                    </select>
                  </div>
                  <div>
                    <label className="mb-1 block text-sm font-medium text-slate-700">Control</label>
                    <select value={fieldDraft.widget_type || 'textbox'} onChange={(e) => setFieldDraft((prev) => ({ ...prev, widget_type: e.target.value as LocalCustomFieldDefinition['widget_type'], parent_field_id: e.target.value === 'drilldown' ? prev.parent_field_id : null }))} className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-indigo-500">
                      {(fieldDraft.data_type || 'text') === 'select' ? (
                        <>
                          <option value="select">Select</option>
                          <option value="drilldown">Drilldown</option>
                        </>
                      ) : (
                        <option value="textbox">Textbox</option>
                      )}
                    </select>
                  </div>
                  <div>
                    <label className="mb-1 block text-sm font-medium text-slate-700">Orden</label>
                    <input type="number" value={fieldDraft.sort_order ?? 0} onChange={(e) => setFieldDraft((prev) => ({ ...prev, sort_order: Number(e.target.value) || 0 }))} className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-indigo-500" />
                  </div>
                  <div className="flex items-center gap-6 rounded-lg border border-slate-200 bg-white px-3 py-2">
                    <label className="flex items-center gap-2 text-sm text-slate-600">
                      <input type="checkbox" checked={fieldDraft.required !== false} onChange={(e) => setFieldDraft((prev) => ({ ...prev, required: e.target.checked }))} />
                      Requerido
                    </label>
                    <label className="flex items-center gap-2 text-sm text-slate-600">
                      <input type="checkbox" checked={fieldDraft.active !== false} onChange={(e) => setFieldDraft((prev) => ({ ...prev, active: e.target.checked }))} />
                      Activo
                    </label>
                  </div>
                </div>

                {fieldDraft.widget_type === 'drilldown' && (
                  <div>
                    <label className="mb-1 block text-sm font-medium text-slate-700">Campo padre</label>
                    <select value={fieldDraft.parent_field_id || ''} onChange={(e) => setFieldDraft((prev) => ({ ...prev, parent_field_id: e.target.value || null, options: (prev.options || []).map((option) => ({ ...option, parent_option_id: null })) }))} className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-indigo-500">
                      <option value="">Seleccione el campo padre</option>
                      {customFieldDefinitions.filter((field) => field.id !== editingFieldId && field.data_type === 'select' && field.widget_type !== 'drilldown').map((field) => (
                        <option key={field.id} value={field.id}>
                          {field.label}
                        </option>
                      ))}
                    </select>
                  </div>
                )}

                <DefinitionOptionsEditor
                  definition={fieldDraft}
                  definitions={customFieldDefinitions}
                  onChange={(options) => setFieldDraft((prev) => ({ ...prev, options }))}
                />

                <div className="flex justify-end gap-3 pt-2">
                  <button type="button" onClick={resetFieldDraft} className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-600 hover:bg-white">
                    Limpiar
                  </button>
                  <button type="submit" disabled={savingFieldDefinition} className="rounded-lg bg-indigo-600 px-5 py-2 text-sm font-bold text-white hover:bg-indigo-700 disabled:opacity-60">
                    {savingFieldDefinition ? 'Guardando...' : (editingFieldId ? 'Actualizar Campo' : 'Crear Campo')}
                  </button>
                </div>
              </form>
            </div>
          </div>
        </div>
      )}

      <div data-testid="store-maintenance-list" className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
        <div className="flex shrink-0 flex-col gap-3 border-b border-slate-100 bg-slate-50/50 p-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-3 flex-1 max-w-md">
            <Search size={18} className="text-slate-400" />
            <input
              type="text"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              placeholder="Buscar por nombre, email, responsable o código..."
              className="bg-transparent border-none outline-none text-sm w-full"
            />
          </div>
          <div className="text-xs text-slate-400 font-medium">
            Mostrando {filteredStores.length} de {stores.length} locales registrados
          </div>
        </div>
        <div data-testid="store-maintenance-list-scroll" className="min-h-[320px] flex-1 overflow-auto overscroll-contain">
          <table className="w-full min-w-[1080px] table-fixed text-left">
            <colgroup>
              <col className="w-[250px]" />
              <col className="w-[230px]" />
              <col className="w-[145px]" />
              <col className="w-[110px]" />
              <col className="w-[90px]" />
              <col className="w-[170px]" />
              <col className="w-[110px]" />
            </colgroup>
            <thead className="sticky top-0 z-20 border-b border-slate-100 bg-slate-50 text-[10px] font-bold uppercase tracking-widest text-slate-500 shadow-sm">
              <tr>
                <th className="px-6 py-4">Información Local</th>
                <th className="px-6 py-4">Responsable</th>
                <th className="px-6 py-4">Ubicación (Piso)</th>
                <th className="px-6 py-4 text-center">Metraje (Mts²)</th>
                <th className="px-6 py-4 text-center">Renta %</th>
                <th className="px-6 py-4">Campos Libres</th>
                <th className="sticky right-0 z-30 bg-slate-50 px-4 py-3 text-right">Acciones</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {loading ? (
                <tr>
                  <td colSpan={7} className="px-6 py-12 text-center text-slate-400">
                    <div className="flex flex-col items-center gap-2">
                      <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-indigo-600" />
                      <span className="text-sm">Cargando datos de locales...</span>
                    </div>
                  </td>
                </tr>
              ) : filteredStores.length > 0 ? (
                filteredStores.map((store) => (
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
                      {store.email && (
                        <div className="text-[10px] text-slate-400 flex items-center gap-1 mt-0.5 ml-5">
                          <Mail size={10} /> {store.email}
                        </div>
                      )}
                      {store.email_secundario && (
                        <div className="text-[10px] text-slate-400 flex items-center gap-1 mt-0.5 ml-5">
                          <Mail size={10} /> {store.email_secundario}
                        </div>
                      )}
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
                    <td className="px-6 py-4 min-w-[220px]">
                      {activeFieldDefinitions.length === 0 ? (
                        <span className="text-xs text-slate-400">Sin configuración</span>
                      ) : (
                        <div className="flex flex-wrap gap-2">
                          {activeFieldDefinitions.slice(0, 3).map((definition) => (
                            <span key={definition.id} className="rounded-full bg-slate-100 px-2 py-1 text-[10px] text-slate-600">
                              {definition.label}
                            </span>
                          ))}
                          {activeFieldDefinitions.length > 3 && (
                            <span className="rounded-full bg-indigo-50 px-2 py-1 text-[10px] text-indigo-600">
                              +{activeFieldDefinitions.length - 3} más
                            </span>
                          )}
                        </div>
                      )}
                    </td>
                    <td className="sticky right-0 z-10 bg-white px-4 py-3 text-right group-hover:bg-slate-50">
                      <div className="flex items-center justify-end gap-1">
                        {store.processing_status === 'SUSPENDED_AUTH_ERROR' ? (
                          <button
                            onClick={async () => {
                              if (confirm('¿Reactivar este local? Se restablecerá el contador de fallos.')) {
                                try {
                                  await ApiService.reactivateStore(store.id, session?.access_token);
                                  loadStores();
                                } catch (e) { alert('Error: ' + e); }
                              }
                            }}
                            className="bg-red-100 text-red-700 px-3 py-1 rounded-lg text-xs font-bold hover:bg-red-200 transition-colors flex items-center gap-1"
                          >
                            Reactivar
                          </button>
                        ) : (
                          <>
                            <button onClick={() => handleEdit(store)} className="p-2 text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 rounded-lg transition-all" title="Editar">
                              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z" /><path d="m15 5 4 4" /></svg>
                            </button>
                            <button onClick={() => handleDelete(store.id, store.nombre)} className="p-2 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-all" title="Eliminar">
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
                  <td colSpan={7} className="px-6 py-20 text-center">
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

      {showSalesPurge && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-3 backdrop-blur-sm sm:p-4">
          <div data-testid="store-maintenance-purge-modal" className="flex max-h-[92vh] w-full max-w-6xl flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl">
            <div className="flex shrink-0 items-center justify-between border-b border-slate-100 px-5 py-3 sm:px-6">
              <div>
                <h3 className="font-bold text-slate-800">Depuración de ventas</h3>
                <p className="text-xs text-slate-500">Herramientas administrativas para eliminar cargas históricas.</p>
              </div>
              <button type="button" onClick={() => setShowSalesPurge(false)} className="rounded-lg border border-slate-200 px-3 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50">
                Cerrar
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-4 sm:p-5">
              <SalesPurge />
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
