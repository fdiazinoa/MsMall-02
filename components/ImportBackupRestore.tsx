import React, { useEffect, useRef, useState } from 'react';
import { ApiService } from '../api';
import { useAuth } from '../context/AuthProvider';

type Result = Awaited<ReturnType<typeof ApiService.restoreImportBackup>>;
const KINDS = [['locales', 'Locales'], ['importadores', 'Importadores API / locales'], ['ftp', 'FTP / SFTP'], ['webservice', 'Webservice'], ['ventas', 'Ventas']];

export const ImportBackupRestore: React.FC<{ mallId: string; token: string }> = ({ mallId, token }) => {
  const { isAdmin } = useAuth();
  const [kind, setKind] = useState('locales');
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const request = useRef<AbortController | null>(null);
  useEffect(() => () => { request.current?.abort(); }, []);
  if (!isAdmin) return null;

  const run = async (apply: boolean) => {
    if (!file || busy) return;
    const controller = new AbortController();
    request.current = controller;
    setBusy(true); setError('');
    try {
      const next = await ApiService.restoreImportBackup(mallId, token, kind, file, apply, controller.signal);
      if (!controller.signal.aborted) setResult(next);
    } catch (err) {
      if (!controller.signal.aborted) {
        setResult(null);
        setError(err instanceof Error ? err.message : 'No se pudo leer el CSV.');
      }
    } finally {
      if (!controller.signal.aborted) setBusy(false);
    }
  };

  return <section aria-label="Restaurar desde CSV" className="space-y-4 rounded-2xl border border-slate-200 bg-white p-5">
    <h2 className="text-lg font-bold text-slate-800">Restaurar desde CSV</h2>
    <p className="text-sm text-slate-600">Restaura primero locales, después importadores y finalmente ventas. Solo se aceptan los CSV descargados por este sistema para el Mall activo. Los registros existentes se omiten y no se sobrescriben.</p>
    <p className="text-sm text-amber-800">Los backups no incluyen credenciales. Los importadores se recuperan en modo MANUAL y los receptores ERP deshabilitados; revisa la configuración y completa las credenciales antes de activarlos. Máximo 5 MB y 2,000 filas por archivo.</p>
    <fieldset disabled={busy} className="flex flex-wrap items-end gap-3">
      <legend className="sr-only">Archivo de restauración</legend>
      <label className="text-sm font-medium">Tipo de backup
        <select value={kind} onChange={e => { setKind(e.target.value); setResult(null); setError(''); }} className="mt-1 block rounded-lg border p-2">
          {KINDS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>
      </label>
      <label className="text-sm font-medium">Archivo CSV
        <input type="file" accept=".csv,text/csv" className="mt-1 block text-sm" onChange={e => {
          const next = e.target.files?.[0] || null;
          setResult(null); setError('');
          if (next && next.size > 5 * 1024 * 1024) { setFile(null); setError('El archivo supera 5 MB.'); }
          else setFile(next);
        }} />
      </label>
      <button type="button" disabled={!file} onClick={() => void run(false)} className="rounded-lg border border-indigo-200 px-4 py-2 text-sm font-semibold text-indigo-700 disabled:opacity-50">Validar y previsualizar</button>
    </fieldset>
    {busy && <p role="status" className="text-sm">Revisando registros… Esto puede tardar varios minutos. Mantén esta sección abierta.</p>}
    {error && <p role="alert" className="text-sm text-red-700">{error} Si se interrumpió una restauración, vuelve a validar: los registros guardados se omitirán.</p>}
    {result && <div className="space-y-3 text-sm">
      <p role="status">Filas: {result.total} · Por restaurar: {result.applied ? Math.max(0, result.total - result.restaurados - result.omitidos - result.errores.length) : result.pendientes} · Omitidas: {result.omitidos} · Restauradas: {result.restaurados} · Errores: {result.errores.length}</p>
      {result.errores.length > 0 && <div role="alert"><p>{result.applied ? 'Algunos registros no se guardaron. Vuelve a validar para reintentar solo los pendientes.' : 'Corrige los errores antes de volver a validar. No se guardó ninguna fila.'}</p><ul className="mt-2 max-h-48 overflow-auto text-red-700">{result.errores.map(item => <li key={item.line}>Fila {item.line}: {item.error}</li>)}</ul></div>}
      <details><summary className="cursor-pointer">Vista previa (primeras 20 filas)</summary>
        <ul className="mt-2 max-h-48 overflow-auto">{result.preview.map(item => <li key={item.line}>Fila {item.line}: {item.label || item.id || 'configuración'} — {item.status}</li>)}</ul>
      </details>
      {!result.applied && result.errores.length === 0 && result.pendientes > 0 && <button type="button" disabled={busy} onClick={() => void run(true)} className="rounded-lg bg-indigo-600 px-4 py-2 font-semibold text-white disabled:opacity-50">Confirmar restauración de {result.pendientes} registros</button>}
      {result.applied && <p>Restauración finalizada. Vuelve a validar el archivo para comprobar si quedan registros pendientes.</p>}
    </div>}
  </section>;
};
