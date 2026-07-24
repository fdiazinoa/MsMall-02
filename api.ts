import { createClient } from '@supabase/supabase-js';
import { SaleReport, IngestionResponse, DateRange, KPIData, User, ImportConfig, SaleDetail, ImportProtocol, FileType, ImportFrequency, RemoteConnection, RoleConfig, ConnectionMonitorStatusResponse, ConnectionMonitorFailuresResponse, ConnectionRetryActionResponse, ConnectionRetryBatchResponse, MissingDaysEmailSettings, MissingDaysSendNowResponse, ResendMessagingStatus, ResendSenderConfigPayload, ResendTestMessageResponse, SecurityApiToken, SecurityExporterWebserviceConfig, SecurityServiceAccount, SecurityTokenAuditLogEntry, SecurityTokenPairReveal, LoadLogEntry, CopilotSettings, CopilotSettingsPayload, CopilotChatMessage, CopilotChatResponse, CopilotEmailSendResponse } from './types';

const SUPABASE_URL = import.meta.env.VITE_SUPABASE_URL || '';
const SUPABASE_ANON_KEY = import.meta.env.VITE_SUPABASE_ANON_KEY || '';

export const supabase = (SUPABASE_URL && SUPABASE_ANON_KEY)
  ? createClient(SUPABASE_URL, SUPABASE_ANON_KEY)
  : null;

if (!supabase) {
  console.warn("Supabase no está configurado. Verifica tu archivo .env");
}

const BASE_URL = '/api/v1';
const DIRECT_BACKEND_BASE_URL = import.meta.env.VITE_DIRECT_BACKEND_BASE_URL || '';
const STORES_STORAGE_KEY = 'msmall_mock_stores';
const USERS_STORAGE_KEY = 'msmall_mock_users';
const IMPORTS_STORAGE_KEY = 'msmall_mock_imports';
const DEFAULT_RAILWAY_BASE_URL = 'https://msmall-02-production.up.railway.app/api/v1';

const normalizeApiBaseUrl = (value: string): string => {
  const trimmed = (value || '').trim();
  if (!trimmed) return '';
  if (trimmed === BASE_URL) return BASE_URL;
  return `${trimmed.replace(/\/+$/, '').replace(/\/api\/v1$/i, '').replace(/\/api$/i, '')}/api/v1`;
};

const getApiBaseUrls = (): string[] => {
  const urls: string[] = [];
  const normalizedDirectBase = normalizeApiBaseUrl(DIRECT_BACKEND_BASE_URL);
  const isVercelHost = typeof window !== 'undefined' && window.location.hostname.endsWith('vercel.app');

  if (isVercelHost) {
    urls.push(BASE_URL);
  }

  if (normalizedDirectBase && normalizedDirectBase !== BASE_URL) {
    urls.push(normalizedDirectBase);
  } else if (isVercelHost) {
    urls.push(DEFAULT_RAILWAY_BASE_URL);
  }

  urls.push(BASE_URL);
  return Array.from(new Set(urls));
};

const getExecuteManualBaseUrls = (): string[] => getApiBaseUrls();

const isNetworkFetchFailure = (error: any): boolean => {
  const msg = String(error?.message || error || '');
  return (
    msg.includes('Failed to fetch') ||
    msg.includes('ERR_NETWORK_CHANGED') ||
    msg.includes('NetworkError')
  );
};

const withAuthHeaders = (token?: string, headers: Record<string, string> = {}): Record<string, string> => {
  if (!token) return headers;
  return { ...headers, Authorization: `Bearer ${token}` };
};

const parseErrorDetail = async (response: Response, fallbackMessage: string): Promise<string> => {
  const raw = await response.text().catch(() => '');
  const fallbackWithStatus = `${fallbackMessage} (HTTP ${response.status}${response.statusText ? ` ${response.statusText}` : ''})`;
  if (!raw) return fallbackWithStatus;
  if (raw.trim().startsWith('<')) return fallbackWithStatus;

  try {
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed === 'object') {
      if (typeof parsed.detail === 'string' && parsed.detail.trim()) return parsed.detail;
      if (Array.isArray(parsed.detail) && parsed.detail.length > 0) {
        const first = parsed.detail[0];
        if (typeof first === 'string' && first.trim()) return first;
        if (first && typeof first === 'object') {
          if (typeof first.msg === 'string' && first.msg.trim()) return first.msg;
          if (typeof first.message === 'string' && first.message.trim()) return first.message;
        }
      }
      if (typeof parsed.message === 'string' && parsed.message.trim()) return parsed.message;
    }
  } catch {
    // Ignore parse errors and use fallback.
  }

  return fallbackWithStatus;
};

const normalizeErrorMessage = (error: any, fallbackMessage: string): string => {
  if (error instanceof Error && error.message && error.message.trim()) {
    return error.message;
  }
  if (typeof error === 'string' && error.trim()) {
    return error;
  }
  return fallbackMessage;
};

const getRemoteOperationTimeoutMs = (
  filename: string,
  options?: {
    timeoutMs?: number;
    largeFile?: boolean;
    operation?: 'analysis' | 'execute';
  }
): number => {
  if (options?.timeoutMs && options.timeoutMs > 0) return options.timeoutMs;

  const normalizedFilename = String(filename || '').toLowerCase();
  const isJson = normalizedFilename.endsWith('.json');
  const isLargeFile = Boolean(options?.largeFile);
  const operation = options?.operation || 'analysis';

  if (operation === 'execute') {
    if (isJson || isLargeFile) return 900000;
    return 300000;
  }

  if (isJson || isLargeFile) return 420000;
  return 180000;
};

const toFiniteNumber = (value: any): number => {
  const n = Number(value);
  return Number.isFinite(n) ? n : 0;
};

const toOptionalNonNegativeInt = (value: any): number | null => {
  const n = Number(value);
  if (!Number.isFinite(n)) return null;
  return Math.max(Math.trunc(n), 0);
};

const extractLoadCount = (message: string, patterns: RegExp[]): number | null => {
  for (const pattern of patterns) {
    const match = message.match(pattern);
    if (match?.[1]) {
      const parsed = toOptionalNonNegativeInt(match[1]);
      if (parsed !== null) return parsed;
    }
  }
  return null;
};

const normalizeLoadChannel = (value: any): string | null => {
  const raw = String(value || '').trim();
  if (!raw) return null;
  const upper = raw.toUpperCase();
  if (upper === 'WEBSERVICE') return 'WebService';
  if (upper === 'FTP' || upper === 'SFTP' || upper === 'API') return upper;
  return raw;
};

const inferLoadChannel = (row: any): string | null => {
  const metadata = row?.metadata && typeof row.metadata === 'object' ? row.metadata : {};
  const fromFields = normalizeLoadChannel(row?.canal ?? metadata?.canal ?? metadata?.channel);
  if (fromFields) return fromFields;

  const haystack = `${row?.mensaje || ''} ${row?.archivo || ''}`.toLowerCase();
  if (haystack.includes('webservice')) return 'WebService';
  if (haystack.includes('sftp')) return 'SFTP';
  if (haystack.includes('ftp')) return 'FTP';
  if (haystack.includes('api')) return 'API';
  return null;
};

const normalizeLoadLogRow = (row: any): LoadLogEntry => {
  const metadata = row?.metadata && typeof row.metadata === 'object' ? row.metadata : {};
  const detalles = Array.isArray(row?.detalles)
    ? row.detalles.filter((item: any) => item && typeof item === 'object')
    : [];
  const message = String(row?.mensaje || '').trim();
  const recordsProcessed =
    toOptionalNonNegativeInt(row?.records_processed ?? metadata?.records_processed)
    ?? extractLoadCount(message, [
      /(?:^|\s)(\d+)\s+registros?\s+(?:cargados?|procesados?)/i,
      /procesado:\s*(\d+)\s+registros?/i,
      /inserci[oó]n confirmada de\s*(\d+)\s+registros?/i,
    ]);
  const errorCount =
    toOptionalNonNegativeInt(row?.error_count ?? metadata?.error_count)
    ?? (detalles.length > 0 ? detalles.length : extractLoadCount(message, [
      /errores?:\s*(\d+)/i,
      /se encontraron\s*(\d+)\s+errores?/i,
    ]))
    ?? 0;

  let estado = String(row?.estado || '').trim().toLowerCase() || 'error';
  if (estado === 'exito' && errorCount > 0) estado = 'parcial';

  return {
    ...row,
    id: row?.id ?? `${row?.fecha_hora || ''}-${row?.archivo || ''}-${row?.local_nombre || row?.local_id || ''}`,
    fecha_hora: String(row?.fecha_hora || ''),
    mall_id: row?.mall_id ?? metadata?.mall_id ?? null,
    mall_nombre: row?.mall_nombre ?? metadata?.mall_nombre ?? null,
    local_id: row?.local_id ?? metadata?.local_id ?? null,
    local_nombre: row?.local_nombre ?? metadata?.local_nombre ?? null,
    archivo: row?.archivo ?? metadata?.archivo ?? null,
    estado,
    mensaje: message || 'Sin detalle adicional.',
    batch_id: row?.batch_id ?? metadata?.batch_id ?? null,
    detalles,
    canal: inferLoadChannel(row),
    records_processed: recordsProcessed,
    error_count: errorCount,
    metadata,
  };
};

const parseCsvLine = (line: string): string[] => {
  const out: string[] = [];
  let current = '';
  let inQuotes = false;

  for (let i = 0; i < line.length; i++) {
    const ch = line[i];

    if (ch === '"') {
      // Escaped quote inside quoted field.
      if (inQuotes && line[i + 1] === '"') {
        current += '"';
        i++;
        continue;
      }
      inQuotes = !inQuotes;
      continue;
    }

    if (ch === ',' && !inQuotes) {
      out.push(current);
      current = '';
      continue;
    }

    current += ch;
  }

  out.push(current);
  return out;
};

const parseCsvAmount = (raw: any): number => {
  if (raw === null || raw === undefined) return NaN;
  let text = String(raw).trim();
  if (!text) return NaN;

  // Remove wrapping quotes and spaces/currency symbols.
  text = text.replace(/^"(.*)"$/, '$1').trim();
  text = text.replace(/\s+/g, '');
  text = text.replace(/^RD\$/i, '');
  text = text.replace(/[$€]/g, '');

  const hasComma = text.includes(',');
  const hasDot = text.includes('.');

  if (hasComma && hasDot) {
    const lastComma = text.lastIndexOf(',');
    const lastDot = text.lastIndexOf('.');
    if (lastDot > lastComma) {
      // 4,984.34 => comma thousands, dot decimal
      text = text.replace(/,/g, '');
    } else {
      // 4.984,34 => dot thousands, comma decimal
      text = text.replace(/\./g, '').replace(',', '.');
    }
  } else if (hasComma) {
    const commaCount = (text.match(/,/g) || []).length;
    if (commaCount > 1) {
      text = text.replace(/,/g, '');
    } else {
      const [left, right = ''] = text.split(',');
      if (right.length === 3 && left.length >= 1) {
        // Likely thousands separator
        text = `${left}${right}`;
      } else {
        text = `${left}.${right}`;
      }
    }
  }

  const n = Number(text);
  return Number.isFinite(n) ? n : NaN;
};

const pad2 = (value: number): string => String(value).padStart(2, '0');

const isValidDateParts = (year: number, month: number, day: number): boolean => {
  if (!Number.isInteger(year) || !Number.isInteger(month) || !Number.isInteger(day)) return false;
  if (year < 1900 || year > 2100) return false;
  if (month < 1 || month > 12) return false;
  if (day < 1 || day > 31) return false;
  const dt = new Date(Date.UTC(year, month - 1, day));
  return dt.getUTCFullYear() === year && (dt.getUTCMonth() + 1) === month && dt.getUTCDate() === day;
};

const toYmdIfValid = (year: number, month: number, day: number): string | null => {
  if (!isValidDateParts(year, month, day)) return null;
  return `${year}-${pad2(month)}-${pad2(day)}`;
};

const expandTwoDigitYear = (yy: number): number => {
  // Keep current operational data in modern years while preserving older values if needed.
  return yy >= 70 ? 1900 + yy : 2000 + yy;
};

type CsvDateFormatPreference =
  | 'auto'
  | 'dd/mm/yyyy'
  | 'dd/mm/yy'
  | 'mm/dd/yyyy'
  | 'mm/dd/yy'
  | 'dd-mm-yyyy'
  | 'dd-mm-yy'
  | 'yyyy-mm-dd'
  | 'yyyy/mm/dd'
  | 'yyyymmdd';

