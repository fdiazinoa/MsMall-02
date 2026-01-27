
import React, { useState, useEffect } from 'react';
import { ApiService } from '../api';
// Fix: Import types from '../types' instead of '../api'
import { ImportConfig, ImportProtocol } from '../types';
import { 
  Server, Plus, Play, Trash2, Settings2, 
  ArrowRightLeft, CheckCircle2, XCircle, Clock,
  Key, Globe, FolderOpen, Database, RefreshCw, AlertCircle
} from 'lucide-react';

const STANDARD_FIELDS = [
  { key: 'factura_numero', label: 'Nº Factura / Boleta', required: true },
  { key: 'fecha_venta', label: 'Fecha Venta', required: true },
  { key: 'local_codigo', label: 'Código Local', required: true },
  { key: 'total_bruto', label: 'Total Bruto', required: true },
  { key: 'total_impuestos', label: 'Impuestos', required: false },
  { key: 'total_neto', label: 'Total Neto', required: false }
];

export const ImportManager: React.FC = () => {
  const [configs, setConfigs] = useState<ImportConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [syncingId, setSyncingId] = useState<string | null>(null);
  const [testingConnection, setTestingConnection] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [activeStep, setActiveStep] = useState(1);
  
  const [editingConfig, setEditingConfig] = useState<ImportConfig>({
    id: '',
    nombre: '',
    protocolo: 'SFTP',
    host: '',
    puerto: 22,
    usuario: '',
    ruta_remota: '/',
    estado: 'activo',
    mapping: {
      factura_numero: '',
      fecha_venta: '',
      local_codigo: '',
      total_bruto: '',
      total_impuestos: '',
      total_neto: ''
    }
  });

  const loadConfigs = async () => {
    setLoading(true);
    const data = await ApiService.getImportConfigs();
    setConfigs(data);
    setLoading(false);
  };

  useEffect(() => { loadConfigs(); }, []);

  const handleTestConnection = async () => {
    setTestingConnection(true);
    const success = await ApiService.testConnection(editingConfig);
    setTestingConnection(false);
    alert(success ? "Conexión exitosa con el servidor remoto." : "Error: No se pudo establecer la conexión. Verifique Host y Usuario.");
  };

  const handleSave = async () => {
    // Validar mapeo mínimo
    const missing = STANDARD_FIELDS.filter(f => f.required && !editingConfig.mapping[f.key]);
    if (missing.length > 0) {
      alert(`Faltan campos obligatorios en el mapeo: ${missing.map(m => m.label).join(', ')}`);
      return;
    }

    await ApiService.saveImportConfig(editingConfig);
    setShowForm(false);
    setActiveStep(1);
    setEditingConfig({
      id: '', nombre: '', protocolo: 'SFTP', host: '', puerto: 22, usuario: '', ruta_remota: '/', estado: 'activo',
      mapping: { factura_numero: '', fecha_venta: '', local_codigo: '', total_bruto: '', total_impuestos: '', total_neto: '' }
    });
    loadConfigs();
  };

  const handleSyncNow = async (id: string) => {
    setSyncingId(id);
    try {
      const result = await ApiService.syncImportConnection(id);
      if (result.success) {
        alert(result.message);
      } else {
        alert("Error en la sincronización: " + result.message);
      }
    } finally {
      setSyncingId(null);
      loadConfigs();
    }
  };

  const handleDelete = async (id: string) => {
    if (confirm('¿Seguro que desea eliminar esta configuración de importación?')) {
      await ApiService.deleteImportConfig(id);
      loadConfigs();
    }
  };

  return (
    <div className="space-y-6 animate-in fade-in duration-500">
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
        <div>
          <h2 className="text-2xl font-bold text-slate-800">Importación Automatizada</h2>
          <p className="text-slate-500 text-sm">Configure conexiones directas vía FTP/SFTP para auditoría automática.</p>
        </div>
        <button 
          onClick={() => setShowForm(true)}
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
            <button onClick={() => setShowForm(false)} className="text-slate-400 hover:text-slate-600"><XCircle size={20}/></button>
          </div>

          <div className="p-8">
            {activeStep === 1 ? (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                <div className="space-y-5">
                  <div>
                    <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1.5">Nombre de la Fuente</label>
                    <input 
                      type="text" className="w-full px-4 py-2.5 rounded-xl border border-slate-200 focus:ring-2 focus:ring-indigo-500 outline-none"
                      placeholder="Ej: Nike Store - SFTP Principal"
                      value={editingConfig.nombre}
                      onChange={e => setEditingConfig({...editingConfig, nombre: e.target.value})}
                    />
                  </div>
                  <div className="flex gap-4">
                    <div className="flex-1">
                      <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1.5">Protocolo</label>
                      <select 
                        className="w-full px-4 py-2.5 rounded-xl border border-slate-200 outline-none bg-white font-medium"
                        value={editingConfig.protocolo}
                        onChange={e => setEditingConfig({...editingConfig, protocolo: e.target.value as ImportProtocol, puerto: e.target.value === 'SFTP' ? 22 : 21})}
                      >
                        <option value="SFTP">SFTP (SSH File Transfer)</option>
                        <option value="FTP">FTP (Estándar)</option>
                      </select>
                    </div>
                    <div className="w-28">
                      <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1.5">Puerto</label>
                      <input 
                        type="number" className="w-full px-4 py-2.5 rounded-xl border border-slate-200 outline-none"
                        value={editingConfig.puerto}
                        onChange={e => setEditingConfig({...editingConfig, puerto: parseInt(e.target.value)})}
                      />
                    </div>
                  </div>
                  <div>
                    <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1.5">Host del Servidor</label>
                    <div className="relative">
                      <Globe size={18} className="absolute left-3.5 top-3 text-slate-300" />
                      <input 
                        type="text" className="w-full pl-11 pr-4 py-2.5 rounded-xl border border-slate-200 outline-none"
                        placeholder="sftp.tu-tienda.com"
                        value={editingConfig.host}
                        onChange={e => setEditingConfig({...editingConfig, host: e.target.value})}
                      />
                    </div>
                  </div>
                </div>
                <div className="space-y-5">
                  <div>
                    <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1.5">Credenciales de Acceso</label>
                    <div className="space-y-3">
                      <div className="relative">
                        <Server size={18} className="absolute left-3.5 top-3 text-slate-300" />
                        <input 
                          type="text" className="w-full pl-11 pr-4 py-2.5 rounded-xl border border-slate-200 outline-none"
                          placeholder="Nombre de usuario"
                          value={editingConfig.usuario}
                          onChange={e => setEditingConfig({...editingConfig, usuario: e.target.value})}
                        />
                      </div>
                      <div className="relative">
                        <Key size={18} className="absolute left-3.5 top-3 text-slate-300" />
                        <input 
                          type="password" className="w-full pl-11 pr-4 py-2.5 rounded-xl border border-slate-200 outline-none"
                          placeholder="Contraseña o Frase de paso SSH"
                        />
                      </div>
                    </div>
                  </div>
                  <div>
                    <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1.5">Ruta Remota de Archivos</label>
                    <div className="relative">
                      <FolderOpen size={18} className="absolute left-3.5 top-3 text-slate-300" />
                      <input 
                        type="text" className="w-full pl-11 pr-4 py-2.5 rounded-xl border border-slate-200 outline-none"
                        placeholder="/home/audit/ventas_diarias/"
                        value={editingConfig.ruta_remota}
                        onChange={e => setEditingConfig({...editingConfig, ruta_remota: e.target.value})}
                      />
                    </div>
                  </div>
                  <button 
                    type="button"
                    onClick={handleTestConnection}
                    disabled={testingConnection || !editingConfig.host}
                    className="w-full py-2.5 border-2 border-indigo-50 text-indigo-600 rounded-xl font-bold flex items-center justify-center gap-2 hover:bg-indigo-50 transition-colors disabled:opacity-50"
                  >
                    {testingConnection ? <RefreshCw className="animate-spin" size={18} /> : <Play size={16} fill="currentColor" />}
                    {testingConnection ? 'Verificando red...' : 'Probar Conexión'}
                  </button>
                </div>
              </div>
            ) : (
              <div className="space-y-6">
                <div className="p-4 bg-indigo-50 rounded-2xl border border-indigo-100 flex gap-4 text-indigo-700 items-start">
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
                
                <div className="grid grid-cols-1 md:grid-cols-2 gap-x-12 gap-y-6 pt-4">
                  {STANDARD_FIELDS.map(field => (
                    <div key={field.key} className="relative group">
                      <div className="flex justify-between items-center mb-1.5">
                        <label className="text-[11px] font-bold text-slate-500 uppercase flex items-center gap-1">
                          {field.label}
                          {field.required && <span className="text-rose-500" title="Requerido">*</span>}
                        </label>
                        <span className="text-[10px] font-mono text-slate-400">Interno: {field.key}</span>
                      </div>
                      <div className="relative">
                        <input 
                          type="text" 
                          className="w-full px-4 py-2.5 rounded-xl border border-slate-200 text-sm focus:ring-2 focus:ring-indigo-500 outline-none pr-10 bg-slate-50 group-hover:bg-white transition-colors"
                          placeholder={`Nombre columna en CSV...`}
                          value={editingConfig.mapping[field.key]}
                          onChange={e => {
                            const newMapping = {...editingConfig.mapping, [field.key]: e.target.value};
                            setEditingConfig({...editingConfig, mapping: newMapping});
                          }}
                        />
                        <ArrowRightLeft size={14} className="absolute right-3.5 top-3 text-slate-300" />
                      </div>
                    </div>
                  ))}
                </div>
                
                <div className="bg-amber-50 p-4 rounded-xl border border-amber-100 flex gap-3 text-amber-700 mt-4">
                  <AlertCircle size={20} className="shrink-0" />
                  <p className="text-[11px] leading-relaxed">
                    <strong>Nota:</strong> Si el archivo remoto no contiene una de las columnas opcionales (Impuestos o Neto), el sistema los calculará automáticamente basándose en el Total Bruto y la configuración del local.
                  </p>
                </div>
              </div>
            )}

            <div className="mt-10 pt-6 border-t border-slate-100 flex justify-end gap-3">
              <button onClick={() => { setShowForm(false); setActiveStep(1); }} className="px-6 py-2.5 text-slate-500 font-medium hover:text-slate-800 transition-colors">Cerrar</button>
              {activeStep === 1 ? (
                <button 
                  onClick={() => setActiveStep(2)}
                  className="bg-indigo-600 text-white px-8 py-2.5 rounded-xl font-bold shadow-lg shadow-indigo-600/20 flex items-center gap-2 hover:bg-indigo-700 active:scale-95 transition-all"
                >
                  Configurar Mapeo <ArrowRightLeft size={18} />
                </button>
              ) : (
                <div className="flex gap-2">
                  <button onClick={() => setActiveStep(1)} className="px-6 py-2.5 border border-slate-200 rounded-xl text-slate-600 font-medium hover:bg-slate-50">Atrás</button>
                  <button onClick={handleSave} className="bg-indigo-600 text-white px-10 py-2.5 rounded-xl font-bold shadow-lg shadow-indigo-600/20 hover:bg-indigo-700 active:scale-95 transition-all">Guardar y Activar</button>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Connection List Grid */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        {loading ? (
          <div className="col-span-full py-20 text-center">
            <RefreshCw className="animate-spin mx-auto text-indigo-400 mb-4" size={32} />
            <p className="text-slate-400 font-medium">Cargando servicios de red...</p>
          </div>
        ) : configs.map(config => (
          <div key={config.id} className="bg-white rounded-3xl border border-slate-200 p-6 hover:shadow-xl hover:shadow-indigo-500/5 transition-all group relative overflow-hidden">
            {/* Protocol Badge */}
            <div className={`absolute top-0 right-0 px-6 py-2 rounded-bl-3xl text-[10px] font-bold uppercase tracking-widest ${config.protocolo === 'SFTP' ? 'bg-indigo-600 text-white' : 'bg-amber-500 text-white'}`}>
              {config.protocolo}
            </div>
            
            <div className="flex items-start gap-4 mb-6">
              <div className={`p-4 rounded-2xl ${config.protocolo === 'SFTP' ? 'bg-indigo-50 text-indigo-600' : 'bg-amber-50 text-amber-600'}`}>
                <Server size={28} />
              </div>
              <div>
                <h4 className="font-bold text-slate-800 text-lg">{config.nombre}</h4>
                <div className="flex items-center gap-2 text-xs text-slate-400 mt-1">
                  <Globe size={14} /> 
                  <span className="font-medium">{config.host}:{config.puerto}</span>
                  <span className="w-1 h-1 bg-slate-300 rounded-full"></span>
                  <FolderOpen size={14} /> 
                  <span className="truncate max-w-[150px]">{config.ruta_remota}</span>
                </div>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4 my-6">
              <div className="p-4 bg-slate-50 rounded-2xl border border-slate-100">
                <div className="flex items-center gap-2 text-slate-400 text-[10px] font-bold uppercase tracking-wider mb-2">
                  <Clock size={12} /> Última Ejecución
                </div>
                <p className="text-xs font-bold text-slate-700">{config.ultima_ejecucion || 'Pendiente'}</p>
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
                  {Object.keys(config.mapping).filter(k => config.mapping[k]).slice(0, 3).map(k => (
                    <span key={k} className="px-1.5 py-0.5 bg-white border border-slate-200 rounded text-[8px] font-bold text-slate-500 uppercase">{k.replace('_',' ')}</span>
                  ))}
                  {Object.keys(config.mapping).filter(k => config.mapping[k]).length > 3 && (
                    <span className="text-[8px] text-slate-400 font-bold">+{Object.keys(config.mapping).filter(k => config.mapping[k]).length - 3}</span>
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
                  onClick={() => { setEditingConfig(config); setShowForm(true); }}
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
                  onClick={() => handleSyncNow(config.id)}
                  disabled={syncingId === config.id}
                  className="bg-slate-900 text-white px-5 py-2.5 rounded-xl text-xs font-bold hover:bg-indigo-600 transition-all flex items-center gap-2 shadow-lg shadow-slate-200 active:scale-95 disabled:opacity-50"
                >
                  {syncingId === config.id ? <RefreshCw className="animate-spin" size={14} /> : <Play size={14} fill="white" />}
                  {syncingId === config.id ? 'Sincronizando...' : 'Ejecutar Ahora'}
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
    </div>
  );
};
