
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

export interface SegmentStoreDetail {
  name: string;
  total: number;
  total_neto: number;
  transacciones: number;
  ticket_promedio: number;
  participacion: number;
}

export interface KPIData {
  ventas_totales_bruto: number;
  ventas_totales_neto: number;
  transacciones: number;
  ticket_promedio: number;
  variacion_ventas: number;
  top_locales: { name: string; total: number }[];
  ventas_por_dia: { fecha: string; total: number }[];
  ventas_por_tipo_negocio: { name: string; value: number }[];
  ventas_por_rubro: { name: string; value: number }[];
  ventas_por_tipo_negocio_top_locales?: Record<string, SegmentStoreDetail[]>;
  ventas_por_rubro_top_locales?: Record<string, SegmentStoreDetail[]>;
  ventas_por_tienda_completo?: Record<string, number>;
}

export type UserRole = 'admin' | 'it' | 'tic' | 'auditor' | 'mall_manager';

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

export type ImportProtocol = 'FTP' | 'SFTP' | 'LOCAL' | 'WEBSERVICE' | 'API';
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
  fecha_corte_importacion?: string | null;
  mapping: Record<string, string>; // Estructura: internal_field -> external_column_name
  constants?: Record<string, string>;
  password?: string;
  tipo_ejecucion?: ExecutionMode;
  frecuencia_cron?: string;
}

export interface RemoteConnection {
  id: string;
  mall_id: string;
  nombre: string;
  protocolo: ImportProtocol;
  host: string;
  puerto: number;
  usuario: string;
  password: string;
  password_masked?: string;
  has_password?: boolean;
  ruta_base?: string;
  created_at?: string;
}

export interface ConnectionMonitorRun {
  id: string;
  mall_id: string;
  local_id?: string | null;
  connection_id?: string | null;
  run_type: 'scheduled' | 'manual';
  status: 'ok' | 'fail' | 'partial';
  error_code?: 'auth_error' | 'timeout' | 'endpoint_down' | 'validation_error' | 'unknown_error' | null;
  error_message?: string | null;
  started_at: string;
  finished_at: string;
  duration_ms: number;
  created_by?: string | null;
  created_at?: string | null;
}

export interface ConnectionMonitorStatusResponse {
  mall_id: string;
  summary: {
    total: number;
    ok: number;
    fail: number;
    partial: number;
    pending?: number;
  };
  recent_runs: ConnectionMonitorRun[];
  connections: Array<{
    id: string;
    nombre: string;
    protocolo: ImportProtocol | string;
    host: string;
    last_run?: ConnectionMonitorRun | null;
  }>;
}

export interface ConnectionMonitorFailuresResponse {
  mall_id: string;
  date: string;
  count: number;
  failures: ConnectionMonitorRun[];
}

export interface ConnectionRetryActionResponse {
  status: string;
  connection_id: string;
  mall_id?: string;
  run: ConnectionMonitorRun;
  retry_attempt?: Record<string, any> | null;
  policy: Record<string, any>;
}

export interface ConnectionRetryBatchResponse {
  status: string;
  mall_id: string;
  date: string;
  requested: number;
  limit: number;
  retried_ok: number;
  retried_fail: number;
  skipped: number;
  results: any[];
}

export interface ResendMessagingStatus {
  provider: 'resend';
  domain: string;
  from_email: string;
  from_name: string;
  configured: boolean;
  api_key_env: string;
}

export interface ResendTestMessageResponse {
  status: string;
  id?: string;
  to: string;
  from_email: string;
  domain: string;
  message: string;
}

export interface ResendSenderConfigPayload {
  from_email: string;
  from_name: string;
}

export interface MissingDaysEmailSettings {
  id?: string;
  mall_id: string;
  notification_type: 'missing_days_audit';
  enabled: boolean;
  weekdays: number[];
  send_time: string;
  lookback_days: number;
  send_only_with_gaps: boolean;
  cc_emails: string[];
  created_at?: string;
  updated_at?: string;
}

export interface MissingDaysSendNowResponse {
  status: string;
  mall_id: string;
  fecha_inicio: string;
  fecha_fin: string;
  requested: number;
  sent: number;
  skipped: number;
  failed: number;
  results: Array<{
    local_id: string;
    local_nombre: string;
    email?: string | null;
    status: 'sent' | 'skipped' | 'failed';
    missing_days: number;
    reason?: string;
    resend_id?: string | null;
  }>;
  message: string;
}

export type CopilotProvider = 'openai' | 'gemini';

