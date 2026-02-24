import React, { useState } from 'react';
import { ApiService } from '../api';
import { useAuth } from '../context/AuthProvider';
import Papa from 'papaparse';
import { ArrowRight, FileSpreadsheet, AlertCircle, CheckCircle2, Upload, Info } from 'lucide-react';

const REQUIRED_COLUMNS = [
  { key: 'factura_numero', label: 'Número de Factura', index: 0 },
  { key: 'fecha_venta', label: 'Fecha de Venta', index: 1 },
  { key: 'local_codigo', label: 'Código de Local', index: 2 },
  { key: 'total_bruto', label: 'Total Bruto', index: 3 },
  { key: 'total_impuestos', label: 'Impuestos', index: 4 },
  { key: 'total_neto', label: 'Total Neto', index: 5 },
];

const DATE_FORMAT_OPTIONS = [
  { value: 'auto', label: 'Auto (detectar)' },
  { value: 'dd/mm/yyyy', label: 'DD/MM/YYYY' },
  { value: 'dd/mm/yy', label: 'DD/MM/YY' },
  { value: 'mm/dd/yyyy', label: 'MM/DD/YYYY' },
  { value: 'mm/dd/yy', label: 'MM/DD/YY' },
  { value: 'yyyy-mm-dd', label: 'YYYY-MM-DD' },
  { value: 'dd-mm-yyyy', label: 'DD-MM-YYYY' },
  { value: 'dd-mm-yy', label: 'DD-MM-YY' },
  { value: 'yyyy/mm/dd', label: 'YYYY/MM/DD' },
  { value: 'yyyymmdd', label: 'YYYYMMDD (con/sin hora)' },
] as const;

