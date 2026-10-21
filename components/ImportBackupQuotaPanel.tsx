import React, { useEffect, useRef, useState } from 'react';
import { ApiService, ImportBackupPolicy, ImportBackupQuotaResponse } from '../api';

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
const mb = (bytes: number) => (bytes / 1_000_000).toLocaleString('es-DO', { maximumFractionDigits: 2 });

export const ImportBackupQuotaPanel: React.FC<{
  state: ImportBackupQuotaResponse; cooldown: number; mallId: string; token: string;
  onUpdate: (state: ImportBackupQuotaResponse) => void; onRefresh: () => void;
}> = ({ state, cooldown, mallId, token, onUpdate, onRefresh }) => {
  const { quota, can_configure } = state;
  const [draft, setDraft] = useState<ImportBackupPolicy | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const request = useRef<AbortController | null>(null);
  useEffect(() => () => request.current?.abort(), []);

  const save = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!draft || saving) return;
    const controller = new AbortController();
    request.current = controller;
    setSaving(true);
    setError(null);
    try {
      const result = await ApiService.saveImportBackupPolicy(mallId, token, draft, controller.signal);
      if (!controller.signal.aborted) { onUpdate(result); setDraft(null); setSaved(true); }
    } catch (cause) {
      if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : 'No se pudieron guardar los límites.');
    } finally {
      if (!controller.signal.aborted) setSaving(false);
    }
  };

  return <section aria-label="Cuota de backup" className="space-y-3 rounded-2xl border border-indigo-100 bg-white p-5">
    <div className="flex flex-wrap items-center justify-between gap-2">
      <h2 className="font-semibold text-slate-800">Tu cuota disponible</h2>
      <button type="button" onClick={onRefresh} className="text-sm font-medium text-indigo-600">Actualizar cuota</button>
    </div>
    <dl className="grid gap-3 sm:grid-cols-3">
      <div className="rounded-xl bg-slate-50 p-3"><dt className="text-xs text-slate-500">Solicitudes disponibles hoy</dt>
        <dd className="mt-1 text-lg font-bold text-slate-800">{quota.user.downloads_remaining} / {quota.limits.user_daily_downloads}</dd></div>
      <div className="rounded-xl bg-slate-50 p-3"><dt className="text-xs text-slate-500">Volumen disponible para ti</dt>
        <dd className="mt-1 text-lg font-bold text-slate-800">{mb(quota.user.remaining_bytes)} / {quota.limits.user_daily_mb} MB</dd></div>
      <div className="rounded-xl bg-slate-50 p-3"><dt className="text-xs text-slate-500">Volumen disponible del Mall</dt>
        <dd className="mt-1 text-lg font-bold text-slate-800">{mb(quota.mall.remaining_bytes)} / {quota.limits.mall_daily_mb} MB</dd></div>
    </dl>
    <p className="text-xs text-slate-500">Máximo {quota.limits.max_file_mb} MB por CSV y {quota.limits.max_range_days} días por solicitud. En curso: {quota.user.active}/{quota.limits.user_concurrency} tuyas y {quota.mall.active}/{quota.limits.mall_concurrency} del Mall.</p>
    {cooldown > 0 && <p role="status" className="text-sm text-amber-700">Puedes solicitar otro CSV en {cooldown} segundos.</p>}
    <p className="text-xs text-slate-500">Las solicitudes fallidas o canceladas también cuentan. Tu cuota se comparte entre todos tus Malls. Los volúmenes disponibles descuentan las reservas en curso.</p>
    <p className="text-xs text-slate-500">Se renueva el {new Date(quota.resets_at).toLocaleString('es-DO', { timeZone: quota.timezone })} ({quota.timezone}).</p>
    {can_configure && !draft && <button type="button" onClick={() => { setDraft({ ...quota.limits }); setError(null); setSaved(false); }} className="text-sm font-semibold text-indigo-600">Configurar límites globales</button>}
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
      {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
      <div className="flex gap-3">
        <button disabled={saving} type="submit" className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">{saving ? 'Guardando…' : 'Guardar límites'}</button>
        <button disabled={saving} type="button" onClick={() => setDraft(null)} className="text-sm text-slate-600">Cancelar</button>
      </div>
    </form>}
  </section>;
};
