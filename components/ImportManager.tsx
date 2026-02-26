
import React, { useState, useEffect, useMemo, useRef } from 'react';
import { useAuth } from '../context/AuthProvider';
import { ApiService } from '../api';
// Fix: Import types from '../types' instead of '../api'
import { ImportConfig, ImportProtocol, RemoteConnection, SecurityExporterWebserviceConfig } from '../types';
import { SmartMappingModal } from './SmartMappingModal';
import MappingModal from './MappingModal';
import {
  Server, Plus, Play, Trash2, Settings2,
  ArrowRightLeft, CheckCircle2, XCircle, Clock,
  Key, Globe, FolderOpen, Database, RefreshCw, AlertCircle, FileSearch, FileText, Wand2, RotateCcw,
  LayoutGrid, List
} from 'lucide-react';

const STANDARD_FIELDS = [
  { key: 'factura_numero', label: 'Nº Factura / Boleta', required: true },
  { key: 'fecha_venta', label: 'Fecha Venta', required: true },
  { key: 'local_codigo', label: 'Código Local', required: true },
  { key: 'total_bruto', label: 'Total Bruto', required: true },
  { key: 'total_impuestos', label: 'Impuestos', required: false },
  { key: 'total_neto', label: 'Total Neto', required: false },
  { key: 'comprobante', label: 'Comprobante', required: false },
  { key: 'hora_transaccion', label: 'Hora Transacción', required: false }
];

const createDefaultImportConfig = (): ImportConfig => ({
  id: '',
  nombre: '',
  protocolo: 'SFTP',
  host: '',
  puerto: 22,
  usuario: '',
  ruta_remota: '.',
  tipo_archivo: 'CSV',
  frecuencia: 'manual',
  accion_post_procesado: 'ninguna',
  estado: 'activo',
  mapping: {
    factura_numero: '',
    fecha_venta: '',
    local_codigo: '',
    total_bruto: '',
    total_impuestos: '',
    total_neto: '',
    comprobante: '',
    hora_transaccion: ''
  },
  constants: {},
  password: ''
});

const createDefaultExporterWebserviceDraft = () => ({
  enabled: true,
  contract_type: 'msmall_sales_v1' as const,
  default_granularity: 'transaction' as 'transaction' | 'daily',
  allow_transaction: true,
  allow_daily: true,
  strict_validation: true,
  notes: ''
});

interface ImportManagerProps {
  initialSection?: 'ftp' | 'webservice';
}

