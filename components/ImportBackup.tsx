import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Download, Loader2, Search, ShieldCheck } from 'lucide-react';
import { ApiService, ImportBackupStore, ImportBackupQuotaResponse } from '../api';
import { useAuth } from '../context/AuthProvider';
import { ImportBackupSchedulePanel } from './ImportBackupSchedulePanel';
import { ImportBackupQuotaPanel } from './ImportBackupQuotaPanel';

const formatDate = (value: Date) => `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, '0')}-${String(value.getDate()).padStart(2, '0')}`;
const COLUMNS = [
  'id_registro', 'mall_id', 'mall_nombre', 'local_id', 'codigo_local', 'local_nombre',
  'fecha_venta', 'hora_transaccion', 'numero_transaccion', 'tipo_registro', 'total_bruto',
  'total_impuestos', 'total_neto', 'fecha_creacion_registro', 'fecha_importacion',
  'canal_importacion', 'archivo_origen', 'batch_id'
];

export const ImportBackup: React.FC = () => {
  const { currentMall, session, canAccess } = useAuth();
  if (!canAccess('import_backup')) {
    return <p role="alert" className="p-6 text-slate-600">No tienes permiso para acceder al backup de importaciones.</p>;
  }
  if (!currentMall?.id || !session?.access_token) {
    return <p className="p-6 text-slate-600">Selecciona un Mall para descargar sus importaciones.</p>;
  }
  return <BackupForm key={currentMall.id} mallId={currentMall.id} mallName={currentMall.nombre} token={session.access_token} />;
};