export interface CopilotSettings {
  enabled: boolean;
  provider: CopilotProvider;
  model: string;
  api_key_configured: boolean;
  api_key_masked?: string;
  available: boolean;
}

export interface CopilotSettingsPayload {
  enabled: boolean;
  provider: CopilotProvider;
  model?: string;
  api_key?: string;
  clear_api_key?: boolean;
}

export interface CopilotChatMessage {
  role: 'user' | 'assistant';
  content: string;
  attachments?: CopilotAttachment[];
  email_actions?: CopilotEmailAction[];
  emailActions?: CopilotEmailAction[];
}

export interface CopilotAttachment {
  id: string;
  filename: string;
  mime_type: string;
  download_url: string;
  expires_at?: string;
  label?: string;
  report_type?: string;
  format?: 'xlsx' | 'pdf' | string;
  row_count?: number;
}

export interface CopilotChatResponse {
  answer: string;
  provider: CopilotProvider;
  model: string;
  context_generated_at?: string;
  sources: string[];
  attachments?: CopilotAttachment[];
  email_actions?: CopilotEmailAction[];
  emailActions?: CopilotEmailAction[];
  clarification?: {
    required: boolean;
    intent?: string;
    missing_fields?: string[];
    options?: string[];
  };
}

export interface CopilotEmailAction {
  id: string;
  recipients: string[];
  subject: string;
  report_type?: string;
  row_count?: number;
  attachment_count?: number;
  expires_at?: string;
}

export interface CopilotEmailSendResponse {
  sent: Array<{ email: string; resend_id?: string | null }>;
  subject: string;
  attachment_count: number;
}

export type OperationalFindingSeverity = 'INFO' | 'WARNING' | 'HIGH' | 'CRITICAL';
export type OperationalFindingStatus = 'OPEN' | 'ACKNOWLEDGED' | 'RESOLVED' | 'IGNORED';
export type OperationalFindingSource = 'FTP' | 'SFTP' | 'WEBSERVICE' | 'WORKER' | 'SALES_AUDIT' | 'MISSING_DAYS';

export interface OperationalFinding {
  id: string;
  mall_id: string;
  local_id?: string | null;
  local_name?: string | null;
  type: string;
  severity: OperationalFindingSeverity;
  title: string;
  description: string;
  evidence: Record<string, any>;
  root_cause?: string | null;
  recommendation?: string | null;
  confidence: number;
  priority_score?: number;
  status: OperationalFindingStatus;
  source: OperationalFindingSource;
  detected_at: string;
  resolved_at?: string | null;
  assigned_to?: string | null;
  notified_to?: string[];
  metadata?: Record<string, any>;
  fingerprint?: string;
  updated_at?: string;
}

export interface OperationsAuditorRun {
  id?: string;
  mall_id: string;
  status: string;
  started_at?: string;
  finished_at?: string;
  duration_ms: number;
  findings_created: number;
  findings_updated: number;
  errors?: Array<Record<string, any>>;
  metadata?: Record<string, any>;
  created_by?: string | null;
}

export interface OperationsFindingsResponse {
  findings: OperationalFinding[];
  summary: {
    total_open: number;
    critical: number;
    high: number;
    warning: number;
    info: number;
    affected_locals: number;
    by_severity: Record<string, number>;
    by_source: Record<string, number>;
    last_run_at?: string | null;
    last_run_status?: string | null;
  };
  last_run?: OperationsAuditorRun | null;
}

export interface OperationsAuditorRunResponse {
  status: string;
  mall_id: string;
  findings_created: number;
  findings_updated: number;
  findings_detected: number;
  duration_ms: number;
  errors: Array<Record<string, any>>;
  run?: OperationsAuditorRun;
}

