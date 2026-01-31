import { createClient } from '@supabase/supabase-js';
import { SaleReport, IngestionResponse, DateRange, KPIData, User, ImportConfig, SaleDetail, ImportProtocol, FileType, ImportFrequency } from './types';

const SUPABASE_URL = import.meta.env.VITE_SUPABASE_URL || '';
const SUPABASE_ANON_KEY = import.meta.env.VITE_SUPABASE_ANON_KEY || '';

export const supabase = (SUPABASE_URL && SUPABASE_ANON_KEY)
  ? createClient(SUPABASE_URL, SUPABASE_ANON_KEY)
  : null;

if (!supabase) {
  console.warn("Supabase no está configurado. Verifica tu archivo .env");
}

const BASE_URL = '/api/v1';
const STORES_STORAGE_KEY = 'msmall_mock_stores';
const USERS_STORAGE_KEY = 'msmall_mock_users';
const IMPORTS_STORAGE_KEY = 'msmall_mock_imports';

export interface Store {
  id: string;
  mall_id: string;
  codigo_interno: string;
  nombre: string;
  rubro: string | null;
  created_at: string;
  responsable: string;
  contrato_no: string;
  piso: string;
  tipo_negocio: string;
  mts: string;
  porciento_renta: string;
  upsert_activo: boolean;
  mall_nombre?: string;
  renta_fija?: number;
  breakpoint_venta?: number;
  porcentaje_variable?: number;
}

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
      tipo_ejecucion: local.tipo_ejecucion || 'MANUAL'
    }));
  },

  async saveImportConfig(config: ImportConfig): Promise<void> {
    if (!supabase) throw new Error("Supabase client not initialized");

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
      constants_config: config.constants
    };

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

  async testConnection(config: Partial<ImportConfig>, password?: string): Promise<{ success: boolean, message: string }> {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => {
      console.warn("ApiService: Disparando abort por timeout de 60s");
      controller.abort();
    }, 60000);

    console.log("ApiService: Iniciando POST /remote/test...");
    try {
      const response = await fetch(`${BASE_URL}/remote/test`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
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

  async exploreDirectory(path: string, protocol?: string, host?: string, port?: number, user?: string, password?: string): Promise<{ ruta_actual: string, items: { nombre: string, ruta: string, es_dir: boolean }[] }> {
    try {
      let response;
      if (protocol && protocol !== 'LOCAL') {
        response = await fetch(`${BASE_URL}/remote/list`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
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
        response = await fetch(`${BASE_URL}/explorar-directorio?ruta=${encodeURIComponent(path)}`);
      }

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: "Error desconocido" }));
        throw new Error(errorData.detail || "Error al listar directorio");
      }
      return await response.json();
    } catch (error: any) {
      console.error("Explore directory error:", error);
      throw error.message || error;
    }
  },

  async readRemoteHeaders(config: ImportConfig, password?: string): Promise<string[]> {
    try {
      const response = await fetch(`${BASE_URL}/remote/headers`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
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
      throw error.message || error;
    }
  },

  async analyzeRemoteMapping(config: Partial<ImportConfig>, password?: string, testFile?: string): Promise<any> {
    try {
      const response = await fetch(`${BASE_URL}/mapping/analyze-remote`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          protocolo: config.protocolo,
          host: config.host?.trim(),
          puerto: Number(config.puerto),
          usuario: config.usuario?.trim(),
          password: password || config.password,
          ruta: testFile || config.ruta_remota,
          tipo_archivo: config.tipo_archivo
        })
      });
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: "Error analizando mapeo" }));
        throw new Error(errorData.detail || "Error analizando mapeo");
      }
      return await response.json();
    } catch (error: any) {
      console.error(error);
      throw error.message || error;
    }
  },

  async listRemoteFiles(config: ImportConfig): Promise<{ nombre: string, fecha: string, tamano: number }[]> {
    try {
      const response = await fetch(`${BASE_URL}/remote/list-files`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
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

  async analyzeSingleFile(config: ImportConfig, filename: string): Promise<{
    csv_headers: string[],
    suggested_mapping: Record<string, any>,
    sample_row: Record<string, any>,
    current_mapping: Record<string, string>
  }> {
    try {
      const response = await fetch(`${BASE_URL}/remote/analyze-file`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          config_id: config.id || '',
          filename: filename,
          config: config
        })
      });
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: "Error analizando archivo" }));
        throw new Error(errorData.detail || "Error analizando archivo");
      }
      return await response.json();
    } catch (error: any) {
      console.error("Error in analyzeSingleFile:", error);
      throw error.message || error;
    }
  },

  async executeManualImport(config: ImportConfig, filename: string): Promise<{ status: string, message: string, errors?: any[] }> {
    try {
      const response = await fetch(`${BASE_URL}/remote/execute-manual`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          config_id: config.id,
          filename,
          config // Pass full config
        })
      });
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: "Error ejecutando importación" }));
        throw new Error(errorData.detail || "Error ejecutando importación");
      }
      return await response.json();
    } catch (error: any) {
      console.error(error);
      throw error.message || error;
    }
  },

  // --- MÉTODOS DE AUDITORÍA DE CARGA ---
  async getLoadLogs(mallId?: string): Promise<any[]> {
    if (!supabase) return [];
    try {
      let query = supabase
        .from('logs_carga')
        .select('*')
        .order('fecha_hora', { ascending: false })
        .limit(50);

      // Filter by mall if provided
      if (mallId) {
        // 1. Get store names for this mall
        const { data: stores } = await supabase
          .from('locales')
          .select('nombre')
          .eq('mall_id', mallId);

        const storeNames = (stores || []).map((s: any) => s.nombre);

        if (storeNames.length > 0) {
          query = query.in('local_nombre', storeNames);
        } else {
          // If mall has no stores, return empty or filter by empty list (which returns 0)
          // But query.in with empty list usually throws or returns all. Safety check:
          return [];
        }
      }

      const { data, error } = await query;
      if (error) throw error;
      return data;
    } catch (error) {
      console.error('Error fetching load logs:', error);
      return [];
    }
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

  async clearLoadLogs(): Promise<void> {
    try {
      // Use the backend endpoint instead of direct Supabase call to avoid hanging
      const response = await fetch(`${BASE_URL}/audit/logs`, {
        method: 'DELETE',
        headers: {
          'Content-Type': 'application/json',
          'X-API-Key': 'demo-key-123' // Using the hardcoded demo key common in this mock app
        }
      });

      if (!response.ok) {
        throw new Error("Failed to clear logs via backend");
      }
    } catch (error) {
      console.error('Error clearing load logs:', error);
      throw error;
    }
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

        reportMap[localId].total_bruto += Number(sale.total_bruto) || 0;
        reportMap[localId].total_impuestos += Number(sale.total_impuestos) || 0;
        reportMap[localId].total_neto += Number(sale.total_neto) || 0;
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
      return data as SaleDetail[];
    } catch (error) {
      console.error('Error getting sale details:', error);
      return [];
    }
  },

  async resetAllSales(): Promise<{ success: boolean; message: string }> {
    try {
      const response = await fetch(`${BASE_URL}/admin/reset-sales`, {
        method: 'DELETE',
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || "Error al reiniciar ventas");
      }

      return { success: true, message: data.message };
    } catch (error: any) {
      console.error("Error resetting sales:", error);
      return { success: false, message: error.message || "Error desconocido" };
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
        ventas_por_rubro: [],
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

  async createStore(store: Partial<Store>): Promise<Store> {
    if (!supabase) throw new Error("Supabase no está configurado");

    try {
      // Remove any fields that shouldn't be inserted if they are present but undefined/null
      const { id, created_at, ...storeData } = store as any;

      const { data, error } = await supabase
        .from('locales')
        .insert([storeData])
        .select()
        .single();

      if (error) throw error;
      return data as Store;
    } catch (error) {
      console.error('Error creating store:', error);
      throw error;
    }
  },

  async updateStore(id: string, store: Partial<Store>): Promise<Store> {
    if (!supabase) throw new Error("Supabase no está configurado");
    try {
      // Remove ID/created_at if present in update payload
      const { id: _, created_at, ...storeData } = store as any;
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
      throw error;
    }
  },

  async deleteStore(id: string): Promise<void> {
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

  async ingestSales(file: File, apiKey: string, onProgress?: (progress: number) => void): Promise<IngestionResponse> {
    if (!supabase) {
      return { status: 'error', message: 'Supabase no está configurado', records_processed: 0 };
    }

    const stores = await this.getStores();
    // Create map of codigo_interno -> Store object for quick lookup
    const storeMap = new Map<string, Store>(stores.map(s => [s.codigo_interno.toUpperCase(), s]));

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

          // Process rows (skip header)
          for (let i = 1; i < lines.length; i++) {
            const columns = lines[i].split(',');
            if (columns.length >= 6) {
              const factura = columns[0].trim();
              const fecha = columns[1].trim();
              const storeCode = columns[2].trim();
              const bruto = parseFloat(columns[3].trim());
              const impuestos = parseFloat(columns[4].trim());
              const neto = parseFloat(columns[5].trim());

              const normalizedStoreCode = storeCode.toUpperCase();
              const store = storeMap.get(normalizedStoreCode);

              if (!store) {
                lineErrors.push({ linea: i + 1, error: `Local '${storeCode}' no encontrado.` });
                continue;
              }

              if (!store.id) {
                lineErrors.push({ linea: i + 1, error: `Configuración inválida para local '${storeCode}'. ID no encontrado.` });
                continue;
              }

              currentLocalName = store.nombre;

              recordsToInsert.push({
                local_id: store.id,
                fecha: fecha,
                hora: '12:00:00',
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

          // Handle Upsert Logic
          for (const record of recordsToInsert) {
            const store = stores.find(s => s.id === record.local_id) as Store | undefined;
            if (store?.upsert_activo) {
              await supabase
                .from('ventas')
                .delete()
                .match({ local_id: record.local_id, fecha: record.fecha });
            }
          }

          // Batch insert into Supabase
          if (recordsToInsert.length > 0) {
            // Final safety check
            const validRecords = recordsToInsert.filter(r => r.local_id && r.local_id !== 'null' && r.local_id !== 'undefined');

            if (validRecords.length === 0 && recordsToInsert.length > 0) {
              throw new Error("Error crítico: Todos los registros tienen identificadores de local inválidos.");
            }

            const { error } = await supabase
              .from('ventas')
              .insert(validRecords);
            if (error) throw error;
          }

          if (onProgress) onProgress(100);

          // Log results
          const finalStatus = lineErrors.length > 0 ? (recordsToInsert.length > 0 ? 'exito' : 'error') : 'exito';
          const finalMsg = lineErrors.length > 0
            ? `Procesados ${recordsToInsert.length} registros con ${lineErrors.length} errores.`
            : `Carga exitosa de ${recordsToInsert.length} registros.`;

          await this.logLoad({
            local_nombre: currentLocalName,
            archivo: file.name,
            estado: finalStatus,
            mensaje: finalMsg,
            batch_id: batchId,
            detalles: lineErrors
          });

          resolve({
            status: lineErrors.length > 0 && recordsToInsert.length === 0 ? 'error' : 'success',
            message: finalMsg,
            records_processed: recordsToInsert.length
          });

        } catch (error: any) {
          console.error("Ingestion error:", error);
          await this.logLoad({
            local_nombre: 'Sistema',
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
    const response = await fetch(`${BASE_URL}/admin/users`, {
      headers: { 'Authorization': `Bearer ${token}` }
    });
    if (!response.ok) throw new Error("Error fetching users");
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

  async toggleUserStatus(userId: string): Promise<void> {
    const users = await this.getUsers();
    const updated = users.map(u => u.id === userId ? { ...u, estado: u.estado === 'activo' ? 'inactivo' : 'activo' } as User : u);
    localStorage.setItem(USERS_STORAGE_KEY, JSON.stringify(updated));
  },

  // --- MÉTODOS DE INTELIGENCIA ARTIFICIAL ---
  async getAIAlerts(localId?: string): Promise<any[]> {
    const url = localId ? `${BASE_URL}/insights/alerts?local_id=${localId}` : `${BASE_URL}/insights/alerts`;
    try {
      const response = await fetch(url);
      if (!response.ok) throw new Error("Error al obtener alertas");
      return await response.json();
    } catch (error) {
      console.error(error);
      return [];
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

  async getRanking(metric: string): Promise<any[]> {
    try {
      const response = await fetch(`${BASE_URL}/insights/ranking?metric=${metric}`);
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
      const response = await fetch(`${BASE_URL}/malls/all`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (!response.ok) throw new Error("Error fetching malls");
      return await response.json();
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
  }
};
