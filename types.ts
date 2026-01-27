
export interface SaleReport {
  local_id: string;
  local_nombre: string;
  total_bruto: number;
  total_impuestos: number;
  total_neto: number;
  mall_nombre: string;
}

export interface IngestionResponse {
  message: string;
  records_processed: number;
  status: 'success' | 'error';
}

export interface DateRange {
  startDate: string;
  endDate: string;
}

export interface KPIData {
  ventas_totales_bruto: number;
  ventas_totales_neto: number;
  transacciones: number;
  ticket_promedio: number;
  variacion_ventas: number;
  top_locales: { name: string; total: number }[];
  ventas_por_dia: { fecha: string; total: number }[];
  ventas_por_rubro: { name: string; value: number }[];
}

export type UserRole = 'admin' | 'auditor' | 'mall_manager';

export interface User {
  id: string;
  nombre: string;
  email: string;
  rol: UserRole;
  estado: 'activo' | 'inactivo';
  ultimo_acceso?: string;
  created_at: string;
}

export interface RoleConfig {
  id: UserRole;
  nombre: string;
  permisos: string[];
}

export type ImportProtocol = 'FTP' | 'SFTP' | 'LOCAL';
export type FileType = 'CSV' | 'TXT' | 'JSON' | 'XML';
export type ImportFrequency = 'cada_hora' | 'cada_2_horas' | 'hora_especifica' | 'manual';
export type PostProcessAction = 'ninguna' | 'eliminar' | 'renombrar';

export interface ImportConfig {
  id: string;
  nombre: string;
  protocolo: ImportProtocol;
  host: string;
  puerto: number;
  usuario: string;
  ruta_remota: string;
  tipo_archivo: FileType;
  frecuencia: ImportFrequency;
  hora_especifica?: string;
  accion_post_procesado: PostProcessAction;
  prefijo_renombrado?: string;
  estado: 'activo' | 'pausado';
  ultima_ejecucion?: string;
  resultado_ultimo?: 'exito' | 'error';
  mapping: Record<string, string>; // Estructura: internal_field -> external_column_name
}