export const ImportManager: React.FC<ImportManagerProps> = ({ initialSection = 'ftp' }) => {
  const { currentMall, isAdmin, isTic, session } = useAuth();
  const canManageImports = isAdmin || isTic;
  const authToken = session?.access_token || '';
  const [configs, setConfigs] = useState<ImportConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [syncingId, setSyncingId] = useState<string | null>(null);
  const [testingConnection, setTestingConnection] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [activeStep, setActiveStep] = useState(1);
  const [tempPassword, setTempPassword] = useState('');
  const [remoteConnections, setRemoteConnections] = useState<RemoteConnection[]>([]);
  const [selectedConnectionId, setSelectedConnectionId] = useState('');

  // Explorer State
  const [showExplorer, setShowExplorer] = useState(false);
  const [explorerPath, setExplorerPath] = useState('.');
  const [explorerItems, setExplorerItems] = useState<{ nombre: string, ruta: string, es_dir: boolean }[]>([]);
  const [explorerLoading, setExplorerLoading] = useState(false);
  const [browserFilesSelection, setBrowserFilesSelection] = useState<{
    count: number;
    names: string[];
  } | null>(null);

  // Mapping Helper State
  const [remoteHeaders, setRemoteHeaders] = useState<string[]>([]);
  const [fetchingHeaders, setFetchingHeaders] = useState(false);
  const [showSmartMapping, setShowSmartMapping] = useState(false);
  const [selectedFilePreview, setSelectedFilePreview] = useState<{
    filename: string;
    lines: string[];
    analysisType?: string | null;
    detectedDelimiter?: string | null;
    detectedHasHeader?: boolean | null;
  } | null>(null);

  // Manual Execution Modal State
  const [showManualModal, setShowManualModal] = useState(false);
  const [manualFiles, setManualFiles] = useState<{ nombre: string, fecha: string, tamano: number }[]>([]);
  const [manualLoading, setManualLoading] = useState(false);
  const [executingFile, setExecutingFile] = useState<string | null>(null);
  const [unmarkingFile, setUnmarkingFile] = useState<string | null>(null); // Track file being unmarked
  const [activeConfigId, setActiveConfigId] = useState<string | null>(null);
  const [fileStatuses, setFileStatuses] = useState<Record<string, 'success' | 'error' | 'idle'>>({});
  const [batchMask, setBatchMask] = useState<string>('*');
  const [batchLimit, setBatchLimit] = useState<number>(30);
  const initialBatchProgress = {
    running: false,
    total: 0,
    processed: 0,
    success: 0,
    failed: 0,
    skipped: 0,
    currentFile: '',
    message: ''
  };
  const [batchProgress, setBatchProgress] = useState<{
    running: boolean;
    total: number;
    processed: number;
    success: number;
    failed: number;
    skipped: number;
    currentFile: string;
    message: string;
  }>(initialBatchProgress);
  const batchCancelRef = useRef(false);
  const browserFilesInputRef = useRef<HTMLInputElement | null>(null);
  const exporterWebservicePanelRef = useRef<HTMLDivElement | null>(null);
  const [viewMode, setViewMode] = useState<'cards' | 'list'>('cards');

  // Progress Modal State
  const [showProgressModal, setShowProgressModal] = useState(false);
  const [progressStep, setProgressStep] = useState<'downloading' | 'processing' | 'inserting' | 'complete' | 'error'>('downloading');
  const [progressMessage, setProgressMessage] = useState('');
  const [progressRecords, setProgressRecords] = useState(0);

  // Mapping Modal State
  const [showMappingModal, setShowMappingModal] = useState(false);
  const [mappingData, setMappingData] = useState<{
    fileHeaders: string[],
    suggestedMapping: Record<string, any>,
    currentMapping: Record<string, string>,
    sampleRow: Record<string, any>,
    filename: string
  } | null>(null);

  const [editingConfig, setEditingConfig] = useState<ImportConfig>(createDefaultImportConfig());

  const [availableStores, setAvailableStores] = useState<any[]>([]);
  const [exporterWsConfigs, setExporterWsConfigs] = useState<SecurityExporterWebserviceConfig[]>([]);
  const [exporterWsLoading, setExporterWsLoading] = useState(false);
  const [exporterWsSaving, setExporterWsSaving] = useState(false);
  const [selectedExporterLocalId, setSelectedExporterLocalId] = useState('');
  const [exporterWsDraft, setExporterWsDraft] = useState(createDefaultExporterWebserviceDraft());
  const [exporterWsError, setExporterWsError] = useState<string | null>(null);

  const loadConfigs = async () => {
    if (!currentMall?.id) return;
    setLoading(true);
    const data = await ApiService.getImportConfigs(currentMall.id);
    setConfigs(data);
    setLoading(false);
  };

  const loadStores = async () => {
    const stores = await ApiService.getStores();
    setAvailableStores(stores);
  };

  const loadRemoteConnections = async () => {
    if (!currentMall?.id) return;
    try {
      const items = await ApiService.getRemoteConnections(currentMall.id, authToken);
      setRemoteConnections(items);
    } catch (error: any) {
      console.error("Error loading remote connections:", error);
      setRemoteConnections([]);
    }
  };

  const loadExporterWebserviceConfigs = async () => {
    if (!currentMall?.id || !authToken) {
      setExporterWsConfigs([]);
      return;
    }
    setExporterWsLoading(true);
    setExporterWsError(null);
    try {
      const rows = await ApiService.getSecurityExporterWebserviceConfigs(authToken, { mall_id: currentMall.id });
      setExporterWsConfigs(rows);
    } catch (error: any) {
      console.error("Error loading exporter webservice configs:", error);
      setExporterWsConfigs([]);
      setExporterWsError(error?.message || 'No se pudo cargar la configuración webservice ERP.');
    } finally {
      setExporterWsLoading(false);
    }
  };

  useEffect(() => {
    if (currentMall) {
      loadConfigs();
      loadStores();
      loadRemoteConnections();
    }
  }, [currentMall]);

  useEffect(() => {
    if (currentMall?.id && authToken) {
      loadExporterWebserviceConfigs();
    } else {
      setExporterWsConfigs([]);
    }
  }, [currentMall?.id, authToken]);

  useEffect(() => {
    if (initialSection !== 'webservice') return;
    const id = window.setTimeout(() => {
      exporterWebservicePanelRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 60);
    return () => window.clearTimeout(id);
  }, [initialSection, loading, configs.length]);

  useEffect(() => {
    if (!selectedExporterLocalId && availableStores.length > 0) {
      setSelectedExporterLocalId(String(availableStores[0].id || ''));
    }
  }, [availableStores, selectedExporterLocalId]);

  useEffect(() => {
    if (!selectedExporterLocalId) {
      setExporterWsDraft(createDefaultExporterWebserviceDraft());
      return;
    }
    const existing = exporterWsConfigs.find((row) => String(row.local_id) === String(selectedExporterLocalId));
    if (!existing) {
      setExporterWsDraft(createDefaultExporterWebserviceDraft());
      return;
    }
    setExporterWsDraft({
      enabled: !!existing.enabled,
      contract_type: 'msmall_sales_v1',
      default_granularity: existing.default_granularity === 'daily' ? 'daily' : 'transaction',
      allow_transaction: existing.allow_transaction !== false,
      allow_daily: existing.allow_daily !== false,
      strict_validation: existing.strict_validation !== false,
      notes: existing.notes || ''
    });
  }, [selectedExporterLocalId, exporterWsConfigs]);

  const getStoreLabel = (localId?: string | null) => {
    if (!localId) return 'Local no definido';
    const store = (availableStores || []).find((s) => String(s.id) === String(localId));
    if (!store) return localId;
    return `${store.nombre} (${store.codigo_interno || 'sin código'})`;
  };

  const exporterWsRowsByLocal = useMemo(() => {
    const byLocal = new Map<string, SecurityExporterWebserviceConfig>();
    (exporterWsConfigs || []).forEach((row) => {
      if (!row?.local_id) return;
      byLocal.set(String(row.local_id), row);
    });

    const storeRows = [...(availableStores || [])]
      .sort((a, b) => String(a?.nombre || '').localeCompare(String(b?.nombre || '')))
      .map((store) => {
        const localId = String(store?.id || '');
        return { localId, store, config: byLocal.get(localId) || null };
      });

    const knownIds = new Set(storeRows.map((row) => row.localId));
    const orphanRows = (exporterWsConfigs || [])
      .filter((row) => row?.local_id && !knownIds.has(String(row.local_id)))
      .map((row) => ({
        localId: String(row.local_id),
        store: null,
        config: row,
      }));

    return [...storeRows, ...orphanRows];
  }, [availableStores, exporterWsConfigs]);

  const saveExporterWebserviceConfig = async () => {
    if (!currentMall?.id) {
      alert('Debe seleccionar un mall antes de configurar webservice ERP.');
      return;
    }
    if (!authToken) {
      alert('No hay sesión activa para guardar la configuración webservice ERP.');
      return;
    }
    if (!selectedExporterLocalId) {
      alert('Seleccione un local para configurar el webservice ERP.');
      return;
    }
    setExporterWsSaving(true);
    try {
      const saved = await ApiService.upsertSecurityExporterWebserviceConfig(
        selectedExporterLocalId,
        {
          mall_id: currentMall.id,
          enabled: exporterWsDraft.enabled,
          contract_type: 'msmall_sales_v1',
          default_granularity: exporterWsDraft.default_granularity,
          allow_transaction: exporterWsDraft.allow_transaction,
          allow_daily: exporterWsDraft.allow_daily,
          strict_validation: exporterWsDraft.strict_validation,
          notes: (exporterWsDraft.notes || '').trim() || null
        },
        authToken
      );
      setExporterWsConfigs((prev) => {
        const next = prev.filter((row) => String(row.local_id) !== String(saved.local_id));
        return [saved, ...next];
      });
      setExporterWsError(null);
      alert(`Configuración webservice ERP guardada para ${getStoreLabel(saved.local_id)}.`);
    } catch (error: any) {
      console.error("Error saving exporter webservice config:", error);
      setExporterWsError(error?.message || 'No se pudo guardar la configuración webservice ERP.');
      alert(error?.message || 'No se pudo guardar la configuración webservice ERP.');
    } finally {
      setExporterWsSaving(false);
    }
  };

  const renderExporterWebservicePanel = () => (
    <div className="grid grid-cols-1 xl:grid-cols-[1.1fr_0.9fr] gap-4">
      <div className="bg-white border border-emerald-100 rounded-2xl shadow-sm overflow-hidden">
        <div className="px-5 py-4 border-b border-emerald-50 bg-gradient-to-r from-emerald-50 to-white">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h3 className="text-sm font-bold text-slate-800 flex items-center gap-2">
                <ArrowRightLeft size={16} className="text-emerald-600" />
                ERP Webservice (MsExportador)
              </h3>
              <p className="text-xs text-slate-500 mt-1">
                Configura por local la recepción de ventas vía webservice. Este canal es independiente de FTP/SFTP.
              </p>
            </div>
            <button
              type="button"
              onClick={loadExporterWebserviceConfigs}
              disabled={exporterWsLoading || !currentMall?.id || !authToken}
              className="px-3 py-2 rounded-lg border border-slate-200 text-xs font-semibold text-slate-600 hover:bg-slate-50 disabled:opacity-50 flex items-center gap-2"
            >
              <RefreshCw size={13} className={exporterWsLoading ? 'animate-spin' : ''} />
              Recargar
            </button>
          </div>
        </div>

        <div className="p-5 space-y-4">
          {exporterWsError && (
            <div className="flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
              <AlertCircle size={14} className="mt-0.5 shrink-0" />
              <span>{exporterWsError}</span>
            </div>
          )}

          <div>
            <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1.5">
              Local
            </label>
            <select
              className="w-full px-4 py-2.5 rounded-xl border border-slate-200 outline-none bg-white font-medium text-sm focus:ring-2 focus:ring-emerald-500"
              value={selectedExporterLocalId}
              onChange={(e) => setSelectedExporterLocalId(e.target.value)}
            >
              <option value="">-- Seleccionar local --</option>
              {(availableStores || []).map((store) => (
                <option key={store.id} value={store.id}>
                  {store.nombre} ({store.codigo_interno || 'sin código'})
                </option>
              ))}
            </select>
            <p className="text-[11px] text-slate-500 mt-2">
              Se guarda por local. Selecciona un local, guarda y luego cambia al siguiente para configurarlo.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <label className="flex items-center gap-3 p-3 rounded-xl border border-slate-200 bg-slate-50">
              <input
                type="checkbox"
                checked={exporterWsDraft.enabled}
                onChange={(e) => setExporterWsDraft((prev) => ({ ...prev, enabled: e.target.checked }))}
                className="rounded border-slate-300 text-emerald-600 focus:ring-emerald-500"
              />
              <span className="text-sm font-medium text-slate-700">Canal habilitado</span>
            </label>

            <div>
              <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1.5">
                Granularidad por defecto
              </label>
              <select
                className="w-full px-4 py-2.5 rounded-xl border border-slate-200 outline-none bg-white font-medium text-sm focus:ring-2 focus:ring-emerald-500"
                value={exporterWsDraft.default_granularity}
                onChange={(e) => setExporterWsDraft((prev) => ({ ...prev, default_granularity: e.target.value as 'transaction' | 'daily' }))}
              >
                <option value="transaction">Transacción</option>
                <option value="daily">Resumen diario</option>
              </select>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <label className="flex items-center gap-2 p-3 rounded-xl border border-slate-200 bg-white text-xs font-medium text-slate-700">
              <input
                type="checkbox"
                checked={exporterWsDraft.allow_transaction}
                onChange={(e) => setExporterWsDraft((prev) => ({ ...prev, allow_transaction: e.target.checked }))}
                className="rounded border-slate-300 text-emerald-600 focus:ring-emerald-500"
              />
              Permitir transacción
            </label>
            <label className="flex items-center gap-2 p-3 rounded-xl border border-slate-200 bg-white text-xs font-medium text-slate-700">
              <input
                type="checkbox"
                checked={exporterWsDraft.allow_daily}
                onChange={(e) => setExporterWsDraft((prev) => ({ ...prev, allow_daily: e.target.checked }))}
                className="rounded border-slate-300 text-emerald-600 focus:ring-emerald-500"
              />
              Permitir resumen diario
            </label>
            <label className="flex items-center gap-2 p-3 rounded-xl border border-slate-200 bg-white text-xs font-medium text-slate-700">
              <input
                type="checkbox"
                checked={exporterWsDraft.strict_validation}
                onChange={(e) => setExporterWsDraft((prev) => ({ ...prev, strict_validation: e.target.checked }))}
                className="rounded border-slate-300 text-emerald-600 focus:ring-emerald-500"
              />
              Validación estricta
            </label>
          </div>

          <div>
            <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1.5">
              Notas
            </label>
            <textarea
              rows={3}
              className="w-full px-4 py-2.5 rounded-xl border border-slate-200 outline-none bg-white text-sm focus:ring-2 focus:ring-emerald-500"
              placeholder="Ej: ERP activo desde marzo, envío por transacción."
              value={exporterWsDraft.notes}
              onChange={(e) => setExporterWsDraft((prev) => ({ ...prev, notes: e.target.value }))}
            />
          </div>

          <div className="flex items-center justify-between gap-3 pt-2">
            <div className="text-xs text-slate-500">
              Contrato fijo: <span className="font-semibold text-slate-700">msmall_sales_v1</span>
            </div>
            <button
              type="button"
              onClick={saveExporterWebserviceConfig}
              disabled={exporterWsSaving || !selectedExporterLocalId || !currentMall?.id || !authToken}
              className="px-4 py-2 rounded-xl bg-emerald-600 text-white text-sm font-semibold hover:bg-emerald-700 disabled:opacity-50 flex items-center gap-2"
              title={selectedExporterLocalId ? `Guardar para ${getStoreLabel(selectedExporterLocalId)}` : 'Seleccione un local'}
            >
              {exporterWsSaving ? <RefreshCw size={14} className="animate-spin" /> : <CheckCircle2 size={14} />}
              {exporterWsSaving ? 'Guardando...' : 'Guardar Configuración'}
            </button>
          </div>
        </div>
      </div>

      <div className="bg-white border border-slate-200 rounded-2xl shadow-sm overflow-hidden">
        <div className="px-5 py-4 border-b border-slate-100 bg-slate-50/80">
          <h3 className="text-sm font-bold text-slate-800 flex items-center gap-2">
            <Database size={15} className="text-slate-500" />
            Estado Webservice por Local
          </h3>
          <p className="text-xs text-slate-500 mt-1">
            Se configura un local a la vez. Haz click en cualquier local para cargar su configuración en el formulario.
          </p>
        </div>

        <div className="p-4">
          {exporterWsLoading ? (
            <div className="text-sm text-slate-500 flex items-center gap-2">
              <RefreshCw size={14} className="animate-spin" />
              Cargando configuración webservice...
            </div>
          ) : exporterWsRowsByLocal.length === 0 ? (
            <div className="text-sm text-slate-500 border border-dashed border-slate-200 rounded-xl p-4">
              No hay locales disponibles para configurar en este mall.
            </div>
          ) : (
            <div className="space-y-2 max-h-[360px] overflow-y-auto pr-1">
              {exporterWsRowsByLocal.map((row) => {
                const { localId, store, config } = row;
                const isSelected = String(localId) === String(selectedExporterLocalId);
                const storeLabel = store
                  ? `${store.nombre} (${store.codigo_interno || 'sin código'})`
                  : `${localId} (local no encontrado)`;
                return (
                  <button
                    key={`erpws-${localId}`}
                    type="button"
                    onClick={() => setSelectedExporterLocalId(String(localId))}
                    className={`w-full text-left rounded-xl border px-3 py-3 transition-all ${
                      isSelected ? 'border-emerald-300 bg-emerald-50/70' : 'border-slate-200 bg-white hover:bg-slate-50'
                    }`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="text-sm font-semibold text-slate-800">{storeLabel}</div>
                        <div className="text-[11px] text-slate-500 mt-1">
                          {config
                            ? `${config.allow_transaction ? 'Transacción' : 'Sin transacción'} · ${config.allow_daily ? 'Daily' : 'Sin daily'} · Default ${config.default_granularity}`
                            : 'Sin configuración webservice guardada'}
                        </div>
                      </div>
                      <span className={`inline-flex items-center px-2 py-1 rounded-full text-[10px] font-bold ${
                        !config
                          ? 'bg-slate-100 text-slate-600'
                          : config.enabled
                            ? 'bg-emerald-100 text-emerald-700'
                            : 'bg-amber-100 text-amber-700'
                      }`}>
                        {!config ? 'SIN CONFIG' : config.enabled ? 'HABILITADO' : 'DESHABILITADO'}
                      </span>
                    </div>
                    {config?.notes && (
                      <div className="mt-2 text-xs text-slate-600 line-clamp-2">
                        {config.notes}
                      </div>
                    )}
                  </button>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );

  const closeFormDrawer = () => {
    setShowForm(false);
    setActiveStep(1);
    setTempPassword('');
    setSelectedConnectionId('');
    setShowExplorer(false);
    setBrowserFilesSelection(null);
    setSelectedFilePreview(null);
    setEditingConfig(createDefaultImportConfig());
  };

  const openNewConnectionDrawer = () => {
    setEditingConfig(createDefaultImportConfig());
    setTempPassword('');
    setSelectedConnectionId('');
    setBrowserFilesSelection(null);
    setActiveStep(1);
    setShowForm(true);
  };

  const openEditConnectionDrawer = (config: ImportConfig) => {
    setEditingConfig(config);
    setTempPassword(config.password || '');
    setBrowserFilesSelection(null);
    setActiveStep(1);
    setSelectedConnectionId('');
    setShowForm(true);
  };

  const resetManualExecutionState = () => {
    batchCancelRef.current = false;
    setManualFiles([]);
    setManualLoading(false);
    setExecutingFile(null);
    setUnmarkingFile(null);
    setFileStatuses({});
    setBatchMask('*');
    setBatchLimit(30);
    setBatchProgress(initialBatchProgress);
  };

  const closeManualModal = () => {
    setShowManualModal(false);
    setActiveConfigId(null);
    resetManualExecutionState();
  };

  const handleTestConnection = async () => {
    if (testingConnection) return;
    console.log("Iniciando prueba de conexión...");
    setTestingConnection(true);
    try {
      const result = await ApiService.testConnection(editingConfig, tempPassword, authToken);
      console.log("Resultado prueba recibida:", result);
      alert(result.message);
    } catch (error: any) {
      console.error("Error en handleTestConnection:", error);
      alert("Error inesperado en prueba de conexión: " + (error.message || error));
    } finally {
      console.log("Finalizando estado de prueba.");
      setTestingConnection(false);
    }
  };

  const applySavedConnection = (connectionId: string) => {
    setSelectedConnectionId(connectionId);
    if (!connectionId) return;
    const conn = remoteConnections.find(c => c.id === connectionId);
    if (!conn) return;

    setEditingConfig(prev => ({
      ...prev,
      protocolo: conn.protocolo,
      host: conn.host,
      puerto: conn.puerto,
      usuario: conn.usuario,
      ruta_remota: conn.ruta_base || prev.ruta_remota
    }));
    setTempPassword(conn.password || '');
  };

  const handleSaveCurrentAsConnection = async () => {
    if (!currentMall?.id) {
      alert("Selecciona un mall antes de guardar conexiones.");
      return;
    }
    if (editingConfig.protocolo === 'LOCAL') {
      alert("Las conexiones guardadas aplican solo para FTP/SFTP.");
      return;
    }
    if (!editingConfig.host || !editingConfig.usuario) {
      alert("Completa host y usuario antes de guardar la conexión.");
      return;
    }

    const suggestedName = `${editingConfig.nombre || 'Conexión'} - ${editingConfig.usuario}@${editingConfig.host}`;
    const name = window.prompt("Nombre para esta conexión guardada:", suggestedName)?.trim();
    if (!name) return;

    try {
      const saved = await ApiService.saveRemoteConnection({
        mall_id: currentMall.id,
        nombre: name,
        protocolo: editingConfig.protocolo,
        host: editingConfig.host.trim(),
        puerto: Number(editingConfig.puerto) || (editingConfig.protocolo === 'SFTP' ? 22 : 21),
        usuario: editingConfig.usuario.trim(),
        password: tempPassword || editingConfig.password || '',
        ruta_base: editingConfig.ruta_remota || '.'
      }, authToken);
      await loadRemoteConnections();
      setSelectedConnectionId(saved.id);
      alert("Conexión guardada correctamente.");
    } catch (error: any) {
      alert(`No se pudo guardar la conexión: ${error.message || error}`);
    }
  };

  const handleDeleteSavedConnection = async () => {
    if (!selectedConnectionId) {
      alert("Selecciona una conexión guardada para eliminar.");
      return;
    }
    if (!confirm("¿Eliminar esta conexión guardada?")) return;

    try {
      await ApiService.deleteRemoteConnection(selectedConnectionId, authToken);
      setSelectedConnectionId('');
      await loadRemoteConnections();
      alert("Conexión eliminada.");
    } catch (error: any) {
      alert(`No se pudo eliminar: ${error.message || error}`);
    }
  };

  const handleSave = async () => {
    // Validar mapeo mínimo

    const missing = STANDARD_FIELDS.filter(f => f.required && !editingConfig.mapping[f.key] && !editingConfig.constants?.[f.key]);
    if (missing.length > 0) {
      alert(`Faltan campos obligatorios en el mapeo: ${missing.map(m => m.label).join(', ')}`);
      return;
    }

    // Logic Check: If frequency is automated (not manual), path should likely be a folder, not a file
    const isAutomated = editingConfig.frecuencia !== 'manual';
    const looksLikeFile = editingConfig.ruta_remota.match(/\.[a-zA-Z0-9]+$/);

    if (isAutomated && looksLikeFile) {
      if (!confirm(`Advertencia: Has configurado una frecuencia automática (${editingConfig.frecuencia}) pero la ruta parece ser un archivo específico (${editingConfig.ruta_remota}).\n\nPara automatización, generalmente se debe apuntar a la CARPETA donde llegarán los nuevos archivos.\n\n¿Deseas continuar de todos modos?`)) {
        return;
      }
    }

    const configToSave = { ...editingConfig, password: tempPassword || editingConfig.password };
    try {
      await ApiService.saveImportConfig(configToSave, currentMall?.id);
      closeFormDrawer();
      loadConfigs();
    } catch (error: any) {
      console.error("Error saving config:", error);
      alert(`Error al guardar configuración: ${error.message || error}`);
    }
  };

  const refreshFileList = async (configId: string) => {
    const config = configs.find(c => c.id === configId);
    if (!config) return;

    setManualLoading(true);
    try {
      const files = await ApiService.listRemoteFiles(config, authToken);
      setManualFiles(files);
    } catch (error: any) {
      console.error(error);
      setManualFiles([]);
    } finally {
      setManualLoading(false);
    }
  };

  const stopManualBatch = () => {
    batchCancelRef.current = true;
    setBatchProgress(prev => ({
      ...prev,
      message: 'Deteniendo lote al finalizar el archivo actual...'
    }));
  };

  const handleExecuteManualBatch = async () => {
    if (!activeConfigId) return;
    const config = configs.find(c => c.id === activeConfigId);
    if (!config) return;
    if (!hasRequiredMapping(config)) {
      alert('Configura primero el mapeo obligatorio (Factura, Fecha, Código Local, Total Bruto) antes de procesar en lote.');
      return;
    }

    const safeLimit = Number.isFinite(batchLimit) && batchLimit > 0 ? Math.trunc(batchLimit) : 30;
    const candidates = filteredBatchCandidates.slice(0, safeLimit);
    const skipped = Math.max(filteredBatchCandidates.length - candidates.length, 0);

    if (candidates.length === 0) {
      alert('No hay archivos que coincidan con la máscara para procesar en lote.');
      return;
    }

    batchCancelRef.current = false;
    setBatchProgress({
      running: true,
      total: candidates.length,
      processed: 0,
      success: 0,
      failed: 0,
      skipped,
      currentFile: '',
      message: `Iniciando lote (${candidates.length} archivos)...`
    });

    let processed = 0;
    let success = 0;
    let failed = 0;

    for (const file of candidates) {
      if (batchCancelRef.current) break;

      setBatchProgress(prev => ({
        ...prev,
        currentFile: file.nombre,
        message: `Procesando ${file.nombre}...`
      }));

      try {
        const result = await ApiService.executeManualImport(config, file.nombre, authToken);
        const records = Number(result?.records_processed || 0);
        const ok = (result?.status === 'success' || result?.status === 'partial') && records > 0;

        if (ok) {
          success += 1;
          setFileStatuses(prev => ({ ...prev, [file.nombre]: 'success' }));
        } else {
          failed += 1;
          setFileStatuses(prev => ({ ...prev, [file.nombre]: 'error' }));
        }
      } catch (error) {
        failed += 1;
        setFileStatuses(prev => ({ ...prev, [file.nombre]: 'error' }));
      } finally {
        processed += 1;
        setBatchProgress(prev => ({
          ...prev,
          processed,
          success,
          failed
        }));
      }
    }

    const cancelled = batchCancelRef.current;
    setBatchProgress(prev => ({
      ...prev,
      running: false,
      currentFile: '',
      message: cancelled
        ? `Lote detenido. ${success} OK, ${failed} con error, ${processed}/${prev.total} procesados.`
        : `Lote completado. ${success} OK, ${failed} con error, ${processed}/${prev.total} procesados.`
    }));

    if (activeConfigId) {
      await refreshFileList(activeConfigId);
    }
  };

  const handleSyncNow = async (id: string, name: string) => {
    resetManualExecutionState();
    setActiveConfigId(id);
    const config = configs.find(c => c.id === id);
    if (!config) {
      alert("Configuración no encontrada.");
      return;
    }

    setShowManualModal(true);
    await refreshFileList(id);
  };

  const hasRequiredMapping = (config: ImportConfig) => {
    const requiredFields = ['factura_numero', 'fecha_venta', 'local_codigo', 'total_bruto'];
    return requiredFields.every(field => Boolean(config.mapping?.[field] || config.constants?.[field]));
  };

  const isHeaderEnabled = (config: ImportConfig) => (config.constants?.['_has_header'] ?? 'true') !== 'false';
  const getDataStartRow = (config: ImportConfig) => {
    const fallback = isHeaderEnabled(config) ? 2 : 1;
    const raw = Number(config.constants?.['_data_start_row']);
    return Number.isFinite(raw) && raw > 0 ? Math.trunc(raw) : fallback;
  };
  const formatDelimiter = (delimiter?: string | null) => {
    if (!delimiter) return 'No detectado';
    if (delimiter === '\t') return 'TAB';
    if (delimiter === ';') return '; (punto y coma)';
    if (delimiter === ',') return ', (coma)';
    if (delimiter === '|') return '| (pipe)';
    return delimiter;
  };

  const hasDataRowsInAnalysis = (analysis: any): boolean => {
    const sampleRow = analysis?.sample_row || {};
    const sampleHasValues = Object.values(sampleRow).some(v => String(v ?? '').trim() !== '');
    if (sampleHasValues) return true;

    const previewLines = Array.isArray(analysis?.raw_preview_lines)
      ? analysis.raw_preview_lines.filter((line: string) => String(line || '').trim() !== '')
      : [];
    const headerCount = Array.isArray(analysis?.csv_headers) ? analysis.csv_headers.length : 0;

    if (previewLines.length === 0) return false;
    if (previewLines.length === 1 && headerCount > 0) return false;
    return previewLines.length > 1;
  };

  const maskToRegex = (rawMask: string): RegExp => {
    const normalized = String(rawMask || '*').trim() || '*';
    const wildcardMask = normalized.replace(/%/g, '*');
    // Escape regex tokens first, then restore wildcard semantics for * and ?.
    const escaped = wildcardMask.replace(/[|\\{}()[\]^$+*?.]/g, '\\$&');
    const regexPattern = `^${escaped.replace(/\\\*/g, '.*').replace(/\\\?/g, '.')}$`;
    try {
      return new RegExp(regexPattern, 'i');
    } catch {
      // Never break rendering due to malformed masks.
      return /.*/i;
    }
  };

  const filteredBatchCandidates = useMemo(() => {
    const matcher = maskToRegex(batchMask);
    const nonProcessed = (manualFiles || []).filter((f) => !/^(PR_|ERR_)/i.test(f.nombre));
    const matched = nonProcessed.filter((f) => matcher.test(f.nombre));
    return matched.sort((a, b) => {
      const at = new Date(a.fecha).getTime();
      const bt = new Date(b.fecha).getTime();
      if (Number.isFinite(at) && Number.isFinite(bt) && at !== bt) return at - bt; // Oldest first
      return String(a.nombre || '').localeCompare(String(b.nombre || ''));
    });
  }, [manualFiles, batchMask]);

  const resolveProcessedCountFromLogs = async (config: ImportConfig, filename: string): Promise<number | null> => {
    try {
      const logs = await ApiService.getLoadLogs(currentMall?.id, authToken);
      const targetLog = (logs || []).find((log: any) =>
        log?.archivo === filename &&
        log?.local_nombre === config.nombre &&
        (log?.estado === 'exito' || log?.estado === 'parcial')
      );

      if (!targetLog?.mensaje) return null;

      const match = String(targetLog.mensaje).match(/(\d+)\s+registros/i);
      if (!match) return null;

      const parsed = Number(match[1]);
      return Number.isFinite(parsed) ? parsed : null;
    } catch (error) {
      console.warn("No se pudo resolver contador desde logs:", error);
      return null;
    }
  };

  const handleExecuteManualFile = async (filename: string) => {
    if (!activeConfigId) return;
    const config = configs.find(c => c.id === activeConfigId);
    if (!config) return;

    setExecutingFile(filename);
    setShowProgressModal(true);
    setProgressStep('downloading');
    setProgressMessage(`Conectando al servidor y descargando ${filename}...`);
    setProgressRecords(0);

    try {
      // Step 1: Analyze file structure to validate content and mapping readiness.
      console.log("Analizando estructura del archivo:", filename);
      setProgressStep('processing');
      setProgressMessage(`Analizando estructura del archivo...`);
      const analysis = await ApiService.analyzeSingleFile(config, filename, authToken);

      if (!hasDataRowsInAnalysis(analysis)) {
        const previewLines = Array.isArray(analysis?.raw_preview_lines)
          ? analysis.raw_preview_lines.filter((line: string) => String(line || '').trim() !== '')
          : [];

        if (previewLines.length === 0) {
          setProgressStep('error');
          setProgressMessage('⚠️ El archivo seleccionado no contiene filas de data para importar (vacío o solo encabezado).');
          setFileStatuses(prev => ({ ...prev, [filename]: 'error' }));
          return;
        }

        console.warn("Análisis preliminar sin filas detectadas, pero hay contenido crudo. Se intentará procesar.");
        setProgressStep('processing');
        setProgressMessage('⚠️ El análisis preliminar no detectó filas con certeza, intentando procesar el archivo...');
      }

      if (!hasRequiredMapping(config)) {
        const requiredFields = ['factura_numero', 'fecha_venta', 'local_codigo', 'total_bruto'];
        const currentMapping = analysis.current_mapping || {};
        const missingFields = requiredFields.filter(f => !currentMapping[f]);

        if (missingFields.length > 0 || (analysis.csv_headers || []).length === 0) {
          console.log("Mapeo incompleto o sin headers, mostrando modal");
          setShowProgressModal(false);
          setMappingData({
            fileHeaders: analysis.csv_headers,
            suggestedMapping: analysis.suggested_mapping,
            currentMapping: analysis.current_mapping,
            sampleRow: analysis.sample_row,
            filename: filename
          });
          setShowManualModal(false); // Close the manual files modal
          setShowMappingModal(true);
          setExecutingFile(null);
          return;
        }
      } else {
        console.log("Mapeo requerido detectado, omitiendo análisis remoto previo");
      }

      // Step 2: If mapping is OK, process directly
      console.log("Mapeo completo, procesando directamente");
      setProgressStep('inserting');
      setProgressMessage(`Procesando e insertando registros en la base de datos...`);

      const result = await ApiService.executeManualImport(config, filename, authToken);

      setProgressRecords(result.records_processed || 0);

      if (result.status === 'success' || result.status === 'partial') {
        setProgressStep('complete');
        setProgressMessage(result.message || `✅ Importación exitosa: ${result.records_processed} registros procesados`);
        setFileStatuses(prev => ({ ...prev, [filename]: 'success' }));

        // Auto-close after 3 seconds only on success
        setTimeout(() => {
          setShowProgressModal(false);
          if (activeConfigId) refreshFileList(activeConfigId);
        }, 3000);
      } else {
        setProgressStep('error');
        setProgressMessage(result.message || '❌ Error en la importación');
        setFileStatuses(prev => ({ ...prev, [filename]: 'error' }));
      }
    } catch (error: any) {
      const errorMsg = String(error?.message || error || '');
      console.error(error);

      if (
        errorMsg.includes('ERR_NETWORK_CHANGED') ||
        errorMsg.includes('Failed to fetch') ||
        errorMsg.includes('No se pudo confirmar la importación')
      ) {
        try {
          const latestFiles = await ApiService.listRemoteFiles(config, authToken);
          const renamedExists = latestFiles.some(f => f.nombre === `PR_${filename}`);
          const originalExists = latestFiles.some(f => f.nombre === filename);

          if (renamedExists && !originalExists) {
            const processedCount = await resolveProcessedCountFromLogs(config, filename);
            if (processedCount && processedCount > 0) {
              setProgressRecords(processedCount);
            }
            setProgressStep('complete');
            setProgressMessage(
              processedCount && processedCount > 0
                ? `Conexión cambiada durante la confirmación, pero el archivo se procesó correctamente (${processedCount} registros).`
                : 'Conexión cambiada durante la confirmación, pero el archivo quedó procesado (renombrado con PR_).'
            );
            setFileStatuses(prev => ({ ...prev, [filename]: 'success' }));
            setManualFiles(latestFiles);
            return;
          }
        } catch (checkErr) {
          console.warn("No se pudo verificar estado post error de red:", checkErr);
        }
      }

      setProgressStep('error');
      setProgressMessage("❌ Error en ejecución: " + (error.message || error));
      setFileStatuses(prev => ({ ...prev, [filename]: 'error' }));
    } finally {
      setExecutingFile(null);
      // Only auto-close if successful or partial, NOT on error
      // Check current progressStep is tricky here due to closure, so we rely on checks above/logic
      // Actually, we can just check if we are NOT in error state? 
      // It's safer to remove auto-close here and put it inside the success block above.
    }
  };

  const handleMappingConfirm = async (mapping: Record<string, string>, constants: Record<string, string>) => {
    if (!activeConfigId || !mappingData) return;
    const config = configs.find(c => c.id === activeConfigId);
    if (!config) return;

    setShowMappingModal(false);
    setExecutingFile(mappingData.filename);

    // Show progress modal
    setShowProgressModal(true);
    setProgressStep('downloading');
    setProgressMessage(`Conectando al servidor y descargando ${mappingData.filename}...`);
    setProgressRecords(0);

    try {
      // Combine mapping and constants into final mapping
      const finalMapping: Record<string, string> = { ...mapping };

      console.log("Mapping recibido del modal:", mapping);
      console.log("Constants recibidos del modal:", constants);

      // Update config with new mapping and constants
      const updatedConfig = {
        ...config,
        mapping: finalMapping,
        constants: constants
      };

      console.log("Configuración actualizada a enviar:", updatedConfig);

      // Show processing step
      setProgressStep('processing');
      setProgressMessage('Aplicando mapeo de campos personalizado...');

      // Show inserting step
      setProgressStep('inserting');
      setProgressMessage('Procesando e insertando registros en la base de datos...');

      // Execute import with updated mapping
      const result = await ApiService.executeManualImport(updatedConfig, mappingData.filename, authToken);

      setProgressRecords(result.records_processed || 0);

      console.log("Resultado completo:", result);

      if (result.status === 'success' || result.status === 'partial') {
        setProgressStep('complete');
        let successMessage = result.message || `✅ Importación exitosa: ${result.records_processed} registros procesados`;
        if (result.errors && result.errors.length > 0) {
          successMessage += ` (${result.errors.length} errores parciales)`;
        }
        setProgressMessage(successMessage);
        setFileStatuses(prev => ({ ...prev, [mappingData.filename]: 'success' }));

        // Auto-close after 3 seconds on success
        setTimeout(() => {
          setShowProgressModal(false);
          setShowManualModal(true); // Re-open file list
          if (activeConfigId) refreshFileList(activeConfigId);
        }, 3000);
      } else {
        setProgressStep('error');
        setProgressMessage(result.message || '❌ Error en la importación');
        setFileStatuses(prev => ({ ...prev, [mappingData.filename]: 'error' }));
      }

      setMappingData(null);
    } catch (error: any) {
      console.error(error);
      setProgressStep('error');
      setProgressMessage("❌ Error procesando archivo: " + (error.message || error));
      setFileStatuses(prev => ({ ...prev, [mappingData.filename]: 'error' }));
    } finally {
      setExecutingFile(null);
    }
  };

  const handleDelete = async (id: string) => {
    if (confirm('¿Seguro que desea eliminar esta configuración de importación?')) {
      await ApiService.deleteImportConfig(id);
      loadConfigs();
    }
  };

  const handleUnmarkFile = async (filename: string) => {
    if (!activeConfigId) return;
    const config = configs.find(c => c.id === activeConfigId);
    if (!config) return;

    setUnmarkingFile(filename);
    try {
      const result = await ApiService.unmarkFile(config, filename, authToken);
      alert(result.message || 'Archivo desmarcado correctamente');

      // Refresh file list
      const files = await ApiService.listRemoteFiles(config, authToken);
      setManualFiles(files);

      // Clear status for the old filename
      const newFilename = result.new_name;
      if (newFilename) {
        setFileStatuses(prev => {
          const updated = { ...prev };
          delete updated[filename];
          return updated;
        });
      }
    } catch (error: any) {
      console.error(error);
      alert('Error desmarcando archivo: ' + (error.message || error));
    } finally {
      setUnmarkingFile(null);
    }
  };


  const handleOpenExplorer = async (initialPath: string) => {
    console.log("Opening explorer with path:", initialPath);
    console.log("Config:", editingConfig.host, editingConfig.usuario, "Pass len:", tempPassword.length);
    setShowExplorer(true);
    setExplorerLoading(true);

    try {
      const localInitialPath =
        editingConfig.protocolo === 'LOCAL' &&
        (!initialPath || initialPath === '.' || initialPath === './' || initialPath === '/app')
          ? ''
          : initialPath;

      console.log("Calling ApiService.exploreDirectory...");
      const data = await ApiService.exploreDirectory(
        localInitialPath,
        editingConfig.protocolo,
        editingConfig.host,
        editingConfig.puerto,
        editingConfig.usuario,
        tempPassword,
        authToken
      );
      console.log("Explorer data received:", data);
      setExplorerPath(data.ruta_actual);
      setExplorerItems(data.items);
    } catch (error: any) {
      console.error(error);
      alert("Error al abrir explorador: " + (error.message || error));
      setExplorerItems([]);
    }
    setExplorerLoading(false);
  };

  const handlePickBrowserFiles = () => {
    try {
      const openFilePicker = (window as any).showOpenFilePicker as undefined | ((opts?: any) => Promise<any[]>);
      if (typeof openFilePicker === 'function') {
        openFilePicker({
          multiple: true,
          types: [
            {
              description: 'Archivos de importación',
              accept: {
                'text/csv': ['.csv'],
                'text/plain': ['.txt'],
                'application/json': ['.json'],
                'application/xml': ['.xml'],
                'text/xml': ['.xml']
              }
            }
          ]
        }).then((handles) => {
          if (!handles || handles.length === 0) return;
          const names = handles.map((h: any) => String(h?.name || 'archivo'));
          setBrowserFilesSelection({
            count: handles.length,
            names: names.slice(0, 5)
          });
          if (handles.length === 1) {
            setEditingConfig(prev => ({ ...prev, tipo_archivo: detectFileType(names[0]) }));
          }
        }).catch((err: any) => {
          const msg = String(err?.message || err || '').toLowerCase();
          if (msg.includes('abort') || msg.includes('cancel')) return;
          browserFilesInputRef.current?.click();
        });
        return;
      }

      browserFilesInputRef.current?.click();
    } catch (error: any) {
      console.error(error);
      alert('No se pudo abrir el selector de archivos del navegador.');
    }
  };

  const handleBrowserFilesInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    if (files.length === 0) return;

    const names = files.map((f) => f.name);
    setBrowserFilesSelection({
      count: files.length,
      names: names.slice(0, 5)
    });
    if (files.length === 1) {
      setEditingConfig(prev => ({ ...prev, tipo_archivo: detectFileType(files[0].name) }));
    }

    // Allow re-selecting the same file(s).
    e.target.value = '';
  };

  const handleNavigateExplorer = async (path: string) => {
    setExplorerLoading(true);
    try {
      const data = await ApiService.exploreDirectory(
        path,
        editingConfig.protocolo,
        editingConfig.host,
        editingConfig.puerto,
        editingConfig.usuario,
        tempPassword,
        authToken
      );
      setExplorerPath(data.ruta_actual);
      setExplorerItems(data.items);
    } catch (error: any) {
      console.error(error);
      alert("Error al navegar: " + (error.message || error));
      setExplorerItems([]);
    }
    setExplorerLoading(false);
  };

  const handleSelectDirectory = (path: string) => {
    setEditingConfig({ ...editingConfig, ruta_remota: path });
    setShowExplorer(false);
  };

  const detectFileType = (filename: string): ImportConfig['tipo_archivo'] => {
    const lowerName = filename.toLowerCase();
    if (lowerName.endsWith('.json')) return 'JSON';
    if (lowerName.endsWith('.xml')) return 'XML';
    if (lowerName.endsWith('.txt')) return 'TXT';
    if (lowerName.endsWith('.csv')) return 'CSV';
    return editingConfig.tipo_archivo;
  };

  const handleSelectExplorerFile = (item: { nombre: string, ruta: string, es_dir: boolean }) => {
    setShowExplorer(false);
    setFetchingHeaders(true);
    setSelectedFilePreview(null);

    const newConfig = {
      ...editingConfig,
      ruta_remota: item.ruta,
      tipo_archivo: detectFileType(item.nombre)
    };
    setEditingConfig(newConfig);

    ApiService.analyzeRemoteMapping(newConfig, tempPassword, item.ruta, authToken)
      .then(result => {
        setRemoteHeaders(result.csv_headers || []);
        setSelectedFilePreview({
          filename: item.nombre,
          lines: Array.isArray(result.raw_preview_lines) ? result.raw_preview_lines : [],
          analysisType: result.analysis_type || newConfig.tipo_archivo || null,
          detectedDelimiter: result.detected_delimiter ?? null,
          detectedHasHeader: typeof result.detected_has_header === 'boolean' ? result.detected_has_header : null
        });
        setEditingConfig(prev => {
          const nextMapping: Record<string, string> = { ...prev.mapping };
          if (result.suggested_mapping) {
            Object.entries(result.suggested_mapping).forEach(([field, suggestion]: [string, any]) => {
              nextMapping[field] = suggestion.csv_header;
            });
          }
          return { ...prev, mapping: nextMapping };
        });
        setActiveStep(2);
      })
      .catch(err => {
        console.error(err);
        const msg = String(err?.message || err || "Error analizando archivo");
        alert("Error analizando archivo: " + msg);
      })
      .finally(() => setFetchingHeaders(false));
  };

  const renderExplorerModal = () => (
    showExplorer && (
      <div className="fixed inset-0 z-[130] flex items-center justify-center bg-black/40 backdrop-blur-sm p-4 animate-in fade-in duration-200">
        <div className="w-full max-w-2xl bg-white rounded-2xl border border-slate-200 shadow-2xl overflow-hidden animate-in slide-in-from-bottom-4 duration-300 flex flex-col max-h-[80vh]">
          <div className="bg-slate-50 p-3 border-b border-slate-100 flex justify-between items-center">
            <div className="min-w-0 max-w-[85%]">
              <span className="text-[10px] font-bold text-slate-500 truncate block">{explorerPath}</span>
              {editingConfig.protocolo === 'LOCAL' && (
                <span className="text-[10px] text-amber-700 bg-amber-50 border border-amber-200 rounded px-1.5 py-0.5 inline-block mt-1">
                  Directorio local (servidor): muestra carpetas del servidor donde corre MsMall
                </span>
              )}
            </div>
            <button onClick={() => setShowExplorer(false)} className="text-slate-400 hover:text-slate-600"><XCircle size={14} /></button>
          </div>
          <div className="max-h-60 overflow-y-auto p-2 space-y-1">
            {explorerLoading ? (
              <div className="py-8 text-center"><RefreshCw className="animate-spin mx-auto text-indigo-400" size={20} /></div>
            ) : (
              <>
                {(explorerItems || []).map((item, idx) => (
                  <div
                    key={idx}
                    className="flex items-center justify-between p-2 hover:bg-indigo-50 rounded-lg cursor-pointer group transition-colors"
                    onClick={() => {
                      if (item.nombre === '..') {
                        handleNavigateExplorer(item.ruta);
                        return;
                      }
                      if (item.es_dir) {
                        handleNavigateExplorer(item.ruta);
                        return;
                      }
                      handleSelectExplorerFile(item);
                    }}
                  >
                    <div className="flex items-center gap-2">
                      {item.es_dir ? <FolderOpen size={16} className="text-indigo-400" /> : <FileText size={16} className="text-slate-400" />}
                      <span className="text-sm text-slate-700 font-medium">{item.nombre}</span>
                    </div>
                    {item.nombre !== '..' && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          if (item.es_dir) {
                            handleSelectDirectory(item.ruta);
                          } else {
                            handleSelectExplorerFile(item);
                          }
                        }}
                        className="bg-indigo-600 text-white text-[10px] px-2 py-1 rounded-md font-bold hover:bg-indigo-700 transition-colors"
                      >
                        {item.es_dir ? 'Seleccionar Carpeta' : 'Usar para Mapeo'}
                      </button>
                    )}
                  </div>
                ))}
                {explorerItems.length === 0 && (
                  <div className="py-4 text-center text-xs text-slate-400">No se encontraron carpetas</div>
                )}
              </>
            )}
          </div>
          <div className="p-3 bg-slate-50 border-t border-slate-100 flex justify-end">
            <button
              onClick={() => handleSelectDirectory(explorerPath)}
              className="bg-indigo-600 text-white text-xs px-4 py-1.5 rounded-lg font-bold hover:bg-indigo-700"
            >
              Seleccionar Actual (Dir)
            </button>
          </div>
        </div>
      </div>
    )
  );

  if (!canManageImports) {
    return (
      <div className="bg-amber-50 border border-amber-200 text-amber-800 rounded-xl p-4 text-sm font-medium">
        Solo usuarios con rol IT o ADMIN pueden gestionar conexiones e importaciones remotas.
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-in fade-in duration-500">
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
        <div>
          <h2 className="text-2xl font-bold text-slate-800">Importación Automatizada</h2>
          <p className="text-slate-500 text-sm">Configure conexiones directas vía FTP/SFTP para auditoría automática.</p>
        </div>
        <div className="flex items-center gap-3 w-full md:w-auto">
          <div className="inline-flex items-center bg-white border border-slate-200 rounded-xl p-1 shadow-sm">
            <button
              onClick={() => setViewMode('cards')}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all flex items-center gap-1.5 ${
                viewMode === 'cards' ? 'bg-indigo-600 text-white shadow-sm' : 'text-slate-500 hover:text-slate-700'
              }`}
              title="Vista Tarjetas"
            >
              <LayoutGrid size={14} />
              Tarjetas
            </button>
            <button
              onClick={() => setViewMode('list')}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all flex items-center gap-1.5 ${
                viewMode === 'list' ? 'bg-indigo-600 text-white shadow-sm' : 'text-slate-500 hover:text-slate-700'
              }`}
              title="Modo Lista"
            >
              <List size={14} />
              Modo Lista
            </button>
          </div>

          <button
            onClick={openNewConnectionDrawer}
            className="bg-indigo-600 text-white px-5 py-2.5 rounded-xl flex items-center gap-2 hover:bg-indigo-700 transition-all shadow-lg shadow-indigo-200 active:scale-95 font-medium whitespace-nowrap"
          >
            <Plus size={18} />
            Nueva Conexión
          </button>
        </div>
      </div>

      {showForm && (
        <div className="fixed inset-0 z-[105] bg-black/40 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="absolute inset-0 flex justify-end" onClick={closeFormDrawer}>
            <div
              className="w-full lg:w-[1120px] h-full bg-white border-l border-indigo-100 shadow-2xl animate-in slide-in-from-right duration-200 flex flex-col"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="bg-slate-50 border-b border-slate-100 p-6 flex justify-between items-center sticky top-0 z-10">
            <div className="flex items-center gap-4">
              <div className={`flex items-center gap-2 px-3 py-1 rounded-full text-xs font-bold ${activeStep === 1 ? 'bg-indigo-600 text-white' : 'bg-slate-200 text-slate-500'}`}>
                1. Conexión
              </div>
              <div className="w-8 h-px bg-slate-300"></div>
              <div className={`flex items-center gap-2 px-3 py-1 rounded-full text-xs font-bold ${activeStep === 2 ? 'bg-indigo-600 text-white' : 'bg-slate-200 text-slate-500'}`}>
                2. Mapeo de Campos
              </div>
            </div>
            <button onClick={closeFormDrawer} className="text-slate-400 hover:text-slate-600"><XCircle size={20} /></button>
          </div>

              <div className="flex-1 overflow-y-auto">
                <div className="p-8">
            {activeStep === 1 ? (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                <div className="space-y-5">
                  <div className="bg-indigo-50/50 p-4 rounded-2xl border border-indigo-100 mb-6">
                    <label className="block text-[10px] font-bold text-indigo-600 uppercase tracking-widest mb-1.5 flex items-center gap-2">
                      <Database size={12} /> Asociar a Local Existente
                    </label>
                    <select
                      className="w-full px-4 py-2.5 rounded-xl border border-slate-200 outline-none bg-white font-medium text-sm focus:ring-2 focus:ring-indigo-500 transition-all"
                      value={editingConfig.id || ''}
                      onChange={e => {
                        const selectedId = e.target.value;
                        if (!selectedId) {
                          setEditingConfig({ ...editingConfig, id: '', nombre: '' });
                          return;
                        }
                        const store = availableStores.find(s => s.id === selectedId);
                        if (store) {
                          const existingConfig = configs.find(c => c.id === selectedId);
                          if (existingConfig) {
                            setEditingConfig({ ...existingConfig });
                            setSelectedConnectionId('');
                            const matchedConn = remoteConnections.find(c =>
                              c.protocolo === existingConfig.protocolo &&
                              c.host === existingConfig.host &&
                              String(c.puerto) === String(existingConfig.puerto) &&
                              c.usuario === existingConfig.usuario
                            );
                            if (matchedConn) setSelectedConnectionId(matchedConn.id);
                          } else {
                            setEditingConfig({
                              ...editingConfig,
                              id: store.id,
                              nombre: store.nombre,
                              mapping: { ...editingConfig.mapping, local_codigo: store.codigo_interno }
                            });
                            setSelectedConnectionId('');
                          }
                        }
                      }}
                    >
                      <option value="">-- Nuevo Local (Crear al guardar) --</option>
                      {(availableStores || []).map(s => (
                        <option key={s.id} value={s.id}>{s.nombre} ({s.codigo_interno})</option>
                      ))}
                    </select>
                    <p className="text-[10px] text-slate-400 mt-2 italic">Recomendado: Seleccione un local ya registrado para evitar duplicados.</p>
                  </div>

                  <div>
                    <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1.5 flex justify-between items-center">
                      <span>Nombre de la Fuente / Conexión</span>
                      {editingConfig.id && <span className="text-[9px] bg-indigo-100 text-indigo-600 px-1.5 py-0.5 rounded">Vinculado a ID: {editingConfig.id.substring(0, 8)}...</span>}
                    </label>
                    <input
                      type="text" className="w-full px-4 py-2.5 rounded-xl border border-slate-200 focus:ring-2 focus:ring-indigo-500 outline-none font-medium"
                      placeholder="Ej: Nike Store - SFTP Principal"
                      value={editingConfig.nombre}
                      onChange={e => setEditingConfig({ ...editingConfig, nombre: e.target.value })}
                    />
                  </div>

                  {editingConfig.protocolo !== 'LOCAL' && (
                    <div className="p-3 rounded-xl border border-indigo-100 bg-indigo-50/50 space-y-2">
                      <label className="block text-[10px] font-bold text-indigo-600 uppercase tracking-widest">
                        Conexiones Guardadas (FTP/SFTP)
                      </label>
                      <div className="flex flex-col md:flex-row gap-2">
                        <select
                          className="min-w-0 flex-1 px-3 py-2 rounded-lg border border-slate-200 bg-white text-sm truncate"
                          value={selectedConnectionId}
                          onChange={(e) => applySavedConnection(e.target.value)}
                          title={remoteConnections.find(c => c.id === selectedConnectionId)?.nombre || ''}
                        >
                          <option value="">-- Seleccionar conexión guardada --</option>
                          {remoteConnections.map((conn) => (
                            <option key={conn.id} value={conn.id}>
                              {conn.nombre} ({conn.usuario}@{conn.host})
                            </option>
                          ))}
                        </select>
                        <div className="flex gap-2 shrink-0">
                          <button
                            type="button"
                            onClick={handleSaveCurrentAsConnection}
                            className="px-3 py-2 rounded-lg bg-indigo-600 text-white text-xs font-bold hover:bg-indigo-700 whitespace-nowrap"
                          >
                            Guardar Actual
                          </button>
                          <button
                            type="button"
                            onClick={handleDeleteSavedConnection}
                            disabled={!selectedConnectionId}
                            className="px-3 py-2 rounded-lg border border-rose-200 text-rose-600 text-xs font-bold hover:bg-rose-50 disabled:opacity-50 whitespace-nowrap"
                          >
                            Eliminar
                          </button>
                        </div>
                      </div>
                    </div>
                  )}
                  <div className="flex gap-4">
                    <div className="flex-1">
                      <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1.5">Protocolo</label>
                      <select
                        className="w-full px-4 py-2.5 rounded-xl border border-slate-200 outline-none bg-white font-medium"
                        value={editingConfig.protocolo}
                        onChange={e => {
                          const nextProtocol = e.target.value as ImportProtocol;
                          if (nextProtocol === 'LOCAL') setSelectedConnectionId('');
                          if (nextProtocol !== 'LOCAL') setBrowserFilesSelection(null);
                          setEditingConfig({ ...editingConfig, protocolo: nextProtocol, puerto: nextProtocol === 'SFTP' ? 22 : 21 });
                        }}
                      >
                        <option value="SFTP">SFTP (SSH File Transfer)</option>
                        <option value="FTP">FTP (Estándar)</option>
                        <option value="LOCAL">Directorio local (servidor)</option>
                      </select>
                    </div>
                    {editingConfig.protocolo !== 'LOCAL' && (
                      <div className="w-28">
                        <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1.5">Puerto</label>
                        <input
                          type="text"
                          inputMode="numeric"
                          pattern="[0-9]*"
                          className="w-full px-4 py-2.5 rounded-xl border border-slate-200 outline-none"
                          value={editingConfig.puerto}
                          onChange={e => {
                            const val = e.target.value.replace(/\D/g, '');
                            setEditingConfig({ ...editingConfig, puerto: val === '' ? 0 : parseInt(val) });
                          }}
                        />
                      </div>
                    )}
                  </div>
                  {editingConfig.protocolo !== 'LOCAL' && (
                    <div>
                      <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1.5">Host del Servidor</label>
                      <div className="relative">
                        <Globe size={18} className="absolute left-3.5 top-3 text-slate-300" />
                        <input
                          type="text" className="w-full pl-11 pr-4 py-2.5 rounded-xl border border-slate-200 outline-none"
                          placeholder="sftp.tu-tienda.com"
                          value={editingConfig.host}
                          onChange={e => setEditingConfig({ ...editingConfig, host: e.target.value })}
                        />
                      </div>
                    </div>
                  )}
                  <div>
                    <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1.5">Tipo de Archivo</label>
                    <div className="flex gap-2">
                      {['CSV', 'TXT', 'JSON', 'XML'].map((type) => (
                        <button
                          key={type}
                          type="button"
                          onClick={() => setEditingConfig({ ...editingConfig, tipo_archivo: type as any })}
                          className={`flex-1 py-2 rounded-xl border-2 font-bold text-xs transition-all ${editingConfig.tipo_archivo === type
                            ? 'border-indigo-600 bg-indigo-50 text-indigo-600'
                            : 'border-slate-100 bg-slate-50 text-slate-400 hover:bg-slate-100'
                            }`}
                        >
                          {type}
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className="pt-4 border-t border-slate-100">
                    <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-3">Frecuencia de Sincronización</label>
                    <div className="grid grid-cols-2 gap-3">
                      {[
                        { id: 'manual', label: 'Manual', mode: 'MANUAL' },
                        { id: 'cada_hora', label: 'Cada Hora', mode: 'AUTOMATICO' },
                        { id: 'cada_2_horas', label: 'Cada 2 Horas', mode: 'AUTOMATICO' },
                        { id: 'hora_especifica', label: 'Hora Específica', mode: 'AUTOMATICO' }
                      ].map((freq) => (
                        <button
                          key={freq.id}
                          type="button"
                          onClick={() => setEditingConfig({
                            ...editingConfig,
                            frecuencia: freq.id as any,
                            tipo_ejecucion: freq.mode as any
                          })}
                          className={`py-2 px-3 rounded-xl border-2 font-bold text-[11px] transition-all text-left flex items-center gap-2 ${editingConfig.frecuencia === freq.id
                            ? 'border-indigo-600 bg-indigo-50 text-indigo-600'
                            : 'border-slate-100 bg-slate-50 text-slate-400 hover:bg-slate-100'
                            }`}
                        >
                          <div className={`w-3 h-3 rounded-full border-2 ${editingConfig.frecuencia === freq.id ? 'border-indigo-600 bg-indigo-600' : 'border-slate-300'}`} />
                          {freq.label}
                        </button>
                      ))}
                    </div>
                    {editingConfig.frecuencia === 'hora_especifica' && (
                      <div className="mt-3 animate-in fade-in slide-in-from-top-1">
                        <input
                          type="time"
                          className="w-full px-4 py-2 rounded-xl border border-slate-200 outline-none font-medium text-slate-600"
                          value={editingConfig.hora_especifica || '08:00'}
                          onChange={e => setEditingConfig({ ...editingConfig, hora_especifica: e.target.value })}
                        />
                      </div>
                    )}
                  </div>
                </div>
                <div className="space-y-5">
                  {editingConfig.protocolo !== 'LOCAL' && (
                    <div>
                      <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1.5">Credenciales de Acceso</label>
                      <div className="space-y-3">
                        <div className="relative">
                          <Server size={18} className="absolute left-3.5 top-3 text-slate-300" />
                          <input
                            type="text" className="w-full pl-11 pr-4 py-2.5 rounded-xl border border-slate-200 outline-none"
                            placeholder="Nombre de usuario"
                            value={editingConfig.usuario}
                            onChange={e => setEditingConfig({ ...editingConfig, usuario: e.target.value })}
                          />
                        </div>
                        <div className="relative">
                          <Key size={18} className="absolute left-3.5 top-3 text-slate-300" />
                          <input
                            type="password" className="w-full pl-11 pr-4 py-2.5 rounded-xl border border-slate-200 outline-none"
                            placeholder="Contraseña o Frase de paso SSH"
                            value={tempPassword}
                            onChange={e => setTempPassword(e.target.value)}
                          />
                        </div>
                      </div>
                    </div>
                  )}
                  <div>
                    <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1.5">
                      {editingConfig.protocolo === 'LOCAL' ? 'Ruta del Directorio (Servidor)' : 'Ruta Remota de Archivos'}
                    </label>
                    <div className="relative">
                      <button
                        type="button"
                        onClick={() => handleOpenExplorer(editingConfig.ruta_remota)}
                        className="absolute left-3.5 top-3 text-indigo-600 hover:text-indigo-800 transition-colors"
                        title="Explorar Directorio"
                      >
                        <FolderOpen size={18} />
                      </button>
                      <input
                        type="text" className="w-full pl-11 pr-4 py-2.5 rounded-xl border border-slate-200 outline-none"
                        placeholder={editingConfig.protocolo === 'LOCAL' ? 'Ej: C:\\Ventas' : '/home/audit/ventas_diarias/'}
                        value={editingConfig.ruta_remota}
                        onChange={e => setEditingConfig({ ...editingConfig, ruta_remota: e.target.value })}
                      />
                    </div>
                    {editingConfig.protocolo === 'LOCAL' && (
                      <div className="mt-2 space-y-2">
                        <div className="flex flex-col sm:flex-row gap-2">
                          <button
                            type="button"
                            onClick={() => handleOpenExplorer(editingConfig.ruta_remota)}
                            className="px-3 py-2 rounded-lg border border-indigo-200 text-indigo-700 bg-indigo-50 hover:bg-indigo-100 text-xs font-bold"
                          >
                            Explorar directorio local (servidor)
                          </button>
                          <button
                            type="button"
                            onClick={handlePickBrowserFiles}
                            className="px-3 py-2 rounded-lg border border-cyan-200 text-cyan-700 bg-cyan-50 hover:bg-cyan-100 text-xs font-bold"
                          >
                            Seleccionar archivos de mi equipo
                          </button>
                        </div>
                        <p className="text-[11px] text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
                          <code>Directorio local (servidor)</code> navega carpetas del servidor donde corre MsMall (ej. Railway/Linux). Tu PC no es accesible desde el backend.
                        </p>
                        {browserFilesSelection && (
                          <p className="text-[11px] text-cyan-700 bg-cyan-50 border border-cyan-200 rounded-lg px-3 py-2">
                            Archivos seleccionados de tu equipo: <strong>{browserFilesSelection.count}</strong>
                            {browserFilesSelection.names.length > 0 ? ` · ${browserFilesSelection.names.join(', ')}` : ''}
                            {browserFilesSelection.count > browserFilesSelection.names.length ? ' ...' : ''}
                          </p>
                        )}
                      </div>
                    )}
                  </div>

                  <div>
                    <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-3">Acción Post-Procesado</label>
                    <div className="space-y-2">
                      {[
                        { id: 'NINGUNA', label: 'Ninguna (Mantener archivo)', icon: 'Clock' },
                        { id: 'ELIMINAR', label: 'Eliminar archivo después de procesar', icon: 'Trash2' },
                        { id: 'RENOMBRAR_PROCESADO', label: 'Renombrar archivo (Backup)', icon: 'RefreshCw' }
                      ].map((action) => (
                        <div key={action.id} className="space-y-2">
                          <button
                            type="button"
                            onClick={() => setEditingConfig({ ...editingConfig, accion_post_procesado: action.id as any })}
                            className={`w-full py-3 px-4 rounded-xl border-2 font-bold text-xs transition-all text-left flex items-center gap-3 ${editingConfig.accion_post_procesado === action.id
                              ? 'border-indigo-600 bg-indigo-50 text-indigo-600'
                              : 'border-slate-100 bg-slate-50 text-slate-400 hover:bg-slate-100'
                              }`}
                          >
                            <div className={`w-4 h-4 rounded-full border-2 flex items-center justify-center ${editingConfig.accion_post_procesado === action.id ? 'border-indigo-600' : 'border-slate-300'}`}>
                              {editingConfig.accion_post_procesado === action.id && <div className="w-2 h-2 rounded-full bg-indigo-600" />}
                            </div>
                            {action.label}
                          </button>
                          {action.id === 'RENOMBRAR_PROCESADO' && editingConfig.accion_post_procesado === 'RENOMBRAR_PROCESADO' && (
                            <div className="mt-2 ml-7 animate-in fade-in slide-in-from-top-1">
                              <input
                                type="text"
                                placeholder="Prefijo (ej: procesado_)"
                                className="w-full px-4 py-2 rounded-xl border border-slate-200 outline-none font-medium text-slate-600 text-xs shadow-inner bg-white/50"
                                value={editingConfig.prefijo_renombrado || ''}
                                onChange={e => setEditingConfig({ ...editingConfig, prefijo_renombrado: e.target.value })}
                              />
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>

                  {editingConfig.protocolo !== 'LOCAL' && (
                    <div className="flex flex-col gap-3">
                      <button
                        type="button"
                        onClick={handleTestConnection}
                        disabled={testingConnection || !editingConfig.host}
                        className="w-full py-2.5 border-2 border-indigo-50 text-indigo-600 rounded-xl font-bold flex items-center justify-center gap-2 hover:bg-indigo-50 transition-colors disabled:opacity-50 shadow-sm"
                      >
                        {testingConnection ? <RefreshCw className="animate-spin" size={18} /> : <Play size={16} fill="currentColor" />}
                        {testingConnection ? 'Verificando red...' : 'Probar Conexión'}
                      </button>

                      {editingConfig.frecuencia === 'manual' && editingConfig.id && (
                        <button
                          type="button"
                          onClick={() => handleSyncNow(editingConfig.id, editingConfig.nombre)}
                          className="w-full py-3 bg-slate-900 text-white rounded-xl font-bold flex items-center justify-center gap-2 hover:bg-indigo-600 transition-all shadow-lg active:scale-95 group"
                        >
                          <Database size={18} className="text-indigo-400 group-hover:text-white transition-colors" />
                          Listar y Procesar Archivos
                        </button>
                      )}
                    </div>
                  )}
                </div>
              </div>
            ) : (
              <div className="space-y-6">
                <div className="flex justify-between items-center mb-6">
                  <div className="p-4 bg-indigo-50 rounded-2xl border border-indigo-100 flex gap-4 text-indigo-700 items-start flex-1">
                    <div className="p-2 bg-indigo-600 rounded-lg text-white">
                      <Database size={20} />
                    </div>
                    <div>
                      <h5 className="font-bold text-sm">Motor de Transformación</h5>
                      <p className="text-xs mt-1 leading-relaxed">
                        El sistema buscará los nombres de columna definidos aquí en el archivo CSV remoto y los convertirá a nuestra estructura estándar de auditoría.
                      </p>
                    </div>
                  </div>

                  <button
                    onClick={() => {
                      console.log("Button 'Seleccionar Archivo Ejemplo' clicked");
                      handleOpenExplorer(editingConfig.ruta_remota);
                    }}
                    className="ml-4 px-4 py-3 bg-slate-900 text-white rounded-xl text-xs font-bold shadow-lg hover:bg-slate-800 transition-all flex items-center gap-2"
                    disabled={fetchingHeaders}
                  >
                    {fetchingHeaders ? <RefreshCw className="animate-spin" size={16} /> : <FileSearch size={16} />}
                    {fetchingHeaders ? 'Leyendo...' : 'Seleccionar Archivo'}
                  </button>

                  <button
                    onClick={() => setShowSmartMapping(true)}
                    className="ml-2 px-4 py-3 bg-indigo-600 text-white rounded-xl text-xs font-bold shadow-lg shadow-indigo-200 hover:bg-indigo-700 transition-all flex items-center gap-2 animate-pulse hover:animate-none"
                  >
                    <Wand2 size={16} /> Auto-Mapeo Mágico ✨
                  </button>
                </div>

                <div className="mb-6 p-4 bg-slate-50 border border-slate-200 rounded-xl grid grid-cols-1 md:grid-cols-2 gap-4">
                  <label className="flex items-center gap-2 text-xs font-semibold text-slate-700">
                    <input
                      type="checkbox"
                      checked={!isHeaderEnabled(editingConfig)}
                      onChange={(e) => {
                        const hasHeader = !e.target.checked;
                        const nextConstants = { ...(editingConfig.constants || {}) } as Record<string, string>;
                        nextConstants._has_header = hasHeader ? 'true' : 'false';
                        if (!nextConstants._data_start_row) {
                          nextConstants._data_start_row = hasHeader ? '2' : '1';
                        }
                        setEditingConfig(prev => ({ ...prev, constants: nextConstants }));
                      }}
                      className="rounded border-slate-300"
                    />
                    Archivo sin encabezado
                  </label>

                  <label className="text-xs font-semibold text-slate-700 flex flex-col gap-1">
                    Línea donde inicia la data
                    <input
                      type="number"
                      min={1}
                      value={getDataStartRow(editingConfig)}
                      onChange={(e) => {
                        const rowValue = Math.max(1, Number(e.target.value || 1));
                        const nextConstants = { ...(editingConfig.constants || {}) } as Record<string, string>;
                        nextConstants._data_start_row = String(rowValue);
                        setEditingConfig(prev => ({ ...prev, constants: nextConstants }));
                      }}
                      className="px-3 py-2 rounded-lg border border-slate-300 bg-white text-sm"
                    />
                  </label>
                </div>

                {selectedFilePreview && (
                  <div className="mb-6 rounded-xl border border-slate-200 bg-white">
                    <div className="px-4 py-3 border-b border-slate-100 flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                      <div>
                        <h6 className="text-sm font-bold text-slate-800">Vista Previa Cruda del Archivo</h6>
                        <p className="text-xs text-slate-500">{selectedFilePreview.filename}</p>
                      </div>
                      <div className="flex flex-wrap gap-2 text-[11px]">
                        <span className="px-2 py-1 rounded-md bg-slate-100 text-slate-600 font-semibold">
                          Tipo: {selectedFilePreview.analysisType || 'N/A'}
                        </span>
                        <span className="px-2 py-1 rounded-md bg-slate-100 text-slate-600 font-semibold">
                          Delimitador: {formatDelimiter(selectedFilePreview.detectedDelimiter)}
                        </span>
                        <span className="px-2 py-1 rounded-md bg-slate-100 text-slate-600 font-semibold">
                          Encabezado detectado: {selectedFilePreview.detectedHasHeader === null ? 'N/A' : selectedFilePreview.detectedHasHeader ? 'Sí' : 'No'}
                        </span>
                      </div>
                    </div>
                    <div className="max-h-64 overflow-auto p-3 bg-slate-950 rounded-b-xl">
                      {selectedFilePreview.lines.length > 0 ? (
                        <div className="space-y-1 font-mono text-[11px]">
                          {selectedFilePreview.lines.map((line, idx) => (
                            <div key={`${selectedFilePreview.filename}-${idx}`} className="grid grid-cols-[36px_1fr] gap-2">
                              <span className="text-slate-500 text-right select-none">{idx + 1}</span>
                              <span className="text-slate-200 whitespace-pre-wrap break-all">{line}</span>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <div className="text-xs text-slate-400">No hay líneas para mostrar en la vista previa.</div>
                      )}
                    </div>
                  </div>
                )}

                <SmartMappingModal
                  isOpen={showSmartMapping}
                  onClose={() => setShowSmartMapping(false)}
                  onConfirm={(newMapping, sampleData) => {
                    setEditingConfig(prev => ({
                      ...prev,
                      mapping: { ...prev.mapping, ...newMapping },
                      constants: { ...prev.constants, _date_format: sampleData?._date_format || 'auto' }
                    }));
                  }}
                  systemFields={STANDARD_FIELDS}
                />

                {remoteHeaders.length > 0 && (
                  <div className="mb-6 p-3 bg-green-50 border border-green-100 rounded-xl flex items-center gap-2 text-green-700 text-xs font-bold animate-in fade-in">
                    <CheckCircle2 size={16} />
                    Se detectaron {remoteHeaders.length} columnas en el archivo remoto.
                  </div>
                )}

                <div className="grid grid-cols-1 gap-y-6 pt-4">
                  {(STANDARD_FIELDS || []).map(field => {
                    const isConstant = (editingConfig.constants || {}) && field.key in (editingConfig.constants || {});
                    const currentValue = isConstant ? editingConfig.constants?.[field.key] : (editingConfig.mapping || {})[field.key];

                    return (
                      <div key={field.key} className="relative group bg-slate-50 p-4 rounded-xl border border-slate-200">
                        <div className="flex justify-between items-center mb-3">
                          <label className="text-xs font-bold text-slate-700 uppercase flex items-center gap-1">
                            {field.label}
                            {field.required && <span className="text-rose-500" title="Requerido">*</span>}
                          </label>
                          <span className="text-[10px] font-mono text-slate-400 bg-white px-2 py-0.5 rounded border border-slate-100">
                            Interno: {field.key}
                          </span>
                        </div>

                        <div className="flex flex-col md:flex-row gap-3">
                          <div className="md:w-1/3">
                            <select
                              className={`w-full px-3 py-2.5 rounded-xl border outline-none text-sm font-medium transition-colors ${isConstant ? 'border-indigo-200 bg-indigo-50 text-indigo-700' : 'border-slate-200 bg-white text-slate-600'
                                }`}
                              value={isConstant ? 'CONSTANT' : 'VARIABLE'}
                              onChange={(e) => {
                                const value = e.target.value;
                                if (value === 'CONSTANT') {
                                  // Switch to constant, clear mapping, set default empty constant
                                  const newMapping = { ...editingConfig.mapping };
                                  delete newMapping[field.key];

                                  setEditingConfig({
                                    ...editingConfig,
                                    mapping: newMapping,
                                    constants: { ...editingConfig.constants, [field.key]: '' }
                                  });
                                } else {
                                  // Switch to variable, clear constant
                                  const newConstants = { ...editingConfig.constants };
                                  delete newConstants[field.key];
                                  setEditingConfig({
                                    ...editingConfig,
                                    constants: newConstants
                                  });
                                }
                              }}
                            >
                              <option value="VARIABLE">Columna CSV</option>
                              <option value="CONSTANT">Valor Constante</option>
                            </select>
                          </div>

                          <div className="flex-1 relative">
                            {isConstant ? (
                              <div className="relative group/input">
                                <input
                                  type="text"
                                  className="w-full px-4 py-2.5 rounded-xl border border-indigo-400 text-sm focus:ring-2 focus:ring-indigo-500 outline-none bg-white text-indigo-900 placeholder:text-slate-300 font-bold shadow-sm transition-all"
                                  placeholder={`Ingrese el valor fijo (ej: 001) ...`}
                                  value={editingConfig.constants?.[field.key] || ''}
                                  onChange={e => {
                                    setEditingConfig({
                                      ...editingConfig,
                                      constants: { ...editingConfig.constants, [field.key]: e.target.value }
                                    });
                                  }}
                                />
                                <div className="absolute right-3 top-3 text-[10px] font-bold text-indigo-300 uppercase pointer-events-none group-focus-within/input:text-indigo-500 transition-colors">
                                  Valor Fijo
                                </div>
                              </div>
                            ) : (
                              <div className="relative">
                                {remoteHeaders.length > 0 ? (
                                  <select
                                    className="w-full px-4 py-2.5 rounded-xl border border-slate-200 text-sm focus:ring-2 focus:ring-indigo-500 outline-none pr-10 bg-white appearance-none"
                                    value={currentValue || ''}
                                    onChange={e => {
                                      setEditingConfig({
                                        ...editingConfig,
                                        mapping: { ...editingConfig.mapping, [field.key]: e.target.value }
                                      });
                                    }}
                                  >
                                    <option value="">-- Seleccionar Columna Remota --</option>
                                    {remoteHeaders.map(h => (
                                      <option key={h} value={h}>{h}</option>
                                    ))}
                                  </select>
                                ) : (
                                  <input
                                    type="text"
                                    className="w-full px-4 py-2.5 rounded-xl border border-slate-200 text-sm focus:ring-2 focus:ring-indigo-500 outline-none pr-10 bg-white placeholder:text-slate-400"
                                    placeholder={`Nombre de la columna en el archivo CSV...`}
                                    value={currentValue || ''}
                                    onChange={e => {
                                      setEditingConfig({
                                        ...editingConfig,
                                        mapping: { ...editingConfig.mapping, [field.key]: e.target.value }
                                      });
                                    }}
                                  />
                                )}
                                <div className="absolute right-3.5 top-3 text-slate-300 pointer-events-none">
                                  {remoteHeaders.length > 0 ? <ArrowRightLeft size={14} className="rotate-90" /> : <ArrowRightLeft size={14} />}
                                </div>
                              </div>
                            )}
                          </div>
                        </div>
                        {field.key === 'fecha_venta' && (
                          <div className="mt-3 pt-3 border-t border-slate-100 animate-in fade-in">
                            <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1.5 flex items-center gap-2">
                              <Clock size={12} /> Formato de Fecha Esperado
                            </label>
                            <select
                              className="w-full px-4 py-2 rounded-xl border border-slate-200 outline-none text-xs font-medium bg-white"
                              value={editingConfig.constants?._date_format || 'auto'}
                              onChange={e => setEditingConfig({
                                ...editingConfig,
                                constants: { ...editingConfig.constants, _date_format: e.target.value }
                              })}
                            >
                              <option value="auto">Auto (Intentar detectar)</option>
                              <option value="DD/MM/YYYY">DD/MM/YYYY (Ej: 31/01/2024)</option>
                              <option value="DDmmYYYY">DDmmYYYY (Ej: 31012024)</option>
                              <option value="YYYYmmDD">YYYYmmDD (Ej: 20240131)</option>
                              <option value="MM/DD/YYYY">MM/DD/YYYY (Ej: 01/31/2024)</option>
                              <option value="YYYY-MM-DD">YYYY-MM-DD (Ej: 2024-01-31)</option>
                              <option value="YYYY/MM/DD">YYYY/MM/DD (Ej: 2026/01/01)</option>
                            </select>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>

                <div className="bg-amber-50 p-4 rounded-xl border border-amber-100 flex gap-3 text-amber-700 mt-4">
                  <AlertCircle size={20} className="shrink-0" />
                  <p className="text-[11px] leading-relaxed">
                    <strong>Nota:</strong> Si el archivo remoto no contiene una de las columnas opcionales (Impuestos o Neto), el sistema los calculará automáticamente basándose en el Total Bruto y la configuración del local.
                  </p>
                </div>
              </div>
            )}

            {renderExplorerModal()}
            <input
              ref={browserFilesInputRef}
              type="file"
              multiple
              accept=".csv,.txt,.json,.xml,text/csv,text/plain,application/json,text/xml,application/xml"
              onChange={handleBrowserFilesInputChange}
              className="hidden"
            />
                </div>
              </div>

              <div className="border-t border-slate-100 flex justify-end gap-3 px-8 py-5 bg-white">
            <button onClick={closeFormDrawer} className="px-6 py-2.5 text-slate-500 font-medium hover:text-slate-800 transition-colors">Cerrar</button>
            {activeStep === 1 ? (
              <div className="flex gap-2">
                <button
                  onClick={handleSave}
                  className="px-8 py-2.5 border-2 border-indigo-600 text-indigo-600 rounded-xl font-bold hover:bg-indigo-50 active:scale-95 transition-all"
                >
                  Guardar
                </button>
                <button
                  onClick={() => setActiveStep(2)}
                  className="bg-indigo-600 text-white px-8 py-2.5 rounded-xl font-bold shadow-lg shadow-indigo-600/20 flex items-center gap-2 hover:bg-indigo-700 active:scale-95 transition-all"
                >
                  Configurar Mapeo <ArrowRightLeft size={18} />
                </button>
              </div>
            ) : (
              <div className="flex gap-2">
                <button onClick={() => setActiveStep(1)} className="px-6 py-2.5 border border-slate-200 rounded-xl text-slate-600 font-medium hover:bg-slate-50">Atrás</button>
                <button onClick={handleSave} className="bg-indigo-600 text-white px-10 py-2.5 rounded-xl font-bold shadow-lg shadow-indigo-600/20 hover:bg-indigo-700 active:scale-95 transition-all">Guardar y Activar</button>
              </div>
            )}
              </div>
            </div>
          </div>
        </div>
      )}

      {loading ? (
        <div className="py-20 text-center">
          <RefreshCw className="animate-spin mx-auto text-indigo-400 mb-4" size={32} />
          <p className="text-slate-400 font-medium">Cargando servicios de red...</p>
        </div>
      ) : configs.length === 0 ? (
        <div className="py-24 bg-white rounded-[2rem] border-2 border-dashed border-slate-200 text-center flex flex-col items-center justify-center">
          <div className="w-20 h-20 bg-slate-50 rounded-full flex items-center justify-center mb-6">
            <Server size={32} className="text-slate-300" />
          </div>
          <h3 className="text-lg font-bold text-slate-800">No hay automatizaciones configuradas</h3>
          <p className="text-slate-400 text-sm mt-1 mb-8 max-w-sm">Conecte sus tiendas vía SFTP para que el sistema audite las ventas cada noche sin intervención manual.</p>
          <button onClick={openNewConnectionDrawer} className="bg-indigo-600 text-white px-8 py-3 rounded-2xl font-bold shadow-xl shadow-indigo-100 hover:scale-105 transition-transform">Configurar Primera Fuente</button>
        </div>
      ) : viewMode === 'cards' ? (
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
          {(configs || []).map(config => (
            <div key={config.id} className="bg-white rounded-3xl border border-slate-200 p-6 hover:shadow-xl hover:shadow-indigo-500/5 transition-all group relative overflow-hidden">
              <div className={`absolute top-0 right-0 px-6 py-2 rounded-bl-3xl text-[10px] font-bold uppercase tracking-widest ${config.protocolo === 'SFTP' ? 'bg-indigo-600 text-white' : config.protocolo === 'LOCAL' ? 'bg-emerald-600 text-white' : 'bg-amber-500 text-white'}`}>
                {config.protocolo === 'LOCAL' ? 'Dir. local (servidor)' : config.protocolo}
              </div>

              <div className="flex items-start gap-4 mb-6">
                <div className={`p-4 rounded-2xl ${config.protocolo === 'SFTP' ? 'bg-indigo-50 text-indigo-600' : config.protocolo === 'LOCAL' ? 'bg-emerald-50 text-emerald-600' : 'bg-amber-50 text-amber-600'}`}>
                  {config.protocolo === 'LOCAL' ? <FolderOpen size={28} /> : <Server size={28} />}
                </div>
                <div>
                  <h4 className="font-bold text-slate-800 text-lg">{config.nombre}</h4>
                  <div className="flex items-center gap-2 text-xs text-slate-400 mt-1">
                    {config.protocolo !== 'LOCAL' && (
                      <>
                        <Globe size={14} />
                        <span className="font-medium">{config.host}:{config.puerto}</span>
                        <span className="w-1 h-1 bg-slate-300 rounded-full"></span>
                      </>
                    )}
                    <FolderOpen size={14} />
                    <span className="truncate max-w-[250px]">{config.ruta_remota}</span>
                    <span className="w-1 h-1 bg-slate-300 rounded-full"></span>
                    <Database size={14} />
                    <span className="font-bold text-indigo-600">{config.tipo_archivo}</span>
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4 my-6">
                <div className="p-4 bg-slate-50 rounded-2xl border border-slate-100">
                  <div className="flex items-center gap-2 text-slate-400 text-[10px] font-bold uppercase tracking-wider mb-2">
                    <Clock size={12} /> Última Ejecución
                  </div>
                  <p className="text-xs font-bold text-slate-700">
                    {config.ultima_ejecucion ? new Date(config.ultima_ejecucion).toLocaleString() : 'Pendiente'}
                  </p>
                  {config.resultado_ultimo && (
                    <div className={`inline-flex items-center gap-1 mt-2 text-[10px] font-bold uppercase ${config.resultado_ultimo === 'exito' ? 'text-green-600' : 'text-rose-600'}`}>
                      {config.resultado_ultimo === 'exito' ? <CheckCircle2 size={10} /> : <XCircle size={10} />}
                      {config.resultado_ultimo === 'exito' ? 'Sincronizado' : 'Error Red'}
                    </div>
                  )}
                </div>
                <div className="p-4 bg-slate-50 rounded-2xl border border-slate-100">
                  <div className="flex items-center gap-2 text-slate-400 text-[10px] font-bold uppercase tracking-wider mb-2">
                    <Database size={12} /> Mapeo Activo
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {Object.keys(config.mapping || {}).filter(k => (config.mapping || {})[k]).slice(0, 3).map(k => (
                      <span key={k} className="px-1.5 py-0.5 bg-white border border-slate-200 rounded text-[8px] font-bold text-slate-500 uppercase">{k.replace('_', ' ')}</span>
                    ))}
                    {Object.keys(config.mapping || {}).filter(k => (config.mapping || {})[k]).length > 3 && (
                      <span className="text-[8px] text-slate-400 font-bold">+{Object.keys(config.mapping || {}).filter(k => (config.mapping || {})[k]).length - 3}</span>
                    )}
                  </div>
                </div>
              </div>

              <div className="flex items-center justify-between pt-5 border-t border-slate-50">
                <div className="flex items-center gap-1.5">
                  <div className={`w-2 h-2 rounded-full ${config.estado === 'activo' ? 'bg-green-500 animate-pulse' : 'bg-slate-300'}`}></div>
                  <span className="text-[10px] font-bold text-slate-500 uppercase tracking-tighter">Status: {config.estado}</span>
                </div>

                <div className="flex items-center gap-2">
                  <button
                    onClick={() => openEditConnectionDrawer(config)}
                    className="p-2.5 text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 rounded-xl transition-all"
                    title="Editar Mapeo"
                  >
                    <Settings2 size={20} />
                  </button>
                  <button
                    onClick={() => handleDelete(config.id)}
                    className="p-2.5 text-slate-400 hover:text-rose-600 hover:bg-rose-50 rounded-xl transition-all"
                    title="Eliminar Conexión"
                  >
                    <Trash2 size={20} />
                  </button>
                  <button
                    onClick={() => handleSyncNow(config.id, config.nombre)}
                    disabled={syncingId === config.id}
                    className="bg-slate-900 text-white px-5 py-2.5 rounded-xl text-xs font-bold hover:bg-indigo-600 transition-all flex items-center gap-2 shadow-lg shadow-slate-200 active:scale-95 disabled:opacity-50"
                  >
                    {syncingId === config.id ? <RefreshCw className="animate-spin" size={14} /> : <Play size={14} fill="white" />}
                    Ejecutar Ahora
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="bg-white rounded-[2rem] border border-slate-200 shadow-sm overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[1100px] text-left">
              <thead>
                <tr className="bg-slate-50 border-b border-slate-100">
                  <th className="px-5 py-4 text-[10px] font-bold text-slate-400 uppercase tracking-widest">Conexión</th>
                  <th className="px-5 py-4 text-[10px] font-bold text-slate-400 uppercase tracking-widest">Protocolo</th>
                  <th className="px-5 py-4 text-[10px] font-bold text-slate-400 uppercase tracking-widest">Acceso</th>
                  <th className="px-5 py-4 text-[10px] font-bold text-slate-400 uppercase tracking-widest">Ruta Remota</th>
                  <th className="px-5 py-4 text-[10px] font-bold text-slate-400 uppercase tracking-widest">Última Ejecución</th>
                  <th className="px-5 py-4 text-[10px] font-bold text-slate-400 uppercase tracking-widest">Mapeo</th>
                  <th className="px-5 py-4 text-[10px] font-bold text-slate-400 uppercase tracking-widest">Estado</th>
                  <th className="px-5 py-4 text-[10px] font-bold text-slate-400 uppercase tracking-widest text-center">Acciones</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {(configs || []).map((config) => {
                  const activeMappings = Object.keys(config.mapping || {}).filter(k => (config.mapping || {})[k]).length;
                  const isActive = config.estado === 'activo';

                  return (
                    <tr key={config.id} className="hover:bg-indigo-50/30 transition-colors">
                      <td className="px-5 py-4">
                        <div className="flex items-center gap-3">
                          <div className={`p-2.5 rounded-xl ${config.protocolo === 'SFTP' ? 'bg-indigo-50 text-indigo-600' : config.protocolo === 'LOCAL' ? 'bg-emerald-50 text-emerald-600' : 'bg-amber-50 text-amber-600'}`}>
                            {config.protocolo === 'LOCAL' ? <FolderOpen size={16} /> : <Server size={16} />}
                          </div>
                          <div>
                            <p className="text-sm font-bold text-slate-800">{config.nombre}</p>
                            <p className="text-[11px] text-slate-400 font-medium uppercase tracking-wide">{config.tipo_archivo}</p>
                          </div>
                        </div>
                      </td>
                      <td className="px-5 py-4">
                        <span className={`inline-flex px-2.5 py-1 rounded-full text-[10px] font-bold uppercase tracking-wide ${config.protocolo === 'SFTP' ? 'bg-indigo-100 text-indigo-700' : config.protocolo === 'LOCAL' ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-700'}`}>
                          {config.protocolo === 'LOCAL' ? 'Dir. local (servidor)' : config.protocolo}
                        </span>
                      </td>
                      <td className="px-5 py-4 text-xs text-slate-600 font-medium">
                        {config.protocolo === 'LOCAL' ? (
                          <span className="text-slate-400">N/A</span>
                        ) : (
                          <div className="space-y-0.5">
                            <p>{config.host}:{config.puerto}</p>
                            <p className="text-slate-400">{config.usuario || '-'}</p>
                          </div>
                        )}
                      </td>
                      <td className="px-5 py-4 text-xs text-slate-600 max-w-[260px]">
                        <span className="truncate block font-medium">{config.ruta_remota}</span>
                      </td>
                      <td className="px-5 py-4 text-xs text-slate-600">
                        {config.ultima_ejecucion ? new Date(config.ultima_ejecucion).toLocaleString() : 'Pendiente'}
                      </td>
                      <td className="px-5 py-4 text-xs text-slate-600">
                        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-slate-100 text-slate-600 font-bold">
                          <Database size={12} />
                          {activeMappings} campos
                        </span>
                      </td>
                      <td className="px-5 py-4">
                        <div className="flex items-center gap-2">
                          <span className={`w-2 h-2 rounded-full ${isActive ? 'bg-green-500' : 'bg-slate-300'}`}></span>
                          <span className={`text-[11px] font-bold uppercase ${isActive ? 'text-green-700' : 'text-slate-500'}`}>
                            {config.estado}
                          </span>
                        </div>
                        {config.resultado_ultimo && (
                          <div className={`text-[10px] font-bold mt-1 ${config.resultado_ultimo === 'exito' ? 'text-green-600' : 'text-rose-600'}`}>
                            {config.resultado_ultimo === 'exito' ? 'Sincronizado' : 'Error Red'}
                          </div>
                        )}
                      </td>
                      <td className="px-5 py-4 text-center">
                        <div className="inline-flex items-center gap-2">
                          <button
                            onClick={() => openEditConnectionDrawer(config)}
                            className="p-2 text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 rounded-lg transition-all"
                            title="Editar"
                          >
                            <Settings2 size={16} />
                          </button>
                          <button
                            onClick={() => handleDelete(config.id)}
                            className="p-2 text-slate-400 hover:text-rose-600 hover:bg-rose-50 rounded-lg transition-all"
                            title="Eliminar"
                          >
                            <Trash2 size={16} />
                          </button>
                          <button
                            onClick={() => handleSyncNow(config.id, config.nombre)}
                            disabled={syncingId === config.id}
                            className="bg-indigo-600 text-white px-3 py-2 rounded-lg text-[11px] font-bold hover:bg-indigo-700 transition-all flex items-center gap-1.5 active:scale-95 disabled:opacity-50"
                          >
                            {syncingId === config.id ? <RefreshCw className="animate-spin" size={12} /> : <Play size={12} fill="white" />}
                            Ejecutar
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <div ref={exporterWebservicePanelRef}>
        {renderExporterWebservicePanel()}
      </div>

      {/* Manual Execution Modal */}
      {showManualModal && (
        <div className="fixed inset-0 z-[110] flex items-center justify-center bg-black/50 backdrop-blur-sm p-4 animate-in fade-in duration-200">
          <div className="w-full max-w-4xl bg-white rounded-[2rem] border border-slate-200 shadow-2xl overflow-hidden animate-in zoom-in-95 duration-300 flex flex-col max-h-[85vh]">
	            <div className="bg-slate-50 p-6 border-b border-slate-100 flex justify-between items-center">
              <div>
                <h3 className="text-xl font-bold text-slate-800 flex items-center gap-2">
                  <Play size={20} className="text-indigo-600" fill="currentColor" />
                  Ejecución de Importación Manual
                </h3>
                <p className="text-slate-400 text-xs mt-0.5">Seleccione un archivo del servidor remoto para procesar inmediatamente.</p>
              </div>
	              <button
	                onClick={closeManualModal}
	                className="p-2 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded-full transition-colors"
	              >
	                <XCircle size={24} />
	              </button>
	            </div>

	            <div className="flex-1 overflow-y-auto p-6">
              <div className="mb-5 p-4 bg-slate-50 border border-slate-200 rounded-2xl">
                <div className="flex flex-col lg:flex-row lg:items-end gap-3">
                  <div className="flex-1">
                    <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1.5">
                      Máscara de Archivo
                    </label>
                    <input
                      type="text"
                      value={batchMask}
                      onChange={(e) => setBatchMask(e.target.value)}
                      placeholder="Ej: *2026* (también acepta %2026%)"
                      className="w-full px-3 py-2 rounded-xl border border-slate-200 text-sm outline-none focus:ring-2 focus:ring-indigo-500 bg-white"
                      disabled={batchProgress.running}
                    />
                  </div>
                  <div className="w-full lg:w-36">
                    <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1.5">
                      Límite
                    </label>
                    <input
                      type="number"
                      min={1}
                      max={500}
                      value={batchLimit}
                      onChange={(e) => {
                        const n = Number(e.target.value);
                        setBatchLimit(Number.isFinite(n) ? Math.max(1, Math.min(500, Math.trunc(n))) : 30);
                      }}
                      className="w-full px-3 py-2 rounded-xl border border-slate-200 text-sm outline-none focus:ring-2 focus:ring-indigo-500 bg-white"
                      disabled={batchProgress.running}
                    />
                  </div>
                  <div className="w-full lg:w-auto">
                    {batchProgress.running ? (
                      <button
                        onClick={stopManualBatch}
                        className="w-full lg:w-auto bg-rose-600 text-white px-4 py-2.5 rounded-xl text-xs font-bold hover:bg-rose-700 transition-all"
                      >
                        Detener Lote
                      </button>
                    ) : (
                      <button
                        onClick={handleExecuteManualBatch}
                        className="w-full lg:w-auto bg-indigo-600 text-white px-4 py-2.5 rounded-xl text-xs font-bold hover:bg-indigo-700 transition-all"
                      >
                        Procesar Lote
                      </button>
                    )}
                  </div>
                </div>

                <div className="mt-3 flex flex-wrap items-center gap-2 text-[11px]">
                  <span className="px-2 py-1 rounded-lg bg-white border border-slate-200 text-slate-600 font-bold">
                    Coinciden: {filteredBatchCandidates.length}
                  </span>
                  <span className="px-2 py-1 rounded-lg bg-white border border-slate-200 text-slate-600 font-bold">
                    A procesar: {Math.min(filteredBatchCandidates.length, Math.max(1, Math.trunc(batchLimit || 0)))}
                  </span>
                  {batchProgress.skipped > 0 && (
                    <span className="px-2 py-1 rounded-lg bg-amber-50 border border-amber-200 text-amber-700 font-bold">
                      Saltados por límite: {batchProgress.skipped}
                    </span>
                  )}
                </div>

                {(batchProgress.total > 0 || batchProgress.running) && (
                  <div className="mt-3">
                    <div className="flex items-center justify-between text-[11px] font-bold mb-1">
                      <span className="text-slate-600">
                        {batchProgress.currentFile ? `Procesando: ${batchProgress.currentFile}` : 'Procesamiento por lote'}
                      </span>
                      <span className="text-slate-500">
                        {batchProgress.processed}/{batchProgress.total} ({Math.round((batchProgress.processed / Math.max(batchProgress.total, 1)) * 100)}%)
                      </span>
                    </div>
                    <div className="h-2 w-full bg-slate-200 rounded-full overflow-hidden">
                      <div
                        className={`h-full ${batchProgress.running ? 'bg-indigo-600' : 'bg-emerald-600'} transition-all duration-300`}
                        style={{ width: `${Math.round((batchProgress.processed / Math.max(batchProgress.total, 1)) * 100)}%` }}
                      />
                    </div>
                    <div className="mt-2 text-[11px] text-slate-600 flex flex-wrap items-center gap-3">
                      <span>OK: <strong className="text-green-700">{batchProgress.success}</strong></span>
                      <span>Error: <strong className="text-rose-700">{batchProgress.failed}</strong></span>
                      {batchProgress.message && <span className="text-slate-500">{batchProgress.message}</span>}
                    </div>
                  </div>
                )}
              </div>

	              {manualLoading ? (
	                <div className="py-20 text-center">
	                  <RefreshCw className="animate-spin mx-auto text-indigo-400 mb-4" size={32} />
	                  <p className="text-slate-500 font-medium">Buscando archivos en el servidor...</p>
                </div>
              ) : manualFiles.length > 0 ? (
                <div className="overflow-hidden rounded-2xl border border-slate-100">
                  <table className="w-full text-left">
                    <thead>
                      <tr className="bg-slate-50 border-b border-slate-100">
                        <th className="px-5 py-4 text-[10px] font-bold text-slate-400 uppercase tracking-widest">Nombre del Archivo</th>
                        <th className="px-5 py-4 text-[10px] font-bold text-slate-400 uppercase tracking-widest">Fecha Modificación</th>
                        <th className="px-5 py-4 text-[10px] font-bold text-slate-400 uppercase tracking-widest text-right">Tamaño</th>
                        <th className="px-5 py-4 text-[10px] font-bold text-slate-400 uppercase tracking-widest text-center">Acción</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-50">
                      {(manualFiles || []).map((file) => {
                        const isServerMarkedProcessed = file.nombre.startsWith('PR_');
                        const isProcessed = isServerMarkedProcessed || fileStatuses[file.nombre] === 'success';
                        const isErrored = !isProcessed && fileStatuses[file.nombre] === 'error';

                        return (
                        <tr key={file.nombre} className="hover:bg-indigo-50/30 transition-colors group">
                          <td className="px-5 py-4">
                            <div className="flex items-center gap-3">
                              <div className="p-2 bg-slate-100 rounded-lg group-hover:bg-indigo-100 group-hover:text-indigo-600 transition-colors">
                                <FileText size={16} />
                              </div>
                              <span className="text-sm font-bold text-slate-700">{file.nombre}</span>
                            </div>
                          </td>
                          <td className="px-5 py-4 text-xs text-slate-500">
                            {new Date(file.fecha).toLocaleString()}
                          </td>
                          <td className="px-5 py-4 text-xs font-mono text-slate-500 text-right">
                            {(file.tamano / 1024).toFixed(1)} KB
                          </td>
                          <td className="px-5 py-4 text-center">
                            <div className="flex items-center justify-center gap-2">
                              {/* Unmark button for processed files */}
	                              {file.nombre.startsWith('PR_') && (
	                                <button
	                                  onClick={() => handleUnmarkFile(file.nombre)}
	                                  disabled={unmarkingFile === file.nombre || batchProgress.running}
	                                  className="p-2 text-amber-600 hover:text-amber-700 hover:bg-amber-50 rounded-xl transition-all disabled:opacity-50"
	                                  title="Desmarcar archivo para reprocesar"
	                                >
                                  {unmarkingFile === file.nombre ? (
                                    <RefreshCw className="animate-spin" size={16} />
                                  ) : (
                                    <RotateCcw size={16} />
                                  )}
                                </button>
                              )}

                              {/* Execute button */}
	                              <button
	                                onClick={() => handleExecuteManualFile(file.nombre)}
	                                disabled={executingFile === file.nombre || isProcessed || batchProgress.running}
	                                className={`px-4 py-2 rounded-xl text-xs font-bold active:scale-95 transition-all shadow-lg flex items-center gap-2 disabled:opacity-50
	                                  ${isProcessed
	                                    ? 'bg-green-500 text-white shadow-green-200 cursor-default'
                                    : isErrored
                                      ? 'bg-rose-500 text-white shadow-rose-200 hover:bg-rose-600'
                                      : 'bg-indigo-600 text-white shadow-indigo-200 hover:bg-indigo-700'
                                  }`}
                              >
                                {executingFile === file.nombre ? <RefreshCw className="animate-spin" size={14} />
                                  : isProcessed ? <CheckCircle2 size={14} />
                                    : <Play size={12} fill="white" />}
                                {isProcessed ? 'Procesado' : isErrored ? 'Reintentar' : 'Procesar Ahora'}
                              </button>
                            </div>
                          </td>
                        </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="py-20 text-center">
                  <div className="w-16 h-16 bg-slate-50 rounded-full flex items-center justify-center mx-auto mb-4">
                    <FileSearch size={24} className="text-slate-300" />
                  </div>
                  <h4 className="font-bold text-slate-800">No se encontraron archivos</h4>
                  <p className="text-slate-400 text-sm mt-1">Asegúrese de que el servidor tenga archivos con la extensión configurada.</p>
                </div>
              )}
            </div>

	            <div className="bg-slate-50 p-6 border-t border-slate-100 flex justify-end">
	              <button
	                onClick={closeManualModal}
	                className="px-6 py-2.5 bg-white border border-slate-200 rounded-xl text-slate-600 font-bold hover:bg-slate-50 active:scale-95 transition-all text-sm"
	              >
	                Cerrar Ventana
	              </button>
            </div>
          </div>
        </div>
      )}

      {/* Progress Modal */}
      {showProgressModal && (
        <div className="fixed inset-0 z-[120] flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 animate-in fade-in duration-200">
          <div className="w-full max-w-md bg-white rounded-3xl border border-slate-200 shadow-2xl overflow-hidden animate-in zoom-in-95 duration-300">
            <div className="bg-gradient-to-r from-indigo-600 to-purple-600 p-6 text-white">
              <h3 className="text-xl font-bold flex items-center gap-2">
                <Database size={24} />
                Procesando Importación
              </h3>
            </div>

            <div className="p-8">
              {/* Progress Steps */}
              <div className="space-y-6">
                {/* Step 1: Downloading */}
                <div className={`flex items-center gap-4 ${progressStep === 'downloading' ? 'opacity-100' : progressStep === 'processing' || progressStep === 'inserting' || progressStep === 'complete' ? 'opacity-50' : 'opacity-30'}`}>
                  <div className={`w-12 h-12 rounded-full flex items-center justify-center ${progressStep === 'downloading' ? 'bg-indigo-100 text-indigo-600' : 'bg-green-100 text-green-600'}`}>
                    {progressStep === 'downloading' ? <RefreshCw size={24} className="animate-spin" /> : <CheckCircle2 size={24} />}
                  </div>
                  <div>
                    <p className="font-bold text-slate-700">Descargando archivo</p>
                    <p className="text-xs text-slate-400">Conectando al servidor remoto...</p>
                  </div>
                </div>

                {/* Step 2: Processing */}
                <div className={`flex items-center gap-4 ${progressStep === 'processing' ? 'opacity-100' : progressStep === 'inserting' || progressStep === 'complete' ? 'opacity-50' : 'opacity-30'}`}>
                  <div className={`w-12 h-12 rounded-full flex items-center justify-center ${progressStep === 'processing' ? 'bg-indigo-100 text-indigo-600' : progressStep === 'inserting' || progressStep === 'complete' ? 'bg-green-100 text-green-600' : 'bg-slate-100 text-slate-400'}`}>
                    {progressStep === 'processing' ? <RefreshCw size={24} className="animate-spin" /> : progressStep === 'inserting' || progressStep === 'complete' ? <CheckCircle2 size={24} /> : <FileText size={24} />}
                  </div>
                  <div>
                    <p className="font-bold text-slate-700">Analizando estructura</p>
                    <p className="text-xs text-slate-400">Validando mapeo y formato...</p>
                  </div>
                </div>

                {/* Step 3: Inserting */}
                <div className={`flex items-center gap-4 ${progressStep === 'inserting' ? 'opacity-100' : progressStep === 'complete' ? 'opacity-50' : 'opacity-30'}`}>
                  <div className={`w-12 h-12 rounded-full flex items-center justify-center ${progressStep === 'inserting' ? 'bg-indigo-100 text-indigo-600' : progressStep === 'complete' ? 'bg-green-100 text-green-600' : 'bg-slate-100 text-slate-400'}`}>
                    {progressStep === 'inserting' ? <RefreshCw size={24} className="animate-spin" /> : progressStep === 'complete' ? <CheckCircle2 size={24} /> : <Database size={24} />}
                  </div>
                  <div>
                    <p className="font-bold text-slate-700">Insertando registros</p>
                    <p className="text-xs text-slate-400">Guardando en base de datos...</p>
                    {progressRecords > 0 && (
                      <p className="text-xs font-bold text-indigo-600 mt-1">{progressRecords} registros procesados</p>
                    )}
                  </div>
                </div>
              </div>

              {/* Result Message */}
              {(progressStep === 'complete' || progressStep === 'error') && (
                <div className={`mt-6 p-4 rounded-xl border-2 ${progressStep === 'complete' ? 'bg-green-50 border-green-200' : 'bg-rose-50 border-rose-200'} animate-in fade-in slide-in-from-bottom-2`}>
                  <p className={`text-sm font-bold ${progressStep === 'complete' ? 'text-green-700' : 'text-rose-700'}`}>
                    {progressMessage}
                  </p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Mapping Modal - Rendered at root level for proper z-index */}
      <MappingModal
        isOpen={showMappingModal}
        onClose={() => setShowMappingModal(false)}
        onConfirm={handleMappingConfirm}
        fileHeaders={mappingData?.fileHeaders || []}
        suggestedMapping={mappingData?.suggestedMapping || {}}
        currentMapping={mappingData?.currentMapping || {}}
        sampleRow={mappingData?.sampleRow || {}}
        filename={mappingData?.filename || ''}
      />
    </div>
  );
};
