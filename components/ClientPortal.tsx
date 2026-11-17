import React, { useEffect, useRef, useState } from 'react';
import { portalRequest } from '../api';
import { useAuth } from '../context/AuthProvider';
import { UploadCloud, LogOut, CheckCircle2 } from 'lucide-react';

export interface PortalLocal { id: string; nombre: string; codigo_interno: string; mall_id: string }
type Mapping = Record<string, string>;
type Options = { date_format: string; decimal_separator: string };
type RowError = { linea: number; error: string };
interface Analysis {
  headers: string[]; sample: Record<string, unknown>[]; row_count: number; format: string;
  tables: { index: number; rows: number; columns: number }[];
  suggested_mapping: Record<string, { csv_header: string; is_confident: boolean }>;
  saved: { mapping: Mapping; options: Options } | null;
}
interface UploadResult { id?: string; filename?: string; status: string; records_processed: number; errors: RowError[]; created_at?: string }
const FIELDS = [
  ['factura_numero', 'Número de factura', true], ['fecha_venta', 'Fecha de venta', true],
  ['total_bruto', 'Total bruto', true], ['total_impuestos', 'Impuestos', true],
  ['total_neto', 'Total neto', true], ['hora', 'Hora', false],
] as const;
const DEFAULT_OPTIONS = { date_format: 'auto', decimal_separator: '.' };
const control = 'w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-slate-800 disabled:opacity-60';
const STATUS: Record<string, string> = { processing: 'En proceso; consulta el historial', success: 'Importado', partial: 'Importación parcial', error: 'Error', invalid: 'Requiere correcciones' };

