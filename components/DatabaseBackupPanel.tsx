import React, { useEffect, useRef, useState } from 'react';
import { ApiService } from '../api';

type Capabilities = Awaited<ReturnType<typeof ApiService.getDatabaseBackupCapabilities>>;
export const DatabaseBackupPanel: React.FC<{ mallId: string; mallName: string; token: string; onDownloaded: () => void }> = ({ mallId, mallName, token, onDownloaded }) => {
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [success, setSuccess] = useState('');
  const [retry, setRetry] = useState(0);
  const request = useRef<AbortController | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    setCapabilities(null); setError('');
    ApiService.getDatabaseBackupCapabilities(mallId, token, controller.signal).then(result => {
      if (!controller.signal.aborted) setCapabilities(result);
    }).catch(err => { if (!controller.signal.aborted) setError(err instanceof Error ? err.message : 'No se pudieron verificar los permisos.'); });
    return () => { controller.abort(); request.current?.abort(); };
  }, [mallId, token, retry]);

  const download = async (scope: 'mall' | 'platform') => {
    if (busy) return;
    const controller = new AbortController();
    request.current = controller;
    setBusy(true); setError(''); setSuccess('');
    try {
      const blob = await ApiService.downloadDatabaseBackup(mallId, token, scope, controller.signal);
      if (controller.signal.aborted) return;
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url; link.download = `backup_${scope}_${mallId}_${new Date().toISOString().slice(0, 10)}.zip`;
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
    <h2 className="text-lg font-bold text-slate-800">Backup del Mall y de la plataforma</h2>
    <p className="text-sm text-slate-600">Descarga SQL en un ZIP. El backup del Mall incluye sus registros y relaciones identificables; el completo incluye la base lógica y roles sin contraseñas de PostgreSQL. No incluye archivos físicos de Storage ni código o variables del servidor.</p>
    <p className="text-sm text-amber-800">Estos SQL pueden incluir credenciales guardadas. Protégelos. No se restauran desde CSV. El backup por Mall requiere un esquema compatible y usuarios/catálogos compartidos existentes. Se aplican las cuotas de descarga del usuario y del Mall activo, también para el backup completo.</p>
    {!capabilities && !error && <p role="status" className="text-sm">Verificando disponibilidad…</p>}
    {capabilities && !capabilities.enabled && <p className="text-sm text-amber-800">Backups SQL no habilitados. El administrador debe configurar la conexión de backups en el servidor.</p>}
    {capabilities && !capabilities.mall && !capabilities.platform && <p className="text-sm text-slate-600">Se requiere un administrador asignado a este Mall. El backup completo es exclusivo del administrador global.</p>}
    <div className="flex flex-wrap gap-3">
      {capabilities?.mall && <button type="button" disabled={busy || !capabilities.enabled} onClick={() => void download('mall')} className="rounded-xl border border-indigo-200 px-4 py-3 text-sm font-semibold text-indigo-700 disabled:opacity-50">Descargar backup de {mallName}</button>}
      {capabilities?.platform && <button type="button" disabled={busy || !capabilities.enabled} onClick={() => void download('platform')} className="rounded-xl bg-indigo-600 px-4 py-3 text-sm font-semibold text-white disabled:opacity-50">Descargar backup completo de la plataforma</button>}
    </div>
    {busy && <p role="status" className="text-sm">Generando backup… Puede tardar varios minutos. Mantén esta pantalla abierta.</p>}
    {success && <p role="status" className="text-sm text-emerald-700">{success}</p>}
    {error && <p role="alert" className="text-sm text-red-700">{error} {!capabilities && <button type="button" onClick={() => setRetry(value => value + 1)} className="underline">Reintentar permisos</button>}</p>}
  </section>;
};
