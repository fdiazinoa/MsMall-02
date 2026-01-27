
import React, { useState } from 'react';
import { ApiService } from '../api';

export const UploadForm: React.FC = () => {
  const [file, setFile] = useState<File | null>(null);
  const [apiKey, setApiKey] = useState('demo-key-123');
  const [status, setStatus] = useState<{ type: 'success' | 'error' | 'info' | 'idle', message: string }>({ type: 'idle', message: '' });
  const [isLoading, setIsLoading] = useState(false);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0]);
      setStatus({ type: 'idle', message: '' });
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) return;

    setIsLoading(true);
    setStatus({ type: 'idle', message: '' });

    try {
      const result = await ApiService.ingestSales(file, apiKey);
      
      setStatus({ 
        type: result.message.includes('Mock') ? 'info' : 'success', 
        message: `¡Listo! ${result.message}. Se procesaron ${result.records_processed} registros.` 
      });
      
      setFile(null);
      const fileInput = document.getElementById('csv-upload') as HTMLInputElement;
      if (fileInput) fileInput.value = '';
      
    } catch (error) {
      console.error("Upload error:", error);
      setStatus({ 
        type: 'error', 
        message: 'Ocurrió un error al procesar el archivo. Verifica el formato.' 
      });
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-8">
      <div className="mb-8">
        <h3 className="text-xl font-bold text-slate-800">Cargar Ventas (CSV)</h3>
        <p className="text-slate-500 mt-1">Sube el archivo de ventas diario para procesar auditoría.</p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-6">
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-2">Clave API del Local (Header: X-API-Key)</label>
          <input 
            type="text" 
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            className="w-full px-4 py-2 rounded-lg border border-slate-300 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition-all outline-none"
            placeholder="Introduce la API Key del local..."
            required
          />
        </div>

        <div className="border-2 border-dashed border-slate-300 rounded-xl p-10 flex flex-col items-center justify-center bg-slate-50 hover:bg-slate-100 transition-colors cursor-pointer relative">
          <input 
            type="file" 
            id="csv-upload"
            accept=".csv"
            onChange={handleFileChange}
            className="absolute inset-0 opacity-0 cursor-pointer"
            required
          />
          <svg xmlns="http://www.w3.org/2000/svg" className="w-12 h-12 text-slate-400 mb-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M4 14.899A7 7 0 1 1 15.71 8h1.79a4.5 4.5 0 0 1 2.5 8.242"/><path d="M12 12v9"/><path d="m16 16-4-4-4 4"/></svg>
          <p className="text-slate-600 font-medium">{file ? file.name : 'Haz clic o arrastra un archivo CSV'}</p>
          <p className="text-slate-400 text-sm mt-1">Formato: factura, fecha, local, bruto, impuestos, neto</p>
        </div>

        {status.type !== 'idle' && (
          <div className={`p-4 rounded-lg flex items-start gap-3 ${
            status.type === 'success' ? 'bg-green-50 text-green-700' : 
            status.type === 'info' ? 'bg-blue-50 text-blue-700' : 
            'bg-red-50 text-red-700'
          }`}>
            <span className="mt-0.5">
              {status.type === 'success' ? '✅' : status.type === 'info' ? 'ℹ️' : '❌'}
            </span>
            <p className="text-sm font-medium">{status.message}</p>
          </div>
        )}

        <button
          type="submit"
          disabled={!file || isLoading}
          className={`w-full py-3 rounded-xl font-semibold text-white transition-all shadow-lg ${
            !file || isLoading ? 'bg-slate-400 cursor-not-allowed' : 'bg-indigo-600 hover:bg-indigo-700 active:scale-95'
          }`}
        >
          {isLoading ? 'Procesando...' : 'Iniciar Ingesta de Datos'}
        </button>
      </form>

      <div className="mt-8 pt-8 border-t border-slate-100">
        <h4 className="text-sm font-semibold text-slate-700 mb-4">Ejemplo del Formato Requerido:</h4>
        <div className="bg-slate-900 rounded-lg p-4 font-mono text-xs text-indigo-300 overflow-x-auto">
          <p>factura_numero,fecha_venta,local_codigo,total_bruto,total_impuestos,total_neto</p>
          <p>12345,2024-01-26,L001,100.00,10.00,90.00</p>
          <p>12346,2024-01-26,L001,50.00,5.00,45.00</p>
        </div>
      </div>
    </div>
  );
};
