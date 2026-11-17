import React, { useEffect, useState } from 'react';
import { ApiService } from '../api';
import { useAuth } from '../context/AuthProvider';
import type { User } from '../types';
import { ClientPortalAdmin } from './ClientPortalAdmin';

export function PortalClientsManagement() {
  const { session, isAdmin, canAccess } = useAuth();
  const token = session?.access_token;
  const allowed = isAdmin || canAccess('users');
  const enabled = import.meta.env.VITE_CLIENT_PORTAL_ENABLED === 'true';
  const [clients, setClients] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!token || !allowed || !enabled) return;
    let ignore = false;
    setLoading(true);
    setError('');
    ApiService.getUsers(token).then(users => {
      if (!ignore) setClients(users.filter(user => user.portal_client));
    }).catch(cause => {
      if (!ignore) setError(cause instanceof Error ? cause.message : 'No se pudieron cargar las cuentas de clientes.');
    }).finally(() => { if (!ignore) setLoading(false); });
    return () => { ignore = true; };
  }, [token, allowed, enabled]);

  async function refreshClients() {
    const users = await ApiService.getUsers(token);
    setClients(users.filter(user => user.portal_client));
  }

  if (!allowed) return <p role="alert" className="rounded-xl bg-amber-50 p-4 text-amber-800">No tienes permiso para gestionar clientes del portal.</p>;
  if (!enabled) return <p role="status" className="rounded-xl bg-amber-50 p-4 text-amber-800">La gestión de clientes del portal no está habilitada.</p>;

  return <div className="space-y-5">
    <div>
      <h2 className="text-xl font-bold text-slate-800">Clientes del portal</h2>
      <p className="mt-1 text-sm text-slate-500">Gestiona las cuentas externas que cargan archivos de ventas. Cada cuenta accede únicamente al portal y a su local vinculado.</p>
    </div>
    {loading ? <p role="status" className="rounded-xl bg-white p-5 text-slate-600">Cargando cuentas de clientes…</p> : error ? <div role="alert" className="rounded-xl bg-red-50 p-5 text-red-800"><p>{error}</p><button className="mt-3 font-semibold underline" onClick={() => {
      setLoading(true);
      refreshClients().then(() => setError('')).catch(cause => setError(cause instanceof Error ? cause.message : 'No se pudieron cargar las cuentas.')).finally(() => setLoading(false));
    }}>Reintentar</button></div> : <ClientPortalAdmin token={token} users={clients} onCreated={refreshClients} />}
  </div>;
}
