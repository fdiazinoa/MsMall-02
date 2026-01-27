
import React, { useState, useEffect } from 'react';
// Fix: Import User and UserRole from '../types' as they are defined there, while ApiService remains in '../api'
import { ApiService } from '../api';
import { User, UserRole } from '../types';
import { 
  Users, UserPlus, Shield, ShieldCheck, 
  ShieldAlert, Mail, Calendar, MoreVertical,
  Search, CheckCircle2, XCircle
} from 'lucide-react';

const ROLE_STYLES: Record<UserRole, { label: string, color: string, icon: any }> = {
  admin: { label: 'Administrador', color: 'bg-rose-50 text-rose-600 border-rose-100', icon: ShieldCheck },
  auditor: { label: 'Auditor Externo', color: 'bg-indigo-50 text-indigo-600 border-indigo-100', icon: Shield },
  mall_manager: { label: 'Gerente Mall', color: 'bg-amber-50 text-amber-600 border-amber-100', icon: ShieldAlert },
};

export const UserManagement: React.FC = () => {
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [newUserData, setNewUserData] = useState<Partial<User>>({
    nombre: '',
    email: '',
    rol: 'auditor'
  });

  const loadUsers = async () => {
    setLoading(true);
    try {
      const data = await ApiService.getUsers();
      setUsers(data);
    } finally {
      setLoading(false);
    }
  };

  const handleToggleStatus = async (id: string) => {
    await ApiService.toggleUserStatus(id);
    loadUsers();
  };

  const handleCreateUser = async (e: React.FormEvent) => {
    e.preventDefault();
    await ApiService.createUser(newUserData);
    setShowForm(false);
    setNewUserData({ nombre: '', email: '', rol: 'auditor' });
    loadUsers();
  };

  useEffect(() => {
    loadUsers();
  }, []);

  return (
    <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
        <div>
          <h2 className="text-2xl font-bold text-slate-800">Gestión de Usuarios</h2>
          <p className="text-slate-500 text-sm">Controle el acceso y los permisos de la plataforma auditores.</p>
        </div>
        <button 
          onClick={() => setShowForm(!showForm)}
          className="bg-indigo-600 text-white px-5 py-2.5 rounded-xl flex items-center gap-2 hover:bg-indigo-700 transition-all shadow-lg shadow-indigo-200 active:scale-95 font-medium"
        >
          <UserPlus size={18} />
          Nuevo Usuario
        </button>
      </div>

      {showForm && (
        <div className="bg-white p-8 rounded-2xl border border-indigo-100 shadow-xl animate-in zoom-in-95 duration-200 max-w-2xl">
          <div className="flex justify-between items-center mb-6">
            <h3 className="text-lg font-bold text-slate-800">Registrar Usuario</h3>
            <button onClick={() => setShowForm(false)} className="text-slate-400 hover:text-slate-600"><XCircle size={20}/></button>
          </div>
          <form onSubmit={handleCreateUser} className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-bold text-slate-500 uppercase mb-1">Nombre Completo</label>
                <input 
                  type="text" required
                  className="w-full px-4 py-2 rounded-lg border border-slate-200 focus:ring-2 focus:ring-indigo-500 outline-none"
                  value={newUserData.nombre}
                  onChange={e => setNewUserData({...newUserData, nombre: e.target.value})}
                />
              </div>
              <div>
                <label className="block text-xs font-bold text-slate-500 uppercase mb-1">Email Corporativo</label>
                <input 
                  type="email" required
                  className="w-full px-4 py-2 rounded-lg border border-slate-200 focus:ring-2 focus:ring-indigo-500 outline-none"
                  value={newUserData.email}
                  onChange={e => setNewUserData({...newUserData, email: e.target.value})}
                />
              </div>
            </div>
            <div>
              <label className="block text-xs font-bold text-slate-500 uppercase mb-1">Asignar Rol</label>
              <select 
                className="w-full px-4 py-2 rounded-lg border border-slate-200 focus:ring-2 focus:ring-indigo-500 outline-none bg-white"
                value={newUserData.rol}
                onChange={e => setNewUserData({...newUserData, rol: e.target.value as UserRole})}
              >
                <option value="admin">Administrador del Sistema</option>
                <option value="auditor">Auditor de Cuentas</option>
                <option value="mall_manager">Gerente de Centro Comercial</option>
              </select>
            </div>
            <div className="pt-4 flex justify-end gap-3">
              <button type="button" onClick={() => setShowForm(false)} className="px-6 py-2 text-slate-500 font-medium">Cancelar</button>
              <button type="submit" className="bg-indigo-600 text-white px-8 py-2 rounded-lg font-bold shadow-lg shadow-indigo-100">Crear Acceso</button>
            </div>
          </form>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        {/* Roles Summary Cards */}
        {Object.entries(ROLE_STYLES).map(([key, style]) => {
          const Icon = style.icon;
          const count = users.filter(u => u.rol === key).length;
          return (
            <div key={key} className={`p-4 rounded-2xl border ${style.color} bg-opacity-40`}>
              <div className="flex items-center justify-between mb-2">
                <div className={`p-2 rounded-lg bg-white`}>
                  <Icon size={18} />
                </div>
                <span className="text-xl font-bold">{count}</span>
              </div>
              <p className="text-xs font-bold uppercase tracking-wider">{style.label}</p>
            </div>
          );
        })}
        <div className="p-4 rounded-2xl border border-slate-100 bg-white">
          <div className="flex items-center justify-between mb-2">
            <div className="p-2 rounded-lg bg-indigo-50 text-indigo-600">
              <Users size={18} />
            </div>
            <span className="text-xl font-bold text-slate-800">{users.length}</span>
          </div>
          <p className="text-xs font-bold text-slate-400 uppercase tracking-wider">Total Usuarios</p>
        </div>
      </div>

      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="p-4 border-b border-slate-100 bg-slate-50/50 flex items-center justify-between">
          <div className="flex items-center gap-3 flex-1 max-w-md">
            <Search size={18} className="text-slate-400" />
            <input type="text" placeholder="Filtrar usuarios..." className="bg-transparent border-none outline-none text-sm w-full" />
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left">
            <thead className="bg-slate-50/50 text-slate-500 text-[10px] uppercase font-bold tracking-widest border-b border-slate-100">
              <tr>
                <th className="px-6 py-4">Usuario</th>
                <th className="px-6 py-4">Rol de Acceso</th>
                <th className="px-6 py-4">Estado</th>
                <th className="px-6 py-4">Último Acceso</th>
                <th className="px-6 py-4 text-right">Acciones</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {loading ? (
                <tr><td colSpan={5} className="px-6 py-12 text-center text-slate-400 italic">Cargando directorio de usuarios...</td></tr>
              ) : users.map(user => {
                const style = ROLE_STYLES[user.rol];
                return (
                  <tr key={user.id} className="hover:bg-slate-50 transition-colors group">
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-3">
                        <div className="w-9 h-9 rounded-full bg-slate-100 flex items-center justify-center font-bold text-slate-500 border border-slate-200 uppercase text-xs">
                          {user.nombre.split(' ').map(n => n[0]).join('').slice(0, 2)}
                        </div>
                        <div>
                          <div className="text-sm font-bold text-slate-800">{user.nombre}</div>
                          <div className="text-xs text-slate-400 flex items-center gap-1"><Mail size={10}/> {user.email}</div>
                        </div>
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-[10px] font-bold uppercase tracking-tight ${style.color}`}>
                        <style.icon size={12} />
                        {style.label}
                      </span>
                    </td>
                    <td className="px-6 py-4">
                      <button 
                        onClick={() => handleToggleStatus(user.id)}
                        className={`inline-flex items-center gap-1 text-xs font-medium ${user.estado === 'activo' ? 'text-green-600' : 'text-slate-400'}`}
                      >
                        {user.estado === 'activo' ? <CheckCircle2 size={14}/> : <XCircle size={14}/>}
                        {user.estado === 'activo' ? 'Activo' : 'Inactivo'}
                      </button>
                    </td>
                    <td className="px-6 py-4 text-xs text-slate-500">
                      <div className="flex items-center gap-1.5">
                        <Calendar size={12} className="text-slate-400"/>
                        {user.ultimo_acceso || 'Sin actividad'}
                      </div>
                    </td>
                    <td className="px-6 py-4 text-right">
                      <button className="p-2 text-slate-400 hover:text-indigo-600 rounded-lg transition-colors">
                        <MoreVertical size={18} />
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
