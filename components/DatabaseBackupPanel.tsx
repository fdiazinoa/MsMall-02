import React, { useEffect, useRef, useState } from 'react';
import { ApiService } from '../api';

const localDate = (date: Date) => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
type Capabilities = Awaited<ReturnType<typeof ApiService.getDatabaseBackupCapabilities>>;
export const DatabaseBackupPanel: React.FC<{ mallId: string; mallName: string; token: string; onDownloaded: () => void }> = ({ mallId, mallName, token, onDownloaded }) => {
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [success, setSuccess] = useState('');
  const [retry, setRetry] = useState(0);
  const [start, setStart] = useState(() => localDate(new Date(new Date().getFullYear(), new Date().getMonth(), 1)));
  const [end, setEnd] = useState(() => localDate(new Date()));
  const dateError = !start || !end ? 'Indica ambas fechas.' : end < start ? 'La fecha final debe ser igual o posterior a la inicial.' : '';
  const request = useRef<AbortController | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    setCapabilities(null); setError('');
    let timer: ReturnType<typeof setTimeout> | undefined;
    const load = async (attempt = 0) => {
      try {
        const result = await ApiService.getDatabaseBackupCapabilities(mallId, token, controller.signal);
        if (!controller.signal.aborted) setCapabilities(result);
      } catch (err) {
        if (controller.signal.aborted) return;
        // Frontend and backend deployments may become available at different times.
        const status = (err as { status?: number })?.status;
        if (status === 404 && attempt < 3) {
          timer = setTimeout(() => void load(attempt + 1), 1000 * 2 ** attempt);
          return;
        }
        setError(status === 404
          ? 'El servicio de backups SQL todavía no está disponible. Reintenta cuando termine la actualización del servidor.'
          : err instanceof Error ? err.message : 'No se pudo verificar la disponibilidad.');
      }
    };
    void load();
    return () => { controller.abort(); clearTimeout(timer); request.current?.abort(); };
  }, [mallId, token, retry]);

  const download = async () => {
    if (busy || dateError) return;
    const controller = new AbortController();
    request.current = controller;
    setBusy(true); setError(''); setSuccess('');
    try {
      const blob = await ApiService.downloadDatabaseBackup(mallId, token, 'mall', controller.signal, start, end);
      if (controller.signal.aborted) return;
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url; link.download = `backup_mall_${mallId}_${start}_${end}.zip`;
      document.body.appendChild(link); link.click(); link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      setSuccess('ZIP generado. Guarda el archivo en un lugar protegido; contiene datos sensibles.');
    } catch (err) {
      if (!controller.signal.aborted) setError(err instanceof Error ? err.message : 'No se pudo descargar el backup.');
    } finally {
      if (!controller.signal.aborted) { setBusy(false); onDownloaded(); }
    }
  };

  return <section aria-label="Backups SQL" className="space-y-4 rounded-2xl border border-slate-200 bg-white p-5">
    <h2 className="text-lg font-bold text-slate-800">Backup del Mall seleccionado</h2>
    {!capabilities && !error && <p role="status" className="text-sm">Verificando disponibilidad…</p>}
    {capabilities && !capabilities.enabled && <p className="text-sm text-amber-800">Backups SQL no habilitados. El administrador debe configurar la conexión de backups en el servidor.</p>}
    {capabilities && !capabilities.mall && <p className="text-sm text-slate-600">Se requiere un administrador asignado a este Mall.</p>}
    <fieldset disabled={busy} className="flex flex-wrap gap-3">
      <legend className="mb-2 text-sm font-medium">Período de ventas y cargas</legend>
      <label className="text-sm">Fecha inicial<input type="date" value={start} onChange={event => { setStart(event.target.value); setSuccess(''); }} className="mt-1 block rounded-lg border p-2" /></label>
      <label className="text-sm">Fecha final<input type="date" value={end} min={start || undefined} onChange={event => { setEnd(event.target.value); setSuccess(''); }} className="mt-1 block rounded-lg border p-2" /></label>
    </fieldset>
    <p className="text-xs text-slate-500">El período filtra ventas y logs de carga. Los locales, configuraciones y otros datos del Mall se incluyen completos.</p>
    {dateError && <p role="alert" className="text-sm text-red-700">{dateError}</p>}
    <div className="flex flex-wrap gap-3">
      {capabilities?.mall && <button type="button" disabled={busy || !capabilities.enabled || Boolean(dateError)} onClick={() => void download()} className="rounded-xl border border-indigo-200 px-4 py-3 text-sm font-semibold text-indigo-700 disabled:opacity-50">Descargar backup de {mallName}</button>}
    </div>
    {busy && <p role="status" className="text-sm">Generando backup… Puede tardar varios minutos. Mantén esta pantalla abierta.</p>}
    {success && <p role="status" className="text-sm text-emerald-700">{success}</p>}
    {error && <p role="alert" className="text-sm text-red-700">{error} {!capabilities && <button type="button" onClick={() => setRetry(value => value + 1)} className="underline">Reintentar</button>}</p>}
  </section>;
};
