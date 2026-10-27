import { RetailNavigation } from './RetailNavigation';

import React, { useState } from 'react';
import { useAuth } from '../context/AuthProvider';
import { AppTab } from './appTabs';

interface SidebarProps {
  activeTab: AppTab;
  setActiveTab: (tab: AppTab) => void;
}

export const Sidebar: React.FC<SidebarProps> = ({ activeTab, setActiveTab }) => {
  const { changePassword } = useAuth();
  const [showPasswordModal, setShowPasswordModal] = useState(false);
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [savingPassword, setSavingPassword] = useState(false);

  const resetPasswordModal = () => {
    setShowPasswordModal(false);
    setCurrentPassword('');
    setNewPassword('');
    setConfirmPassword('');
    setSavingPassword(false);
  };

  const handlePasswordChange = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!currentPassword || !newPassword || !confirmPassword) {
      alert('Complete todos los campos.');
      return;
    }
    if (newPassword !== confirmPassword) {
      alert('La confirmación no coincide con la nueva contraseña.');
      return;
    }

    setSavingPassword(true);
    try {
      await changePassword(currentPassword, newPassword);
      alert('Contraseña actualizada correctamente.');
      resetPasswordModal();
    } catch (error: any) {
      alert(error?.message || 'No se pudo cambiar la contraseña.');
      setSavingPassword(false);
    }
  };

  return (
    <>
      {showPasswordModal && (
        <div className="fixed inset-0 z-[120] flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
          <div className="w-full max-w-md bg-white rounded-2xl shadow-2xl p-6">
            <h3 className="text-lg font-bold text-slate-800 mb-1">Cambiar Contraseña</h3>
            <p className="text-sm text-slate-500 mb-4">Actualiza tu acceso de forma segura.</p>

            <form onSubmit={handlePasswordChange} className="space-y-3">
              <input
                type="password"
                placeholder="Contraseña actual"
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
                className="w-full border border-slate-300 rounded-lg px-3 py-2 text-slate-800"
                autoComplete="current-password"
                required
              />
              <input
                type="password"
                placeholder="Nueva contraseña (mínimo 8)"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                className="w-full border border-slate-300 rounded-lg px-3 py-2 text-slate-800"
                autoComplete="new-password"
                required
              />
              <input
                type="password"
                placeholder="Confirmar nueva contraseña"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                className="w-full border border-slate-300 rounded-lg px-3 py-2 text-slate-800"
                autoComplete="new-password"
                required
              />

              <div className="pt-2 flex justify-end gap-2">
                <button
                  type="button"
                  onClick={resetPasswordModal}
                  className="px-4 py-2 text-slate-600"
                  disabled={savingPassword}
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  disabled={savingPassword}
                  className="px-4 py-2 rounded-lg bg-indigo-600 text-white disabled:opacity-50"
                >
                  {savingPassword ? 'Guardando...' : 'Guardar'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      <RetailNavigation activeTab={activeTab} setActiveTab={setActiveTab} onPassword={() => setShowPasswordModal(true)} />
    </>
  );
};
