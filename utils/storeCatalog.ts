import {
  ApiService,
  DEFAULT_STORE_CATALOG_VALUES,
  Store,
  StoreCatalogFieldName,
  StoreCatalogOption,
} from '../api';

export const STORE_CATALOG_MIGRATION_FILE = '20260301_store_field_options.sql';

export const normalizeStoreCatalogText = (value: any): string =>
  String(value || '').trim().replace(/\s+/g, ' ');

export const normalizeStoreCatalogKey = (value: any): string =>
  normalizeStoreCatalogText(value)
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '');

export const getStoreCatalogFieldValue = (
  store: Partial<Store>,
  fieldName: StoreCatalogFieldName
): string => normalizeStoreCatalogText(fieldName === 'tipo_negocio' ? store.tipo_negocio : store.rubro);

export const buildStoreCatalogValues = (params: {
  fieldName: StoreCatalogFieldName;
  catalogOptions: StoreCatalogOption[];
  catalogTableAvailable: boolean | null;
  stores?: Partial<Store>[];
  selectedValue?: string;
}): string[] => {
  const { fieldName, catalogOptions, catalogTableAvailable, stores = [], selectedValue = '' } = params;
  const ordered = new Map<string, string>();
  const sources = [
    ...(catalogTableAvailable === true ? [] : DEFAULT_STORE_CATALOG_VALUES[fieldName]),
    ...catalogOptions
      .filter((option) => option.field_name === fieldName)
      .map((option) => option.value),
    ...stores.map((store) => getStoreCatalogFieldValue(store, fieldName)),
    getStoreCatalogFieldValue({ [fieldName]: selectedValue } as Partial<Store>, fieldName),
  ];

  sources.forEach((value) => {
    const cleanValue = normalizeStoreCatalogText(value);
    const key = normalizeStoreCatalogKey(cleanValue);
    if (!cleanValue || !key || ordered.has(key)) return;
    ordered.set(key, cleanValue);
  });

  return Array.from(ordered.values()).sort((a, b) =>
    a.localeCompare(b, undefined, { sensitivity: 'base', numeric: true })
  );
};

export const buildStoreCatalogUsageMap = (
  stores: Partial<Store>[],
  fieldName: StoreCatalogFieldName
): Map<string, number> => {
  const usageMap = new Map<string, number>();

  stores.forEach((store) => {
    const value = getStoreCatalogFieldValue(store, fieldName);
    const key = normalizeStoreCatalogKey(value);
    if (!key) return;
    usageMap.set(key, (usageMap.get(key) || 0) + 1);
  });

  return usageMap;
};

export const getStoreCatalogOptionRow = (
  catalogOptions: StoreCatalogOption[],
  fieldName: StoreCatalogFieldName,
  value: string
): StoreCatalogOption | undefined =>
  catalogOptions.find(
    (option) =>
      option.field_name === fieldName &&
      normalizeStoreCatalogKey(option.value) === normalizeStoreCatalogKey(value)
  );

export const loadStoreCatalogOptions = async (
  mallId: string
): Promise<{ options: StoreCatalogOption[]; available: boolean }> => {
  const result = await ApiService.getStoreCatalogOptions(mallId);

  if (!result.available) {
    return { options: [], available: false };
  }

  if (result.options.length === 0) {
    await ApiService.seedStoreCatalogDefaults(mallId);
    const seededResult = await ApiService.getStoreCatalogOptions(mallId);
    return {
      options: seededResult.options,
      available: seededResult.available,
    };
  }

  return {
    options: result.options,
    available: true,
  };
};
