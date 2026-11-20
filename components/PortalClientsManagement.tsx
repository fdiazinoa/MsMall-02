import React, { useEffect, useState } from 'react';
import { portalRequest } from '../api';
import { useAuth } from '../context/AuthProvider';
import { ClientPortalAdmin } from './ClientPortalAdmin';
import type { PortalClientAccount } from './ClientPortalAdmin';

export function PortalClientsManagement() {
  const { session, isAdmin, canAccess, currentMall } = useAuth();
  if (!isAdmin && !canAccess('users')) return <p role="alert" className="rounded-xl bg-amber-50 p-4 text-amber-800">No tienes permiso para gestionar clientes del portal.</p>;
  if (import.meta.env.VITE_CLIENT_PORTAL_ENABLED !== 'true') return <p role="status" className="rounded-xl bg-amber-50 p-4 text-amber-800">La gestión de clientes del portal no está habilitada.</p>;
  if (!currentMall?.id) return <p role="status" className="rounded-xl bg-amber-50 p-4 text-amber-800">Selecciona un mall para gestionar los clientes del portal.</p>;

  return <React.Fragment key={currentMall.id}><ClientsForMall token={session?.access_token} mallId={currentMall.id} /></React.Fragment>;
}

function ClientsForMall({ token, mallId }: { token: string; mallId: string }) {
  const [clients, setClients] = useState<PortalClientAccount[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const path = `/admin/portal/clients?mall_id=${encodeURIComponent(mallId)}`;

  useEffect(() => {
    if (!token) return;
    let ignore = false;
    setLoading(true);
    setError('');
    portalRequest<PortalClientAccount[]>(path, token).then(users => {
      if (!ignore) setClients(users.filter(user => user.portal_client && user.mall_id === mallId));
    }).catch(cause => {
      if (!ignore) setError(cause instanceof Error ? cause.message : 'No se pudieron cargar las cuentas de clientes.');
    }).finally(() => { if (!ignore) setLoading(false); });
    return () => { ignore = true; };
  }, [token, path, mallId]);

  async function refreshClients() {
    const users = await portalRequest<PortalClientAccount[]>(path, token);
    setClients(users.filter(user => user.portal_client && user.mall_id === mallId));
  }

  return <div className="space-y-5">
    <div>
      <h2 className="text-xl font-bold text-slate-800">Clientes del portal</h2>
      <p className="mt-1 text-sm text-slate-500">Gestiona las cuentas externas que cargan archivos de ventas. Cada cuenta accede únicamente al portal y a su local vinculado.</p>
    </div>
    {loading ? <p role="status" className="rounded-xl bg-white p-5 text-slate-600">Cargando cuentas de clientes…</p> : error ? <div role="alert" className="rounded-xl bg-red-50 p-5 text-red-800"><p>{error}</p><button className="mt-3 font-semibold underline" onClick={() => {
      setLoading(true);
      refreshClients().then(() => setError('')).catch(cause => setError(cause instanceof Error ? cause.message : 'No se pudieron cargar las cuentas.')).finally(() => setLoading(false));
    }}>Reintentar</button></div> : <ClientPortalAdmin mallId={mallId} token={token} users={clients} onCreated={refreshClients} />}
  </div>;
}