export const UploadForm: React.FC = () => {
  const { currentMall } = useAuth();
  const [file, setFile] = useState<File | null>(null);
  const [apiKey, setApiKey] = useState('demo-key-123');
  const [status, setStatus] = useState<{ type: 'success' | 'error' | 'info' | 'idle', message: string }>({ type: 'idle', message: '' });
  const [isLoading, setIsLoading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);

  // Mapping State
  const [isMappingNeeded, setIsMappingNeeded] = useState(false);
  const [csvHeaders, setCsvHeaders] = useState<string[]>([]);
  const [columnMapping, setColumnMapping] = useState<Record<string, string>>({});
  const [constantValues, setConstantValues] = useState<Record<string, string>>({});
  const [dateFormatPreference, setDateFormatPreference] = useState<(typeof DATE_FORMAT_OPTIONS)[number]['value']>('auto');

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const selectedFile = e.target.files[0];
      setFile(selectedFile);
      setStatus({ type: 'idle', message: '' });
      setUploadProgress(0);
      setIsMappingNeeded(false);
      setConstantValues({});

      // Analyze CSV headers
      Papa.parse(selectedFile, {
        header: true,
        preview: 1,
        complete: (results) => {
          if (results.meta.fields) {
            const headers = results.meta.fields;
            setCsvHeaders(headers);

            // Check if all required columns exist exactly
            const missingColumns = REQUIRED_COLUMNS.filter(col => !headers.includes(col.key));

            if (missingColumns.length > 0) {
              setIsMappingNeeded(true);
              // Auto-map if possible (fuzzy match or exact match)
              const initialMapping: Record<string, string> = {};
              REQUIRED_COLUMNS.forEach(req => {
                const match = headers.find(h => h.toLowerCase().includes(req.key.split('_')[0]) || h.toLowerCase() === req.key.toLowerCase());
                if (match) initialMapping[req.key] = match;
              });
              setColumnMapping(initialMapping);
            }
          }
        },
        error: (err) => {
          console.error("Error parsing CSV:", err);
          setStatus({ type: 'error', message: 'Error al leer el archivo CSV.' });
        }
      });
    }
  };

  const handleMappingChange = (requiredKey: string, selectedHeader: string) => {
    setColumnMapping(prev => ({ ...prev, [requiredKey]: selectedHeader }));
    if (selectedHeader !== 'CONSTANT') {
      setConstantValues(prev => {
        const newValues = { ...prev };
        delete newValues[requiredKey];
        return newValues;
      });
    }
  };

  const handleConstantChange = (requiredKey: string, value: string) => {
    setConstantValues(prev => ({ ...prev, [requiredKey]: value }));
  };

  const normalizeDate = (dateStr: string): string => {
    // Preserve the original value. ApiService.ingestSales applies the selected parser
    // deterministically to avoid browser-dependent Date parsing.
    return String(dateStr || '').trim();
  };

  const processMappedFile = async (originalFile: File): Promise<File> => {
    return new Promise((resolve, reject) => {
      Papa.parse(originalFile, {
        header: true,
        complete: (results) => {
          try {
            // Transform data based on mapping
            const transformedData = results.data.map((row: any) => {
              // Create array in specific order expected by api.ts
              // [factura, fecha, local, bruto, impuestos, neto]
              return REQUIRED_COLUMNS.map(col => {
                const mappedHeader = columnMapping[col.key];
                let value = '';

                if (mappedHeader === 'CONSTANT') {
                  value = constantValues[col.key] || '';
                } else {
                  value = row[mappedHeader] || '';
                }

                // Normalize Date if this is the date column
                if (col.key === 'fecha_venta') {
                  return normalizeDate(value);
                }

                return value;
              });
            });

            // Filter out empty rows
            const cleanData = transformedData.filter(row => row.some(cell => cell !== ''));

            // Add header row expected by api.ts logic (it skips first row)
            const headerRow = REQUIRED_COLUMNS.map(c => c.key);

            // Unparse to CSV string
            const csv = Papa.unparse([headerRow, ...cleanData], { header: false });

            const newFile = new File([csv], "mapped_sales.csv", { type: "text/csv" });
            resolve(newFile);
          } catch (err) {
            reject(err);
          }
        },
        error: (err) => reject(err)
      });
    });
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) return;

    setIsLoading(true);
    setUploadProgress(0);
    setStatus({ type: 'idle', message: '' });

    try {
      if (!currentMall?.id) {
        throw new Error('Selecciona un mall antes de importar.');
      }

      let fileToUpload = file;

      if (isMappingNeeded) {
        // Validate mapping
        const missingMappings = REQUIRED_COLUMNS.filter(col => {
          const mapping = columnMapping[col.key];
          if (!mapping) return true;
          if (mapping === 'CONSTANT' && !constantValues[col.key]) return true;
          return false;
        });

        if (missingMappings.length > 0) {
          throw new Error(`Falta mapear o definir valor para: ${missingMappings.map(c => c.label).join(', ')}`);
        }
        setStatus({ type: 'info', message: 'Transformando archivo según mapeo...' });
        fileToUpload = await processMappedFile(file);
      }

      const result = await ApiService.ingestSales(
        fileToUpload,
        apiKey,
        currentMall.id,
        (progress) => {
          setUploadProgress(progress);
        },
        dateFormatPreference
      );

      setStatus({
        type: result.message.includes('Mock') ? 'info' : 'success',
        message: `¡Listo! ${result.message}. Se procesaron ${result.records_processed} registros.`
      });

      if (!isMappingNeeded) {
        setFile(null);
        const fileInput = document.getElementById('csv-upload') as HTMLInputElement;
        if (fileInput) fileInput.value = '';
      }

    } catch (error: any) {
      console.error("Upload error:", error);
      setStatus({
        type: 'error',
        message: error.message || 'Ocurrió un error al procesar el archivo.'
      });
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-8">
      <div className="mb-8">
        <h3 className="text-xl font-bold text-slate-800 flex items-center gap-2">
          <Upload className="text-indigo-600" size={24} />
          Cargar Ventas (CSV)
        </h3>
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

        <div>
          <label className="block text-sm font-medium text-slate-700 mb-2">Formato de Fecha (como importador FTP)</label>
          <select
            value={dateFormatPreference}
            onChange={(e) => setDateFormatPreference(e.target.value as (typeof DATE_FORMAT_OPTIONS)[number]['value'])}
            className="w-full px-4 py-2 rounded-lg border border-slate-300 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition-all outline-none bg-white"
          >
            {DATE_FORMAT_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </select>
          <p className="text-xs text-slate-500 mt-1">
            Usa un formato fijo para fechas ambiguas (ej. <code>13/01/26</code>). `Auto` mantiene detección automática.
          </p>
        </div>

        <div className={`border-2 border-dashed rounded-xl p-10 flex flex-col items-center justify-center transition-all cursor-pointer relative ${isMappingNeeded ? 'border-amber-300 bg-amber-50' : 'border-slate-300 bg-slate-50 hover:bg-slate-100'}`}>
          <input
            type="file"
            id="csv-upload"
            accept=".csv"
            onChange={handleFileChange}
            className="absolute inset-0 opacity-0 cursor-pointer"
            required={!file} // Only required if no file selected yet
          />
          <FileSpreadsheet className={`w-12 h-12 mb-4 ${isMappingNeeded ? 'text-amber-500' : 'text-slate-400'}`} />
          <p className="text-slate-600 font-medium">{file ? file.name : 'Haz clic o arrastra un archivo CSV'}</p>
          {!isMappingNeeded && <p className="text-slate-400 text-sm mt-1">Formato: factura, fecha, local, bruto, impuestos, neto</p>}
        </div>

        {isMappingNeeded && (
          <div className="bg-amber-50 border border-amber-200 rounded-xl p-6 animate-in fade-in slide-in-from-top-4">
            <div className="flex items-center gap-2 mb-4 text-amber-800">
              <AlertCircle size={20} />
              <h4 className="font-bold">Mapeo de Columnas Requerido</h4>
            </div>
            <p className="text-sm text-amber-700 mb-4">
              El archivo no coincide con el formato estándar. Por favor, relaciona las columnas de tu archivo con los campos requeridos.
              Si una columna no existe en el archivo, selecciona "VALOR CONSTANTE" para ingresar un valor fijo.
            </p>

            <div className="space-y-3">
              {REQUIRED_COLUMNS.map((col) => (
                <div key={col.key} className="grid grid-cols-1 md:grid-cols-3 gap-4 items-center bg-white p-3 rounded-lg border border-amber-100">
                  <div className="font-medium text-slate-700 text-sm flex items-center gap-2">
                    <div className="w-6 h-6 rounded-full bg-indigo-100 text-indigo-600 flex items-center justify-center text-xs font-bold">
                      {col.index + 1}
                    </div>
                    {col.label}
                  </div>
                  <div className="flex justify-center text-slate-400">
                    <ArrowRight size={16} />
                  </div>
                  <div className="flex flex-col gap-2">
                    <select
                      value={columnMapping[col.key] || ''}
                      onChange={(e) => handleMappingChange(col.key, e.target.value)}
                      className="w-full px-3 py-2 rounded-lg border border-slate-300 text-sm focus:ring-2 focus:ring-indigo-500 outline-none"
                      required
                    >
                      <option value="">-- Seleccionar Columna --</option>
                      <option value="CONSTANT" className="font-bold text-indigo-600">-- VALOR CONSTANTE --</option>
                      {csvHeaders.map(h => (
                        <option key={h} value={h}>{h}</option>
                      ))}
                    </select>
                    {columnMapping[col.key] === 'CONSTANT' && (
                      <input
                        type="text"
                        placeholder={`Valor para ${col.label}`}
                        value={constantValues[col.key] || ''}
                        onChange={(e) => handleConstantChange(col.key, e.target.value)}
                        className="w-full px-3 py-2 rounded-lg border border-indigo-300 bg-indigo-50 text-sm focus:ring-2 focus:ring-indigo-500 outline-none animate-in fade-in slide-in-from-top-1"
                        required
                      />
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {status.type !== 'idle' && (
          <div className={`p-4 rounded-lg flex items-start gap-3 ${status.type === 'success' ? 'bg-green-50 text-green-700' :
            status.type === 'info' ? 'bg-blue-50 text-blue-700' :
              'bg-red-50 text-red-700'
            }`}>
            <span className="mt-0.5">
              {status.type === 'success' ? <CheckCircle2 size={18} /> : status.type === 'info' ? <Info size={18} /> : <AlertCircle size={18} />}
            </span>
            <p className="text-sm font-medium">{status.message}</p>
          </div>
        )}

        {isLoading && (
          <div className="w-full bg-slate-200 rounded-full h-2.5 mb-4 overflow-hidden">
            <div
              className="bg-indigo-600 h-2.5 rounded-full transition-all duration-300 ease-out"
              style={{ width: `${uploadProgress}%` }}
            ></div>
            <p className="text-xs text-center text-slate-500 mt-1">{uploadProgress}% Completado</p>
          </div>
        )}

        <button
          type="submit"
          disabled={!file || isLoading}
          className={`w-full py-3 rounded-xl font-semibold text-white transition-all shadow-lg ${!file || isLoading ? 'bg-slate-400 cursor-not-allowed' : 'bg-indigo-600 hover:bg-indigo-700 active:scale-95'
            }`}
        >
          {isLoading ? 'Procesando...' : isMappingNeeded ? 'Transformar e Ingestar' : 'Iniciar Ingesta de Datos'}
        </button>
      </form>

      {!isMappingNeeded && (
        <div className="mt-8 pt-8 border-t border-slate-100">
          <h4 className="text-sm font-semibold text-slate-700 mb-4">Ejemplo del Formato Requerido:</h4>
          <div className="bg-slate-900 rounded-lg p-4 font-mono text-xs text-indigo-300 overflow-x-auto">
            <p>factura_numero,fecha_venta,local_codigo,total_bruto,total_impuestos,total_neto</p>
            <p>12345,2024-01-26,L001,100.00,10.00,90.00</p>
            <p>12346,2024-01-26,L001,50.00,5.00,45.00</p>
          </div>
        </div>
      )}
    </div>
  );
};
