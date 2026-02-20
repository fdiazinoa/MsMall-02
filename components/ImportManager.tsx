
import React, { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthProvider';
import { ApiService } from '../api';
// Fix: Import types from '../types' instead of '../api'
import { ImportConfig, ImportProtocol } from '../types';
import { SmartMappingModal } from './SmartMappingModal';
import MappingModal from './MappingModal';
import {
  Server, Plus, Play, Trash2, Settings2,
  ArrowRightLeft, CheckCircle2, XCircle, Clock,
  Key, Globe, FolderOpen, Database, RefreshCw, AlertCircle, FileSearch, FileText, Wand2, RotateCcw
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

export const ImportManager: React.FC = () => {
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

  // Explorer State
  const [showExplorer, setShowExplorer] = useState(false);
  const [explorerPath, setExplorerPath] = useState('.');
  const [explorerItems, setExplorerItems] = useState<{ nombre: string, ruta: string, es_dir: boolean }[]>([]);
  const [explorerLoading, setExplorerLoading] = useState(false);

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

  const [editingConfig, setEditingConfig] = useState<ImportConfig>({
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
    constants: {}
  });

  const [availableStores, setAvailableStores] = useState<any[]>([]);

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

  useEffect(() => {
    if (currentMall) {
      loadConfigs();
      loadStores();
    }
  }, [currentMall]);

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
      setShowForm(false);
      setActiveStep(1);
      setTempPassword('');
      setEditingConfig({
        id: '', nombre: '', protocolo: 'SFTP', host: '', puerto: 22, usuario: '', ruta_remota: '.', tipo_archivo: 'CSV',
        frecuencia: 'manual', accion_post_procesado: 'ninguna', estado: 'activo',
        mapping: { factura_numero: '', fecha_venta: '', local_codigo: '', total_bruto: '', total_impuestos: '', total_neto: '', comprobante: '', hora_transaccion: '' },
        constants: {},
        password: ''
      });
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
      // Don't alert on refresh, just log
    } finally {
      setManualLoading(false);
    }
  };

  const handleSyncNow = async (id: string, name: string) => {
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

  const resolveProcessedCountFromLogs = async (config: ImportConfig, filename: string): Promise<number | null> => {
    try {
      const logs = await ApiService.getLoadLogs(currentMall?.id);
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
        setProgressStep('error');
        setProgressMessage('⚠️ El archivo seleccionado no contiene filas de data para importar (vacío o solo encabezado).');
        setFileStatuses(prev => ({ ...prev, [filename]: 'error' }));
        return;
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
      console.log("Calling ApiService.exploreDirectory...");
      const data = await ApiService.exploreDirectory(
        initialPath || '.',
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
      <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/40 backdrop-blur-sm p-4 animate-in fade-in duration-200">
        <div className="w-full max-w-2xl bg-white rounded-2xl border border-slate-200 shadow-2xl overflow-hidden animate-in slide-in-from-bottom-4 duration-300 flex flex-col max-h-[80vh]">
          <div className="bg-slate-50 p-3 border-b border-slate-100 flex justify-between items-center">
            <span className="text-[10px] font-bold text-slate-500 truncate max-w-[80%]">{explorerPath}</span>
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
        <button
          onClick={() => {
            setEditingConfig({
              id: '', nombre: '', protocolo: 'SFTP', host: '', puerto: 22, usuario: '', ruta_remota: '.', tipo_archivo: 'CSV',
              frecuencia: 'manual', accion_post_procesado: 'ninguna', estado: 'activo',
              mapping: { factura_numero: '', fecha_venta: '', local_codigo: '', total_bruto: '', total_impuestos: '', total_neto: '', comprobante: '', hora_transaccion: '' },
              constants: {},
              password: ''
            });
            setTempPassword('');
            setActiveStep(1);
            setShowForm(true);
          }}
          className="bg-indigo-600 text-white px-5 py-2.5 rounded-xl flex items-center gap-2 hover:bg-indigo-700 transition-all shadow-lg shadow-indigo-200 active:scale-95 font-medium"
        >
          <Plus size={18} />
          Nueva Conexión
        </button>
      </div>

      {showForm && (
        <div className="bg-white rounded-2xl border border-indigo-100 shadow-2xl animate-in zoom-in-95 duration-200 overflow-hidden">
          <div className="bg-slate-50 border-b border-slate-100 p-6 flex justify-between items-center">
            <div className="flex items-center gap-4">
              <div className={`flex items-center gap-2 px-3 py-1 rounded-full text-xs font-bold ${activeStep === 1 ? 'bg-indigo-600 text-white' : 'bg-slate-200 text-slate-500'}`}>
                1. Conexión
              </div>
              <div className="w-8 h-px bg-slate-300"></div>
              <div className={`flex items-center gap-2 px-3 py-1 rounded-full text-xs font-bold ${activeStep === 2 ? 'bg-indigo-600 text-white' : 'bg-slate-200 text-slate-500'}`}>
                2. Mapeo de Campos
              </div>
            </div>
            <button onClick={() => {
              setShowForm(false);
              setTempPassword('');
              setEditingConfig({
                id: '', nombre: '', protocolo: 'SFTP', host: '', puerto: 22, usuario: '', ruta_remota: '.', tipo_archivo: 'CSV',
                frecuencia: 'manual', accion_post_procesado: 'ninguna', estado: 'activo',
                mapping: { factura_numero: '', fecha_venta: '', local_codigo: '', total_bruto: '', total_impuestos: '', total_neto: '', comprobante: '', hora_transaccion: '' },
                constants: {},
                password: ''
              });
            }} className="text-slate-400 hover:text-slate-600"><XCircle size={20} /></button>
          </div>

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
                          } else {
                            setEditingConfig({
                              ...editingConfig,
                              id: store.id,
                              nombre: store.nombre,
                              mapping: { ...editingConfig.mapping, local_codigo: store.codigo_interno }
                            });
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
                  <div className="flex gap-4">
                    <div className="flex-1">
                      <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1.5">Protocolo</label>
                      <select
                        className="w-full px-4 py-2.5 rounded-xl border border-slate-200 outline-none bg-white font-medium"
                        value={editingConfig.protocolo}
                        onChange={e => setEditingConfig({ ...editingConfig, protocolo: e.target.value as ImportProtocol, puerto: e.target.value === 'SFTP' ? 22 : 21 })}
                      >
                        <option value="SFTP">SFTP (SSH File Transfer)</option>
                        <option value="FTP">FTP (Estándar)</option>
                        <option value="LOCAL">Directorio Local (Windows/Linux)</option>
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
                      {editingConfig.protocolo === 'LOCAL' ? 'Ruta del Directorio' : 'Ruta Remota de Archivos'}
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
          </div>

          <div className="mt-10 pt-6 border-t border-slate-100 flex justify-end gap-3 px-8 pb-8">
            <button onClick={() => { setShowForm(false); setActiveStep(1); }} className="px-6 py-2.5 text-slate-500 font-medium hover:text-slate-800 transition-colors">Cerrar</button>
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
      )}

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        {loading ? (
          <div className="col-span-full py-20 text-center">
            <RefreshCw className="animate-spin mx-auto text-indigo-400 mb-4" size={32} />
            <p className="text-slate-400 font-medium">Cargando servicios de red...</p>
          </div>
        ) : (configs || []).map(config => (
          <div key={config.id} className="bg-white rounded-3xl border border-slate-200 p-6 hover:shadow-xl hover:shadow-indigo-500/5 transition-all group relative overflow-hidden">
            <div className={`absolute top-0 right-0 px-6 py-2 rounded-bl-3xl text-[10px] font-bold uppercase tracking-widest ${config.protocolo === 'SFTP' ? 'bg-indigo-600 text-white' : config.protocolo === 'LOCAL' ? 'bg-emerald-600 text-white' : 'bg-amber-500 text-white'}`}>
              {config.protocolo === 'LOCAL' ? 'Directorio' : config.protocolo}
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
                  onClick={() => {
                    setEditingConfig(config);
                    setTempPassword(config.password || '');
                    setShowForm(true);
                  }}
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

        {!loading && configs.length === 0 && (
          <div className="col-span-full py-24 bg-white rounded-[2rem] border-2 border-dashed border-slate-200 text-center flex flex-col items-center justify-center">
            <div className="w-20 h-20 bg-slate-50 rounded-full flex items-center justify-center mb-6">
              <Server size={32} className="text-slate-300" />
            </div>
            <h3 className="text-lg font-bold text-slate-800">No hay automatizaciones configuradas</h3>
            <p className="text-slate-400 text-sm mt-1 mb-8 max-w-sm">Conecte sus tiendas vía SFTP para que el sistema audite las ventas cada noche sin intervención manual.</p>
            <button onClick={() => setShowForm(true)} className="bg-indigo-600 text-white px-8 py-3 rounded-2xl font-bold shadow-xl shadow-indigo-100 hover:scale-105 transition-transform">Configurar Primera Fuente</button>
          </div>
        )}
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
                onClick={() => setShowManualModal(false)}
                className="p-2 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded-full transition-colors"
              >
                <XCircle size={24} />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-6">
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
                      {(manualFiles || []).map((file) => (
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
                                  disabled={unmarkingFile === file.nombre}
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
                                disabled={executingFile === file.nombre || fileStatuses[file.nombre] === 'success'}
                                className={`px-4 py-2 rounded-xl text-xs font-bold active:scale-95 transition-all shadow-lg flex items-center gap-2 disabled:opacity-50
                                  ${fileStatuses[file.nombre] === 'success'
                                    ? 'bg-green-500 text-white shadow-green-200 cursor-default'
                                    : fileStatuses[file.nombre] === 'error'
                                      ? 'bg-rose-500 text-white shadow-rose-200 hover:bg-rose-600'
                                      : 'bg-indigo-600 text-white shadow-indigo-200 hover:bg-indigo-700'
                                  }`}
                              >
                                {executingFile === file.nombre ? <RefreshCw className="animate-spin" size={14} />
                                  : fileStatuses[file.nombre] === 'success' ? <CheckCircle2 size={14} />
                                    : <Play size={12} fill="white" />}
                                {fileStatuses[file.nombre] === 'success' ? 'Procesado' : fileStatuses[file.nombre] === 'error' ? 'Reintentar' : 'Procesar Ahora'}
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))}
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
                onClick={() => setShowManualModal(false)}
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
