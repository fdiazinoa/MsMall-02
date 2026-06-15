import React, { useMemo, useState } from 'react';
import Papa from 'papaparse';
import { AlertCircle, CheckCircle2, Download, FileSpreadsheet, RefreshCcw, Store as StoreIcon, Upload } from 'lucide-react';
import { ApiService, Store } from '../api';
import { useAuth } from '../context/AuthProvider';

type DelimiterOption = 'auto' | ',' | ';' | '\t' | '|';

type ImportField =
  | 'codigo_interno'
  | 'nombre'
  | 'responsable'
  | 'contrato_no'
  | 'piso'
  | 'tipo_negocio'
  | 'mts'
  | 'porciento_renta'
  | 'breakpoint_venta'
  | 'rubro'
  | 'upsert_activo';

type PreviewRow = Record<string, string>;

const IMPORT_FIELDS: Array<{ key: ImportField; label: string; required?: boolean }> = [
  { key: 'codigo_interno', label: 'Codigo interno', required: true },
  { key: 'nombre', label: 'Nombre del local', required: true },
  { key: 'responsable', label: 'Responsable' },
  { key: 'contrato_no', label: 'Contrato' },
  { key: 'piso', label: 'Piso' },
  { key: 'tipo_negocio', label: 'Tipo de negocio' },
  { key: 'mts', label: 'Metraje' },
  { key: 'porciento_renta', label: 'Porcentaje renta' },
  { key: 'breakpoint_venta', label: 'Breakpoint venta' },
  { key: 'rubro', label: 'Rubro' },
  { key: 'upsert_activo', label: 'Upsert activo' },
];

const DELIMITER_OPTIONS: Array<{ value: DelimiterOption; label: string }> = [
  { value: 'auto', label: 'Auto detectar' },
  { value: ',', label: 'Coma (,)' },
  { value: ';', label: 'Punto y coma (;)' },
  { value: '\t', label: 'Tab' },
  { value: '|', label: 'Pipe (|)' },
];

const REQUIRED_FIELDS = IMPORT_FIELDS.filter((field) => field.required).map((field) => field.key);

const emptyMapping = (): Record<ImportField, string> =>
  IMPORT_FIELDS.reduce((acc, field) => {
    acc[field.key] = '';
    return acc;
  }, {} as Record<ImportField, string>);

const normalizeHeader = (value: string): string =>
  String(value || '')
    .trim()
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '');

const parseOptionalNumber = (value: string): number | null => {
  const raw = String(value || '').trim();
  if (!raw) return null;
  const normalized = raw.replace(/\s+/g, '').replace(/%/g, '').replace(/,/g, '.');
  const parsed = Number(normalized);
  return Number.isFinite(parsed) ? parsed : null;
};

const parseBoolean = (value: string): boolean => {
  const raw = String(value || '').trim().toLowerCase();
  return ['1', 'true', 'si', 'sí', 'yes', 'y', 'activo'].includes(raw);
};

const buildTemplate = (): string => {
  const headers = IMPORT_FIELDS.map((field) => field.key).join(',');
  const sample = [
    'K-80',
    'American Eagle',
    'Juan Perez',
    'CTR-001',
    'Nivel 2',
    'RETAIL',
    '120',
    '7.5',
    '1500000',
    'MODA',
    'true',
  ].join(',');
  return `${headers}\n${sample}\n`;
};

