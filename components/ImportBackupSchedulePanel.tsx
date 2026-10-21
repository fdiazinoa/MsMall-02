import React, { useCallback, useEffect, useRef, useState } from 'react';
import { ApiService, ImportBackupScheduleConfig, ImportBackupScheduleState, ImportBackupStore } from '../api';
import { useAuth } from '../context/AuthProvider';

const initial: ImportBackupScheduleConfig = { frequency: 'weekly', run_hour: 2, folder: 'importaciones', local_ids: null, retention_days: 30, enabled: false };
const statuses: Record<string, string> = { pending: 'Generando', completed: 'Disponible', failed: 'Falló', expired: 'Vencido' };
const errors: Record<string, string> = {
  permissions_revoked: 'El propietario ya no tiene los permisos necesarios.',
  schedule_or_permissions_changed: 'La programación o sus permisos cambiaron durante la ejecución.',
  worker_interrupted: 'La ejecución se interrumpió.', generation_failed: 'No se pudo generar o guardar el CSV completo.'
};

export const ImportBackupSchedulePanel: React.FC<{
  mallId: string; token: string; stores: ImportBackupStore[]; onDownloaded: () => void;
}> = ({ mallId, token, stores, onDownloaded }) => {
  const { canAccess } = useAuth();
  const [state, setState] = useState<ImportBackupScheduleState | null>(null);
  const [draft, setDraft] = useState<ImportBackupScheduleConfig>(initial);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const request = useRef<AbortController | null>(null);
  const canSave = canAccess('backup_schedules', state?.schedule ? 'update' : 'create');
  const accept = useCallback((result: ImportBackupScheduleState) => {
    setState(result);
    setDraft(result.schedule ? { frequency: result.schedule.frequency, run_hour: result.schedule.run_hour,
      folder: result.schedule.folder, local_ids: result.schedule.local_ids, retention_days: result.schedule.retention_days, enabled: result.schedule.enabled } : initial);
  }, []);
  const refresh = useCallback(() => {
    request.current?.abort();
    const controller = new AbortController(); request.current = controller;
    setError(null);
    ApiService.getImportBackupSchedule(mallId, token, controller.signal).then(result => {
      if (!controller.signal.aborted) accept(result);
    }).catch(cause => { if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : 'No se pudo consultar la programación.'); });
  }, [mallId, token, accept]);
  useEffect(() => { refresh(); return () => request.current?.abort(); }, [refresh]);

  const mutate = async (action: 'save' | 'delete') => {
    if (busy) return;
    request.current?.abort();
    const controller = new AbortController(); request.current = controller;
    setBusy(true); setError(null); setNotice(null);
    try {
      const result = action === 'save' ? await ApiService.saveImportBackupSchedule(mallId, token, draft, controller.signal)
        : await ApiService.deleteImportBackupSchedule(mallId, token, controller.signal);
      if (!controller.signal.aborted) { accept(result); setNotice(action === 'save' ? 'Programación guardada.' : 'Programación eliminada. Los archivos existentes conservan su fecha de vencimiento.'); }
    } catch (cause) { if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : 'No se pudo guardar.'); }
    finally { if (!controller.signal.aborted) setBusy(false); }
  };
  const download = async (id: string, filename: string) => {
    if (busy) return;
    request.current?.abort();
    const controller = new AbortController(); request.current = controller;
    setBusy(true); setError(null);
    try {
      const result = await ApiService.downloadStoredImportBackup(mallId, token, id, controller.signal);
      if (controller.signal.aborted) return;
      const url = URL.createObjectURL(result.blob); const anchor = document.createElement('a');
      anchor.href = url; anchor.download = filename; document.body.appendChild(anchor); anchor.click(); anchor.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      setNotice(`Archivo descargado: ${filename}.`);
    } catch (cause) { if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : 'No se pudo descargar.'); }
    finally { if (!controller.signal.aborted) { setBusy(false); onDownloaded(); } }
  };
  const date = (value: string) => new Date(value).toLocaleString('es-DO', { timeZone: 'America/Santo_Domingo' });
  return <section aria-label="Backups automáticos" className="space-y-4 rounded-2xl border border-slate-200 bg-white p-5">
    <div className="flex flex-wrap justify-between gap-3"><h2 className="text-lg font-bold text-slate-800">Backups automáticos</h2>
      <button type="button" disabled={busy} onClick={() => { refresh(); onDownloaded(); }} className="text-sm font-medium text-indigo-600">Actualizar historial</button></div>
    <p className="text-sm text-slate-600">Guarda CSV en almacenamiento privado y descárgalos aquí. La generación y cada descarga consumen la cuota disponible.</p>
    {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
    {notice && <p role="status" className="text-sm text-emerald-700">{notice}</p>}
    {!state && !error && <p role="status">Consultando programación…</p>}
    {state && <>
      {!state.automation_enabled && <p className="rounded-lg bg-amber-50 p-3 text-sm text-amber-800">La ejecución automática está pendiente de activación. Puedes guardar la configuración; no se ejecutará hasta que el servicio esté habilitado.</p>}
      <form onSubmit={event => { event.preventDefault(); void mutate('save'); }} className="space-y-4">
        <fieldset disabled={busy || !canSave} className="grid gap-4 sm:grid-cols-2">
          <legend className="sr-only">Programación de backup</legend>
          <label className="text-sm font-medium text-slate-700">Frecuencia
            <select value={draft.frequency} onChange={event => setDraft(value => ({ ...value, frequency: event.target.value as ImportBackupScheduleConfig['frequency'] }))} className="mt-1 block w-full rounded-lg border p-2">
              <option value="weekly">Semanal — lunes, semana anterior</option><option value="fortnightly">Quincenal — días 1 y 16, quincena anterior</option><option value="monthly">Mensual — día 1, mes anterior</option>
            </select></label>
          <label className="text-sm font-medium text-slate-700">Hora (Santo Domingo)
            <select value={draft.run_hour} onChange={event => setDraft(value => ({ ...value, run_hour: Number(event.target.value) }))} className="mt-1 block w-full rounded-lg border p-2">
              {Array.from({ length: 24 }, (_, hour) => <option key={hour} value={hour}>{String(hour).padStart(2, '0')}:00</option>)}
            </select></label>
          <label className="text-sm font-medium text-slate-700">Carpeta de destino (privada)
            <input required maxLength={80} pattern="[a-zA-Z0-9_-]+(/[a-zA-Z0-9_-]+)*" value={draft.folder} onChange={event => setDraft(value => ({ ...value, folder: event.target.value }))} className="mt-1 block w-full rounded-lg border p-2" />
          </label>
          <label className="text-sm font-medium text-slate-700">Conservar archivos (días)
            <input type="number" min={7} max={90} required value={draft.retention_days} onChange={event => setDraft(value => ({ ...value, retention_days: Number(event.target.value) }))} className="mt-1 block w-full rounded-lg border p-2" /></label>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={draft.enabled} onChange={event => setDraft(value => ({ ...value, enabled: event.target.checked }))} />Activar programación</label>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={draft.local_ids === null} onChange={event => setDraft(value => ({ ...value, local_ids: event.target.checked ? null : [] }))} />Todos los locales, incluidos los inactivos</label>
          {draft.local_ids !== null && <fieldset className="max-h-48 space-y-2 overflow-y-auto sm:col-span-2"><legend className="mb-2 text-sm font-semibold">Locales incluidos</legend>
            {stores.map(store => <label key={store.id} className="flex items-center gap-2 text-sm"><input type="checkbox" checked={draft.local_ids!.includes(store.id)} onChange={event => setDraft(value => ({ ...value, local_ids: event.target.checked ? [...(value.local_ids || []), store.id] : value.local_ids!.filter(id => id !== store.id) }))} />{store.codigo_interno} · {store.nombre}</label>)}
          </fieldset>}
        </fieldset>
        <p className="text-xs text-slate-500">Máximo {state.max_file_mb} MB por archivo automático, sujeto a los límites globales. Si hay importaciones en curso, la ejecución puede comenzar después de la hora indicada.</p>
        {state.schedule && <p className="text-sm text-slate-600">{state.schedule.enabled ? `Próxima ejecución: ${date(state.schedule.next_run_at)}.` : 'Programación pausada.'} Carpeta guardada: {state.schedule.folder}/</p>}
        <div className="flex gap-4">{canSave && <button type="submit" disabled={busy || (draft.local_ids !== null && draft.local_ids.length === 0)} className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">Guardar programación</button>}
          {state.schedule && canAccess('backup_schedules', 'delete') && <button type="button" disabled={busy} onClick={() => void mutate('delete')} className="text-sm text-red-600">Eliminar programación</button>}</div>
      </form>
      <h3 className="font-semibold text-slate-800">Archivos y ejecuciones recientes</h3>
      {!state.artifacts.length && <p className="text-sm text-slate-500">Todavía no hay ejecuciones.</p>}
      <ul className="divide-y">{state.artifacts.map(file => <li key={file.id} className="flex flex-wrap items-center justify-between gap-3 py-3 text-sm">
        <div><p className="font-medium text-slate-800">{file.filename}</p><p className="text-slate-500">{statuses[file.status] || file.status} · {file.start_date} al {file.end_date} · {file.records} registros · {(file.bytes / 1_000_000).toLocaleString('es-DO', { maximumFractionDigits: 2 })} MB</p>
          {file.status === 'completed' && <p className="text-xs text-slate-500">Vence: {date(file.expires_at)}</p>}
          {file.error && <p className="text-xs text-red-600">{file.error.startsWith('quota_') ? 'No había cuota suficiente o había otra descarga en curso.' : errors[file.error] || 'La ejecución no se completó.'}</p>}</div>
        {file.status === 'completed' && new Date(file.expires_at).getTime() > Date.now() && <button type="button" disabled={busy} onClick={() => void download(file.id, file.filename)} className="font-medium text-indigo-600">Descargar CSV</button>}
      </li>)}</ul>
    </>}
  </section>;
};
