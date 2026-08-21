import React, { useState } from 'react';
import { ArrowLeft, CheckCircle2, KeyRound, Mail } from 'lucide-react';

interface ForgotPasswordScreenProps {
  initialEmail?: string;
  onRequest: (email: string) => Promise<void>;
  onBack: () => void;
}

interface ResetPasswordScreenProps {
  hasRecoverySession: boolean;
  onReset: (newPassword: string) => Promise<void>;
  onFinish: () => void;
}

const AuthCard: React.FC<React.PropsWithChildren> = ({ children }) => (
  <div className="flex min-h-screen items-center justify-center bg-slate-900 p-6 text-white">
    <div className="w-full max-w-md rounded-3xl border border-slate-700 bg-slate-800 p-8 shadow-2xl">
      <img
        src="/msmall-icon-192.png"
        alt="MSMALL"
        className="mx-auto mb-6 h-16 w-16 rounded-2xl shadow-lg shadow-indigo-500/20"
      />
      {children}
    </div>
  </div>
);

export const ForgotPasswordScreen: React.FC<ForgotPasswordScreenProps> = ({
  initialEmail = '',
  onRequest,
  onBack,
}) => {
  const [email, setEmail] = useState(initialEmail);
  const [submitting, setSubmitting] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await onRequest(email);
      setSent(true);
    } catch (requestError: any) {
      setError(requestError?.message || 'No se pudo procesar la solicitud. Intenta nuevamente.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AuthCard>
      {sent ? (
        <div className="text-center">
          <CheckCircle2 className="mx-auto mb-4 text-emerald-400" size={44} />
          <h2 className="mb-2 text-2xl font-bold">Revisa tu correo</h2>
          <p className="mb-6 text-sm leading-relaxed text-slate-400">
            Si el correo pertenece a una cuenta de MsMall, recibirás un enlace para crear una nueva contraseña.
          </p>
          <button
            type="button"
            onClick={onBack}
            className="w-full rounded-xl bg-indigo-600 py-3 font-bold transition-colors hover:bg-indigo-700"
          >
            Volver al inicio de sesión
          </button>
        </div>
      ) : (
        <>
          <Mail className="mx-auto mb-4 text-indigo-400" size={38} />
          <h2 className="mb-2 text-center text-2xl font-bold">Recuperar contraseña</h2>
          <p className="mb-6 text-center text-sm text-slate-400">
            Ingresa el correo asociado a tu cuenta y enviaremos las instrucciones.
          </p>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="mb-1.5 ml-1 block text-xs font-bold uppercase text-slate-500">Email</label>
              <input
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="tu@email.com"
                autoComplete="email"
                className="w-full rounded-xl border border-slate-700 bg-slate-900 px-4 py-3 text-white outline-none transition-all placeholder:text-slate-600 focus:ring-2 focus:ring-indigo-500/50"
                required
              />
            </div>
            {error && (
              <div className="rounded-xl border border-red-500/20 bg-red-500/10 p-3 text-xs text-red-400">
                {error}
              </div>
            )}
            <button
              type="submit"
              disabled={submitting}
              className="w-full rounded-xl bg-indigo-600 py-3 font-bold transition-colors hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {submitting ? 'Enviando...' : 'Enviar enlace de recuperación'}
            </button>
            <button
              type="button"
              onClick={onBack}
              className="flex w-full items-center justify-center gap-2 py-2 text-sm text-slate-400 transition-colors hover:text-white"
            >
              <ArrowLeft size={16} /> Volver al inicio de sesión
            </button>
          </form>
        </>
      )}
    </AuthCard>
  );
};

export const ResetPasswordScreen: React.FC<ResetPasswordScreenProps> = ({
  hasRecoverySession,
  onReset,
  onFinish,
}) => {
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [completed, setCompleted] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    if (newPassword.length < 8) {
      setError('La nueva contraseña debe tener al menos 8 caracteres.');
      return;
    }
    if (newPassword !== confirmPassword) {
      setError('La confirmación no coincide con la nueva contraseña.');
      return;
    }

    setSubmitting(true);
    try {
      await onReset(newPassword);
      setCompleted(true);
    } catch (resetError: any) {
      setError(resetError?.message || 'No se pudo actualizar la contraseña.');
    } finally {
      setSubmitting(false);
    }
  };

  if (completed) {
    return (
      <AuthCard>
        <div className="text-center">
          <CheckCircle2 className="mx-auto mb-4 text-emerald-400" size={44} />
          <h2 className="mb-2 text-2xl font-bold">Contraseña actualizada</h2>
          <p className="mb-6 text-sm text-slate-400">Ya puedes iniciar sesión con tu nueva contraseña.</p>
          <button
            type="button"
            onClick={onFinish}
            className="w-full rounded-xl bg-indigo-600 py-3 font-bold transition-colors hover:bg-indigo-700"
          >
            Ir al inicio de sesión
          </button>
        </div>
      </AuthCard>
    );
  }

  if (!hasRecoverySession) {
    return (
      <AuthCard>
        <div className="text-center">
          <KeyRound className="mx-auto mb-4 text-amber-400" size={42} />
          <h2 className="mb-2 text-2xl font-bold">Enlace inválido o expirado</h2>
          <p className="mb-6 text-sm text-slate-400">
            Solicita un nuevo enlace de recuperación desde la pantalla de inicio de sesión.
          </p>
          <button
            type="button"
            onClick={onFinish}
            className="w-full rounded-xl bg-indigo-600 py-3 font-bold transition-colors hover:bg-indigo-700"
          >
            Volver al inicio de sesión
          </button>
        </div>
      </AuthCard>
    );
  }

  return (
    <AuthCard>
      <KeyRound className="mx-auto mb-4 text-indigo-400" size={40} />
      <h2 className="mb-2 text-center text-2xl font-bold">Crear nueva contraseña</h2>
      <p className="mb-6 text-center text-sm text-slate-400">Usa al menos 8 caracteres.</p>
      <form onSubmit={handleSubmit} className="space-y-4">
        <input
          type="password"
          value={newPassword}
          onChange={(event) => setNewPassword(event.target.value)}
          placeholder="Nueva contraseña"
          autoComplete="new-password"
          minLength={8}
          className="w-full rounded-xl border border-slate-700 bg-slate-900 px-4 py-3 text-white outline-none transition-all placeholder:text-slate-600 focus:ring-2 focus:ring-indigo-500/50"
          required
        />
        <input
          type="password"
          value={confirmPassword}
          onChange={(event) => setConfirmPassword(event.target.value)}
          placeholder="Confirmar nueva contraseña"
          autoComplete="new-password"
          minLength={8}
          className="w-full rounded-xl border border-slate-700 bg-slate-900 px-4 py-3 text-white outline-none transition-all placeholder:text-slate-600 focus:ring-2 focus:ring-indigo-500/50"
          required
        />
        {error && (
          <div className="rounded-xl border border-red-500/20 bg-red-500/10 p-3 text-xs text-red-400">
            {error}
          </div>
        )}
        <button
          type="submit"
          disabled={submitting}
          className="w-full rounded-xl bg-indigo-600 py-3 font-bold transition-colors hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {submitting ? 'Actualizando...' : 'Guardar nueva contraseña'}
        </button>
      </form>
    </AuthCard>
  );
};