const normalizeCsvSaleDate = (raw: any, preferredFormat: CsvDateFormatPreference = 'auto'): string | null => {
  if (raw === null || raw === undefined) return null;
  let text = String(raw).trim();
  if (!text) return null;
  text = text.replace(/^"(.*)"$/, '$1').trim().replace(/^'(.*)'$/, '$1').trim();
  // Common POS/Excel exports append a zeroed time to the date field. Keep only the date part
  // before applying the format-specific parser (e.g. "2026-01-02 00:00:00.000").
  text = text.replace(
    /^((?:\d{4}[-/]\d{2}[-/]\d{2})|(?:\d{2}[-/]\d{2}[-/]\d{2,4}))(?:[ T]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?)$/,
    '$1'
  );
  const pref = String(preferredFormat || 'auto').toLowerCase() as CsvDateFormatPreference;

  let m: RegExpMatchArray | null;

  // Match order mirrors worker_importacion.normalize_date (dd/mm first, then others),
  // with an explicit override when the user selects a CSV date format in the UI.
  m = text.match(/^(\d{2})\/(\d{2})\/(\d{4})$/); // DD/MM/YYYY
  if (m) {
    const year = Number(m[3]);
    const first = Number(m[1]);
    const second = Number(m[2]);
    const ddmm = toYmdIfValid(year, second, first);
    const mmdd = toYmdIfValid(year, first, second);
    if (pref === 'mm/dd/yyyy') return mmdd || ddmm;
    if (pref === 'dd/mm/yyyy') return ddmm || mmdd;
    if (ddmm) return ddmm;
    if (mmdd) return mmdd;
    return null;
  }

  m = text.match(/^(\d{4})-(\d{2})-(\d{2})$/); // YYYY-MM-DD
  if (m) {
    return toYmdIfValid(Number(m[1]), Number(m[2]), Number(m[3]));
  }

  m = text.match(/^(\d{2})-(\d{2})-(\d{4})$/); // DD-MM-YYYY
  if (m) {
    const year = Number(m[3]);
    const first = Number(m[1]);
    const second = Number(m[2]);
    const ddmm = toYmdIfValid(year, second, first);
    if (pref === 'dd-mm-yyyy') return ddmm;
    return ddmm;
  }

  m = text.match(/^(\d{2})\/(\d{2})\/(\d{2})$/); // DD/MM/YY or MM/DD/YY
  if (m) {
    const year = expandTwoDigitYear(Number(m[3]));
    const first = Number(m[1]);
    const second = Number(m[2]);
    const ddmm = toYmdIfValid(year, second, first);
    const mmdd = toYmdIfValid(year, first, second);
    if (pref === 'mm/dd/yy') return mmdd || ddmm;
    if (pref === 'dd/mm/yy') return ddmm || mmdd;
    if (ddmm) return ddmm;
    if (mmdd) return mmdd;
    return null;
  }

  m = text.match(/^(\d{2})-(\d{2})-(\d{2})$/); // DD-MM-YY
  if (m) {
    return toYmdIfValid(expandTwoDigitYear(Number(m[3])), Number(m[2]), Number(m[1]));
  }

  m = text.match(/^(\d{4})\/(\d{2})\/(\d{2})$/); // YYYY/MM/DD
  if (m) {
    return toYmdIfValid(Number(m[1]), Number(m[2]), Number(m[3]));
  }

  m = text.match(/^(\d{4})(\d{2})(\d{2})(?:[ T](\d{2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?)?$/); // YYYYmmDD[ time]
  if (m) {
    return toYmdIfValid(Number(m[1]), Number(m[2]), Number(m[3]));
  }

  return null;
};

const isDateOnOrBefore = (value: string | null | undefined, cutoff: string | null | undefined): boolean => {
  if (!value || !cutoff) return false;
  return value <= cutoff;
};

const normalizeCsvSaleTime = (raw: any): string | null => {
  if (raw === null || raw === undefined) return null;
  let text = String(raw).trim();
  if (!text) return null;
  text = text.replace(/^"(.*)"$/, '$1').trim().replace(/^'(.*)'$/, '$1').trim();

  let hourOnly = text.match(/^(\d{1,2})$/);
  if (hourOnly) {
    const hh = Number(hourOnly[1]);
    if (hh >= 0 && hh <= 23) {
      return `${pad2(hh)}:00:00`;
    }
  }

  let m = text.match(/\b(\d{1,2}):(\d{2})(?::(\d{2}))?\b/);
  if (m) {
    const hh = Number(m[1]);
    const mm = Number(m[2]);
    const ss = Number(m[3] || '0');
    if (hh >= 0 && hh <= 23 && mm >= 0 && mm <= 59 && ss >= 0 && ss <= 59) {
      return `${pad2(hh)}:${pad2(mm)}:${pad2(ss)}`;
    }
  }

  m = text.match(/^(\d{2})(\d{2})(\d{2})$/); // HHMMSS
  if (m) {
    const hh = Number(m[1]);
    const mm = Number(m[2]);
    const ss = Number(m[3]);
    if (hh >= 0 && hh <= 23 && mm >= 0 && mm <= 59 && ss >= 0 && ss <= 59) {
      return `${pad2(hh)}:${pad2(mm)}:${pad2(ss)}`;
    }
  }

  m = text.match(/^(\d{2})(\d{2})$/); // HHMM
  if (m) {
    const hh = Number(m[1]);
    const mm = Number(m[2]);
    if (hh >= 0 && hh <= 23 && mm >= 0 && mm <= 59) {
      return `${pad2(hh)}:${pad2(mm)}:00`;
    }
  }

  return null;
};

const normalizeSaleTotals = <T extends { total_bruto?: any; total_impuestos?: any; total_neto?: any }>(row: T) => {
  const bruto = toFiniteNumber(row.total_bruto);
  const impuestos = toFiniteNumber(row.total_impuestos);
  const neto = toFiniteNumber(row.total_neto);

  // Keep a small epsilon for decimal rounding differences.
  const EPSILON = 0.05;

  // Canonical convention for reports: neto ≈ bruto + impuestos.
  const asIsDelta = Math.abs(neto - (bruto + impuestos));
  const swappedDelta = Math.abs(bruto - (neto + impuestos));

  if (swappedDelta + EPSILON < asIsDelta) {
    return {
      total_bruto: neto,
      total_impuestos: impuestos,
      total_neto: bruto
    };
  }

  return {
    total_bruto: bruto,
    total_impuestos: impuestos,
    total_neto: neto
  };
};

const fetchJsonWithBaseFallback = async <T>(
  path: string,
  init: RequestInit,
  fallbackMessage: string
): Promise<T> => {
  const baseUrls = getApiBaseUrls();
  let lastError: any = null;

  for (let i = 0; i < baseUrls.length; i++) {
    const baseUrl = baseUrls[i];
    const endpoint = `${baseUrl}${path}`;

    try {
      const response = await fetch(endpoint, init);
      if (response.ok) {
        return await response.json();
      }

      // 5xx from proxy/rewrite should try direct backend fallback.
      if (response.status >= 500 && i < baseUrls.length - 1) {
        console.warn(`API fallback: ${endpoint} respondió ${response.status}. Intentando siguiente base...`);
        continue;
      }

      const detail = await parseErrorDetail(response, fallbackMessage);
      throw new Error(detail);
    } catch (error: any) {
      lastError = error;
      if (isNetworkFetchFailure(error) && i < baseUrls.length - 1) {
        console.warn(`API fallback: fallo de red en ${endpoint}. Intentando siguiente base...`);
        continue;
      }
      throw error;
    }
  }

  throw lastError || new Error(fallbackMessage);
};

export interface Store {
  id: string;
  mall_id: string;
  codigo_interno: string;
  nombre: string;
  email?: string | null;
  rubro: string | null;
  created_at: string;
  responsable: string;
  contrato_no: string;
  piso: string;
  tipo_negocio: string;
  mts: string;
  porciento_renta: string | number;
  upsert_activo?: boolean;
  mall_nombre?: string;
  renta_fija?: string | number;
  breakpoint_venta?: string | number;
  porcentaje_variable?: string | number;
  processing_status?: 'IDLE' | 'BUSY' | 'SUSPENDED_AUTH_ERROR';
  consecutive_failures?: number;
  fecha_corte_importacion?: string | null;
}

export type StoreCatalogFieldName = 'tipo_negocio' | 'rubro';

export interface StoreCatalogOption {
  id: string;
  mall_id: string;
  field_name: StoreCatalogFieldName;
  value: string;
  value_key?: string;
  sort_order?: number | null;
  created_at?: string;
  updated_at?: string;
}

export interface StoreCatalogOptionsResult {
  options: StoreCatalogOption[];
  available: boolean;
}

export type CustomFieldDataType = 'text' | 'number' | 'date' | 'select';
export type CustomFieldWidgetType = 'textbox' | 'select' | 'drilldown';

export interface LocalCustomFieldOption {
  id?: string;
  field_definition_id?: string;
  label: string;
  value: string;
  sort_order?: number;
  active?: boolean;
  parent_option_id?: string | null;
}

export interface LocalCustomFieldDefinition {
  id: string;
  mall_id: string;
  key: string;
  label: string;
  data_type: CustomFieldDataType;
  widget_type: CustomFieldWidgetType;
  required: boolean;
  active: boolean;
  sort_order: number;
  parent_field_id?: string | null;
  options: LocalCustomFieldOption[];
}

export interface LocalCustomFieldValue {
  field_definition_id: string;
  value_text?: string | null;
  value_number?: number | null;
  value_date?: string | null;
  selected_option_id?: string | null;
  display_value?: string | number | null;
  filter_value?: string | number | null;
}

export interface LocalCustomFieldBundle {
  local_id: string;
  mall_id: string;
  definitions: LocalCustomFieldDefinition[];
  values: LocalCustomFieldValue[];
}

export const DEFAULT_STORE_CATALOG_VALUES: Record<StoreCatalogFieldName, string[]> = {
  tipo_negocio: [
    'RETAIL',
    'GASTRONOMIA',
    'SERVICIOS',
    'ENTRETENIMIENTO',
    'SALUD',
    'BELLEZA',
    'HOGAR',
    'TECNOLOGIA',
    'SUPERMERCADO',
    'DEPARTAMENTAL',
    'FINANCIERO',
    'EDUCACION',
    'AUTOMOTRIZ',
    'DEPORTES',
    'OTROS',
  ],
  rubro: [
    'MODA',
    'ZAPATERIA',
    'DEPORTES',
    'FAST FOOD',
    'RESTAURANTE',
    'CAFETERIA',
    'HELADERIA',
    'JOYERIA',
    'TECNOLOGIA',
    'HOGAR Y DECORACION',
    'SALUD Y FARMACIA',
    'BELLEZA Y COSMETICA',
    'SERVICIOS FINANCIEROS',
    'ENTRETENIMIENTO',
    'LIBRERIA',
    'INFANTIL',
    'SUPERMERCADO',
    'TELECOMUNICACIONES',
    'OPTICA',
    'OTROS',
  ],
};

const STORE_CATALOG_TABLE = 'store_field_options';
const STORE_CATALOG_MIGRATION_FILE = '20260301_store_field_options.sql';

const normalizeCatalogText = (value: any): string => String(value || '').trim().replace(/\s+/g, ' ');

const isMissingStoreCatalogTableError = (error: any): boolean => {
  const message = String(error?.message || error?.details || '');
  return (
    error?.code === '42P01' ||
    error?.code === 'PGRST205' ||
    (
      message.includes(STORE_CATALOG_TABLE) &&
      (
        message.toLowerCase().includes('does not exist') ||
        message.toLowerCase().includes('schema cache')
      )
    )
  );
};

const toStoreCatalogError = (error: any, fallbackMessage: string): Error => {
  if (isMissingStoreCatalogTableError(error)) {
    return new Error(`La base de datos no está actualizada: ejecute el script '${STORE_CATALOG_MIGRATION_FILE}'.`);
  }
  if (error?.code === '23505') {
    return new Error('Ese valor ya existe en la lista.');
  }
  return error instanceof Error ? error : new Error(normalizeErrorMessage(error, fallbackMessage));
};

const isMissingStoreEmailColumnError = (error: any): boolean => {
  const message = String(error?.message || error?.details || error?.hint || '').toLowerCase();
  return (
    error?.code === 'PGRST204' &&
    (
      message.includes("'email'") ||
      message.includes('"email"') ||
      message.includes('email')
    )
  );
};

const normalizeStorePayload = (store: Partial<Store>): Record<string, any> => {
  const { id, created_at, ...storeData } = store as any;
  if ('email' in storeData) {
    const email = String(storeData.email || '').trim().toLowerCase();
    storeData.email = email || null;
  }
  return storeData;
};

const toStorePersistenceError = (error: any): Error => {
  if (isMissingStoreEmailColumnError(error)) {
    return new Error("La base de datos no está actualizada: ejecute el script '20260511_add_local_email.sql'.");
  }
  return error instanceof Error ? error : new Error(normalizeErrorMessage(error, 'Error guardando local'));
};

export const ApiService = {
  // --- MÉTODOS DE IMPORTACIÓN AUTOMATIZADA ---
  async getImportConfigs(mallId?: string): Promise<ImportConfig[]> {
    if (!supabase) return [];

    // Fetch only locals with configured SFTP host
    let query = supabase
      .from('locales')
      .select('*')
      .not('sftp_host', 'is', null)
      .neq('sftp_host', ''); // Also exclude empty strings

    if (mallId) {
      query = query.eq('mall_id', mallId);
    }

    const { data, error } = await query;

    if (error) {
      console.error("Error fetching configs:", error);
      return [];
    }

    return (data || []).map((local: any) => ({
      id: local.id,
      nombre: local.nombre,
      protocolo: (local.sftp_protocol || 'SFTP') as ImportProtocol,
      host: local.sftp_host || '',
      puerto: local.sftp_port || 22,
      usuario: local.sftp_user || '',
      password: local.sftp_pass || '',
      ruta_remota: local.sftp_path || '.',
      tipo_archivo: (local.file_type || 'CSV') as FileType,
      frecuencia: (local.frecuencia_cron || 'manual') as ImportFrequency,
      hora_especifica: local.hora_especifica || '',
      estado: 'activo',
      accion_post_procesado: (local.accion_post_procesado === 'RENOMBRAR_BACKUP' || local.accion_post_procesado === 'RENOMBRAR_PROCESADO') ? 'RENOMBRAR_PROCESADO' : (local.accion_post_procesado === 'ELIMINAR' ? 'ELIMINAR' : 'NINGUNA'),
      prefijo_renombrado: local.prefijo_backup || 'PR_',
      mapping: local.mapping_config || {},
      constants: local.constants_config || {},
      fecha_corte_importacion: local.fecha_corte_importacion || null,
      tipo_ejecucion: local.tipo_ejecucion || 'MANUAL',
      ultima_ejecucion: local.ultima_ejecucion,
      resultado_ultimo: local.resultado_ultimo
    }));
  },

  async saveImportConfig(config: ImportConfig, mallId?: string): Promise<void> {
    if (!supabase) throw new Error("Supabase client not initialized");

    if (!config.id && !mallId) {
      throw new Error("No se puede crear la configuración sin un mall seleccionado.");
    }

    const dbPayload: any = {
      nombre: config.nombre, // Ensure name is saved if it's new
      sftp_host: config.host,
      sftp_port: config.puerto,
      sftp_user: config.usuario,
      sftp_pass: config.password,
      sftp_protocol: config.protocolo,
      sftp_path: config.ruta_remota,
      file_type: config.tipo_archivo,
      tipo_ejecucion: config.frecuencia !== 'manual' ? 'AUTOMATICO' : 'MANUAL',
      frecuencia_cron: config.frecuencia,
      hora_especifica: config.hora_especifica || null,
      accion_post_procesado: (config.accion_post_procesado === 'RENOMBRAR_PROCESADO' || config.accion_post_procesado === 'renombrar') ? 'RENOMBRAR_BACKUP' : (config.accion_post_procesado === 'ELIMINAR' || config.accion_post_procesado === 'eliminar' ? 'ELIMINAR' : 'NINGUNA'),
      prefijo_backup: config.prefijo_renombrado || 'PR_',
      mapping_config: config.mapping,
      constants_config: config.constants,
      fecha_corte_importacion: config.fecha_corte_importacion || null
    };

    if (mallId) {
      dbPayload.mall_id = mallId;
    }

    // Logic to always ensure codigo_interno is present and valid
    let finalCodigoInterno = `IMP-${Math.floor(Math.random() * 100000)}`;

    if (config.id) {
      const { data: existing } = await supabase
        .from('locales')
        .select('id, codigo_interno')
        .eq('id', config.id)
        .maybeSingle();

      if (existing && existing.codigo_interno) {
        finalCodigoInterno = existing.codigo_interno;
      }
    }

    // Always set the code
    dbPayload.codigo_interno = finalCodigoInterno;

    // Payload for Upsert
    const payload = config.id ? { id: config.id, ...dbPayload } : dbPayload;

    const { error } = await supabase
      .from('locales')
      .upsert(payload)
      .select();

    if (error) {
      console.error("Error saving config to Supabase:", error);
      if (error.code === 'PGRST204' && (error.message.includes('hora_especifica') || error.details?.includes('hora_especifica') || error.hint?.includes('hora_especifica'))) {
        throw new Error("La base de datos no está actualizada: Falta la columna 'hora_especifica' en la tabla 'locales'. Por favor ejecute el script SQL provisto.");
      }
      throw error;
    }
  },

  async deleteImportConfig(id: string): Promise<void> {
    if (!supabase) return;

    // Soft delete configuration by clearing fields
    const { error } = await supabase
      .from('locales')
      .update({
        sftp_host: null,
        tipo_ejecucion: 'MANUAL',
        frecuencia_cron: null
      })
      .eq('id', id);

    if (error) {
      console.error("Error deleting config:", error);
      throw error;
    }
  },

  async getRemoteConnections(mallId: string, token?: string): Promise<RemoteConnection[]> {
    if (!mallId) return [];
    const data = await fetchJsonWithBaseFallback<any[]>(
      `/remote-connections?mall_id=${encodeURIComponent(mallId)}`,
      {
        method: 'GET',
        headers: withAuthHeaders(token, { 'Accept': 'application/json' })
      },
      "No se pudieron cargar las conexiones guardadas."
    );

    return (data || []).map((row: any) => ({
      id: row.id,
      mall_id: row.mall_id,
      nombre: row.nombre,
      protocolo: (row.protocolo || 'SFTP') as ImportProtocol,
      host: row.host || '',
      puerto: Number(row.puerto || 22),
      usuario: row.usuario || '',
      password: '', // Nunca exponer secretos desde backend.
      password_masked: row.password_masked || '',
      has_password: Boolean(row.has_password),
      ruta_base: row.ruta_base || '',
      created_at: row.created_at
    }));
  },

  async saveRemoteConnection(
    payload: Omit<RemoteConnection, 'id' | 'created_at'> & { id?: string },
    token?: string
  ): Promise<RemoteConnection> {
    if (!payload.mall_id) throw new Error("mall_id es requerido.");

    const requestPayload: any = {
      mall_id: payload.mall_id,
      nombre: payload.nombre,
      protocolo: payload.protocolo,
      host: payload.host,
      puerto: payload.puerto,
      usuario: payload.usuario,
      password: payload.password || undefined,
      ruta_base: payload.ruta_base || null
    };

    const isUpdate = Boolean(payload.id);
    const data = await fetchJsonWithBaseFallback<any>(
      isUpdate ? `/remote-connections/${encodeURIComponent(payload.id as string)}` : '/remote-connections',
      {
        method: isUpdate ? 'PATCH' : 'POST',
        headers: withAuthHeaders(token, {
          'Content-Type': 'application/json',
          'Accept': 'application/json'
        }),
        body: JSON.stringify(requestPayload)
      },
      "No se pudo guardar la conexión remota."
    );

    return {
      id: data.id,
      mall_id: data.mall_id,
      nombre: data.nombre,
      protocolo: (data.protocolo || 'SFTP') as ImportProtocol,
      host: data.host || '',
      puerto: Number(data.puerto || 22),
      usuario: data.usuario || '',
      password: '',
      password_masked: data.password_masked || '',
      has_password: Boolean(data.has_password),
      ruta_base: data.ruta_base || '',
      created_at: data.created_at
    };
  },

  async deleteRemoteConnection(id: string, token?: string): Promise<void> {
    if (!id) return;
    await fetchJsonWithBaseFallback<{ status: string }>(
      `/remote-connections/${encodeURIComponent(id)}`,
      {
        method: 'DELETE',
        headers: withAuthHeaders(token, { 'Accept': 'application/json' })
      },
      "No se pudo eliminar la conexión remota."
    );
  },

  async syncImportConnection(id: string): Promise<{ success: boolean, processed: number, message: string }> {
    // Simulación de latencia de red y procesamiento
    await new Promise(resolve => setTimeout(resolve, 2500));

    const configs = await this.getImportConfigs();
    const config = configs.find(c => c.id === id);

    if (!config) throw new Error("Configuración no encontrada");

    // Simulamos un éxito del 90%
    const isSuccess = Math.random() > 0.1;
    const processed = isSuccess ? Math.floor(Math.random() * 50) + 10 : 0;

    const updatedConfigs = configs.map(c => c.id === id ? {
      ...c,
      ultima_ejecucion: new Date().toLocaleString(),
      resultado_ultimo: isSuccess ? 'exito' : 'error' as any
    } : c);

    localStorage.setItem(IMPORTS_STORAGE_KEY, JSON.stringify(updatedConfigs));

    return {
      success: isSuccess,
      processed,
      message: isSuccess
        ? `Sincronización exitosa: ${processed} archivos procesados aplicando el mapeo.`
        : "Error de conexión: El servidor remoto rechazó la clave SSH o el directorio no existe."
    };
  },

  async testConnection(config: Partial<ImportConfig>, password?: string, token?: string): Promise<{ success: boolean, message: string }> {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => {
      console.warn("ApiService: Disparando abort por timeout de 60s");
      controller.abort();
    }, 60000);

    console.log("ApiService: Iniciando POST /remote/test...");
    try {
      const response = await fetch(`${BASE_URL}/remote/test`, {
        method: 'POST',
        headers: withAuthHeaders(token, { 'Content-Type': 'application/json' }),
        body: JSON.stringify({
          protocolo: config.protocolo,
          host: config.host?.trim(),
          puerto: Number(config.puerto) || (config.protocolo === 'SFTP' ? 22 : 21),
          usuario: config.usuario?.trim(),
          password: password,
          ruta: config.ruta_remota || '.'
        }),
        signal: controller.signal
      });
      clearTimeout(timeoutId);
      console.log("ApiService: Respuesta recibida, status:", response.status);

      const data = await response.json().catch(() => ({ detail: "Error de servidor" }));

      if (!response.ok) {
        throw new Error(data.detail || "Error al probar la conexión");
      }

      return {
        success: data.status === 'success',
        message: data.message || "Conexión exitosa"
      };
    } catch (error: any) {
      clearTimeout(timeoutId);
      console.error("ApiService: Error en testConnection:", error);
      const isTimeout = error.name === 'AbortError' || error.message?.includes('aborted');
      return {
        success: false,
        message: isTimeout ? "Error: Tiempo de espera agotado (Timeout)" : (error.message || String(error))
      };
    }
  },

  async exploreDirectory(path: string, protocol?: string, host?: string, port?: number, user?: string, password?: string, token?: string): Promise<{ ruta_actual: string, items: { nombre: string, ruta: string, es_dir: boolean }[] }> {
    try {
      let response;
      if (protocol && protocol !== 'LOCAL') {
        response = await fetch(`${BASE_URL}/remote/list`, {
          method: 'POST',
          headers: withAuthHeaders(token, { 'Content-Type': 'application/json' }),
          body: JSON.stringify({
            protocolo: protocol,
            host: host?.trim(),
            puerto: Number(port),
            usuario: user?.trim(),
            password: password,
            ruta: path
          })
        });
      } else {
        response = await fetch(`${BASE_URL}/explorar-directorio?ruta=${encodeURIComponent(path)}`, {
          headers: withAuthHeaders(token)
        });
      }

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: "Error desconocido" }));
        throw new Error(errorData.detail || "Error al listar directorio");
      }
      return await response.json();
    } catch (error: any) {
      console.error("Explore directory error:", error);
      throw new Error(normalizeErrorMessage(error, "Error al listar directorio"));
    }
  },

  async readRemoteHeaders(config: ImportConfig, password?: string, token?: string): Promise<string[]> {
    try {
      const response = await fetch(`${BASE_URL}/remote/headers`, {
        method: 'POST',
        headers: withAuthHeaders(token, { 'Content-Type': 'application/json' }),
        body: JSON.stringify({
          protocolo: config.protocolo,
          host: config.host?.trim(),
          puerto: Number(config.puerto),
          usuario: config.usuario?.trim(),
          password: password || config.password,
          ruta: config.ruta_remota,
          tipo_archivo: config.tipo_archivo
        })
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: "Error desconocido" }));
        throw new Error(errorData.detail || "Error al leer headers remotos");
      }
      const data = await response.json();
      return data.headers;
    } catch (error: any) {
      console.error("Read remote headers error:", error);
      throw new Error(normalizeErrorMessage(error, "Error al leer headers remotos"));
    }
  },

  async analyzeRemoteMapping(config: Partial<ImportConfig>, password?: string, testFile?: string, token?: string): Promise<any> {
    try {
      const constants = config.constants || {};
      const rawHasHeader = constants['_has_header'];
      const hasHeader =
        rawHasHeader === 'true' ? true :
          rawHasHeader === 'false' ? false :
            undefined;
      const startRowRaw = constants['_data_start_row'];
      const parsedStartRow = Number(startRowRaw);
      const dataStartRow = Number.isFinite(parsedStartRow) && parsedStartRow > 0
        ? Math.trunc(parsedStartRow)
        : undefined;

      const response = await fetch(`${BASE_URL}/mapping/analyze-remote`, {
        method: 'POST',
        headers: withAuthHeaders(token, { 'Content-Type': 'application/json' }),
        body: JSON.stringify({
          protocolo: config.protocolo,
          host: config.host?.trim(),
          puerto: Number(config.puerto),
          usuario: config.usuario?.trim(),
          password: password || config.password,
          ruta: testFile || config.ruta_remota,
          tipo_archivo: config.tipo_archivo,
          has_header: hasHeader,
          data_start_row: dataStartRow
        })
      });
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: "Error analizando mapeo" }));
        throw new Error(errorData.detail || "Error analizando mapeo");
      }
      return await response.json();
    } catch (error: any) {
      console.error(error);
      throw new Error(normalizeErrorMessage(error, "Error analizando archivo remoto"));
    }
  },

  async listRemoteFiles(config: ImportConfig, token?: string): Promise<{ nombre: string, fecha: string, tamano: number }[]> {
    try {
      const response = await fetch(`${BASE_URL}/remote/list-files`, {
        method: 'POST',
        headers: withAuthHeaders(token, { 'Content-Type': 'application/json' }),
        body: JSON.stringify(config)
      });
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: "Error listando archivos" }));
        throw new Error(errorData.detail || "Error listando archivos");
      }
      return await response.json();
    } catch (error: any) {
      console.error(error);
      throw error.message || error;
    }
  },

  async analyzeSingleFile(
    config: ImportConfig,
    filename: string,
    token?: string,
    options?: { timeoutMs?: number; largeFile?: boolean }
  ): Promise<{
    csv_headers: string[],
    suggested_mapping: Record<string, any>,
    sample_row: Record<string, any>,
    current_mapping: Record<string, string>,
    raw_preview_lines?: string[],
    analysis_type?: string,
    detected_delimiter?: string | null,
    detected_has_header?: boolean | null
  }> {
    const payload = {
      config_id: config.id || '',
      filename,
      config
    };
    const timeoutMs = getRemoteOperationTimeoutMs(filename, {
      timeoutMs: options?.timeoutMs,
      largeFile: options?.largeFile,
      operation: 'analysis'
    });

    const maxAttempts = 2;
    let lastError: any = null;

    for (let attempt = 1; attempt <= maxAttempts; attempt++) {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

      try {
        const response = await fetch(`${BASE_URL}/remote/analyze-file`, {
          method: 'POST',
          headers: withAuthHeaders(token, { 'Content-Type': 'application/json' }),
          body: JSON.stringify(payload),
          signal: controller.signal
        });

        clearTimeout(timeoutId);

        if (!response.ok) {
          const errorData = await response.json().catch(() => ({ detail: "Error analizando archivo" }));
          throw new Error(errorData.detail || "Error analizando archivo");
        }

        return await response.json();
      } catch (error: any) {
        clearTimeout(timeoutId);
        lastError = error;
        console.error(`Error in analyzeSingleFile (attempt ${attempt}/${maxAttempts}):`, error);

        const msg = normalizeErrorMessage(error, "Error analizando archivo");
        const isTimeout = error?.name === 'AbortError' || msg.toLowerCase().includes('aborted');
        const isNetworkFailure = msg.includes('Failed to fetch') || msg.includes('ERR_NETWORK_CHANGED');

        if (attempt < maxAttempts && isNetworkFailure) {
          await new Promise(resolve => setTimeout(resolve, 1200 * attempt));
          continue;
        }

        if (isTimeout) {
          throw new Error("Timeout analizando archivo remoto. Para archivos grandes la primera carga puede tardar varios minutos.");
        }
        if (isNetworkFailure) {
          throw new Error("No se pudo contactar el servicio de análisis remoto (Failed to fetch). Verifica red/VPN e intenta de nuevo.");
        }
        throw new Error(msg || "Error analizando archivo");
      }
    }

    throw new Error(normalizeErrorMessage(lastError, "Error analizando archivo"));
  },

  async executeManualImport(
    config: ImportConfig,
    filename: string,
    token?: string,
    options?: { timeoutMs?: number; largeFile?: boolean }
  ): Promise<{ status: string, message: string, errors?: any[], records_processed?: number }> {
    const requestId = (typeof crypto !== 'undefined' && 'randomUUID' in crypto)
      ? crypto.randomUUID()
      : `req-${Date.now()}-${Math.floor(Math.random() * 100000)}`;

    const payload = {
      config_id: config.id,
      filename,
      config,
      request_id: requestId
    };

    const baseUrls = getExecuteManualBaseUrls();
    let lastError: any = null;
    const timeoutMs = getRemoteOperationTimeoutMs(filename, {
      timeoutMs: options?.timeoutMs,
      largeFile: options?.largeFile,
      operation: 'execute'
    });

    for (let i = 0; i < baseUrls.length; i++) {
      const baseUrl = baseUrls[i];
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

      try {
        const response = await fetch(`${baseUrl}/remote/execute-manual`, {
          method: 'POST',
          headers: withAuthHeaders(token, { 'Content-Type': 'application/json' }),
          body: JSON.stringify(payload),
          signal: controller.signal
        });
        clearTimeout(timeoutId);

        if (!response.ok) {
          const serverDetail = await parseErrorDetail(response, "Error ejecutando importación");

          // If proxy route fails with 5xx, try direct backend (if available).
          if (response.status >= 500 && i < baseUrls.length - 1) {
            console.warn(`executeManualImport: ${baseUrl} respondió ${response.status}. Intentando fallback...`);
            continue;
          }
          throw new Error(serverDetail);
        }

        return await response.json();
      } catch (error: any) {
        clearTimeout(timeoutId);
        lastError = error;
        const msg = String(error?.message || error || '');
        const isTimeout = error?.name === 'AbortError' || msg.toLowerCase().includes('aborted');
        const isNetworkFailure = isNetworkFetchFailure(error);

        // On network/proxy failure, attempt direct backend as fallback.
        if ((isNetworkFailure || isTimeout) && i < baseUrls.length - 1) {
          console.warn(`executeManualImport: fallo en ${baseUrl} (${msg}). Intentando fallback...`);
          continue;
        }

        if (isTimeout) {
          throw new Error("Timeout ejecutando importación remota. Para archivos grandes la primera carga puede tardar varios minutos.");
        }
        if (isNetworkFailure) {
          throw new Error("No se pudo confirmar la importación por cambio de red (ERR_NETWORK_CHANGED). Revisa conexión/VPN e intenta de nuevo.");
        }
        throw new Error(msg || "Error ejecutando importación");
      }
    }

    throw new Error(lastError?.message || "Error ejecutando importación");
  },

  async unmarkFile(config: ImportConfig, filename: string, token?: string): Promise<{ status: string, message: string, old_name?: string, new_name?: string }> {
    try {
      const response = await fetch(`${BASE_URL}/remote/unmark-file`, {
        method: 'POST',
        headers: withAuthHeaders(token, { 'Content-Type': 'application/json' }),
        body: JSON.stringify({
          config_id: config.id,
          filename,
          config
        })
      });
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: "Error desmarcando archivo" }));
        throw new Error(errorData.detail || "Error desmarcando archivo");
      }
      return await response.json();
    } catch (error: any) {
      console.error(error);
      throw error.message || error;
    }
  },

  // --- MÉTODOS DE AUDITORÍA DE CARGA ---
  async getLoadLogs(mallId?: string, token?: string): Promise<LoadLogEntry[]> {
    try {
      const query = new URLSearchParams();
      if (mallId) query.set('mall_id', mallId);
      const suffix = query.toString() ? `?${query.toString()}` : '';
      const headers: Record<string, string> = { 'Accept': 'application/json' };
      if (mallId) headers['X-Mall-Id'] = mallId;
      const rows = await fetchJsonWithBaseFallback<any[]>(
        `/load-logs${suffix}`,
        {
          method: 'GET',
          headers: withAuthHeaders(token, headers)
        },
        'Error cargando historial de cargas'
      );
      return Array.isArray(rows) ? rows.map(normalizeLoadLogRow) : [];
    } catch (error) {
      console.error('Error fetching load logs:', error);
      return [];
    }
  },



  async reactivateStore(id: string, token?: string) {
    await fetchJsonWithBaseFallback<{ status: string; message: string }>(
      `/locales/${encodeURIComponent(id)}/reactivate-processing`,
      {
        method: 'POST',
        headers: withAuthHeaders(token, { 'Accept': 'application/json' })
      },
      'No se pudo reactivar el local'
    );
    return true;
  },

  async logLoad(log: any): Promise<void> {
    if (!supabase) return;
    try {
      const { error } = await supabase
        .from('logs_carga')
        .insert([log]);
      if (error) {
        console.error('Supabase Error details:', error);
        throw error;
      }
    } catch (error) {
      console.error('Error creating load log:', error);
    }
  },

  async clearLoadLogs(mallId: string, token?: string): Promise<{ status: string; message: string; deleted_count?: number }> {
    if (!mallId) {
      throw new Error("mall_id es requerido para limpiar historial.");
    }

    return fetchJsonWithBaseFallback<{ status: string; message: string; deleted_count?: number }>(
      `/load-logs?mall_id=${encodeURIComponent(mallId)}`,
      {
        method: 'DELETE',
        headers: withAuthHeaders(token, {
          'Accept': 'application/json',
          'X-Mall-Id': mallId
        })
      },
      "Error limpiando historial de cargas"
    );
  },

  // --- CONNECTION MONITOR / RETRY (PR-5) ---
  async getConnectionsStatus(mallId: string, token?: string): Promise<ConnectionMonitorStatusResponse> {
    if (!mallId) throw new Error("mall_id es requerido.");
    return fetchJsonWithBaseFallback<ConnectionMonitorStatusResponse>(
      `/connections/status?mall_id=${encodeURIComponent(mallId)}`,
      {
        method: 'GET',
        headers: withAuthHeaders(token, { 'Accept': 'application/json' })
      },
      "No se pudo obtener el estado de conexiones"
    );
  },

  async getConnectionFailures(mallId: string, date: string, token?: string): Promise<ConnectionMonitorFailuresResponse> {
    if (!mallId) throw new Error("mall_id es requerido.");
    if (!date) throw new Error("date es requerido.");
    return fetchJsonWithBaseFallback<ConnectionMonitorFailuresResponse>(
      `/connections/failures?mall_id=${encodeURIComponent(mallId)}&date=${encodeURIComponent(date)}`,
      {
        method: 'GET',
        headers: withAuthHeaders(token, { 'Accept': 'application/json' })
      },
      "No se pudieron cargar las fallas de conexiones"
    );
  },

  async retryConnection(connectionId: string, token?: string): Promise<ConnectionRetryActionResponse> {
    if (!connectionId) throw new Error("connectionId es requerido.");
    return fetchJsonWithBaseFallback<ConnectionRetryActionResponse>(
      `/connections/${encodeURIComponent(connectionId)}/retry`,
      {
        method: 'POST',
        headers: withAuthHeaders(token, { 'Accept': 'application/json' })
      },
      "No se pudo ejecutar el reintento de conexión"
    );
  },

  async retryFailedConnections(mallId: string, date: string, token?: string): Promise<ConnectionRetryBatchResponse> {
    if (!mallId) throw new Error("mall_id es requerido.");
    if (!date) throw new Error("date es requerido.");
    return fetchJsonWithBaseFallback<ConnectionRetryBatchResponse>(
      `/connections/retry-failed?mall_id=${encodeURIComponent(mallId)}&date=${encodeURIComponent(date)}`,
      {
        method: 'POST',
        headers: withAuthHeaders(token, { 'Accept': 'application/json' })
      },
      "No se pudieron ejecutar los reintentos en lote"
    );
  },

  // --- OTROS MÉTODOS ---
  async getSalesReport(dates: DateRange & { mallId?: string }, localId?: string): Promise<SaleReport[]> {
    if (!supabase) return [];

    try {
      let allSales: any[] = [];
      let page = 0;
      const pageSize = 1000;

      while (true) {
        let query = supabase
          .from('ventas')
          .select('*')
          .gte('fecha', dates.startDate)
          .lte('fecha', dates.endDate);

        if (dates.mallId) {
          query = query.eq('mall_id', dates.mallId);
        }

        if (localId) {
          query = query.eq('local_id', localId);
        }

        const { data: salesChunk, error } = await query.range(page * pageSize, (page + 1) * pageSize - 1);

        if (error) throw error;

        if (salesChunk) {
          allSales = [...allSales, ...salesChunk];
          if (salesChunk.length < pageSize) break; // Fin de datos
        } else {
          break;
        }
        page++;
      }

      const sales = allSales;

      const stores = await this.getStores();
      const storeMap = new Map(stores.map(s => [s.id, s]));

      const reportMap: Record<string, SaleReport> = {};

      sales?.forEach((sale: any) => {
        if (!sale.local_id) return;
        const localId = String(sale.local_id);
        const store = storeMap.get(localId) as Store | undefined;
        const storeName = store?.nombre || 'Desconocido';
        const mallName = store?.mall_nombre || 'Mall Principal';
        const totals = normalizeSaleTotals(sale);

        if (!reportMap[localId]) {
          reportMap[localId] = {
            local_id: localId,
            local_nombre: storeName,
            total_bruto: 0,
            total_impuestos: 0,
            total_neto: 0,
            mall_nombre: mallName
          };
        }

        reportMap[localId].total_bruto += totals.total_bruto;
        reportMap[localId].total_impuestos += totals.total_impuestos;
        reportMap[localId].total_neto += totals.total_neto;
      });

      return Object.values(reportMap);
    } catch (error) {
      console.error('Error getting sales report:', error);
      return [];
    }
  },

  async getSaleDetails(localId: string, dates: DateRange & { mallId?: string }): Promise<SaleDetail[]> {
    if (!supabase) return [];
    if (!localId || localId === 'null') return [];

    try {
      const { data, error } = await supabase
        .from('ventas')
        .select('*')
        .eq('local_id', localId)
        .gte('fecha', dates.startDate)
        .lte('fecha', dates.endDate)
        .order('fecha', { ascending: false })
        .order('hora', { ascending: false });

      if (error) throw error;
      return ((data as SaleDetail[]) || []).map((row) => ({
        ...row,
        ...normalizeSaleTotals(row)
      }));
    } catch (error) {
      console.error('Error getting sale details:', error);
      return [];
    }
  },


  async getKPIs(dates: DateRange & { mallId?: string }, token: string): Promise<KPIData> {
    try {
      // Call Backend API to assume Service Role access (Bypassing RLS)
      const params = new URLSearchParams({
        start_date: dates.startDate,
        end_date: dates.endDate
      });

      const headers: any = {
        'Authorization': `Bearer ${token}`
      };
      if (dates.mallId) {
        headers['X-Mall-Id'] = dates.mallId;
      }

      const response = await fetch(`${BASE_URL}/analytics/dashboard?${params.toString()}`, { headers });
      if (!response.ok) {
        throw new Error(`Failed to fetch dashboard data: ${response.statusText}`);
      }

      const data = await response.json();
      return data as KPIData;

    } catch (error) {
      console.error("Error fetching KPIs from backend:", error);
      // Return empty structure on error
      return {
        ventas_totales_bruto: 0,
        ventas_totales_neto: 0,
        transacciones: 0,
        ticket_promedio: 0,
        variacion_ventas: 0,
        top_locales: [],
        ventas_por_dia: [],
        ventas_por_tipo_negocio: [],
        ventas_por_rubro: [],
        ventas_por_tipo_negocio_top_locales: {},
        ventas_por_rubro_top_locales: {},
        ventas_por_tienda_completo: {}
      };
    }
  },

  async getStores(mallId?: string): Promise<Store[]> {
    if (!supabase) return [];

    try {
      let query = supabase.from('locales').select('*');

      if (mallId) {
        query = query.eq('mall_id', mallId);
      }

      const { data, error } = await query;

      if (error) throw error;
      return data as Store[];
    } catch (error) {
      console.error('Error fetching stores:', error);
      return [];
    }
  },

  async getStoreCatalogOptions(mallId: string): Promise<StoreCatalogOptionsResult> {
    if (!supabase) return { options: [], available: false };

    try {
      const { data, error } = await supabase
        .from(STORE_CATALOG_TABLE)
        .select('*')
        .eq('mall_id', mallId)
        .order('field_name', { ascending: true })
        .order('sort_order', { ascending: true })
        .order('value', { ascending: true });

      if (error) {
        if (isMissingStoreCatalogTableError(error)) {
          return { options: [], available: false };
        }
        throw error;
      }

      return {
        options: (data as StoreCatalogOption[]) || [],
        available: true,
      };
    } catch (error) {
      console.error('Error fetching store catalog options:', error);
      throw toStoreCatalogError(error, 'Error cargando catálogos de locales');
    }
  },

  async seedStoreCatalogDefaults(mallId: string): Promise<StoreCatalogOption[]> {
    if (!supabase) throw new Error("Supabase no está configurado");

    const rows = (Object.entries(DEFAULT_STORE_CATALOG_VALUES) as Array<[StoreCatalogFieldName, string[]]>)
      .flatMap(([fieldName, values]) =>
        values.map((value, index) => ({
          mall_id: mallId,
          field_name: fieldName,
          value,
          sort_order: index + 1,
        }))
      );

    try {
      const { data, error } = await supabase
        .from(STORE_CATALOG_TABLE)
        .upsert(rows, { onConflict: 'mall_id,field_name,value_key' })
        .select('*');

      if (error) throw error;
      return (data as StoreCatalogOption[]) || [];
    } catch (error) {
      console.error('Error seeding store catalog defaults:', error);
      throw toStoreCatalogError(error, 'Error cargando valores por defecto del catálogo');
    }
  },

  async createStoreCatalogOption(option: {
    mall_id: string;
    field_name: StoreCatalogFieldName;
    value: string;
    sort_order?: number | null;
  }): Promise<StoreCatalogOption> {
    if (!supabase) throw new Error("Supabase no está configurado");

    const value = normalizeCatalogText(option.value);
    if (!value) {
      throw new Error('El valor no puede estar vacío.');
    }

    try {
      const { data, error } = await supabase
        .from(STORE_CATALOG_TABLE)
        .insert([{
          ...option,
          value,
        }])
        .select()
        .single();

      if (error) throw error;
      return data as StoreCatalogOption;
    } catch (error) {
      console.error('Error creating store catalog option:', error);
      throw toStoreCatalogError(error, 'Error creando valor del catálogo');
    }
  },

  async updateStoreCatalogOption(
    id: string,
    updates: Partial<Pick<StoreCatalogOption, 'value' | 'sort_order'>>
  ): Promise<StoreCatalogOption> {
    if (!supabase) throw new Error("Supabase no está configurado");

    const payload: Record<string, any> = { ...updates };
    if (payload.value !== undefined) {
      payload.value = normalizeCatalogText(payload.value);
      if (!payload.value) {
        throw new Error('El valor no puede estar vacío.');
      }
    }

    try {
      const { data, error } = await supabase
        .from(STORE_CATALOG_TABLE)
        .update(payload)
        .eq('id', id)
        .select()
        .single();

      if (error) throw error;
      return data as StoreCatalogOption;
    } catch (error) {
      console.error('Error updating store catalog option:', error);
      throw toStoreCatalogError(error, 'Error actualizando valor del catálogo');
    }
  },

  async deleteStoreCatalogOption(id: string): Promise<void> {
    if (!supabase) throw new Error("Supabase no está configurado");

    try {
      const { error } = await supabase
        .from(STORE_CATALOG_TABLE)
        .delete()
        .eq('id', id);

      if (error) throw error;
    } catch (error) {
      console.error('Error deleting store catalog option:', error);
      throw toStoreCatalogError(error, 'Error eliminando valor del catálogo');
    }
  },

  async bulkReplaceStoreFieldValue(
    mallId: string,
    fieldName: StoreCatalogFieldName,
    previousValue: string,
    nextValue: string
  ): Promise<void> {
    if (!supabase) throw new Error("Supabase no está configurado");

    const cleanPreviousValue = normalizeCatalogText(previousValue);
    const cleanNextValue = normalizeCatalogText(nextValue);
    if (!cleanPreviousValue || !cleanNextValue || cleanPreviousValue === cleanNextValue) {
      return;
    }

    try {
      const { error } = await supabase
        .from('locales')
        .update({ [fieldName]: cleanNextValue } as any)
        .eq('mall_id', mallId)
        .eq(fieldName, cleanPreviousValue);

      if (error) throw error;
    } catch (error) {
      console.error(`Error replacing store field value for ${fieldName}:`, error);
      throw error instanceof Error ? error : new Error('Error actualizando locales asociados');
    }
  },

  async createStore(store: Partial<Store>, token?: string): Promise<Store> {
    const storeData = normalizeStorePayload(store);
    if (token) {
      return fetchJsonWithBaseFallback<Store>(
        '/locales',
        {
          method: 'POST',
          headers: withAuthHeaders(token, {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
          }),
          body: JSON.stringify(storeData),
        },
        'Error creando local'
      );
    }
    if (!supabase) throw new Error("Supabase no está configurado");

    try {
      const { data, error } = await supabase
        .from('locales')
        .insert([storeData])
        .select()
        .single();

      if (error) throw error;
      return data as Store;
    } catch (error) {
      console.error('Error creating store:', error);
      throw toStorePersistenceError(error);
    }
  },

  async updateStore(id: string, store: Partial<Store>, token?: string): Promise<Store> {
    const storeData = normalizeStorePayload(store);
    if (token) {
      return fetchJsonWithBaseFallback<Store>(
        `/locales/${encodeURIComponent(id)}`,
        {
          method: 'PATCH',
          headers: withAuthHeaders(token, {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
          }),
          body: JSON.stringify(storeData),
        },
        'Error actualizando local'
      );
    }
    if (!supabase) throw new Error("Supabase no está configurado");
    try {
      const { data, error } = await supabase
        .from('locales')
        .update(storeData)
        .eq('id', id)
        .select()
        .single();
      if (error) throw error;
      return data as Store;
    } catch (error) {
      console.error('Error updating store:', error);
      throw toStorePersistenceError(error);
    }
  },

  async deleteStore(id: string, token?: string): Promise<void> {
    if (token) {
      await fetchJsonWithBaseFallback<{ status: string }>(
        `/locales/${encodeURIComponent(id)}`,
        {
          method: 'DELETE',
          headers: withAuthHeaders(token, { 'Accept': 'application/json' }),
        },
        'Error eliminando local'
      );
      return;
    }
    if (!supabase) throw new Error("Supabase no está configurado");
    console.log('[DEBUG] DeleteStore called for ID:', id);

    try {
      const { error, count } = await supabase
        .from('locales')
        .delete({ count: 'exact' })
        .eq('id', id);

      console.log(`[DEBUG] Delete result: Error=${error?.message}, Count=${count}`);

      if (error) {
        if (error.code === '23503') {
          throw new Error("No se puede eliminar este local porque tiene registros asociados (Ventas o Configuraciones).");
        }
        throw error;
      }

      if (count === 0) {
        throw new Error("Local no encontrado o sin permisos para eliminar.");
      }
    } catch (error: any) {
      console.error('Error deleting store:', error);
      throw error.message || error;
    }
  },

  async getLocalCustomFieldDefinitions(mallId: string, token?: string, includeInactive = true): Promise<LocalCustomFieldDefinition[]> {
    return fetchJsonWithBaseFallback<LocalCustomFieldDefinition[]>(
      `/locales/custom-fields?mall_id=${encodeURIComponent(mallId)}&include_inactive=${includeInactive ? 'true' : 'false'}`,
      { headers: withAuthHeaders(token) },
      'Error obteniendo campos libres.'
    );
  },

  async createLocalCustomFieldDefinition(
    payload: Partial<LocalCustomFieldDefinition>,
    token?: string
  ): Promise<LocalCustomFieldDefinition> {
    return fetchJsonWithBaseFallback<LocalCustomFieldDefinition>(
      '/locales/custom-fields',
      {
        method: 'POST',
        headers: withAuthHeaders(token, { 'Content-Type': 'application/json' }),
        body: JSON.stringify(payload),
      },
      'Error creando campo libre.'
    );
  },

  async updateLocalCustomFieldDefinition(
    fieldId: string,
    payload: Partial<LocalCustomFieldDefinition>,
    token?: string
  ): Promise<LocalCustomFieldDefinition> {
    return fetchJsonWithBaseFallback<LocalCustomFieldDefinition>(
      `/locales/custom-fields/${fieldId}`,
      {
        method: 'PATCH',
        headers: withAuthHeaders(token, { 'Content-Type': 'application/json' }),
        body: JSON.stringify(payload),
      },
      'Error actualizando campo libre.'
    );
  },

  async getStoreCustomFields(localId: string, token?: string, includeInactive = false): Promise<LocalCustomFieldBundle> {
    return fetchJsonWithBaseFallback<LocalCustomFieldBundle>(
      `/locales/${localId}/custom-fields?include_inactive=${includeInactive ? 'true' : 'false'}`,
      { headers: withAuthHeaders(token) },
      'Error obteniendo valores de campos libres.'
    );
  },

  async saveStoreCustomFields(localId: string, values: LocalCustomFieldValue[], token?: string): Promise<LocalCustomFieldBundle> {
    return fetchJsonWithBaseFallback<LocalCustomFieldBundle>(
      `/locales/${localId}/custom-fields`,
      {
        method: 'PUT',
        headers: withAuthHeaders(token, { 'Content-Type': 'application/json' }),
        body: JSON.stringify({ values }),
      },
      'Error guardando campos libres.'
    );
  },

  async ingestSales(
    file: File,
    apiKey: string,
    mallId: string,
    onProgress?: (progress: number) => void,
    dateFormatPreference: CsvDateFormatPreference = 'auto'
  ): Promise<IngestionResponse> {
    if (!supabase) {
      return { status: 'error', message: 'Supabase no está configurado', records_processed: 0 };
    }

    if (!mallId) {
      return { status: 'error', message: 'Debe seleccionar un mall antes de importar.', records_processed: 0 };
    }

    const stores = await this.getStores(mallId);
    // Create map of codigo_interno -> Store object for quick lookup
    const storeMap = new Map<string, Store>(stores.map(s => [s.codigo_interno.toUpperCase(), s]));
    const storeById = new Map<string, Store>(stores.map(s => [s.id, s]));

    return new Promise((resolve, reject) => {
      const reader = new FileReader();

      reader.onprogress = (event) => {
        if (event.lengthComputable && onProgress) {
          const percentLoaded = Math.round((event.loaded / event.total) * 50);
          onProgress(percentLoaded);
        }
      };

      reader.onload = async (event) => {
        const batchId = crypto.randomUUID();
        try {
          const text = event.target?.result as string;
          if (!text) {
            resolve({ status: 'error', message: 'Archivo vacío', records_processed: 0 });
            return;
          }

          if (onProgress) onProgress(60);

          const lines = text.split(/\r\n|\n/).filter(line => line.trim() !== '');

          if (lines.length === 0) {
            resolve({ status: 'error', message: 'Archivo sin contenido', records_processed: 0 });
            return;
          }

          const recordsToInsert = [];
          const lineErrors: { linea: number, error: string }[] = [];
          let currentLocalName = 'Desconocido';
          const touchedLocalIds = new Set<string>();

          // Process rows (skip header)
          for (let i = 1; i < lines.length; i++) {
            const columns = parseCsvLine(lines[i]);
            if (columns.length >= 6) {
              const factura = columns[0].trim();
              const fechaRaw = columns[1].trim();
              const fecha = normalizeCsvSaleDate(fechaRaw, dateFormatPreference);
              const storeCode = columns[2].trim();
              const bruto = parseCsvAmount(columns[3]);
              const impuestos = parseCsvAmount(columns[4]);
              const neto = parseCsvAmount(columns[5]);
              const horaRaw = (columns[6] ?? '').trim();
              const hora = horaRaw ? normalizeCsvSaleTime(horaRaw) : null;
              const normalizedStoreCode = storeCode.toUpperCase();
              const store = storeMap.get(normalizedStoreCode);

              if (store?.id) {
                currentLocalName = store.nombre;
                touchedLocalIds.add(store.id);
              }

              if (!fecha) {
                lineErrors.push({
                  linea: i + 1,
                  error: `Formato de fecha inválido: ${fechaRaw}`
                });
                continue;
              }

              if (![bruto, impuestos, neto].every(Number.isFinite)) {
                lineErrors.push({
                  linea: i + 1,
                  error: `Montos inválidos. bruto='${columns[3] ?? ''}', impuestos='${columns[4] ?? ''}', neto='${columns[5] ?? ''}'`
                });
                continue;
              }

              if (horaRaw && !hora) {
                lineErrors.push({
                  linea: i + 1,
                  error: `Formato de hora inválido: ${horaRaw}`
                });
                continue;
              }

              if (!store) {
                lineErrors.push({ linea: i + 1, error: `Local '${storeCode}' no encontrado.` });
                continue;
              }

              if (!store.id) {
                lineErrors.push({ linea: i + 1, error: `Configuración inválida para local '${storeCode}'. ID no encontrado.` });
                continue;
              }

              if (isDateOnOrBefore(fecha, store.fecha_corte_importacion)) {
                lineErrors.push({
                  linea: i + 1,
                  error: `Fecha ${fecha} pertenece a un periodo cerrado para el local '${storeCode}' (cierre hasta ${store.fecha_corte_importacion}).`
                });
                continue;
              }

              recordsToInsert.push({
                local_id: store.id,
                mall_id: store.mall_id,  // Include mall_id from store
                fecha: fecha,
                hora: hora || '12:00:00',
                total_bruto: bruto,
                total_impuestos: impuestos,
                total_neto: neto,
                factura_no: factura
              });
            } else if (lines[i].trim() !== '') {
              lineErrors.push({ linea: i + 1, error: 'Formato de línea inválido (faltan columnas).' });
            }
          }

          if (onProgress) onProgress(80);

          const dedupeKey = (record: any): string | null => {
            const localId = record?.local_id;
            const fecha = record?.fecha;
            const facturaNo = String(record?.factura_no || '').trim();
            if (!localId || !fecha || !facturaNo) return null;
            return `${localId}|${fecha}|${facturaNo}`;
          };

          // De-duplicate rows within the same file (last row wins).
          const dedupedMap = new Map<string, any>();
          const recordsWithoutKey: any[] = [];
          for (const record of recordsToInsert) {
            const key = dedupeKey(record);
            if (key) dedupedMap.set(key, record);
            else recordsWithoutKey.push(record);
          }
          const dedupedRecords = [...dedupedMap.values(), ...recordsWithoutKey];

          let processedCount = 0;

          // Batch upsert into Supabase
          if (recordsToInsert.length > 0) {
            // Preserve "upsert_activo" behavior: replace data by local+date for configured stores.
            const rowsToClear = new Set<string>();
            for (const record of dedupedRecords) {
              const store = storeById.get(record.local_id);
              if (store?.upsert_activo && record.local_id && record.fecha) {
                rowsToClear.add(`${record.local_id}|${record.fecha}`);
              }
            }
            for (const rowKey of rowsToClear) {
              const [localId, fecha] = rowKey.split('|');
              await supabase
                .from('ventas')
                .delete()
                .match({ local_id: localId, fecha });
            }

            // Final safety check
            const validRecords = dedupedRecords.filter(r => r.local_id && r.local_id !== 'null' && r.local_id !== 'undefined');
            processedCount = validRecords.length;

            if (validRecords.length === 0 && dedupedRecords.length > 0) {
              throw new Error("Error crítico: Todos los registros tienen identificadores de local inválidos.");
            }

            try {
              const { error: upsertError } = await supabase
                .from('ventas')
                .upsert(validRecords, { onConflict: 'local_id,fecha,factura_no', ignoreDuplicates: false });
              if (upsertError) throw upsertError;
            } catch (upsertErr: any) {
              const upsertMsg = String(upsertErr?.message || upsertErr || '').toLowerCase();
              const noUniqueConstraint =
                upsertMsg.includes('no unique') ||
                upsertMsg.includes('no unique or exclusion constraint') ||
                upsertMsg.includes('on conflict');

              if (!noUniqueConstraint) {
                throw upsertErr;
              }

              // Fallback path when DB does not have a unique constraint for upsert.
              const keyedRecords = validRecords.filter((r) => !!dedupeKey(r));
              const noKeyRecords = validRecords.filter((r) => !dedupeKey(r));

              const existingMap = new Map<string, string>();
              if (keyedRecords.length > 0) {
                const localIds = [...new Set(keyedRecords.map((r) => r.local_id))];
                const fechas = [...new Set(keyedRecords.map((r) => r.fecha))];
                const { data: existingRows, error: existingError } = await supabase
                  .from('ventas')
                  .select('id, local_id, fecha, factura_no')
                  .in('local_id', localIds)
                  .in('fecha', fechas);
                if (existingError) throw existingError;

                for (const ex of (existingRows || [])) {
                  const k = `${ex.local_id}|${ex.fecha}|${String(ex.factura_no || '').trim()}`;
                  if (ex.id) existingMap.set(k, ex.id);
                }
              }

              const updates: Array<{ id: string; payload: any }> = [];
              const inserts: any[] = [...noKeyRecords];

              for (const rec of keyedRecords) {
                const key = dedupeKey(rec)!;
                const existingId = existingMap.get(key);
                if (existingId) {
                  updates.push({ id: existingId, payload: rec });
                } else {
                  inserts.push(rec);
                }
              }

              for (const upd of updates) {
                const { error: updateError } = await supabase
                  .from('ventas')
                  .update(upd.payload)
                  .eq('id', upd.id);
                if (updateError) throw updateError;
              }

              if (inserts.length > 0) {
                const { error: insertError } = await supabase
                  .from('ventas')
                  .insert(inserts);
                if (insertError) throw insertError;
              }
            }
          }

          if (onProgress) onProgress(100);

          // Log results
          const finalStatus = lineErrors.length > 0 ? (processedCount > 0 ? 'exito' : 'error') : 'exito';
          const finalMsg = lineErrors.length > 0
            ? `Procesados ${processedCount} registros con ${lineErrors.length} errores.`
            : `Carga exitosa de ${processedCount} registros.`;
          const singleLocalId = touchedLocalIds.size === 1 ? Array.from(touchedLocalIds)[0] : null;
          const singleLocalName = touchedLocalIds.size === 1 ? currentLocalName : (touchedLocalIds.size > 1 ? 'Multiple locales' : currentLocalName);

          await this.logLoad({
            local_nombre: singleLocalName,
            mall_id: mallId,
            local_id: singleLocalId,
            archivo: file.name,
            estado: finalStatus,
            mensaje: finalMsg,
            batch_id: batchId,
            detalles: lineErrors
          });

          resolve({
            status: lineErrors.length > 0 && processedCount === 0 ? 'error' : 'success',
            message: finalMsg,
            records_processed: processedCount
          });

        } catch (error: any) {
          console.error("Ingestion error:", error);
          await this.logLoad({
            local_nombre: 'Sistema',
            mall_id: mallId,
            archivo: file.name,
            estado: 'error',
            mensaje: `Error crítico: ${error.message || 'Error desconocido'}`,
            batch_id: batchId,
            detalles: [{ linea: 0, error: error.message || 'Error crítico del sistema' }]
          });
          resolve({
            status: 'error',
            message: `Error al guardar en BD: ${error.message || 'Error desconocido'}`,
            records_processed: 0
          });
        }
      };

      reader.onerror = (error) => reject(error);
      reader.readAsText(file);
    });
  },

  async getUsers(token: string): Promise<User[]> {
    return fetchJsonWithBaseFallback<User[]>(
      '/admin/users',
      { headers: { 'Authorization': `Bearer ${token}` } },
      "Error fetching users"
    );
  },

  async getRoles(token: string): Promise<RoleConfig[]> {
    return fetchJsonWithBaseFallback<RoleConfig[]>(
      '/admin/roles',
      { headers: withAuthHeaders(token) },
      'No se pudieron cargar los roles'
    );
  },

  async createRole(payload: Omit<RoleConfig, 'id' | 'is_factory'>, token: string): Promise<any> {
    return fetchJsonWithBaseFallback('/admin/roles', {
      method: 'POST', headers: withAuthHeaders(token, { 'Content-Type': 'application/json' }), body: JSON.stringify(payload),
    }, 'No se pudo crear el rol');
  },

  async updateRole(roleId: string, payload: Omit<RoleConfig, 'id' | 'is_factory'>, token: string): Promise<any> {
    return fetchJsonWithBaseFallback(`/admin/roles/${roleId}`, {
      method: 'PUT', headers: withAuthHeaders(token, { 'Content-Type': 'application/json' }), body: JSON.stringify(payload),
    }, 'No se pudo actualizar el rol');
  },

  async deleteRole(roleId: string, token: string): Promise<any> {
    return fetchJsonWithBaseFallback(`/admin/roles/${roleId}`, {
      method: 'DELETE', headers: withAuthHeaders(token),
    }, 'No se pudo eliminar el rol');
  },

  async restoreFactoryRole(roleId: string, token: string): Promise<any> {
    return fetchJsonWithBaseFallback(`/admin/roles/${roleId}/restore-factory`, {
      method: 'POST', headers: withAuthHeaders(token),
    }, 'No se pudo restaurar el rol de fábrica');
  },

  async createUser(email: string, password: string, role: string, mallIds: string[], token: string, roleId?: string): Promise<any> {
    const response = await fetch(`${BASE_URL}/admin/users`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        email,
        password,
        rol: role,
        role_id: roleId,
        mall_ids: mallIds
      })
    });
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({ detail: "Error creando usuario" }));
      throw new Error(errorData.detail || "Error creando usuario");
    }
    return await response.json();
  },

  async assignUserMalls(userId: string, mallIds: string[], role: string, token: string): Promise<void> {
    const response = await fetch(`${BASE_URL}/admin/users/${userId}/malls`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ mall_ids: mallIds, rol: role })
    });
    if (!response.ok) throw new Error("Error assigning malls");
  },

  async updateUser(
    userId: string,
    payload: { email?: string; nombre?: string; rol?: string; role_id?: string; mall_ids?: string[] },
    token: string
  ): Promise<any> {
    const response = await fetch(`${BASE_URL}/admin/users/${userId}`, {
      method: 'PUT',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(payload)
    });
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({ detail: "Error actualizando usuario" }));
      throw new Error(errorData.detail || "Error actualizando usuario");
    }
    return await response.json();
  },

  async getResendMessagingStatus(token: string): Promise<ResendMessagingStatus> {
    return fetchJsonWithBaseFallback<ResendMessagingStatus>(
      '/admin/messaging/resend',
      { headers: withAuthHeaders(token, { 'Accept': 'application/json' }) },
      "No se pudo cargar la configuración de Resend"
    );
  },

  async saveResendSenderConfig(payload: ResendSenderConfigPayload, token: string): Promise<ResendMessagingStatus> {
    return fetchJsonWithBaseFallback<ResendMessagingStatus>(
      '/admin/messaging/resend/sender',
      {
        method: 'PUT',
        headers: withAuthHeaders(token, {
          'Accept': 'application/json',
          'Content-Type': 'application/json'
        }),
        body: JSON.stringify(payload)
      },
      "No se pudo guardar el remitente de Resend"
    );
  },

  async sendResendTestMessage(
    payload: { to: string; subject?: string; message?: string },
    token: string
  ): Promise<ResendTestMessageResponse> {
    return fetchJsonWithBaseFallback<ResendTestMessageResponse>(
      '/admin/messaging/resend/test',
      {
        method: 'POST',
        headers: withAuthHeaders(token, {
          'Accept': 'application/json',
          'Content-Type': 'application/json'
        }),
        body: JSON.stringify(payload)
      },
      "No se pudo enviar el mensaje de prueba"
    );
  },

  async getMissingDaysEmailSettings(mallId: string, token: string): Promise<MissingDaysEmailSettings> {
    return fetchJsonWithBaseFallback<MissingDaysEmailSettings>(
      `/admin/messaging/missing-days/settings?mall_id=${encodeURIComponent(mallId)}`,
      { headers: withAuthHeaders(token, { 'Accept': 'application/json' }) },
      "No se pudo cargar la programación de envío"
    );
  },

  async saveMissingDaysEmailSettings(
    settings: MissingDaysEmailSettings,
    token: string
  ): Promise<MissingDaysEmailSettings> {
    return fetchJsonWithBaseFallback<MissingDaysEmailSettings>(
      '/admin/messaging/missing-days/settings',
      {
        method: 'PUT',
        headers: withAuthHeaders(token, {
          'Accept': 'application/json',
          'Content-Type': 'application/json'
        }),
        body: JSON.stringify(settings)
      },
      "No se pudo guardar la programación de envío"
    );
  },

  async sendMissingDaysEmailNow(mallId: string, token: string): Promise<MissingDaysSendNowResponse> {
    return fetchJsonWithBaseFallback<MissingDaysSendNowResponse>(
      '/admin/messaging/missing-days/send-now',
      {
        method: 'POST',
        headers: withAuthHeaders(token, {
          'Accept': 'application/json',
          'Content-Type': 'application/json'
        }),
        body: JSON.stringify({ mall_id: mallId })
      },
      "No se pudo ejecutar el envío inmediato"
    );
  },

  async getCopilotSettings(token: string): Promise<CopilotSettings> {
    return fetchJsonWithBaseFallback<CopilotSettings>(
      '/admin/copilot/settings',
      {
        method: 'GET',
        headers: withAuthHeaders(token, { 'Accept': 'application/json' })
      },
      "No se pudo cargar la configuración de Copilot"
    );
  },

  async saveCopilotSettings(payload: CopilotSettingsPayload, token: string): Promise<CopilotSettings> {
    return fetchJsonWithBaseFallback<CopilotSettings>(
      '/admin/copilot/settings',
      {
        method: 'PUT',
        headers: withAuthHeaders(token, {
          'Accept': 'application/json',
          'Content-Type': 'application/json'
        }),
        body: JSON.stringify(payload)
      },
      "No se pudo guardar la configuración de Copilot"
    );
  },

  async getCopilotStatus(mallId: string, token: string): Promise<CopilotSettings> {
    return fetchJsonWithBaseFallback<CopilotSettings>(
      `/copilot/status?mall_id=${encodeURIComponent(mallId)}`,
      {
        method: 'GET',
        headers: withAuthHeaders(token, { 'Accept': 'application/json' })
      },
      "No se pudo consultar el estado de Copilot"
    );
  },

  async sendCopilotMessage(
    mallId: string,
    message: string,
    history: CopilotChatMessage[],
    token: string
  ): Promise<CopilotChatResponse> {
    return fetchJsonWithBaseFallback<CopilotChatResponse>(
      '/copilot/chat',
      {
        method: 'POST',
        headers: withAuthHeaders(token, {
          'Accept': 'application/json',
          'Content-Type': 'application/json'
        }),
        body: JSON.stringify({
          mall_id: mallId,
          message,
          history: history.slice(-8)
        })
      },
      "Copilot no pudo responder"
    );
  },

  async sendCopilotEmailDraft(mallId: string, draftId: string, token: string): Promise<CopilotEmailSendResponse> {
    return fetchJsonWithBaseFallback<CopilotEmailSendResponse>(
      '/copilot/email/send',
      {
        method: 'POST',
        headers: withAuthHeaders(token, {
          'Accept': 'application/json',
          'Content-Type': 'application/json'
        }),
        body: JSON.stringify({
          mall_id: mallId,
          draft_id: draftId
        })
      },
      "No se pudo enviar el correo del Copilot"
    );
  },

  async toggleUserStatus(userId: string): Promise<void> {
    const users = await this.getUsers();
    const updated = users.map(u => u.id === userId ? { ...u, estado: u.estado === 'activo' ? 'inactivo' : 'activo' } as User : u);
    localStorage.setItem(USERS_STORAGE_KEY, JSON.stringify(updated));
  },

  // --- MÉTODOS DE INTELIGENCIA ARTIFICIAL ---
  async getAIAlerts(localId?: string): Promise<{ alerts: any[], status: 'ok' | 'no_data' | 'error', summary?: any, source?: string }> {
    const url = localId ? `${BASE_URL}/insights/alerts?local_id=${localId}` : `${BASE_URL}/insights/alerts`;
    try {
      const response = await fetch(url);
      if (!response.ok) throw new Error("Error al obtener alertas");
      const data = await response.json();
      return {
        alerts: Array.isArray(data?.alerts) ? data.alerts : [],
        status: data?.status || 'error',
        summary: data?.summary || null,
        source: data?.source || null,
      };
    } catch (error) {
      console.error(error);
      return { alerts: [], status: 'error', summary: null, source: null };
    }
  },

  async getBenchmarking(localId: string): Promise<any> {
    try {
      const response = await fetch(`${BASE_URL}/insights/benchmarking/${localId}`);
      if (!response.ok) throw new Error("Error al obtener benchmarking");
      return await response.json();
    } catch (error) {
      console.error(error);
      return null;
    }
  },

  async getHeatmap(localId: string): Promise<any[]> {
    try {
      const response = await fetch(`${BASE_URL}/insights/heatmap/${localId}`);
      if (!response.ok) throw new Error("Error al obtener heatmap");
      return await response.json();
    } catch (error) {
      console.error(error);
      return [];
    }
  },

  async getEfficiency(localId: string): Promise<any> {
    try {
      const response = await fetch(`${BASE_URL}/insights/efficiency/${localId}`);
      if (!response.ok) throw new Error("Error al obtener eficiencia");
      return await response.json();
    } catch (error) {
      console.error(error);
      return null;
    }
  },

  async getRanking(metric: string, mallId?: string): Promise<any[]> {
    try {
      const params = new URLSearchParams();
      params.set('metric', metric);
      if (mallId) params.set('mall_id', mallId);
      const response = await fetch(`${BASE_URL}/insights/ranking?${params.toString()}`);
      if (!response.ok) throw new Error("Error al obtener ranking");
      return await response.json();
    } catch (error) {
      console.error(error);
      return [];
    }
  },


  async getSalesCube(params: any, token: string): Promise<any> {
    try {
      const response = await fetch(`${BASE_URL}/analytics/cubo`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${token}`,
          ...(params.mallId ? { "X-Mall-Id": params.mallId } : {})
        },
        body: JSON.stringify(params),
      });
      if (!response.ok) throw new Error("Error fetching Sales Cube");
      return await response.json();
    } catch (error) {
      console.error(error);
      throw error;
    }
  },

  async analyzeMapping(file: File): Promise<any> {
    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await fetch(`${BASE_URL}/mapping/analyze`, {
        method: 'POST',
        body: formData
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: "Error desconocido" }));
        throw new Error(errorData.detail || "Error al analizar mapeo");
      }
      return await response.json();
    } catch (error: any) {
      console.error("Analyze mapping error:", error);
      throw error.message || error;
    }
  },

  // --- MALL MANAGEMENT (ADMIN) ---
  async getMalls(token: string): Promise<any[]> {
    try {
      return await fetchJsonWithBaseFallback<any[]>(
        '/malls/all',
        { headers: { 'Authorization': `Bearer ${token}` } },
        "Error fetching malls"
      );
    } catch (e) {
      console.error(e);
      return [];
    }
  },

  async createMall(mallData: { nombre: string, conf_locale?: string, conf_moneda?: string, metadata?: any }, token: string): Promise<any> {
    const response = await fetch(`${BASE_URL}/malls`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify(mallData)
    });
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || "Error creating mall");
    }
    return await response.json();
  },

  async updateMall(id: string, mallData: { nombre?: string, conf_locale?: string, conf_moneda?: string, metadata?: any }, token: string): Promise<any> {
    const response = await fetch(`${BASE_URL}/malls/${id}`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify(mallData)
    });
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || "Error updating mall");
    }
    return await response.json();
  },

  async deleteMall(id: string, token: string): Promise<void> {
    const response = await fetch(`${BASE_URL}/malls/${id}`, {
      method: 'DELETE',
      headers: {
        'Authorization': `Bearer ${token}`
      }
    });
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || "Error deleting mall");
    }
  },
  async purgeSales(localId: string, startDate?: string, endDate?: string, confirmation?: string, mallId?: string, token?: string): Promise<{ success: boolean; message: string }> {
    console.log("📡 [API] purgeSales CALLED", { localId, startDate, endDate, confirmation, mallId, hasToken: !!token });
    try {
      const url = `${BASE_URL}/admin/sales/purge`;
      console.log("📡 [API] Sending DELETE to:", url);

      const response = await fetch(url, {
        method: 'DELETE',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
          'X-Mall-Id': mallId || ''
        },
        body: JSON.stringify({
          local_id: localId,
          fecha_inicio: startDate,
          fecha_fin: endDate,
          confirmacion: confirmation
        })
      });

      console.log("📡 [API] Response status:", response.status);
      const data = await response.json();
      console.log("📡 [API] Response data:", data);

      if (!response.ok) {
        throw new Error(data.detail || "Error al depurar ventas");
      }

      return { success: true, message: data.message };
    } catch (error: any) {
      console.error("📡 [API] Error purging sales:", error);
      return { success: false, message: error.message || "Error desconocido" };
    }
  },

  async getSecurityServiceAccounts(
    token: string,
    filters: { mall_id?: string; local_id?: string; token_type?: string; status?: string; q?: string } = {}
  ): Promise<SecurityServiceAccount[]> {
    const params = new URLSearchParams();
    if (filters.mall_id) params.set('mall_id', filters.mall_id);
    if (filters.local_id) params.set('local_id', filters.local_id);
    if (filters.token_type) params.set('token_type', filters.token_type);
    if (filters.status) params.set('status', filters.status);
    if (filters.q) params.set('q', filters.q);
    const qs = params.toString();
    return fetchJsonWithBaseFallback<SecurityServiceAccount[]>(
      `/security/service-accounts${qs ? `?${qs}` : ''}`,
      { method: 'GET', headers: withAuthHeaders(token, { 'Accept': 'application/json' }) },
      "No se pudieron cargar los service accounts."
    );
  },

  async createSecurityServiceAccount(
    payload: { name: string; mall_id: string; local_id: string; token_type?: 'exporter'; scopes: string[] },
    token: string
  ): Promise<SecurityServiceAccount> {
    return fetchJsonWithBaseFallback<SecurityServiceAccount>(
      '/security/service-accounts',
      {
        method: 'POST',
        headers: withAuthHeaders(token, { 'Content-Type': 'application/json', 'Accept': 'application/json' }),
        body: JSON.stringify({ ...payload, token_type: payload.token_type || 'exporter' }),
      },
      "No se pudo crear el service account."
    );
  },

  async updateSecurityServiceAccountStatus(
    serviceAccountId: string,
    status: 'active' | 'disabled',
    token: string
  ): Promise<SecurityServiceAccount> {
    return fetchJsonWithBaseFallback<SecurityServiceAccount>(
      `/security/service-accounts/${encodeURIComponent(serviceAccountId)}/status`,
      {
        method: 'PATCH',
        headers: withAuthHeaders(token, { 'Content-Type': 'application/json', 'Accept': 'application/json' }),
        body: JSON.stringify({ status }),
      },
      "No se pudo actualizar el estado del service account."
    );
  },

  async regenerateSecurityServiceAccount(serviceAccountId: string, token: string): Promise<SecurityServiceAccount> {
    return fetchJsonWithBaseFallback<SecurityServiceAccount>(
      `/security/service-accounts/${encodeURIComponent(serviceAccountId)}/regenerate`,
      {
        method: 'POST',
        headers: withAuthHeaders(token, { 'Accept': 'application/json' }),
      },
      "No se pudo regenerar el secreto del service account."
    );
  },

  async revokeTokensBySecurityServiceAccount(serviceAccountId: string, token: string, reason?: string): Promise<{ revoked_count: number }> {
    return fetchJsonWithBaseFallback<{ revoked_count: number }>(
      `/security/service-accounts/${encodeURIComponent(serviceAccountId)}/revoke-tokens`,
      {
        method: 'POST',
        headers: withAuthHeaders(token, { 'Content-Type': 'application/json', 'Accept': 'application/json' }),
        body: JSON.stringify({ reason: reason || 'ui_service_account_bulk_revoke' }),
      },
      "No se pudieron revocar los tokens del service account."
    );
  },

  async getSecurityTokens(
    token: string,
    filters: { mall_id?: string; local_id?: string; token_type?: string; status?: string; q?: string } = {}
  ): Promise<SecurityApiToken[]> {
    const params = new URLSearchParams();
    if (filters.mall_id) params.set('mall_id', filters.mall_id);
    if (filters.local_id) params.set('local_id', filters.local_id);
    if (filters.token_type) params.set('token_type', filters.token_type);
    if (filters.status) params.set('status', filters.status);
    if (filters.q) params.set('q', filters.q);
    const qs = params.toString();
    return fetchJsonWithBaseFallback<SecurityApiToken[]>(
      `/security/tokens${qs ? `?${qs}` : ''}`,
      { method: 'GET', headers: withAuthHeaders(token, { 'Accept': 'application/json' }) },
      "No se pudieron cargar los tokens."
    );
  },

  async createSecurityToken(
    payload: { token_type: 'app' | 'exporter'; mall_id: string; local_id?: string; scopes: string[]; expires_in?: number | null; service_account_id?: string },
    token: string
  ): Promise<SecurityTokenPairReveal> {
    return fetchJsonWithBaseFallback<SecurityTokenPairReveal>(
      '/security/tokens',
      {
        method: 'POST',
        headers: withAuthHeaders(token, { 'Content-Type': 'application/json', 'Accept': 'application/json' }),
        body: JSON.stringify(payload),
      },
      "No se pudo crear el token."
    );
  },

  async updateSecurityTokenStatus(tokenId: string, status: 'active' | 'disabled', token: string): Promise<SecurityApiToken> {
    return fetchJsonWithBaseFallback<SecurityApiToken>(
      `/security/tokens/${encodeURIComponent(tokenId)}/status`,
      {
        method: 'PATCH',
        headers: withAuthHeaders(token, { 'Content-Type': 'application/json', 'Accept': 'application/json' }),
        body: JSON.stringify({ status }),
      },
      "No se pudo actualizar el estado del token."
    );
  },

  async regenerateSecurityToken(tokenId: string, token: string): Promise<SecurityTokenPairReveal> {
    return fetchJsonWithBaseFallback<SecurityTokenPairReveal>(
      `/security/tokens/${encodeURIComponent(tokenId)}/regenerate`,
      {
        method: 'POST',
        headers: withAuthHeaders(token, { 'Accept': 'application/json' }),
      },
      "No se pudo regenerar el token."
    );
  },

  async revokeSecurityToken(payload: { token_id?: string; jti?: string; reason?: string }, token: string): Promise<{ revoked: boolean; token_id: string }> {
    return fetchJsonWithBaseFallback<{ revoked: boolean; token_id: string }>(
      '/security/tokens/revoke',
      {
        method: 'POST',
        headers: withAuthHeaders(token, { 'Content-Type': 'application/json', 'Accept': 'application/json' }),
        body: JSON.stringify({ ...payload, reason: payload.reason || 'ui_manual_revoke' }),
      },
      "No se pudo revocar el token."
    );
  },

  async revokeSecurityTokensByLocal(payload: { mall_id: string; local_id: string; reason?: string }, token: string): Promise<{ revoked_count: number }> {
    return fetchJsonWithBaseFallback<{ revoked_count: number }>(
      '/security/tokens/revoke/local',
      {
        method: 'POST',
        headers: withAuthHeaders(token, { 'Content-Type': 'application/json', 'Accept': 'application/json' }),
        body: JSON.stringify({ ...payload, reason: payload.reason || 'ui_local_bulk_revoke' }),
      },
      "No se pudieron revocar los tokens del local."
    );
  },

  async revokeSecurityTokensByMall(payload: { mall_id: string; reason?: string }, token: string): Promise<{ revoked_count: number }> {
    return fetchJsonWithBaseFallback<{ revoked_count: number }>(
      '/security/tokens/revoke/mall',
      {
        method: 'POST',
        headers: withAuthHeaders(token, { 'Content-Type': 'application/json', 'Accept': 'application/json' }),
        body: JSON.stringify({ ...payload, reason: payload.reason || 'ui_mall_bulk_revoke' }),
      },
      "No se pudieron revocar los tokens del mall."
    );
  },

  async getSecurityTokenAudit(
    token: string,
    filters: { mall_id?: string; local_id?: string; event_type?: string; token_id?: string; q?: string; limit?: number } = {}
  ): Promise<SecurityTokenAuditLogEntry[]> {
    const params = new URLSearchParams();
    if (filters.mall_id) params.set('mall_id', filters.mall_id);
    if (filters.local_id) params.set('local_id', filters.local_id);
    if (filters.event_type) params.set('event_type', filters.event_type);
    if (filters.token_id) params.set('token_id', filters.token_id);
    if (filters.q) params.set('q', filters.q);
    if (typeof filters.limit === 'number' && Number.isFinite(filters.limit)) params.set('limit', String(filters.limit));
    const qs = params.toString();
    return fetchJsonWithBaseFallback<SecurityTokenAuditLogEntry[]>(
      `/security/token-audit${qs ? `?${qs}` : ''}`,
      { method: 'GET', headers: withAuthHeaders(token, { 'Accept': 'application/json' }) },
      "No se pudo cargar la auditoría de tokens."
    );
  },

  async getSecurityExporterWebserviceConfigs(
    token: string,
    filters: { mall_id?: string; local_id?: string; enabled?: boolean } = {}
  ): Promise<SecurityExporterWebserviceConfig[]> {
    const params = new URLSearchParams();
    if (filters.mall_id) params.set('mall_id', filters.mall_id);
    if (filters.local_id) params.set('local_id', filters.local_id);
    if (typeof filters.enabled === 'boolean') params.set('enabled', String(filters.enabled));
    const qs = params.toString();
    return fetchJsonWithBaseFallback<SecurityExporterWebserviceConfig[]>(
      `/security/exporter/configs${qs ? `?${qs}` : ''}`,
      { method: 'GET', headers: withAuthHeaders(token, { 'Accept': 'application/json' }) },
      "No se pudieron cargar las configuraciones de webservice ERP."
    );
  },

  async getSecurityExporterWebserviceConfig(
    localId: string,
    mallId: string,
    token: string
  ): Promise<SecurityExporterWebserviceConfig> {
    const qs = new URLSearchParams({ mall_id: mallId }).toString();
    return fetchJsonWithBaseFallback<SecurityExporterWebserviceConfig>(
      `/security/exporter/configs/${encodeURIComponent(localId)}?${qs}`,
      { method: 'GET', headers: withAuthHeaders(token, { 'Accept': 'application/json' }) },
      "No se pudo cargar la configuración de webservice ERP."
    );
  },

  async upsertSecurityExporterWebserviceConfig(
    localId: string,
    payload: {
      mall_id: string;
      enabled: boolean;
      contract_type?: 'msmall_sales_v1';
      default_granularity: 'transaction' | 'daily' | 'daily_summary';
      allow_transaction: boolean;
      allow_daily: boolean;
      strict_validation: boolean;
      notes?: string | null;
    },
    token: string
  ): Promise<SecurityExporterWebserviceConfig> {
    return fetchJsonWithBaseFallback<SecurityExporterWebserviceConfig>(
      `/security/exporter/configs/${encodeURIComponent(localId)}`,
      {
        method: 'PUT',
        headers: withAuthHeaders(token, { 'Content-Type': 'application/json', 'Accept': 'application/json' }),
        body: JSON.stringify({
          contract_type: 'msmall_sales_v1',
          ...payload,
        }),
      },
      "No se pudo guardar la configuración de webservice ERP."
    );
  },
};
