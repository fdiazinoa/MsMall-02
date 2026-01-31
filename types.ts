
export interface SaleReport {
  local_id: string;
  local_nombre: string;
  total_bruto: number;
  total_impuestos: number;
  total_neto: number;
  mall_nombre: string;
}

export interface SaleDetail {
  id: string;
  fecha: string;
  hora: string;
  factura_no: string;
  total_bruto: number;
  total_impuestos: number;
  total_neto: number;
  local_id: string;
  comprobante?: string;
  hora_transaccion?: string;
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
  ventas_por_tienda_completo?: Record<string, number>;
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
  renta_fija?: number;
  breakpoint_venta?: number;
  porcentaje_variable?: number;
}

export interface RoleConfig {
  id: UserRole;
  nombre: string;
  permisos: string[];
}

export type ImportProtocol = 'FTP' | 'SFTP' | 'LOCAL';
export type FileType = 'CSV' | 'TXT' | 'JSON' | 'XML';
export type ImportFrequency = 'cada_hora' | 'cada_2_horas' | 'hora_especifica' | 'manual' | 'daily_batch';
export type PostProcessAction = 'ninguna' | 'eliminar' | 'renombrar' | 'NINGUNA' | 'RENOMBRAR_PROCESADO' | 'ELIMINAR';
export type ExecutionMode = 'MANUAL' | 'AUTOMATICO';

export interface LoadLog {
  id: string;
  fecha_hora: string;
  local_nombre: string;
  archivo: string;
  estado: 'exito' | 'error' | 'no_encontrado';
  mensaje: string;
  batch_id?: string;
}

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
  constants?: Record<string, string>;
  password?: string;
  tipo_ejecucion?: ExecutionMode;
  frecuencia_cron?: string;
}
