import React from 'react';
import { ImportBackupQuotaResponse } from '../api';

const mb = (bytes: number) => (bytes / 1_000_000).toLocaleString('es-DO', { maximumFractionDigits: 2 });

export const ImportBackupQuotaPanel: React.FC<{
  state: ImportBackupQuotaResponse; cooldown: number; onRefresh: () => void;
}> = ({ state: { quota }, cooldown, onRefresh }) => {
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
    <p className="text-xs text-slate-500">Se renueva el {new Date(quota.resets_at).toLocaleString('es-DO', { timeZone: quota.timezone })} ({quota.timezone}).</p>
  </section>;
};