export const StoreImportTool: React.FC = () => {
  const { currentMall, session, isAdmin, isTic } = useAuth();
  const authToken = session?.access_token || '';
  const canManageStores = isAdmin || isTic;

  const [file, setFile] = useState<File | null>(null);
  const [delimiter, setDelimiter] = useState<DelimiterOption>('auto');
  const [hasHeaderRow, setHasHeaderRow] = useState(true);
  const [headers, setHeaders] = useState<string[]>([]);
  const [mapping, setMapping] = useState<Record<ImportField, string>>(emptyMapping());
  const [previewRows, setPreviewRows] = useState<PreviewRow[]>([]);
  const [rawRows, setRawRows] = useState<PreviewRow[]>([]);
  const [status, setStatus] = useState<{ type: 'idle' | 'success' | 'error' | 'info'; message: string }>({ type: 'idle', message: '' });
  const [isParsing, setIsParsing] = useState(false);
  const [isImporting, setIsImporting] = useState(false);
  const [importResult, setImportResult] = useState<{ created: number; updated: number; failed: number; errors: string[] } | null>(null);

  const missingRequiredMappings = useMemo(
    () => REQUIRED_FIELDS.filter((field) => !mapping[field]),
    [mapping]
  );

  const inferMapping = (nextHeaders: string[]) => {
    const normalizedHeaders = nextHeaders.map((header) => ({ original: header, normalized: normalizeHeader(header) }));
    const nextMapping = emptyMapping();

    IMPORT_FIELDS.forEach((field) => {
      const directMatch = normalizedHeaders.find((header) => header.normalized === field.key);
      if (directMatch) {
        nextMapping[field.key] = directMatch.original;
        return;
      }

      const partialMatch = normalizedHeaders.find((header) => header.normalized.includes(field.key));
      if (partialMatch) {
        nextMapping[field.key] = partialMatch.original;
      }
    });

    setMapping(nextMapping);
  };

  const parseFile = (selectedFile: File, selectedDelimiter: DelimiterOption, withHeader: boolean) => {
    setIsParsing(true);
    setStatus({ type: 'idle', message: '' });
    setImportResult(null);

    Papa.parse<string[]>(selectedFile, {
      delimiter: selectedDelimiter === 'auto' ? '' : selectedDelimiter,
      skipEmptyLines: true,
      complete: (results) => {
        try {
          const parsedRows = (results.data || [])
            .filter((row) => Array.isArray(row) && row.some((cell) => String(cell ?? '').trim() !== ''))
            .map((row) => row.map((cell) => String(cell ?? '').trim()));

          if (parsedRows.length === 0) {
            setHeaders([]);
            setPreviewRows([]);
            setRawRows([]);
            setMapping(emptyMapping());
            setStatus({ type: 'error', message: 'El archivo no contiene filas utilizables.' });
            return;
          }

          const detectedHeaders = withHeader
            ? parsedRows[0].map((header, index) => header || `columna_${index + 1}`)
            : Array.from({ length: parsedRows[0].length }, (_, index) => `columna_${index + 1}`);

          const dataRows = withHeader ? parsedRows.slice(1) : parsedRows;
          const normalizedRows = dataRows.map((row) => {
            const record: PreviewRow = {};
            detectedHeaders.forEach((header, index) => {
              record[header] = String(row[index] ?? '').trim();
            });
            return record;
          });

          setHeaders(detectedHeaders);
          setRawRows(normalizedRows);
          setPreviewRows(normalizedRows.slice(0, 6));
          inferMapping(detectedHeaders);
          setStatus({ type: 'info', message: `Archivo analizado. ${normalizedRows.length} filas listas para importar.` });
        } catch (error: any) {
          console.error('Error parsing store import file:', error);
          setStatus({ type: 'error', message: error?.message || 'No se pudo analizar el archivo.' });
        } finally {
          setIsParsing(false);
        }
      },
      error: (error) => {
        console.error('Error parsing store import file:', error);
        setStatus({ type: 'error', message: 'No se pudo leer el archivo.' });
        setIsParsing(false);
      },
    });
  };

  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = event.target.files?.[0];
    if (!selectedFile) return;
    setFile(selectedFile);
    parseFile(selectedFile, delimiter, hasHeaderRow);
  };

  const rebuildParsedFile = () => {
    if (!file) return;
    parseFile(file, delimiter, hasHeaderRow);
  };

  const handleDownloadTemplate = () => {
    const blob = new Blob([buildTemplate()], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'template_importador_locales.csv';
    link.click();
    URL.revokeObjectURL(url);
  };

  const buildStorePayload = (row: PreviewRow): Partial<Store> | null => {
    const codigoInterno = mapping.codigo_interno ? String(row[mapping.codigo_interno] || '').trim() : '';
    const nombre = mapping.nombre ? String(row[mapping.nombre] || '').trim() : '';
    if (!codigoInterno || !nombre || !currentMall?.id) return null;
    const mtsValue = mapping.mts ? parseOptionalNumber(String(row[mapping.mts] || '')) : null;
    const porcientoRentaValue = mapping.porciento_renta ? parseOptionalNumber(String(row[mapping.porciento_renta] || '')) : null;
    const breakpointVentaValue = mapping.breakpoint_venta ? parseOptionalNumber(String(row[mapping.breakpoint_venta] || '')) : null;

    const payload: Partial<Store> = {
      mall_id: currentMall.id,
      codigo_interno: codigoInterno,
      nombre,
      responsable: mapping.responsable ? String(row[mapping.responsable] || '').trim() : '',
      contrato_no: mapping.contrato_no ? String(row[mapping.contrato_no] || '').trim() : '',
      piso: mapping.piso ? String(row[mapping.piso] || '').trim() : '',
      tipo_negocio: mapping.tipo_negocio ? String(row[mapping.tipo_negocio] || '').trim() : '',
      rubro: mapping.rubro ? String(row[mapping.rubro] || '').trim() : '',
      upsert_activo: mapping.upsert_activo ? parseBoolean(String(row[mapping.upsert_activo] || '')) : false,
    };

    if (mtsValue !== null) (payload as any).mts = mtsValue;
    if (porcientoRentaValue !== null) payload.porciento_renta = porcientoRentaValue;
    if (breakpointVentaValue !== null) payload.breakpoint_venta = breakpointVentaValue;
    if (!payload.tipo_negocio) delete (payload as any).tipo_negocio;
    if (!payload.rubro) delete (payload as any).rubro;
    return payload;
  };

  const normalizeCatalogValue = (value: string): string => String(value || '').trim().replace(/\s+/g, ' ');

  const ensureCatalogValues = async () => {
    if (!currentMall?.id) return;
    const fields: Array<'tipo_negocio' | 'rubro'> = ['tipo_negocio', 'rubro'];
    const catalogResult = await ApiService.getStoreCatalogOptions(currentMall.id);
    const existing = new Set(
      (catalogResult.options || []).map((option) => `${option.field_name}:${normalizeHeader(option.value)}`)
    );

    for (const field of fields) {
      const mappedHeader = mapping[field];
      if (!mappedHeader) continue;
      const values = Array.from(new Set(
        rawRows
          .map((row) => normalizeCatalogValue(row[mappedHeader] || ''))
          .filter(Boolean)
      ));
      for (const value of values) {
        const key = `${field}:${normalizeHeader(value)}`;
        if (existing.has(key)) continue;
        await ApiService.createStoreCatalogOption({
          mall_id: currentMall.id,
          field_name: field,
          value,
        });
        existing.add(key);
      }
    }
  };

  const handleImport = async () => {
    if (!currentMall?.id) {
      setStatus({ type: 'error', message: 'Seleccione un mall antes de importar.' });
      return;
    }
    if (!canManageStores) {
      setStatus({ type: 'error', message: 'Solo IT o ADMIN pueden importar locales.' });
      return;
    }
    if (!authToken) {
      setStatus({ type: 'error', message: 'La sesión no tiene token válido. Vuelva a iniciar sesión e intente nuevamente.' });
      return;
    }
    if (rawRows.length === 0) {
      setStatus({ type: 'error', message: 'No hay filas para importar.' });
      return;
    }
    if (missingRequiredMappings.length > 0) {
      setStatus({ type: 'error', message: 'Faltan columnas requeridas por mapear: codigo_interno y/o nombre.' });
      return;
    }

    setIsImporting(true);
    setImportResult(null);

    try {
      await ensureCatalogValues();
      const existingStores = await ApiService.getStores(currentMall.id, true);
      const existingByCode = new Map(
        existingStores
          .filter((store) => String(store.codigo_interno || '').trim() !== '')
          .map((store) => [String(store.codigo_interno).trim().toLowerCase(), store])
      );

      let created = 0;
      let updated = 0;
      let failed = 0;
      const errors: string[] = [];

      for (let index = 0; index < rawRows.length; index += 1) {
        const row = rawRows[index];
        const payload = buildStorePayload(row);
        if (!payload) {
          failed += 1;
          errors.push(`Fila ${index + 1}: faltan codigo_interno o nombre.`);
          continue;
        }

        const existing = existingByCode.get(String(payload.codigo_interno).trim().toLowerCase());

        try {
          if (existing?.id) {
            await ApiService.updateStore(existing.id, { ...payload, id: existing.id }, authToken);
            updated += 1;
          } else {
            await ApiService.createStore(payload, authToken);
            created += 1;
          }
        } catch (error: any) {
          failed += 1;
          const rawMessage = String(error?.message || 'error importando local');
          const friendlyMessage = rawMessage.toLowerCase().includes('codigo_interno')
            && (rawMessage.toLowerCase().includes('duplicate') || rawMessage.toLowerCase().includes('duplic') || rawMessage.includes('23505'))
            ? 'codigo_interno ya existe globalmente. Aplicar 20260615_locales_codigo_interno_per_mall.sql para permitir códigos por mall.'
            : rawMessage;
          errors.push(`Fila ${index + 1} (${payload.codigo_interno}): ${friendlyMessage}`);
        }
      }

      setImportResult({ created, updated, failed, errors });
      if (failed === 0) {
        setStatus({ type: 'success', message: `Importación completada. ${created} creados, ${updated} actualizados.` });
      } else {
        setStatus({ type: 'error', message: `Importación parcial. ${created} creados, ${updated} actualizados, ${failed} con error.` });
      }
    } catch (error: any) {
      console.error('Error importing stores:', error);
      setStatus({ type: 'error', message: error?.message || 'No se pudo completar la importación.' });
    } finally {
      setIsImporting(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="space-y-2">
            <div className="inline-flex items-center gap-2 rounded-full bg-indigo-50 px-3 py-1 text-xs font-bold uppercase tracking-wide text-indigo-600">
              <StoreIcon size={14} />
              Herramientas
            </div>
            <div>
              <h2 className="text-2xl font-bold text-slate-900">Importador de Locales</h2>
              <p className="mt-1 text-sm text-slate-500">
                Carga o actualiza locales del mall actual desde archivos CSV o TXT usando el codigo interno como llave operativa.
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={handleDownloadTemplate}
            className="inline-flex items-center gap-2 rounded-xl border border-slate-200 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            <Download size={16} />
            Descargar plantilla
          </button>
        </div>

        <div className="mt-6 grid gap-4 md:grid-cols-3">
          <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
            <label className="mb-2 block text-sm font-medium text-slate-700">Archivo CSV o TXT</label>
            <label className="flex min-h-[130px] cursor-pointer flex-col items-center justify-center gap-3 rounded-2xl border border-dashed border-slate-300 bg-white px-4 py-6 text-center hover:border-indigo-400 hover:bg-indigo-50/30">
              <Upload className="text-indigo-600" size={26} />
              <div>
                <p className="text-sm font-semibold text-slate-800">{file ? file.name : 'Seleccione un archivo'}</p>
                <p className="text-xs text-slate-500">Soporta `.csv` y `.txt` delimitados.</p>
              </div>
              <input type="file" accept=".csv,.txt,text/csv,text/plain" className="hidden" onChange={handleFileChange} />
            </label>
          </div>

          <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
            <label className="mb-2 block text-sm font-medium text-slate-700">Separador</label>
            <select
              value={delimiter}
              onChange={(e) => setDelimiter(e.target.value as DelimiterOption)}
              className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-indigo-500"
            >
              {DELIMITER_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>

            <label className="mt-4 flex items-center gap-2 text-sm text-slate-600">
              <input
                type="checkbox"
                checked={hasHeaderRow}
                onChange={(e) => setHasHeaderRow(e.target.checked)}
              />
              El archivo incluye fila de encabezados
            </label>

            <button
              type="button"
              onClick={rebuildParsedFile}
              disabled={!file || isParsing}
              className="mt-4 inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100 disabled:opacity-60"
            >
              <RefreshCcw size={16} />
              Reanalizar archivo
            </button>
          </div>

          <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
            <div className="mb-2 flex items-center gap-2 text-sm font-medium text-slate-700">
              <FileSpreadsheet size={16} />
              Resumen
            </div>
            <div className="space-y-2 text-sm text-slate-600">
              <p><span className="font-semibold text-slate-800">Mall:</span> {currentMall?.nombre || 'Sin seleccionar'}</p>
              <p><span className="font-semibold text-slate-800">Filas detectadas:</span> {rawRows.length}</p>
              <p><span className="font-semibold text-slate-800">Columnas:</span> {headers.length}</p>
              <p><span className="font-semibold text-slate-800">Campos requeridos:</span> codigo_interno, nombre</p>
            </div>
          </div>
        </div>
      </div>

      <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
        <h3 className="text-lg font-bold text-slate-900">Mapeo de columnas</h3>
        <p className="mt-1 text-sm text-slate-500">
          Ajusta qué columna del archivo corresponde a cada campo de locales. Los campos no mapeados se omiten.
        </p>

        <div className="mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {IMPORT_FIELDS.map((field) => (
            <div key={field.key} className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
              <label className="mb-2 block text-sm font-medium text-slate-700">
                {field.label}
                {field.required && <span className="ml-1 text-red-500">*</span>}
              </label>
              <select
                value={mapping[field.key]}
                onChange={(e) => setMapping((prev) => ({ ...prev, [field.key]: e.target.value }))}
                className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-indigo-500"
              >
                <option value="">No importar</option>
                {headers.map((header) => (
                  <option key={header} value={header}>
                    {header}
                  </option>
                ))}
              </select>
            </div>
          ))}
        </div>

        {missingRequiredMappings.length > 0 && (
          <div className="mt-4 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700">
            Faltan columnas obligatorias por mapear: {missingRequiredMappings.join(', ')}.
          </div>
        )}
      </div>

      <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="flex items-center justify-between gap-4">
          <div>
            <h3 className="text-lg font-bold text-slate-900">Vista previa</h3>
            <p className="mt-1 text-sm text-slate-500">Se muestran las primeras filas para validar antes de importar.</p>
          </div>
          <button
            type="button"
            onClick={handleImport}
            disabled={isImporting || rawRows.length === 0 || missingRequiredMappings.length > 0}
            className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-5 py-2.5 text-sm font-bold text-white hover:bg-indigo-700 disabled:opacity-60"
          >
            <Upload size={16} />
            {isImporting ? 'Importando...' : 'Importar Locales'}
          </button>
        </div>

        {status.type !== 'idle' && (
          <div className={`mt-4 flex items-start gap-3 rounded-2xl px-4 py-3 text-sm ${
            status.type === 'success'
              ? 'border border-emerald-200 bg-emerald-50 text-emerald-700'
              : status.type === 'error'
                ? 'border border-red-200 bg-red-50 text-red-700'
                : 'border border-indigo-200 bg-indigo-50 text-indigo-700'
          }`}>
            {status.type === 'success' ? <CheckCircle2 size={18} /> : <AlertCircle size={18} />}
            <span>{status.message}</span>
          </div>
        )}

        <div className="mt-5 overflow-x-auto rounded-2xl border border-slate-200">
          <table className="w-full min-w-[900px] text-left text-sm">
            <thead className="bg-slate-50 text-xs font-bold uppercase tracking-wide text-slate-500">
              <tr>
                {IMPORT_FIELDS.map((field) => (
                  <th key={field.key} className="px-4 py-3">{field.label}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {previewRows.length === 0 ? (
                <tr>
                  <td colSpan={IMPORT_FIELDS.length} className="px-4 py-8 text-center text-slate-400">
                    {isParsing ? 'Analizando archivo...' : 'Cargue un archivo para ver la vista previa.'}
                  </td>
                </tr>
              ) : (
                previewRows.map((row, index) => (
                  <tr key={`preview-${index}`} className="bg-white">
                    {IMPORT_FIELDS.map((field) => (
                      <td key={field.key} className="px-4 py-3 text-slate-700">
                        {mapping[field.key] ? row[mapping[field.key]] || '—' : '—'}
                      </td>
                    ))}
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {importResult && (
          <div className="mt-5 rounded-2xl border border-slate-200 bg-slate-50 p-4">
            <h4 className="text-sm font-bold text-slate-800">Resultado de importación</h4>
            <div className="mt-3 grid gap-3 md:grid-cols-3">
              <div className="rounded-xl bg-white p-3 text-sm"><span className="font-semibold text-slate-800">Creados:</span> {importResult.created}</div>
              <div className="rounded-xl bg-white p-3 text-sm"><span className="font-semibold text-slate-800">Actualizados:</span> {importResult.updated}</div>
              <div className="rounded-xl bg-white p-3 text-sm"><span className="font-semibold text-slate-800">Con error:</span> {importResult.failed}</div>
            </div>

            {importResult.errors.length > 0 && (
              <div className="mt-4 rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700">
                <div className="mb-2 font-semibold">Errores detectados</div>
                <ul className="space-y-1">
                  {importResult.errors.slice(0, 10).map((error) => (
                    <li key={error}>• {error}</li>
                  ))}
                </ul>
                {importResult.errors.length > 10 && (
                  <p className="mt-2 text-xs text-red-600">Se muestran los primeros 10 errores.</p>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
