
import { SaleReport, IngestionResponse, DateRange, KPIData, User, ImportConfig } from './types';

const BASE_URL = 'http://localhost:8000/api/v1';
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
  mall_nombre?: string;
}

export const ApiService = {
  // --- MÉTODOS DE IMPORTACIÓN AUTOMATIZADA ---
  async getImportConfigs(): Promise<ImportConfig[]> {
    const stored = localStorage.getItem(IMPORTS_STORAGE_KEY);
    if (stored) return JSON.parse(stored);

    const defaults: ImportConfig[] = [
      {
        id: '1',
        nombre: 'Conexión Nike Store - SFTP Principal',
        protocolo: 'SFTP',
        host: 'sftp.nike-retail.com',
        puerto: 22,
        usuario: 'audit_msmall',
        ruta_remota: '/ventas/diarias/',
        tipo_archivo: 'CSV',
        frecuencia: 'manual',
        accion_post_procesado: 'ninguna',
        estado: 'activo',
        ultima_ejecucion: '2024-01-27 08:00',
        resultado_ultimo: 'exito',
        mapping: {
          factura_numero: 'invoice_id',
          fecha_venta: 'date',
          local_codigo: 'store_code',
          total_bruto: 'gross_amount',
          total_impuestos: 'tax',
          total_neto: 'net_amount'
        }
      }
    ];
    localStorage.setItem(IMPORTS_STORAGE_KEY, JSON.stringify(defaults));
    return defaults;
  },

  async saveImportConfig(config: ImportConfig): Promise<void> {
    const configs = await this.getImportConfigs();
    const index = configs.findIndex(c => c.id === config.id);
    if (index >= 0) {
      configs[index] = config;
    } else {
      configs.push({ ...config, id: crypto.randomUUID() });
    }
    localStorage.setItem(IMPORTS_STORAGE_KEY, JSON.stringify(configs));
  },

  async deleteImportConfig(id: string): Promise<void> {
    const configs = await this.getImportConfigs();
    const updated = configs.filter(c => c.id !== id);
    localStorage.setItem(IMPORTS_STORAGE_KEY, JSON.stringify(updated));
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

  async testConnection(config: Partial<ImportConfig>): Promise<boolean> {
    await new Promise(resolve => setTimeout(resolve, 1500));
    return config.host !== '' && config.usuario !== '';
  },

  async exploreDirectory(path: string): Promise<{ ruta_actual: string, items: { nombre: string, ruta: string, es_dir: boolean }[] }> {
    try {
      const response = await fetch(`${BASE_URL}/explorar-directorio?ruta=${encodeURIComponent(path)}`);
      if (!response.ok) throw new Error("Error al explorar directorio");
      return await response.json();
    } catch (error) {
      console.error(error);
      return { ruta_actual: path, items: [] };
    }
  },

  // --- OTROS MÉTODOS ---
  async getSalesReport(dates: DateRange): Promise<SaleReport[]> {
    return []; // Mock
  },

  async getKPIs(dates: DateRange): Promise<KPIData> {
    return {
      ventas_totales_bruto: 125400.50,
      ventas_totales_neto: 112860.45,
      transacciones: 1450,
      ticket_promedio: 86.48,
      variacion_ventas: 12.5,
      top_locales: [],
      ventas_por_dia: [],
      ventas_por_rubro: []
    };
  },

  async getStores(): Promise<Store[]> {
    const stored = localStorage.getItem(STORES_STORAGE_KEY);
    return stored ? JSON.parse(stored) : [];
  },

  async createStore(store: Partial<Store>): Promise<Store> {
    const stores = await this.getStores();
    const newStore = { ...store, id: crypto.randomUUID(), created_at: new Date().toISOString() } as Store;
    localStorage.setItem(STORES_STORAGE_KEY, JSON.stringify([...stores, newStore]));
    return newStore;
  },

  async ingestSales(file: File, apiKey: string): Promise<IngestionResponse> {
    return { status: 'success', message: 'Archivo procesado', records_processed: 10 };
  },

  async getUsers(): Promise<User[]> {
    const stored = localStorage.getItem(USERS_STORAGE_KEY);
    return stored ? JSON.parse(stored) : [];
  },

  async createUser(user: Partial<User>): Promise<User> {
    const users = await this.getUsers();
    const newUser = { ...user, id: crypto.randomUUID(), estado: 'activo', created_at: new Date().toISOString() } as User;
    localStorage.setItem(USERS_STORAGE_KEY, JSON.stringify([...users, newUser]));
    return newUser;
  },

  async toggleUserStatus(userId: string): Promise<void> {
    const users = await this.getUsers();
    const updated = users.map(u => u.id === userId ? { ...u, estado: u.estado === 'activo' ? 'inactivo' : 'activo' } as User : u);
    localStorage.setItem(USERS_STORAGE_KEY, JSON.stringify(updated));
  }
};
