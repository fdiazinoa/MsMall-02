import React, { useEffect, useState } from 'react';
import { AlertTriangle, CheckCircle2, Loader2, Mail, Send, ShieldCheck } from 'lucide-react';
import { ApiService } from '../api';
import { useAuth } from '../context/AuthProvider';
import { ResendMessagingStatus } from '../types';

const DEFAULT_TEST_MESSAGE = 'Mensaje de prueba desde MSMALL usando Resend.';

export const ResendMessagingAdmin: React.FC = () => {
  const { session, isAdmin, user } = useAuth();
  const token = session?.access_token || '';
  const [status, setStatus] = useState<ResendMessagingStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [flash, setFlash] = useState<{ kind: 'success' | 'error'; message: string } | null>(null);
  const [testTo, setTestTo] = useState(user?.email || '');
  const [subject, setSubject] = useState('Prueba de notificaciones MSMALL');
  const [message, setMessage] = useState(DEFAULT_TEST_MESSAGE);

  useEffect(() => {
    let cancelled = false;

    const loadStatus = async () => {
      if (!token) return;
      setLoading(true);
      setError(null);
      try {
        const data = await ApiService.getResendMessagingStatus(token);
        if (!cancelled) setStatus(data);
      } catch (e: any) {
        if (!cancelled) setError(e?.message || 'No se pudo cargar Resend.');
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    loadStatus();
    return () => {
      cancelled = true;
    };
  }, [token]);

  const handleSendTest = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token || !status) return;
    if (!testTo.trim()) {
      setFlash({ kind: 'error', message: 'Indique un destinatario.' });
      return;
    }

    setSaving(true);
    setFlash(null);
    try {
      const result = await ApiService.sendResendTestMessage(
        {
          to: testTo.trim(),
          subject: subject.trim(),
          message: message.trim()
        },
        token
      );
      setFlash({ kind: 'success', message: result.message || 'Mensaje enviado correctamente.' });
    } catch (e: any) {
      setFlash({ kind: 'error', message: e?.message || 'No se pudo enviar el mensaje.' });
    } finally {
      setSaving(false);
    }
  };

  if (!isAdmin) {
    return (
      <div className="bg-amber-50 border border-amber-200 text-amber-800 rounded-xl p-4 text-sm font-medium">
        Solo los usuarios con rol ADMIN pueden configurar mensajería.
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
        <div>
          <h2 className="text-2xl font-bold text-slate-800">Mensajería Resend</h2>
          <p className="text-slate-500 text-sm">Dominio mercasend.net para notificaciones operativas.</p>
        </div>
        <div className={`inline-flex items-center gap-2 rounded-xl border px-4 py-2 text-sm font-bold ${status?.configured ? 'bg-emerald-50 text-emerald-700 border-emerald-200' : 'bg-amber-50 text-amber-700 border-amber-200'}`}>
          {loading ? <Loader2 size={16} className="animate-spin" /> : status?.configured ? <CheckCircle2 size={16} /> : <AlertTriangle size={16} />}
          {loading ? 'Verificando' : status?.configured ? 'Activo' : 'Pendiente'}
        </div>
      </div>

      {error && (
        <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm font-medium text-red-700">
          {error}
        </div>
      )}

      {flash && (
        <div className={`rounded-xl border px-4 py-3 text-sm font-medium ${flash.kind === 'success' ? 'border-emerald-200 bg-emerald-50 text-emerald-700' : 'border-red-200 bg-red-50 text-red-700'}`}>
          {flash.message}
        </div>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)] gap-6">
        <section className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6 space-y-5">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-indigo-50 text-indigo-600 flex items-center justify-center">
              <Mail size={20} />
            </div>
            <div>
              <h3 className="font-bold text-slate-800">Remitente</h3>
              <p className="text-xs text-slate-500">Resend</p>
            </div>
          </div>

          <dl className="space-y-3 text-sm">
            <div className="flex justify-between gap-4 border-b border-slate-100 pb-3">
              <dt className="text-slate-500">Dominio</dt>
              <dd className="font-mono font-bold text-slate-800">{status?.domain || 'mercasend.net'}</dd>
            </div>
            <div className="flex justify-between gap-4 border-b border-slate-100 pb-3">
              <dt className="text-slate-500">Correo</dt>
              <dd className="font-mono font-bold text-slate-800 break-all">{status?.from_email || 'notificaciones@mercasend.net'}</dd>
            </div>
            <div className="flex justify-between gap-4 border-b border-slate-100 pb-3">
              <dt className="text-slate-500">Nombre</dt>
              <dd className="font-bold text-slate-800">{status?.from_name || 'MercaSend Notificaciones'}</dd>
            </div>
            <div className="flex justify-between gap-4">
              <dt className="text-slate-500">Secreto</dt>
              <dd className="font-mono font-bold text-slate-800">{status?.api_key_env || 'RESEND_API_KEY'}</dd>
            </div>
          </dl>

          {!status?.configured && !loading && (
            <div className="flex gap-3 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
              <ShieldCheck size={18} className="mt-0.5 shrink-0" />
              <span>Configure RESEND_API_KEY en el entorno del backend para activar el envío real.</span>
            </div>
          )}
        </section>

        <form onSubmit={handleSendTest} className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6 space-y-4">
          <div>
            <h3 className="font-bold text-slate-800">Prueba de envío</h3>
            <p className="text-xs text-slate-500">El mensaje saldrá desde notificaciones@mercasend.net.</p>
          </div>

          <div className="space-y-1.5">
            <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-widest">Destinatario</label>
            <input
              type="email"
              value={testTo}
              onChange={(e) => setTestTo(e.target.value)}
              className="w-full rounded-xl border border-slate-200 px-4 py-3 text-sm outline-none focus:ring-2 focus:ring-indigo-500"
              placeholder="correo@empresa.com"
              required
            />
          </div>

          <div className="space-y-1.5">
            <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-widest">Asunto</label>
            <input
              type="text"
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              className="w-full rounded-xl border border-slate-200 px-4 py-3 text-sm outline-none focus:ring-2 focus:ring-indigo-500"
              maxLength={120}
            />
          </div>

          <div className="space-y-1.5">
            <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-widest">Mensaje</label>
            <textarea
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              className="min-h-32 w-full rounded-xl border border-slate-200 px-4 py-3 text-sm outline-none focus:ring-2 focus:ring-indigo-500"
              maxLength={1000}
            />
          </div>

          <div className="flex justify-end">
            <button
              type="submit"
              disabled={saving || loading || !status?.configured}
              className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-5 py-2.5 text-sm font-bold text-white shadow-lg shadow-indigo-200 transition-all hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {saving ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
              {saving ? 'Enviando...' : 'Enviar prueba'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