export function ClientPortal() {
  const { session, signOut } = useAuth();
  const token = session.access_token;
  const [selectedLocal, setSelectedLocal] = useState<PortalLocal | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [tableIndex, setTableIndex] = useState(0);
  const [hasHeader, setHasHeader] = useState(true);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [mapping, setMapping] = useState<Mapping>({});
  const [options, setOptions] = useState<Options>(DEFAULT_OPTIONS);
  const [history, setHistory] = useState<UploadResult[]>([]);
  const [errors, setErrors] = useState<RowError[]>([]);
  const [valid, setValid] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [failure, setFailure] = useState('');
  const requestId = useRef<string | null>(null);
  const localId = selectedLocal?.id || '';

  useEffect(() => {
    let ignore = false;
    portalRequest<PortalLocal>('/portal/local', token).then(data => {
      if (!ignore) { setSelectedLocal(data); }
    }).catch(error => { if (!ignore) setFailure(error.message); });
    return () => { ignore = true; };
  }, [token]);

  useEffect(() => {
    let ignore = false;
    setHistory([]);
    if (localId) portalRequest<UploadResult[]>('/portal/history', token)
      .then(data => { if (!ignore) setHistory(data); })
      .catch(error => { if (!ignore) setFailure(error.message); });
    return () => { ignore = true; };
  }, [localId, token]);

  function invalidate() {
    setValid(false); setErrors([]); setMessage(''); setFailure(''); requestId.current = null;
  }
  function resetAnalysis() { invalidate(); setAnalysis(null); setMapping({}); }
  function chooseFile(next: File | null) {
    resetAnalysis(); setTableIndex(0); setFile(null);
    if (!next) return;
    if (next.size > 10 * 1024 * 1024 || !/\.(csv|txt|json|html|htm)$/i.test(next.name)) {
      setFailure('Usa un archivo CSV, TXT, JSON o HTML de hasta 10 MB.'); return;
    }
    setFile(next);
  }
  function body() {
    const form = new FormData();
    form.append('file', file!);
    form.append('table_index', String(tableIndex)); form.append('has_header', String(hasHeader));
    form.append('mapping', JSON.stringify(mapping)); form.append('options', JSON.stringify(options));
    return form;
  }
  async function refreshHistory() {
    setHistory(await portalRequest<UploadResult[]>('/portal/history', token));
  }
  async function run(action: 'analyze' | 'validate' | 'import') {
    if (!file || !localId || busy) return;
    setBusy(true); setFailure(''); setMessage('');
    try {
      const form = body();
      if (action === 'analyze') {
        setValid(false); setAnalysis(null); setErrors([]);
        const result = await portalRequest<Analysis>('/portal/analyze', token, { method: 'POST', body: form });
        setAnalysis(result);
        const suggested: Mapping = {};
        FIELDS.forEach(([key]) => {
          const match = result.suggested_mapping[key === 'hora' ? 'hora_transaccion' : key];
          if (result.headers.includes(key)) suggested[key] = key;
          else if (match?.is_confident) suggested[key] = match.csv_header;
        });
        setMapping(result.saved?.mapping || suggested);
        setOptions(result.saved?.options || DEFAULT_OPTIONS);
        setMessage(result.saved ? 'Mapeo guardado recuperado. Revisa y valida antes de importar.' : 'Revisa las columnas sugeridas y completa el mapeo.');
      } else if (action === 'validate') {
        setValid(false);
        const result = await portalRequest<{ valid: boolean; records: number; error_count: number; errors: RowError[] }>('/portal/validate', token, { method: 'POST', body: form });
        setValid(result.valid); setErrors(result.errors);
        setMessage(result.valid ? `${result.records} ${result.records === 1 ? 'fila validada' : 'filas validadas'}. Puedes confirmar la importación.` : `${result.error_count} errores. Corrige el archivo o el mapeo y vuelve a validar.`);
      } else {
        if (!valid) return;
        requestId.current ||= crypto.randomUUID();
        form.append('request_id', requestId.current);
        const result = await portalRequest<UploadResult>('/portal/import', token, { method: 'POST', body: form });
        setErrors(result.errors || []); setValid(false);
        setMessage(`${STATUS[result.status] || result.status}. ${result.records_processed} ${result.records_processed === 1 ? 'registro procesado' : 'registros procesados'}.`);
        await refreshHistory();
      }
    } catch (error) {
      setFailure(error instanceof Error ? error.message : 'No se pudo completar la operación.');
      // Preserve request_id after uncertain delivery so retry cannot process twice.
    } finally { setBusy(false); }
  }

  return <div className="min-h-screen bg-slate-50 text-slate-800">
    <header className="border-b bg-white px-4 py-5 sm:px-8"><div className="mx-auto flex max-w-5xl items-center justify-between gap-4">
      <div className="flex items-center gap-3"><img src="/msmall-icon-192.png" alt="MSMALL" className="h-11 w-11 rounded-xl" /><div><h1 className="text-xl font-bold">Portal de clientes</h1><p className="text-sm text-slate-500">Carga de ventas · MSMALL</p></div></div>
      <button onClick={signOut} className="flex items-center gap-2 text-sm"><LogOut size={18} />Salir</button>
    </div></header>
    <main className="mx-auto max-w-5xl space-y-6 p-4 sm:p-8">
      <p className="break-all text-sm text-slate-500">{session.user.email}</p>
      {failure && <p role="alert" className="rounded-xl border border-red-200 bg-red-50 p-4 text-red-800">{failure}</p>}
      {!selectedLocal && !failure && <p role="status" className="rounded-xl bg-white p-6">Consultando el local vinculado a tu cuenta…</p>}
      {selectedLocal && <>
        <section className="space-y-5 rounded-2xl border bg-white p-5 sm:p-6">
          <h2 className="text-lg font-bold">1. Carga tu archivo de ventas</h2>
          <div className="rounded-xl bg-slate-50 p-4"><p className="text-xs font-semibold uppercase text-slate-500">Local vinculado a tu cuenta</p><p className="mt-1 font-semibold">{selectedLocal.nombre} · {selectedLocal.codigo_interno}</p></div>
          <p className="text-sm text-slate-500">El archivo debe contener únicamente ventas de tu local.</p>
          <div className="rounded-xl border-2 border-dashed border-indigo-200 bg-indigo-50 p-7 text-center" onDragOver={e => e.preventDefault()} onDrop={e => { e.preventDefault(); if (!busy) chooseFile(e.dataTransfer.files[0] || null); }}>
            <UploadCloud className="mx-auto mb-3 text-indigo-600" size={32} />
            <label htmlFor="portal-file" className="block font-medium">{file?.name || 'Arrastra un archivo o selecciónalo'}</label>
            <input id="portal-file" type="file" accept=".csv,.txt,.json,.html,.htm" disabled={busy} onChange={e => chooseFile(e.target.files?.[0] || null)} className="mt-3 max-w-full text-sm" />
            <p className="mt-3 text-xs text-slate-500">CSV, TXT, JSON o tablas HTML · Máximo 10 MB y 50,000 filas</p>
          </div>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={hasHeader} disabled={busy} onChange={e => { resetAnalysis(); setHasHeader(e.target.checked); }} />La primera fila contiene encabezados (CSV / HTML)</label>
          {!!analysis?.tables.length && <label className="block text-sm">Tabla HTML<select className={`${control} mt-2`} disabled={busy} value={tableIndex} onChange={e => { invalidate(); setAnalysis(null); setTableIndex(Number(e.target.value)); }}>
            {analysis.tables.map(table => <option key={table.index} value={table.index}>Tabla {table.index + 1} · {table.rows} filas · {table.columns} columnas</option>)}
          </select></label>}
          <button disabled={!file || !localId || busy} onClick={() => run('analyze')} className="rounded-lg bg-indigo-600 px-5 py-2.5 font-semibold text-white disabled:opacity-50">{busy ? 'Procesando…' : 'Analizar archivo'}</button>
        </section>
        {analysis && <section className="space-y-5 rounded-2xl border bg-white p-5 sm:p-6">
          <h2 className="text-lg font-bold">2. Revisa el mapeo</h2><p className="text-sm text-slate-500">{analysis.format} · {analysis.row_count} filas. Los campos con * son obligatorios.</p>
          <div className="grid gap-4 sm:grid-cols-2">{FIELDS.map(([key, label, required]) => <label key={key} className="block text-sm font-medium">{label}{required ? ' *' : ''}
            <select className={`${control} mt-2`} disabled={busy} value={mapping[key] || ''} onChange={e => { invalidate(); setMapping({ ...mapping, [key]: e.target.value }); }}>
              <option value="">{required ? 'Selecciona una columna' : 'Sin asignar'}</option>{analysis.headers.map(header => <option key={header} value={header}>{header}</option>)}
            </select><span className="mt-1 block truncate text-xs text-slate-500">Ejemplo: {String(analysis.sample[0]?.[mapping[key]] ?? '—')}</span>
          </label>)}</div>
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="text-sm">Formato de fecha<select className={`${control} mt-2`} disabled={busy} value={options.date_format} onChange={e => { invalidate(); setOptions({ ...options, date_format: e.target.value }); }}>
              <option value="auto">Detectar automáticamente</option><option value="dd/mm/yyyy">DD/MM/AAAA</option><option value="mm/dd/yyyy">MM/DD/AAAA</option><option value="yyyy-mm-dd">AAAA-MM-DD</option>
            </select></label>
            <label className="text-sm">Separador decimal<select className={`${control} mt-2`} disabled={busy} value={options.decimal_separator} onChange={e => { invalidate(); setOptions({ ...options, decimal_separator: e.target.value }); }}><option value=".">Punto (1,234.56)</option><option value=",">Coma (1.234,56)</option></select></label>
          </div>
          <div className="overflow-x-auto"><table className="w-full text-left text-xs"><caption className="mb-2 text-left text-sm font-medium">Vista previa del archivo (primeras 5 filas)</caption><thead><tr>{analysis.headers.map(h => <th key={h} className="whitespace-nowrap border-b p-2">{h}</th>)}</tr></thead><tbody>{analysis.sample.map((row, i) => <tr key={i}>{analysis.headers.map(h => <td key={h} className="max-w-60 truncate border-b p-2">{String(row[h] ?? '')}</td>)}</tr>)}</tbody></table></div>
          <button disabled={busy} onClick={() => run('validate')} className="rounded-lg border border-indigo-600 px-5 py-2.5 font-semibold text-indigo-700 disabled:opacity-50">Validar todas las filas</button>
        </section>}
        {message && <p role="status" className="flex items-start gap-2 rounded-xl bg-indigo-50 p-4 text-indigo-900"><CheckCircle2 size={20} className="shrink-0" />{message}</p>}
        {!!errors.length && <div role="alert" className="max-h-64 overflow-auto rounded-xl border border-red-200 bg-red-50 p-4"><p className="mb-2 font-semibold">Errores (hasta 100)</p><ul className="space-y-1 text-sm">{errors.map((error, i) => <li key={i}>Fila {error.linea}: {error.error}</li>)}</ul></div>}
        {valid && <section className="rounded-2xl border border-indigo-200 bg-white p-6"><h2 className="mb-3 text-lg font-bold">3. Confirma la importación</h2><p className="mb-4 text-sm">Destino: {selectedLocal?.nombre}. Las facturas existentes se actualizarán según las reglas actuales de ingesta. El mapeo se guardará si la carga termina sin errores.</p><button disabled={busy} onClick={() => run('import')} className="rounded-lg bg-indigo-600 px-5 py-3 font-semibold text-white disabled:opacity-50">Importar ventas</button></section>}
        <section className="rounded-2xl border bg-white p-5 sm:p-6"><div className="mb-4 flex items-center justify-between gap-4"><h2 className="text-lg font-bold">Historial de tus cargas</h2><button disabled={busy} onClick={() => refreshHistory().catch(e => setFailure(e.message))} className="text-sm font-medium text-indigo-700">Actualizar</button></div>
          {!history.length ? <p className="text-sm text-slate-500">Todavía no has enviado archivos para este local.</p> : <div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead><tr>{['Archivo', 'Fecha', 'Estado', 'Registros'].map(h => <th key={h} className="border-b p-2">{h}</th>)}</tr></thead><tbody>{history.map(row => <tr key={row.id}><td className="max-w-56 break-words border-b p-2">{row.filename}</td><td className="border-b p-2">{row.created_at ? new Date(row.created_at).toLocaleString() : '—'}</td><td className="border-b p-2">{STATUS[row.status]}{!!row.errors?.length && <details><summary className="cursor-pointer text-red-700">Ver errores</summary><ul>{row.errors.map((e, i) => <li key={i}>Fila {e.linea}: {e.error}</li>)}</ul></details>}</td><td className="border-b p-2">{row.records_processed}</td></tr>)}</tbody></table></div>}
        </section>
      </>}
    </main>
  </div>;
}
