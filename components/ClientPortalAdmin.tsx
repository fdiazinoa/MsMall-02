import React, { useEffect, useState } from 'react';
import { portalRequest } from '../api';
import { PortalLocal } from './ClientPortal';

interface Props { mallId: string; token: string; users: { id: string; email: string; portal_client?: boolean }[]; onCreated: () => Promise<void> }
const input = 'w-full rounded-lg border border-slate-300 bg-white px-3 py-2';
export function ClientPortalAdmin({ mallId, token, users, onCreated }: Props) {
  const [locals, setLocals] = useState<PortalLocal[]>([]);
  const [localId, setLocalId] = useState('');
  const [userId, setUserId] = useState('');
  const [grants, setGrants] = useState<string[]>([]);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  useEffect(() => {
    let ignore = false;
    setLocals([]); setLocalId('');
    portalRequest<PortalLocal[]>(`/admin/portal/locals?mall_id=${encodeURIComponent(mallId)}`, token).then(data => {
      const mallLocals = data.filter(local => local.mall_id === mallId);
      if (!ignore) { setLocals(mallLocals); setLocalId(mallLocals[0]?.id || ''); }
    }).catch(e => { if (!ignore) setError(e.message); });
    return () => { ignore = true; };
  }, [token, mallId]);
  useEffect(() => {
    let ignore = false;
    setGrants([]);
    if (userId) portalRequest<{ local_id: string }[]>(`/admin/portal/grants?user_id=${userId}`, token)
      .then(rows => { if (!ignore) setGrants(rows.map(row => row.local_id)); })
      .catch(e => { if (!ignore) setError(e.message); });
    return () => { ignore = true; };
  }, [userId, token]);
  async function mutate(path: string, method: string, body: object) {
    setBusy(true); setError(''); setMessage('');
    try {
      const result = await portalRequest<{ id?: string }>(path, token, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      if (path.endsWith('/clients')) {
        setEmail(''); setPassword('');
        setMessage('Cuenta creada con acceso exclusivo al portal. Comparte la URL y las credenciales con el cliente.');
        await onCreated(); setUserId(result.id || '');
      } else {
        setGrants(previous => method === 'DELETE' ? previous.filter(id => id !== localId) : [...new Set([...previous, localId])]);
        setMessage(method === 'DELETE' ? 'Acceso al local retirado.' : 'Acceso al local asignado.');
      }
    } catch (e) { setError(e instanceof Error ? e.message : 'No se pudo guardar.'); }
    finally { setBusy(false); }
  }
  return <section className="space-y-4 rounded-2xl border border-indigo-200 bg-white p-5">
    <div><h3 className="font-bold text-slate-800">Acceso al portal de clientes</h3><a href="/portal-cliente" target="_blank" rel="noreferrer" className="text-sm text-indigo-700">Abrir portal de clientes ↗</a></div>
    <p className="text-sm text-slate-500">Las cuentas creadas aquí sólo acceden al portal y al único local vinculado. No reciben malls ni roles internos.</p>
    {error && <p role="alert" className="text-sm text-red-700">{error}</p>}{message && <p role="status" className="text-sm text-indigo-700">{message}</p>}
    <label className="block text-sm">Local<select disabled={busy} className={`${input} mt-1`} value={localId} onChange={e => setLocalId(e.target.value)}><option value="">Selecciona un local</option>{locals.map(local => <option key={local.id} value={local.id}>{local.nombre} · {local.codigo_interno}</option>)}</select></label>
    <form className="grid items-end gap-3 sm:grid-cols-3" onSubmit={e => { e.preventDefault(); mutate('/admin/portal/clients', 'POST', { email, password, local_id: localId }); }}>
      <label className="text-sm">Correo del nuevo cliente<input type="email" autoComplete="off" required disabled={busy} className={`${input} mt-1`} value={email} onChange={e => setEmail(e.target.value)} /></label>
      <label className="text-sm">Contraseña inicial<input type="password" autoComplete="new-password" required minLength={8} disabled={busy} className={`${input} mt-1`} value={password} onChange={e => setPassword(e.target.value)} /></label>
      <button disabled={busy || !localId} className="rounded-lg bg-indigo-600 px-4 py-2 text-white disabled:opacity-50">Crear cuenta de cliente</button>
    </form>
    <div className="space-y-3 border-t pt-4"><label className="block text-sm">Vincular o desvincular una cuenta de cliente<select disabled={busy} className={`${input} mt-1`} value={userId} onChange={e => setUserId(e.target.value)}><option value="">Selecciona una cuenta de cliente</option>{users.filter(user => user.portal_client).map(user => <option key={user.id} value={user.id}>{user.email}</option>)}</select></label>
      {userId && <><p className="text-sm text-slate-500">Local vinculado: {grants.map(id => locals.find(local => local.id === id)?.nombre || id).join(', ') || 'Ninguno'}</p><div className="flex flex-wrap gap-3"><button disabled={busy || !localId || grants.length > 0} onClick={() => mutate('/admin/portal/grants', 'POST', { user_id: userId, local_id: localId })} className="rounded-lg border px-4 py-2 disabled:opacity-50">Vincular local a la cuenta</button><button disabled={busy || !grants.includes(localId)} onClick={() => mutate('/admin/portal/grants', 'DELETE', { user_id: userId, local_id: localId })} className="rounded-lg border border-red-200 px-4 py-2 text-red-700 disabled:opacity-50">Retirar acceso al local</button></div></>}
    </div>
  </section>;
}
