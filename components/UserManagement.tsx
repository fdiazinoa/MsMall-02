
import React, { useState, useEffect } from 'react';
import { ApiService } from '../api';
import { useAuth } from '../context/AuthProvider';
import { User, UserRole } from '../types';
import {
  Users, UserPlus, Shield, ShieldCheck,
  ShieldAlert, Mail, Calendar, MoreVertical,
  Search, CheckCircle2, XCircle, Building
} from 'lucide-react';

const ROLE_STYLES: Record<string, { label: string, color: string, icon: any }> = {
  admin: { label: 'Administrador', color: 'bg-rose-50 text-rose-600 border-rose-100', icon: ShieldCheck },
  auditor: { label: 'Auditor Externo', color: 'bg-indigo-50 text-indigo-600 border-indigo-100', icon: Shield },
  mall_manager: { label: 'Gerente Mall', color: 'bg-amber-50 text-amber-600 border-amber-100', icon: ShieldAlert },
};

export const UserManagement: React.FC = () => {
  const { session } = useAuth();
  const [users, setUsers] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  // Mall Assignment State
  const [availableMalls, setAvailableMalls] = useState<any[]>([]);
  const [assignmentModalOpen, setAssignmentModalOpen] = useState(false);
  const [selectedUser, setSelectedUser] = useState<any>(null);
  const [selectedMallIds, setSelectedMallIds] = useState<string[]>([]);

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

  useEffect(() => {
    loadUsers();
    loadMalls();
  }, [session]);

  const openAssignmentModal = (user: any) => {
    setSelectedUser(user);
    // Pre-select existing malls
    const currentIds = user.malls?.map((m: any) => m.mall_id) || [];
    setSelectedMallIds(currentIds);
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
    try {
      await ApiService.assignUserMalls(selectedUser.id, selectedMallIds, selectedUser.rol, session.access_token);
      setAssignmentModalOpen(false);
      loadUsers(); // Refresh to show new counts/data
    } catch (e) {
      alert("Error asignando malls");
    }
  };

  return (
    <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
        <div>
          <h2 className="text-2xl font-bold text-slate-800">Gestión de Usuarios</h2>
          <p className="text-slate-500 text-sm">Controle el acceso a los Malls.</p>
        </div>
        <button
          onClick={() => alert("Función de crear usuario próximamente. Por favor usa Supabase Auth por ahora.")}
          className="bg-indigo-600 text-white px-5 py-2.5 rounded-xl flex items-center gap-2 hover:bg-indigo-700 transition-all shadow-lg shadow-indigo-200 active:scale-95 font-medium"
        >
          <UserPlus size={18} />
          Nuevo Usuario
        </button>
      </div>

      {/* Assignment Modal */}
      {assignmentModalOpen && selectedUser && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
          <div className="bg-white rounded-xl shadow-2xl w-full max-w-md p-6">
            <h3 className="text-lg font-bold mb-4">Asignar Malls a {selectedUser.email}</h3>
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
              <button onClick={handleSaveAssignments} className="px-4 py-2 bg-indigo-600 text-white rounded">Guardar Cambios</button>
            </div>
          </div>
        </div>
      )}

      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left">
            <thead className="bg-slate-50/50 text-slate-500 text-[10px] uppercase font-bold tracking-widest border-b border-slate-100">
              <tr>
                <th className="px-6 py-4">Usuario</th>
                <th className="px-6 py-4">Rol Principal</th>
                <th className="px-6 py-4 text-center">Malls Asignados</th>
                <th className="px-6 py-4 text-right">Acciones</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {loading ? (
                <tr><td colSpan={5} className="px-6 py-12 text-center text-slate-400 italic">Cargando usuarios...</td></tr>
              ) : users.map(user => (
                <tr key={user.id} className="hover:bg-slate-50 transition-colors group">
                  <td className="px-6 py-4">
                    <div>
                      <div className="text-sm font-bold text-slate-800">{user.email}</div>
                      <div className="text-xs text-slate-400">ID: {user.id.slice(0, 8)}...</div>
                    </div>
                  </td>
                  <td className="px-6 py-4">
                    <span className="inline-flex items-center gap-1 px-2 py-1 rounded bg-slate-100 text-xs font-bold uppercase">{user.rol}</span>
                  </td>
                  <td className="px-6 py-4 text-center">
                    <span className="inline-flex items-center justify-center w-8 h-8 rounded-full bg-indigo-50 text-indigo-600 font-bold border border-indigo-100">
                      {user.malls?.length || 0}
                    </span>
                  </td>
                  <td className="px-6 py-4 text-right">
                    <button
                      onClick={() => openAssignmentModal(user)}
                      className="text-indigo-600 hover:text-indigo-800 text-xs font-bold flex items-center gap-1 ml-auto"
                    >
                      <Building size={14} /> Asignar Malls
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
