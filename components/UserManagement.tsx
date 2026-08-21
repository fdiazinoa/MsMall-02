
import React, { useState, useEffect } from 'react';
import { ApiService } from '../api';
import { useAuth } from '../context/AuthProvider';
import { UserPlus, Shield, ShieldCheck, ShieldAlert, CheckCircle2, UserCog, Building2, Plus, Save, Trash2, Mail } from 'lucide-react';
import { RoleConfig, RolePermission } from '../types';

const MODULES = [
  ['dashboard', 'Dashboard BI'], ['sales_reports', 'Reportes de ventas'], ['stores', 'Locales'],
  ['imports', 'Importaciones'], ['monitor', 'Monitor de cargas'], ['financial', 'Gestión financiera'],
  ['cube', 'Cubo de ventas'], ['comparisons', 'Comparativas BI'], ['malls', 'Gestión de malls'],
  ['users', 'Usuarios'], ['roles', 'Roles y permisos'],
] as const;

const ROLE_STYLES: Record<string, { label: string, color: string, icon: any }> = {
  admin: { label: 'Administrador', color: 'bg-rose-50 text-rose-600 border-rose-100', icon: ShieldCheck },
  it: { label: 'IT', color: 'bg-amber-50 text-amber-700 border-amber-100', icon: ShieldAlert },
  tic: { label: 'IT', color: 'bg-amber-50 text-amber-700 border-amber-100', icon: ShieldAlert },
  auditor: { label: 'Auditor', color: 'bg-indigo-50 text-indigo-600 border-indigo-100', icon: Shield },
  visualizador: { label: 'Visualizador', color: 'bg-slate-50 text-slate-600 border-slate-200', icon: Shield },
  mall_manager: { label: 'Gerente Mall', color: 'bg-slate-50 text-slate-600 border-slate-100', icon: ShieldAlert },
};

const normalizeRole = (role: string) => (role || '').toLowerCase().trim().replace(/[-\s]+/g, '_');

