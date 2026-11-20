import React, { useEffect, useRef, useState } from 'react';
import { ApiService } from '../api';
import { SQLBackupAutomationPanel } from './SQLBackupAutomationPanel';

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
  const [mode, setMode] = useState<'period' | 'base' | 'differential'>('period');
  const [baseline, setBaseline] = useState<Awaited<ReturnType<typeof ApiService.getDatabaseBackupBaseline>>['baseline']>(null);
  const [hasBaseFile, setHasBaseFile] = useState(false);
  const [trafficRefresh, setTrafficRefresh] = useState(0);
  const selectionError = mode === 'period' ? dateError : mode === 'differential' && (!baseline || !hasBaseFile)
    ? 'Genera y conserva el ZIP completo base antes de descargar un diferencial.' : '';
  useEffect(() => {
    const controller = new AbortController();
    setCapabilities(null); setError(''); setBaseline(null); setMode('period'); setHasBaseFile(false); setBusy(false); setSuccess('');
    let timer: ReturnType<typeof setTimeout> | undefined;
    const load = async (attempt = 0) => {
      try {
        const result = await ApiService.getDatabaseBackupCapabilities(mallId, token, controller.signal);
        if (!controller.signal.aborted) setCapabilities(result);
        if (result.enabled && result.mall && result.differential) {
          const loaded = await ApiService.getDatabaseBackupBaseline(mallId, token, controller.signal);
          if (!controller.signal.aborted) setBaseline(loaded.baseline);
        }
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
    if (busy || selectionError) return;
    const controller = new AbortController();
    request.current = controller;
    setBusy(true); setError(''); setSuccess('');
    try {
      const blob = await ApiService.downloadDatabaseBackup(mallId, token, 'mall', controller.signal, start, end, mode, baseline?.id);
      if (controller.signal.aborted) return;
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url; link.download = `backup_mall_${mallId}_${mode}_${mode === 'period' ? `${start}_${end}` : new Date().toISOString().replaceAll(':', '-')}.zip`;
      document.body.appendChild(link); link.click(); link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      setSuccess('ZIP generado. Guarda el archivo en un lugar protegido; contiene datos sensibles.');
      if (mode === 'base') {
        setHasBaseFile(false);
        try {
          const loaded = await ApiService.getDatabaseBackupBaseline(mallId, token, controller.signal);
          if (!controller.signal.aborted) setBaseline(loaded.baseline);
        } catch {
          if (!controller.signal.aborted) setError('El ZIP se generó, pero no se pudo actualizar la referencia base. Recarga esta pantalla antes de generar diferenciales.');
        }
      }
    } catch (err) {
      if (!controller.signal.aborted) setError(err instanceof Error ? err.message : 'No se pudo descargar el backup.');
    } finally {
      if (!controller.signal.aborted) { setBusy(false); setTrafficRefresh(value => value + 1); onDownloaded(); }
    }
  };

  return <section aria-label="Backups SQL" className="space-y-4 rounded-2xl border border-slate-200 bg-white p-5">
    <h2 className="text-lg font-bold text-slate-800">Backup del Mall seleccionado</h2>
    {!capabilities && !error && <p role="status" className="text-sm">Verificando disponibilidad…</p>}
    {capabilities && !capabilities.enabled && <p className="text-sm text-amber-800">Backups SQL no habilitados. El administrador debe configurar la conexión de backups en el servidor.</p>}
    {capabilities && !capabilities.mall && <p className="text-sm text-slate-600">Se requiere un administrador asignado a este Mall.</p>}
    {capabilities?.mall && capabilities.weekly_quota && <SQLBackupAutomationPanel mallId={mallId} token={token} refresh={trafficRefresh} onBaseDownloaded={() => setRetry(value => value + 1)} />}
    {capabilities?.differential && <label className="block text-sm font-medium">Tipo de respaldo
      <select disabled={busy} value={mode} onChange={event => { setMode(event.target.value as typeof mode); setHasBaseFile(false); setSuccess(''); setError(''); }} className="mt-1 block rounded-lg border p-2">
        <option value="period">SQL por período</option>
        <option value="base">Completo para base diferencial</option>
        <option value="differential">Diferencial desde el completo base</option>
      </select>
    </label>}
    {mode === 'period' && <><fieldset disabled={busy} className="flex flex-wrap gap-3">
      <legend className="mb-2 text-sm font-medium">Período de ventas y cargas</legend>
      <label className="text-sm">Fecha inicial<input type="date" value={start} onChange={event => { setStart(event.target.value); setSuccess(''); }} className="mt-1 block rounded-lg border p-2" /></label>
      <label className="text-sm">Fecha final<input type="date" value={end} min={start || undefined} onChange={event => { setEnd(event.target.value); setSuccess(''); }} className="mt-1 block rounded-lg border p-2" /></label>
    </fieldset>
    <p className="text-xs text-slate-500">El período filtra ventas y logs de carga. Los locales, configuraciones y otros datos del Mall se incluyen completos.</p>
    </>}
    {mode === 'base' && <p className="text-sm text-amber-800">Incluye todo el historial del Mall, sin filtro de fechas. Guarda el ZIP: será necesario para recuperar cualquier diferencial. Una base nueva reemplaza la referencia anterior para futuras descargas.</p>}
    {mode !== 'period' && <p className="text-xs text-slate-500">No incluye usuarios Auth, archivos de Storage ni catálogos globales. La recuperación requiere un entorno compatible y esas dependencias.</p>}
    {mode === 'differential' && <div className="space-y-2 text-sm">
      <p>Incluye altas, modificaciones y eliminaciones desde el completo base, incluso registros con fechas antiguas. No requiere descargar los diferenciales anteriores.</p>
      {baseline ? <><p>Base generada el {new Date(baseline.created_at).toLocaleString('es-DO')} · referencia <code>{baseline.id}</code>.</p>
        <label className="flex items-start gap-2"><input type="checkbox" disabled={busy} checked={hasBaseFile} onChange={event => setHasBaseFile(event.target.checked)} />Conservo el ZIP completo correspondiente a esta referencia.</label></>
        : <p>No existe una base vigente. Primero descarga un completo para base diferencial.</p>}
      <p className="text-amber-800">Para recuperar: completo original + un diferencial, en un entorno de recuperación compatible. No se aplican diferenciales uno encima de otro.</p>
    </div>}
    {selectionError && <p role="alert" className="text-sm text-red-700">{selectionError}</p>}
    <div className="flex flex-wrap gap-3">
      {capabilities?.mall && <button type="button" disabled={busy || !capabilities.enabled || Boolean(selectionError)} onClick={() => void download()} className="rounded-xl border border-indigo-200 px-4 py-3 text-sm font-semibold text-indigo-700 disabled:opacity-50">Descargar {mode === 'differential' ? 'diferencial' : mode === 'base' ? 'completo base' : 'backup'} de {mallName}</button>}
    </div>
    {busy && <p role="status" className="text-sm">Generando backup… Puede tardar varios minutos. Mantén esta pantalla abierta.</p>}
    {success && <p role="status" className="text-sm text-emerald-700">{success}</p>}
    {error && <p role="alert" className="text-sm text-red-700">{error} {!capabilities && <button type="button" onClick={() => setRetry(value => value + 1)} className="underline">Reintentar</button>}</p>}
  </section>;
};