export interface OperationsIntelligenceResponse {
  health: 'VERDE' | 'AMARILLO' | 'ROJO' | string;
  summary: {
    total_open?: number;
    critical?: number;
    high?: number;
    warning?: number;
    info?: number;
    affected_locals?: number;
    observations_24h?: number;
    active_patterns?: number;
    by_severity?: Record<string, number>;
    [key: string]: any;
  };
  open_findings: OperationalFinding[];
  recent_observations: Array<{
    id?: string;
    observation_type: string;
    observation: string;
    conclusion?: string | null;
    recommendation?: string | null;
    confidence?: number;
    created_at: string;
    local_id?: string | null;
  }>;
  patterns: Array<{
    id?: string;
    pattern_type: string;
    pattern_name: string;
    description?: string | null;
    occurrences: number;
    confidence?: number;
    last_seen?: string;
  }>;
  operational_digest?: {
    generated_at?: string;
    summary_text?: string;
    top_priority?: string;
    recommended_action?: string;
    new_findings?: number;
    critical_findings?: number;
    high_findings?: number;
  } | null;
  changes_since_last_audit?: Record<string, any>;
  operational_health?: {
    monitored_locations?: number;
    healthy_locations?: number;
    attention_required?: number;
    active_incidents?: number;
    locations?: Array<{
      local_id?: string | null;
      local_name: string;
      score: number;
      status: string;
      last_activity?: string | null;
      missing_days?: number;
      import_failures?: number;
      action?: string;
      priority_score?: number;
    }>;
  };
  priority_locations?: Array<{
    local_id?: string | null;
    local_name: string;
    reason: string;
    action: string;
    priority_score?: number;
    severity?: string;
  }>;
  locations_without_sales?: {
    count?: number;
    items?: OperationalFinding[];
  };
  missing_days_summary?: {
    count?: number;
    days_missing?: number;
    items?: OperationalFinding[];
  };
  import_failures_summary?: {
    count?: number;
    items?: OperationalFinding[];
  };
  recommended_actions?: Array<{
    local_name: string;
    problem: string;
    action: string;
    priority_score?: number;
  }>;
}

export type SecurityTokenType = 'app' | 'exporter';
export type SecurityTokenStatus = 'active' | 'disabled' | 'revoked';

export interface SecurityServiceAccount {
  id: string;
  name?: string | null;
  mall_id: string;
  local_id?: string | null;
  token_type: 'exporter';
  client_id: string;
  scopes: string[] | string;
  status: SecurityTokenStatus;
  created_by?: string | null;
  created_at: string;
  updated_at?: string;
  last_used_at?: string | null;
  last_used_ip?: string | null;
  last_used_ua?: string | null;
  active_tokens?: number;
  total_tokens?: number;
  client_secret?: string; // one-time reveal only
  warning?: string;
}

export interface SecurityApiToken {
  id: string;
  mall_id: string;
  local_id?: string | null;
  token_type: SecurityTokenType;
  scopes: string[] | string;
  jti: string;
  access_expires_at?: string | null;
  refresh_expires_at?: string | null;
  status: SecurityTokenStatus;
  created_by?: string | null;
  service_account_id?: string | null;
  last_used_at?: string | null;
  last_used_ip?: string | null;
  last_used_ua?: string | null;
  revoked_at?: string | null;
  revoked_by?: string | null;
  revoke_reason?: string | null;
  created_at: string;
  updated_at?: string;
}

export interface SecurityTokenPairReveal {
  access_token: string;
  refresh_token?: string;
  token_type: string;
  expires_in: number | null;
  refresh_expires_in?: number;
  token_id: string;
  jti: string;
  scope: string[] | string;
  mall_id: string;
  local_id?: string | null;
  token_kind: SecurityTokenType;
}

export type LoadLogStatus = 'exito' | 'parcial' | 'error' | 'no_encontrado' | string;
export type LoadLogChannel = 'FTP' | 'SFTP' | 'WebService' | 'API' | string;

export interface LoadLogDetail {
  linea?: number;
  error: string;
  [key: string]: any;
}

export interface LoadLogEntry {
  id: number | string;
  fecha_hora: string;
  mall_id?: string | null;
  mall_nombre?: string | null;
  local_id?: string | null;
  local_nombre?: string | null;
  archivo?: string | null;
  estado: LoadLogStatus;
  mensaje: string;
  batch_id?: string | null;
  detalles?: LoadLogDetail[];
  canal?: LoadLogChannel | null;
  records_processed?: number | null;
  error_count?: number | null;
  metadata?: Record<string, any> | null;
}

export interface SecurityTokenAuditLogEntry {
  id: number | string;
  token_id?: string | null;
  event_type: 'issued' | 'refreshed' | 'revoked' | 'used' | 'failed' | string;
  mall_id?: string | null;
  mall_nombre?: string | null;
  local_id?: string | null;
  local_nombre?: string | null;
  ip?: string | null;
  ua?: string | null;
  metadata?: Record<string, any>;
  created_at: string;
}

export interface SecurityExporterWebserviceConfig {
  id?: string;
  mall_id: string;
  local_id: string;
  enabled: boolean;
  contract_type: 'msmall_sales_v1' | string;
  default_granularity: 'transaction' | 'daily' | string;
  allow_transaction: boolean;
  allow_daily: boolean;
  strict_validation: boolean;
  notes?: string | null;
  updated_by?: string | null;
  created_at?: string;
  updated_at?: string;
}
