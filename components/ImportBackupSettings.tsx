import React, { useEffect, useRef, useState } from 'react';
import { ApiService, ImportBackupPolicy } from '../api';
import { useAuth } from '../context/AuthProvider';

const POLICY_FIELDS: Array<{ key: keyof ImportBackupPolicy; label: string; max: number }> = [
  { key: 'user_concurrency', label: 'Simultáneas por usuario', max: 10 },
  { key: 'mall_concurrency', label: 'Simultáneas por Mall', max: 50 },
  { key: 'min_interval_seconds', label: 'Segundos entre solicitudes', max: 86400 },
  { key: 'user_daily_downloads', label: 'Solicitudes diarias por usuario', max: 10000 },
  { key: 'max_file_mb', label: 'MB máximos por archivo', max: 1000 },
  { key: 'user_daily_mb', label: 'MB diarios por usuario', max: 100000 },
  { key: 'mall_daily_mb', label: 'MB diarios por Mall', max: 1000000 },
  { key: 'max_range_days', label: 'Días máximos por solicitud', max: 3660 }
];
export const ImportBackupSettings: React.FC = () => {
  const { isAdmin, currentMall, session } = useAuth();
  if (!isAdmin) return <p role="alert" className="p-6 text-slate-600">Solo un administrador puede configurar los límites de backup.</p>;
  if (!currentMall?.id || !session?.access_token) return <p className="p-6 text-slate-600">Selecciona un Mall para consultar la configuración global.</p>;
  return <SettingsForm key={currentMall.id} mallId={currentMall.id} token={session.access_token} />;
};

const SettingsForm: React.FC<{ mallId: string; token: string }> = ({ mallId, token }) => {
  const [draft, setDraft] = useState<ImportBackupPolicy | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [reload, setReload] = useState(0);
  const request = useRef<AbortController | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    setError(null);
    ApiService.getImportBackupPolicy(mallId, token, controller.signal)
      .then(result => { if (!controller.signal.aborted) setDraft(result.quota.limits); })
      .catch(cause => { if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : 'No se pudieron consultar los límites.'); });
    return () => controller.abort();
  }, [mallId, token, reload]);
  useEffect(() => () => request.current?.abort(), []);

  const save = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!draft || saving) return;
    const controller = new AbortController();
    request.current = controller;
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      const result = await ApiService.saveImportBackupPolicy(mallId, token, draft, controller.signal);
      if (!controller.signal.aborted) { setDraft(result.quota.limits); setSaved(true); }
    } catch (cause) {
      if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : 'No se pudieron guardar los límites.');
    } finally {
      if (!controller.signal.aborted) setSaving(false);
    }
  };

  return <section className="space-y-4 rounded-2xl border border-slate-200 bg-white p-6">
    <h1 className="text-2xl font-bold text-slate-900">Configurar límites globales de backup</h1>
    {!draft && !error && <p role="status">Cargando límites…</p>}
    {error && <p role="alert" className="text-sm text-red-600">{error} {!draft && <button type="button" onClick={() => setReload(value => value + 1)} className="underline">Reintentar</button>}</p>}
    {saved && <p role="status" className="text-sm text-emerald-700">Límites actualizados para todos los usuarios y Malls.</p>}
    {draft && <form onSubmit={save} className="space-y-4 border-t border-slate-100 pt-4">
      <p className="text-sm text-slate-600">Estos límites se aplican a todos los usuarios y Malls. El consumo de hoy se conserva.</p>
      <fieldset disabled={saving} className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <legend className="sr-only">Configuración global de backup</legend>
        {POLICY_FIELDS.map(field => <label key={field.key} className="text-xs font-medium text-slate-600">{field.label}
          <input type="number" min={1} max={field.max} step={1} required value={Number.isNaN(draft[field.key]) ? '' : draft[field.key]}
            onChange={event => setDraft(value => ({ ...value!, [field.key]: event.target.value === '' ? NaN : Number(event.target.value) }))}
            className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" />
        </label>)}
      </fieldset>
      <div className="flex gap-3">
        <button disabled={saving} type="submit" className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">{saving ? 'Guardando…' : 'Guardar límites'}</button>
        <button disabled={saving} type="button" onClick={() => { setDraft(null); setSaved(false); setReload(value => value + 1); }} className="text-sm text-slate-600">Cancelar</button>
      </div>
    </form>}
  </section>;
};