const BackupForm: React.FC<{ mallId: string; mallName: string; token: string }> = ({ mallId, mallName, token }) => {
  const { canAccess } = useAuth();
  const [start, setStart] = useState(() => formatDate(new Date(new Date().getFullYear(), new Date().getMonth(), 1)));
  const [end, setEnd] = useState(() => formatDate(new Date()));
  const [stores, setStores] = useState<ImportBackupStore[]>([]);
  const [allStores, setAllStores] = useState(true);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const downloadRequest = useRef<AbortController | null>(null);
  const quotaRequest = useRef<AbortController | null>(null);
  const mounted = useRef(true);
  const [quotaState, setQuotaState] = useState<ImportBackupQuotaResponse | null>(null);
  const [quotaError, setQuotaError] = useState<string | null>(null);
  const [quotaFetchedAt, setQuotaFetchedAt] = useState(0);
  const [now, setNow] = useState(Date.now);
  const updateQuota = useCallback((state: ImportBackupQuotaResponse) => {
    setQuotaState(state);
    setQuotaError(null);
    setQuotaFetchedAt(Date.now());
    setNow(Date.now());
  }, []);
  const refreshQuota = useCallback(async () => {
    quotaRequest.current?.abort();
    const controller = new AbortController();
    quotaRequest.current = controller;
    try {
      const result = await ApiService.getImportBackupQuota(mallId, token, controller.signal);
      if (!controller.signal.aborted) { updateQuota(result); setQuotaError(null); }
    } catch (cause) {
      if (!controller.signal.aborted) setQuotaError(cause instanceof Error ? cause.message : 'No se pudo consultar la cuota.');
    }
  }, [mallId, token, updateQuota]);

  useEffect(() => {
    refreshQuota();
    const refreshVisible = () => { if (document.visibilityState === 'visible') refreshQuota(); };
    const interval = setInterval(refreshVisible, 30000);
    window.addEventListener('focus', refreshVisible);
    return () => { clearInterval(interval); window.removeEventListener('focus', refreshVisible); quotaRequest.current?.abort(); };
  }, [refreshQuota]);

  useEffect(() => {
    if (!quotaState?.quota.user.cooldown_seconds) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [quotaState]);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setLoadError(null);
    ApiService.getImportBackupStores(mallId, token, controller.signal)
      .then(rows => { if (!controller.signal.aborted) setStores(rows); })
      .catch(cause => {
        if (!controller.signal.aborted) setLoadError(cause instanceof Error ? cause.message : 'No se pudieron cargar los locales.');
      })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [mallId, token, retry]);

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; downloadRequest.current?.abort(); };
  }, []);

  const selectedSet = useMemo(() => new Set(selectedIds), [selectedIds]);
  const visibleStores = useMemo(() => {
    const term = search.trim().toLocaleLowerCase();
    return stores.filter(store => `${store.nombre} ${store.codigo_interno || ''}`.toLocaleLowerCase().includes(term));
  }, [stores, search]);
  const quota = quotaState?.quota;
  const cooldown = Math.max(0, (quota?.user.cooldown_seconds || 0) - Math.floor((now - quotaFetchedAt) / 1000));
  const days = Math.round((Date.parse(`${end}T00:00:00Z`) - Date.parse(`${start}T00:00:00Z`)) / 86400000) + 1;
  const dateError = !start || !end ? 'Selecciona ambas fechas.' : end < start ? 'La fecha final debe ser igual o posterior a la inicial.'
    : quota && days > quota.limits.max_range_days ? `El período máximo es de ${quota.limits.max_range_days} días.` : null;
  const quotaBlock = !quota ? 'Consultando tu cuota disponible…' : quotaError ? 'Actualiza la cuota antes de descargar.'
    : quota.user.downloads_remaining === 0 ? 'Agotaste tus solicitudes disponibles para hoy.'
    : quota.user.remaining_bytes === 0 ? 'Agotaste tu volumen diario de descarga.'
    : quota.mall.remaining_bytes === 0 ? 'El Mall agotó su volumen diario de descarga.'
    : quota.user.active >= quota.limits.user_concurrency ? 'Ya tienes una descarga en curso.'
    : quota.mall.active >= quota.limits.mall_concurrency ? 'El Mall alcanzó su límite de descargas simultáneas.'
    : cooldown > 0 ? `Espera ${cooldown} segundos para solicitar otro CSV.` : null;
  const selectionError = !allStores && selectedIds.length === 0 ? 'Selecciona al menos un local.' : null;

  const handleDownload = async (event: React.FormEvent) => {
    event.preventDefault();
    if (dateError || selectionError || quotaBlock || loading || loadError || downloading || stores.length === 0) return;
    const controller = new AbortController();
    downloadRequest.current = controller;
    setDownloading(true);
    setError(null);
    setSuccess(null);
    try {
      const result = await ApiService.downloadImportBackup(mallId, token, start, end, allStores ? null : selectedIds, controller.signal);
      if (controller.signal.aborted) return;
      const url = URL.createObjectURL(result.blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `backup_${mallId}_${start}_${end}.csv`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      setSuccess(result.records === 0
        ? 'No hay ventas en el período y los locales seleccionados. Se descargó un CSV con los encabezados.'
        : `CSV descargado${result.records === null ? '' : `: ${result.records.toLocaleString()} registros`}.`);
    } catch (cause) {
      if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : 'No se pudo descargar el CSV.');
    } finally {
      if (downloadRequest.current === controller) {
        downloadRequest.current = null;
        if (mounted.current) { setDownloading(false); refreshQuota(); }
      }
    }
  };

  return (
    <section className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Backup de importaciones</h1>
        <p className="mt-1 text-sm text-slate-500">Descarga las ventas almacenadas de {mallName} en un archivo CSV.</p>
      </div>
      {quotaState && <ImportBackupQuotaPanel state={quotaState} cooldown={cooldown} onRefresh={refreshQuota} />}
      {canAccess('backup_schedules') && <ImportBackupSchedulePanel mallId={mallId} token={token} stores={stores} onDownloaded={refreshQuota} />}
      {quotaError && <p role="alert" className="text-sm text-red-600">{quotaError} <button type="button" onClick={refreshQuota} className="underline">Reintentar consulta de cuota</button></p>}
      <form onSubmit={handleDownload} className="space-y-5 rounded-2xl border border-slate-200 bg-white p-5 sm:p-6">
        <fieldset disabled={downloading} className="space-y-5">
          <legend className="mb-3 font-semibold text-slate-800">Período por fecha de venta</legend>
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="text-sm font-medium text-slate-700">Fecha inicial
              <input type="date" value={start} onChange={event => { setStart(event.target.value); setSuccess(null); }} required
                className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2" />
            </label>
            <label className="text-sm font-medium text-slate-700">Fecha final
              <input type="date" value={end} min={start || undefined} onChange={event => { setEnd(event.target.value); setSuccess(null); }} required
                className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2" />
            </label>
          </div>
          <p className="text-xs text-slate-500">Ambas fechas están incluidas. Se usa el día de la venta, aunque se haya importado después.</p>
          {dateError && <p role="alert" className="text-sm text-red-600">{dateError}</p>}
          <fieldset disabled={loading || Boolean(loadError)} className="space-y-3">
            <legend className="mb-3 font-semibold text-slate-800">Locales</legend>
            <label className="flex items-center gap-2 text-sm text-slate-700">
              <input type="radio" name="backup-scope" checked={allStores} onChange={() => { setAllStores(true); setSuccess(null); }} />
              Todos los locales ({stores.length}), incluidos los inactivos
            </label>
            <label className="flex items-center gap-2 text-sm text-slate-700">
              <input type="radio" name="backup-scope" checked={!allStores} onChange={() => { setAllStores(false); setSuccess(null); }} />
              Elegir locales
            </label>
            {!allStores && <div className="space-y-3 rounded-xl border border-slate-200 p-4">
              <label className="flex items-center gap-2 rounded-lg border border-slate-300 px-3 py-2">
                <Search size={16} aria-hidden="true" className="text-slate-400" />
                <input type="search" aria-label="Buscar locales por nombre o código" placeholder="Buscar por nombre o código" value={search}
                  onChange={event => setSearch(event.target.value)} className="min-w-0 flex-1 outline-none" />
              </label>
              <div className="flex flex-wrap items-center gap-3 text-sm">
                <button type="button" onClick={() => { setSelectedIds(ids => Array.from(new Set([...ids, ...visibleStores.map(store => store.id)]))); setSuccess(null); }}
                  className="font-medium text-indigo-600">Seleccionar visibles</button>
                <button type="button" onClick={() => { setSelectedIds([]); setSuccess(null); }} className="text-slate-600">Limpiar selección</button>
                <span className="text-slate-500" aria-live="polite">{selectedIds.length} seleccionados</span>
              </div>
              <div className="max-h-72 space-y-1 overflow-y-auto">
                {visibleStores.map(store => <label key={store.id} className="flex cursor-pointer items-center gap-3 rounded-lg p-2 hover:bg-slate-50">
                  <input type="checkbox" checked={selectedSet.has(store.id)} onChange={event => {
                    const checked = event.target.checked;
                    setSelectedIds(ids => checked ? [...ids, store.id] : ids.filter(id => id !== store.id));
                    setSuccess(null);
                  }} />
                  <span className="text-sm text-slate-700">{store.nombre} <span className="text-slate-400">{store.codigo_interno ? `· ${store.codigo_interno}` : ''}{store.activo === false ? ' · Inactivo' : ''}</span></span>
                </label>)}
                {visibleStores.length === 0 && <p className="p-2 text-sm text-slate-500">No se encontraron locales.</p>}
              </div>
            </div>}
          </fieldset>
        </fieldset>
        {loading && <p role="status" className="text-sm text-slate-500">Cargando locales…</p>}
        {loadError && <div role="alert" className="text-sm text-red-600">{loadError} <button type="button" onClick={() => setRetry(value => value + 1)} className="underline">Reintentar</button></div>}
        {!loading && !loadError && stores.length === 0 && <p role="status" className="text-sm text-slate-500">El Mall seleccionado no tiene locales registrados.</p>}
        {selectionError && <p role="alert" className="text-sm text-red-600">{selectionError}</p>}
        <div className="flex flex-wrap items-center gap-3 border-t border-slate-100 pt-4">
          <button type="submit" disabled={downloading || loading || Boolean(loadError || dateError || selectionError || quotaBlock) || stores.length === 0}
            className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-5 py-3 text-sm font-semibold text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50">
            {downloading ? <Loader2 size={18} className="animate-spin" aria-hidden="true" /> : <Download size={18} aria-hidden="true" />}
            {downloading ? 'Generando CSV…' : 'Descargar CSV'}
          </button>
          {downloading && <button type="button" onClick={() => { downloadRequest.current?.abort(); setDownloading(false); }} className="text-sm text-slate-600">Cancelar descarga</button>}
        </div>
        {!downloading && quotaBlock && <p className="text-sm text-amber-700">{quotaBlock}</p>}
        {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
        {success && <p role="status" className="text-sm text-emerald-700">{success}</p>}
      </form>
      <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-600">
        <p className="flex items-center gap-2 font-medium"><ShieldCheck size={18} aria-hidden="true" />Una fila por registro, con sus importes almacenados.</p>
        <p className="mt-2">Las fechas de importación y los datos de origen se incluyen cuando están disponibles. Los campos desconocidos quedan vacíos.</p>
        <details className="mt-3">
          <summary className="cursor-pointer font-medium">Ver las 18 columnas del CSV</summary>
          <ul className="mt-3 grid gap-1 text-xs sm:grid-cols-2 lg:grid-cols-3">{COLUMNS.map(column => <li key={column}>{column}</li>)}</ul>
        </details>
      </div>
    </section>
  );
}