export const UserManagement: React.FC = () => {
  const { session, isAdmin, canAccess } = useAuth();
  const [users, setUsers] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedMallFilter, setSelectedMallFilter] = useState('ALL');

  // Mall Assignment State
  const [availableMalls, setAvailableMalls] = useState<any[]>([]);
  const [assignmentModalOpen, setAssignmentModalOpen] = useState(false);
  const [selectedUser, setSelectedUser] = useState<any>(null);
  const [selectedMallIds, setSelectedMallIds] = useState<string[]>([]);
  const [editRole, setEditRole] = useState('auditor');
  const [editEmail, setEditEmail] = useState('');
  const [editName, setEditName] = useState('');
  const [savingUser, setSavingUser] = useState(false);
  const [sendingRecoveryUserId, setSendingRecoveryUserId] = useState<string | null>(null);

  // Create User Modal State
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [newEmail, setNewEmail] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [newRole, setNewRole] = useState('auditor');
  const [newMallIds, setNewMallIds] = useState<string[]>([]);
  const [creatingUser, setCreatingUser] = useState(false);
  const [roles, setRoles] = useState<RoleConfig[]>([]);
  const [rolesError, setRolesError] = useState<string | null>(null);
  const [selectedRole, setSelectedRole] = useState<RoleConfig | null>(null);
  const [savingRole, setSavingRole] = useState(false);
  const [showRoleEditor, setShowRoleEditor] = useState(false);

  const loadUsers = async () => {
    if (!session?.access_token) return;
    setLoading(true);
    try {
      const data = await ApiService.getUsers(session.access_token);
      setUsers(data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const loadMalls = async () => {
    if (!session?.access_token) return;
    try {
      const data = await ApiService.getMalls(session.access_token);
      setAvailableMalls(data);
    } catch (e) { console.error(e); }
  };

  const loadRoles = async () => {
    if (!session?.access_token) return;
    try {
      const data = await ApiService.getRoles(session.access_token);
      setRoles(data);
      setRolesError(null);
    } catch (e: any) {
      console.error(e);
      setRolesError(e?.message || 'No se pudieron cargar los roles de fábrica.');
    }
  };

  useEffect(() => {
    loadUsers();
    loadMalls();
    loadRoles();
  }, [session]);

  const filteredUsers = users.filter((user) => {
    if (selectedMallFilter === 'ALL') return true;
    return (user.malls || []).some((mall: any) => mall.mall_id === selectedMallFilter);
  });

  const openCreateModal = () => {
    setNewEmail('');
    setNewPassword('');
    const auditor = roles.find((role) => role.key === 'auditor') || roles[0];
    setNewRole(auditor?.id || 'auditor');
    setNewMallIds([]);
    setCreateModalOpen(true);
  };

  const handleToggleNewMall = (mallId: string) => {
    if (newMallIds.includes(mallId)) {
      setNewMallIds(newMallIds.filter(id => id !== mallId));
    } else {
      setNewMallIds([...newMallIds, mallId]);
    }
  };

  const handleCreateUser = async () => {
    if (!session?.access_token) return;
    if (!newEmail.trim() || !newPassword.trim()) {
      alert("Email y contraseña son requeridos.");
      return;
    }
    if (newPassword.length < 8) {
      alert("La contraseña debe tener al menos 8 caracteres.");
      return;
    }

    setCreatingUser(true);
    try {
      const selected = roles.find((role) => role.id === newRole);
      const result = await ApiService.createUser(newEmail.trim(), newPassword, selected?.key || 'auditor', newMallIds, session.access_token, selected?.id);
      setCreateModalOpen(false);
      await loadUsers();
      alert(result?.message || "Usuario procesado correctamente.");
    } catch (e: any) {
      alert(`Error creando usuario: ${e.message || e}`);
    } finally {
      setCreatingUser(false);
    }
  };

  const openAssignmentModal = (user: any) => {
    setSelectedUser(user);
    // Pre-select existing malls
    const currentIds = user.malls?.map((m: any) => m.mall_id) || [];
    setSelectedMallIds(currentIds);
    setEditRole(user.role_id || roles.find((role) => role.key === normalizeRole(user.rol || 'auditor'))?.id || '');
    setEditEmail(user.email || '');
    setEditName(user.nombre || user.metadata?.nombre || user.metadata?.full_name || '');
    setAssignmentModalOpen(true);
  };

  const handleToggleMall = (mallId: string) => {
    if (selectedMallIds.includes(mallId)) {
      setSelectedMallIds(selectedMallIds.filter(id => id !== mallId));
    } else {
      setSelectedMallIds([...selectedMallIds, mallId]);
    }
  };

  const handleSaveAssignments = async () => {
    if (!selectedUser || !session?.access_token) return;
    setSavingUser(true);
    try {
      await ApiService.updateUser(
        selectedUser.id,
        {
          email: editEmail.trim(),
          nombre: editName.trim(),
          rol: roles.find((role) => role.id === editRole)?.key || 'auditor',
          role_id: editRole,
          mall_ids: selectedMallIds
        },
        session.access_token
      );
      setAssignmentModalOpen(false);
      await loadUsers(); // Refresh to show new data
    } catch (e: any) {
      console.error(e);
      alert(`Error actualizando usuario: ${e?.message || e}`);
    } finally {
      setSavingUser(false);
    }
  };

  const handleSendPasswordRecovery = async (user: any) => {
    if (!session?.access_token || !user?.id) return;
    const email = String(user.email || '').trim();
    if (!email) {
      alert('Este usuario no tiene un correo asociado.');
      return;
    }
    if (!window.confirm(`¿Enviar un enlace de recuperación a ${email}?`)) return;

    setSendingRecoveryUserId(user.id);
    try {
      const result = await ApiService.sendUserPasswordRecovery(user.id, session.access_token);
      alert(result?.message || 'Enlace de recuperación enviado.');
    } catch (error: any) {
      alert(error?.message || 'No se pudo enviar el enlace de recuperación.');
    } finally {
      setSendingRecoveryUserId(null);
    }
  };

  const permissionFor = (role: RoleConfig, moduleKey: string): RolePermission => (
    role.permissions.find((permission) => permission.module_key === moduleKey) ||
    { module_key: moduleKey, can_view: false, can_create: false, can_update: false, can_delete: false }
  );

  const togglePermission = (moduleKey: string, action: keyof Omit<RolePermission, 'module_key'>) => {
    setSelectedRole((current) => {
      if (!current) return current;
      const permission = permissionFor(current, moduleKey);
      const next = { ...permission, [action]: !permission[action] };
      if (action !== 'can_view' && next[action]) next.can_view = true;
      return { ...current, permissions: [...current.permissions.filter((item) => item.module_key !== moduleKey), next] };
    });
  };

  const saveRole = async () => {
    if (!selectedRole || !session?.access_token || !selectedRole.nombre.trim() || !selectedRole.key.trim()) return;
    setSavingRole(true);
    try {
      const payload = { key: selectedRole.key, nombre: selectedRole.nombre, descripcion: selectedRole.descripcion || '', permissions: selectedRole.permissions };
      if (selectedRole.id) await ApiService.updateRole(selectedRole.id, payload, session.access_token);
      else await ApiService.createRole(payload, session.access_token);
      setShowRoleEditor(false);
      await loadRoles();
    } catch (e: any) { alert(e?.message || 'No se pudo guardar el rol.'); }
    finally { setSavingRole(false); }
  };

  const removeRole = async (role: RoleConfig) => {
    if (!session?.access_token || role.is_factory || !confirm(`¿Eliminar el rol ${role.nombre}?`)) return;
    try { await ApiService.deleteRole(role.id, session.access_token); await loadRoles(); }
    catch (e: any) { alert(e?.message || 'No se pudo eliminar el rol.'); }
  };

  const restoreFactoryRole = async (role: RoleConfig) => {
    if (!session?.access_token || !role.is_factory || !confirm(`¿Restaurar los permisos de fábrica de ${role.nombre}?`)) return;
    try { await ApiService.restoreFactoryRole(role.id, session.access_token); await loadRoles(); }
    catch (e: any) { alert(e?.message || 'No se pudo restaurar el rol.'); }
  };

  if (!isAdmin && !canAccess('users')) {
    return (
      <div className="bg-amber-50 border border-amber-200 text-amber-800 rounded-xl p-4 text-sm font-medium">
        Solo los usuarios con rol ADMIN pueden gestionar usuarios y roles.
      </div>
    );
  }

  return (
    <div className="space-y-4 animate-in fade-in slide-in-from-bottom-4 duration-500">
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
        <div>
          <h2 className="text-xl font-bold text-slate-800">Gestión de Usuarios</h2>
          <p className="text-slate-500 text-sm">Controle el acceso a los Malls.</p>
        </div>
        <button
          onClick={openCreateModal}
          className="bg-indigo-600 text-white px-5 py-2.5 rounded-xl flex items-center gap-2 hover:bg-indigo-700 transition-all shadow-lg shadow-indigo-200 active:scale-95 font-medium"
        >
          <UserPlus size={18} />
          Nuevo Usuario
        </button>
      </div>

      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-4">
        <div className="flex flex-col lg:flex-row lg:items-end lg:justify-between gap-4">
          <div className="w-full lg:max-w-sm">
            <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1.5">
              Filtrar por Mall
            </label>
            <div className="relative">
              <Building2 size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
              <select
                value={selectedMallFilter}
                onChange={(e) => setSelectedMallFilter(e.target.value)}
                className="w-full pl-10 pr-4 py-2.5 rounded-xl border border-slate-200 bg-white text-sm outline-none focus:ring-2 focus:ring-indigo-500"
              >
                <option value="ALL">Todos los malls</option>
                {availableMalls.map((mall) => (
                  <option key={mall.id} value={mall.id}>{mall.nombre}</option>
                ))}
              </select>
            </div>
          </div>

          <div className="text-xs text-slate-500 font-medium whitespace-nowrap">
            Mostrando {filteredUsers.length} de {users.length} usuarios
          </div>
        </div>
      </div>

      {createModalOpen && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
          <div className="bg-white rounded-xl shadow-2xl w-full max-w-lg p-4">
            <h3 className="text-lg font-bold mb-4">Crear Nuevo Usuario</h3>
            <div className="space-y-3 mb-4">
              <input
                type="email"
                placeholder="Email"
                value={newEmail}
                onChange={(e) => setNewEmail(e.target.value)}
                className="w-full border border-slate-300 rounded-lg px-3 py-2"
              />
              <input
                type="password"
                placeholder="Contraseña (mínimo 8 caracteres)"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                className="w-full border border-slate-300 rounded-lg px-3 py-2"
              />
              <select
                value={newRole}
                onChange={(e) => setNewRole(e.target.value)}
                className="w-full border border-slate-300 rounded-lg px-3 py-2"
              >
                {roles.map((role) => <option key={role.id} value={role.id}>{role.nombre}</option>)}
              </select>
            </div>

            <div className="mb-4">
              <p className="text-sm font-semibold text-slate-700 mb-2">Malls Asignados</p>
              {availableMalls.length === 0 ? (
                <p className="text-slate-500 italic">No hay malls disponibles.</p>
              ) : (
                <div className="space-y-2 max-h-52 overflow-y-auto border p-2 rounded">
                  {availableMalls.map(mall => (
                    <div key={mall.id} className="flex items-center gap-3 p-2 hover:bg-slate-50 rounded cursor-pointer" onClick={() => handleToggleNewMall(mall.id)}>
                      <div className={`w-5 h-5 rounded border flex items-center justify-center ${newMallIds.includes(mall.id) ? 'bg-indigo-600 border-indigo-600' : 'border-slate-300'}`}>
                        {newMallIds.includes(mall.id) && <CheckCircle2 size={14} className="text-white" />}
                      </div>
                      <span className="text-sm font-medium">{mall.nombre}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="flex justify-end gap-2">
              <button onClick={() => setCreateModalOpen(false)} className="px-4 py-2 text-slate-600">Cancelar</button>
              <button
                onClick={handleCreateUser}
                disabled={creatingUser}
                className="px-4 py-2 bg-indigo-600 text-white rounded disabled:opacity-50"
              >
                {creatingUser ? 'Creando...' : 'Crear Usuario'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Assignment Modal */}
      {assignmentModalOpen && selectedUser && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
          <div className="bg-white rounded-xl shadow-2xl w-full max-w-lg p-4">
            <h3 className="text-lg font-bold mb-4">Editar Usuario</h3>
            <div className="space-y-3 mb-4">
              <input
                type="text"
                placeholder="Nombre de perfil"
                value={editName}
                onChange={(e) => setEditName(e.target.value)}
                className="w-full border border-slate-300 rounded-lg px-3 py-2"
              />
              <input
                type="email"
                placeholder="Email"
                value={editEmail}
                onChange={(e) => setEditEmail(e.target.value)}
                className="w-full border border-slate-300 rounded-lg px-3 py-2"
              />
              <select
                value={editRole}
                onChange={(e) => setEditRole(e.target.value)}
                className="w-full border border-slate-300 rounded-lg px-3 py-2"
              >
                {roles.map((role) => <option key={role.id} value={role.id}>{role.nombre}</option>)}
              </select>
            </div>
            <h4 className="text-sm font-semibold text-slate-700 mb-2">Malls Asignados</h4>
            {availableMalls.length === 0 ? (
              <p className="text-slate-500 italic mb-4">No hay Malls disponibles.</p>
            ) : (
              <div className="space-y-2 max-h-60 overflow-y-auto mb-4 border p-2 rounded">
                {availableMalls.map(mall => (
                  <div key={mall.id} className="flex items-center gap-3 p-2 hover:bg-slate-50 rounded cursor-pointer" onClick={() => handleToggleMall(mall.id)}>
                    <div className={`w-5 h-5 rounded border flex items-center justify-center ${selectedMallIds.includes(mall.id) ? 'bg-indigo-600 border-indigo-600' : 'border-slate-300'}`}>
                      {selectedMallIds.includes(mall.id) && <CheckCircle2 size={14} className="text-white" />}
                    </div>
                    <span className="text-sm font-medium">{mall.nombre}</span>
                  </div>
                ))}
              </div>
            )}
            <div className="flex justify-end gap-2">
              <button onClick={() => setAssignmentModalOpen(false)} className="px-4 py-2 text-slate-600">Cancelar</button>
              <button
                onClick={handleSaveAssignments}
                disabled={savingUser}
                className="px-4 py-2 bg-indigo-600 text-white rounded disabled:opacity-50"
              >
                {savingUser ? 'Guardando...' : 'Guardar Cambios'}
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="max-h-[calc(100dvh-19rem)] min-h-[260px] overflow-auto">
          <table className="w-full text-left">
            <thead className="sticky top-0 z-10 bg-slate-50/95 text-slate-500 text-[10px] uppercase font-bold tracking-widest border-b border-slate-100">
              <tr>
                <th className="px-3 py-2.5">Usuario</th>
                <th className="px-3 py-2.5">Rol Principal</th>
                <th className="px-3 py-2.5 text-center">Malls Asignados</th>
                <th className="px-3 py-2.5 text-right">Acciones</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {loading ? (
                <tr><td colSpan={5} className="px-6 py-8 text-center text-slate-400 italic">Cargando usuarios...</td></tr>
              ) : filteredUsers.length > 0 ? filteredUsers.map(user => (
                <tr key={user.id} className="hover:bg-slate-50 transition-colors group">
                  <td className="px-3 py-2.5">
                    <div>
                      <div className="text-sm font-bold text-slate-800">{user.nombre || user.email}</div>
                      {user.nombre && <div className="text-xs text-slate-500">{user.email}</div>}
                      <div className="text-xs text-slate-400">ID: {user.id.slice(0, 8)}...</div>
                    </div>
                  </td>
                  <td className="px-3 py-2.5">
                    <span className={`inline-flex items-center gap-1 px-2 py-1 rounded border text-xs font-bold uppercase ${ROLE_STYLES[normalizeRole(user.rol)]?.color || 'bg-slate-100 text-slate-600 border-slate-100'}`}>
                      {user.role_name || ROLE_STYLES[normalizeRole(user.rol)]?.label || user.rol}
                    </span>
                  </td>
                  <td className="px-3 py-2.5 text-center">
                    <span className="inline-flex items-center justify-center w-8 h-8 rounded-full bg-indigo-50 text-indigo-600 font-bold border border-indigo-100">
                      {user.malls?.length || 0}
                    </span>
                  </td>
                  <td className="px-3 py-2.5 text-right">
                    <div className="flex flex-wrap items-center justify-end gap-2">
                      {canAccess('users', 'update') && (
                        <button
                          onClick={() => handleSendPasswordRecovery(user)}
                          disabled={sendingRecoveryUserId === user.id}
                          className="flex items-center gap-1 text-xs font-bold text-emerald-700 hover:text-emerald-900 disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          <Mail size={14} />
                          {sendingRecoveryUserId === user.id ? 'Enviando...' : 'Enviar recuperación'}
                        </button>
                      )}
                      <button
                        onClick={() => openAssignmentModal(user)}
                        className="flex items-center gap-1 text-xs font-bold text-indigo-600 hover:text-indigo-800"
                      >
                        <UserCog size={14} /> Editar Perfil / Rol
                      </button>
                    </div>
                  </td>
                </tr>
              )) : (
                <tr>
                  <td colSpan={4} className="px-6 py-8 text-center text-slate-400 italic">
                    No se encontraron usuarios para este mall.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <section className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6">
        <div className="flex flex-col sm:flex-row justify-between gap-3 mb-5">
          <div>
            <h3 className="text-lg font-bold text-slate-800">Mantenimiento de Roles</h3>
            <p className="text-sm text-slate-500">Define qué módulos puede ver, agregar, editar o eliminar cada rol.</p>
          </div>
          <button onClick={() => { setSelectedRole({ id: '', key: '', nombre: '', descripcion: '', is_factory: false, permissions: [] }); setShowRoleEditor(true); }} className="inline-flex items-center justify-center gap-2 px-4 py-2 rounded-lg bg-slate-900 text-white text-sm font-bold">
            <Plus size={16} /> Nuevo rol
          </button>
        </div>
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {rolesError && <div className="md:col-span-2 xl:col-span-3 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
            No se pudieron cargar los roles: {rolesError}. Verifica que la API y la migración RBAC estén desplegadas.
          </div>}
          {!rolesError && roles.length === 0 && <div className="md:col-span-2 xl:col-span-3 rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-600">
            Aún no hay roles configurados.
          </div>}
          {roles.map((role) => (
            <div key={role.id} className="border border-slate-200 rounded-xl p-4">
              <div className="flex justify-between gap-3">
                <div><p className="font-bold text-slate-800">{role.nombre}</p><p className="text-xs text-slate-500 mt-1">{role.descripcion || 'Sin descripción'}</p></div>
                {role.is_factory && <span className="h-fit text-[10px] font-bold uppercase rounded-full bg-indigo-50 text-indigo-600 px-2 py-1">Fábrica</span>}
              </div>
              <p className="text-xs text-slate-500 mt-4">{role.permissions.filter((permission) => permission.can_view).length} módulos con acceso</p>
              <div className="mt-3 flex gap-3 text-xs font-bold">
                <button onClick={() => { setSelectedRole({ ...role, permissions: [...role.permissions] }); setShowRoleEditor(true); }} className="text-indigo-600">Configurar</button>
                {role.is_factory && <button onClick={() => restoreFactoryRole(role)} className="text-slate-600">Restaurar</button>}
                {!role.is_factory && <button onClick={() => removeRole(role)} className="inline-flex items-center gap-1 text-rose-600"><Trash2 size={13} /> Eliminar</button>}
              </div>
            </div>
          ))}
        </div>
      </section>

      {showRoleEditor && selectedRole && (
        <div className="fixed inset-0 z-[110] overflow-y-auto bg-black/50 backdrop-blur-sm p-4">
          <div className="mx-auto my-6 w-full max-w-4xl rounded-2xl bg-white shadow-2xl p-6">
            <div className="flex justify-between gap-4 mb-5"><div><h3 className="text-lg font-bold">{selectedRole.id ? 'Configurar rol' : 'Nuevo rol'}</h3><p className="text-sm text-slate-500">Las acciones requieren automáticamente permiso de ver.</p></div><button onClick={() => setShowRoleEditor(false)} className="text-slate-500">Cancelar</button></div>
            <div className="grid sm:grid-cols-2 gap-3 mb-5">
              <input value={selectedRole.nombre} onChange={(e) => setSelectedRole({ ...selectedRole, nombre: e.target.value })} placeholder="Nombre del rol" className="border rounded-lg px-3 py-2" />
              <input value={selectedRole.key} disabled={selectedRole.is_factory} onChange={(e) => setSelectedRole({ ...selectedRole, key: normalizeRole(e.target.value) })} placeholder="identificador_del_rol" className="border rounded-lg px-3 py-2 disabled:bg-slate-100" />
              <input value={selectedRole.descripcion || ''} onChange={(e) => setSelectedRole({ ...selectedRole, descripcion: e.target.value })} placeholder="Descripción" className="border rounded-lg px-3 py-2 sm:col-span-2" />
            </div>
            <div className="overflow-x-auto border rounded-xl">
              <table className="min-w-full text-sm"><thead className="bg-slate-50 text-slate-500 text-xs uppercase"><tr><th className="text-left p-3">Módulo</th>{['Ver', 'Agregar', 'Editar', 'Eliminar'].map((label) => <th key={label} className="p-3 text-center">{label}</th>)}</tr></thead>
                <tbody>{MODULES.map(([key, label]) => { const permission = permissionFor(selectedRole, key); return <tr key={key} className="border-t"><td className="p-3 font-medium text-slate-700">{label}</td>{(['can_view', 'can_create', 'can_update', 'can_delete'] as const).map((action) => <td key={action} className="p-3 text-center"><input type="checkbox" checked={permission[action]} onChange={() => togglePermission(key, action)} /></td>)}</tr>; })}</tbody>
              </table>
            </div>
            <div className="mt-5 flex justify-end gap-3"><button onClick={() => setShowRoleEditor(false)} className="px-4 py-2 text-slate-600">Cancelar</button><button onClick={saveRole} disabled={savingRole} className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-white font-bold disabled:opacity-50"><Save size={16} />{savingRole ? 'Guardando...' : 'Guardar permisos'}</button></div>
          </div>
        </div>
      )}
    </div>
  );
};
