import React, { useEffect, useRef, useState } from 'react';
import { ApiService, SQLBackupScheduleState } from '../api';

const gb = (bytes: number) => (bytes / 1_000_000_000).toLocaleString('es-DO', { maximumFractionDigits: 2 });
type Traffic = Awaited<ReturnType<typeof ApiService.getSQLBackupTraffic>>;

export const SQLBackupAutomationPanel: React.FC<{ mallId: string; token: string; refresh: number; onBaseDownloaded: () => void }> = ({ mallId, token, refresh, onBaseDownloaded }) => {
  const [traffic, setTraffic] = useState<Traffic | null>(null);
  const [state, setState] = useState<SQLBackupScheduleState | null>(null);
  const [config, setConfig] = useState({ enabled: false, run_hour: 2 });
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [reload, setReload] = useState(0);
  const active = useRef<AbortController | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    setTraffic(null); setState(null); setError(''); setBusy(false);
    void (async () => {
      try {
        const result = await ApiService.getSQLBackupTraffic(mallId, token, controller.signal);
        if (controller.signal.aborted) return;
        setTraffic(result);
        if (result.configured) {
          const loaded = await ApiService.getSQLBackupSchedule(mallId, token, controller.signal);
          if (!controller.signal.aborted) {
            setState(loaded);
            setConfig({ enabled: loaded.schedule?.enabled ?? false, run_hour: loaded.schedule?.run_hour ?? 2 });
          }
        }
      } catch (err) {
        if (!controller.signal.aborted) setError(err instanceof Error ? err.message : 'No se pudo consultar la programación SQL.');
      }
    })();
    return () => { controller.abort(); active.current?.abort(); };
  }, [mallId, token, refresh, reload]);

  const save = async (event: React.FormEvent) => {
    event.preventDefault();
    if (busy) return;
    const controller = new AbortController(); active.current = controller;
    setBusy(true); setError(''); setMessage('');
    try {
      const loaded = await ApiService.saveSQLBackupSchedule(mallId, token, config, controller.signal);
      if (!controller.signal.aborted) { setState(loaded); setMessage('Programación SQL guardada.'); }
    } catch (err) {
      if (!controller.signal.aborted) setError(err instanceof Error ? err.message : 'No se pudo guardar.');
    } finally { if (!controller.signal.aborted) setBusy(false); }
  };

  const download = async (artifact: SQLBackupScheduleState['artifacts'][number]) => {
    if (busy) return;
    const controller = new AbortController(); active.current = controller;
    setBusy(true); setError(''); setMessage('');
    try {
      const blob = await ApiService.downloadSQLBackupArtifact(mallId, token, artifact.id, controller.signal);
      if (controller.signal.aborted) return;
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url; link.download = `backup_${artifact.mode}_${mallId}_${artifact.scheduled_day}.zip`;
      document.body.appendChild(link); link.click(); link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      setMessage('Descarga iniciada. Conserva el completo que corresponde al diferencial.');
      if (artifact.mode === 'base') onBaseDownloaded();
    } catch (err) {
      if (!controller.signal.aborted) setError(err instanceof Error ? err.message : 'No se pudo descargar.');
    } finally {
      if (!controller.signal.aborted) { setBusy(false); setReload(value => value + 1); }
    }
  };

  if (traffic && !traffic.configured) return null;
  const quota = traffic?.quota;
  const blocked = !quota?.enabled || (quota?.remaining_bytes ?? 0) < 1;
  return <div className="space-y-3 rounded-xl border border-indigo-200 bg-indigo-50 p-4">
    <h3 className="font-semibold text-slate-900">Backups SQL gratuitos y automáticos</h3>
    {quota && <>
      <p className="text-sm">Cuota compartida entre Ágora y Santiago Center: <strong>{gb(quota.remaining_bytes)} de {gb(quota.weekly_bytes)} GB disponibles esta semana</strong>. Máximo {gb(quota.max_file_bytes)} GB por archivo.</p>
      <p className="text-xs text-slate-600">Se contabilizan el SQL generado y los ZIP transferidos, incluidos intentos fallidos. Las descargas adicionales también consumen cuota. Reinicio: {new Date(quota.resets_at).toLocaleString('es-DO')}. Servicio sin costo ni cargos por excedente.</p>
      {blocked && <p role="alert" className="text-sm text-amber-900">Generación y descargas bloqueadas hasta que haya cuota disponible.</p>}
    </>}
    {state && <form onSubmit={save} className="space-y-3">
      <fieldset disabled={busy} className="flex flex-wrap items-center gap-4">
        <legend className="sr-only">Programación diaria por Mall</legend>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={config.enabled} onChange={e => setConfig(value => ({ ...value, enabled: e.target.checked }))} />Generación automática diaria</label>
        <label className="text-sm">Hora (Santo Domingo)<select value={config.run_hour} onChange={e => setConfig(value => ({ ...value, run_hour: Number(e.target.value) }))} className="ml-2 rounded border p-2">
          {Array.from({ length: 24 }, (_, hour) => <option key={hour} value={hour}>{String(hour).padStart(2, '0')}:00</option>)}
        </select></label>
        <button type="submit" className="rounded border border-indigo-300 bg-white px-3 py-2 text-sm">Guardar programación</button>
      </fieldset>
      <p className="text-xs text-slate-600">Se crea un completo inicial y se renueva mensualmente; los diferenciales se generan cada día. Se conservan siete días de diferenciales y su completo necesario. Cada recuperación utiliza el completo original y un diferencial.</p>
      {!state.automation_enabled && <p className="text-sm text-amber-900">El administrador todavía debe habilitar el programador en el servidor.</p>}
      {state.schedule?.next_run_at && <p className="text-xs">Próxima ejecución: {new Date(state.schedule.next_run_at).toLocaleString('es-DO')}.</p>}
      {state.schedule?.last_error && <p className="text-sm text-amber-900">La última ejecución quedó pendiente. {state.schedule.last_error === 'quota_weekly_bytes' ? 'Se agotó la cuota semanal.' : 'Revisa la cuota y el estado del servicio.'}</p>}
    </form>}
    {state && state.artifacts.length > 0 && <div className="overflow-x-auto"><table className="w-full text-left text-xs">
      <thead><tr><th className="p-2">Respaldo</th><th className="p-2">Base de referencia</th><th className="p-2">Tamaño</th><th className="p-2">Estado</th><th className="p-2">Descarga</th></tr></thead>
      <tbody>{state.artifacts.map(file => <tr key={file.id} className="border-t border-indigo-100">
        <td className="p-2">{file.mode === 'base' ? 'Completo' : 'Diferencial'} · {file.scheduled_day}</td><td className="p-2"><code>{file.base_id ?? 'Pendiente'}</code></td>
        <td className="p-2">{gb(file.bytes)} GB</td><td className="p-2">{({ completed: 'Disponible', pending: 'Generando', failed: 'Fallido' } as Record<string, string>)[file.status] ?? file.status}</td>
        <td className="p-2"><button type="button" disabled={busy || blocked || file.status !== 'completed'} onClick={() => void download(file)} className="underline disabled:opacity-40">Descargar ZIP</button></td>
      </tr>)}</tbody>
    </table></div>}
    {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
    {message && <p role="status" className="text-sm text-emerald-800">{message}</p>}
    <button type="button" disabled={busy} onClick={() => setReload(value => value + 1)} className="text-xs underline">Actualizar cuota y archivos</button>
  </div>;
};
