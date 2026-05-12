import React, { useEffect, useState } from 'react';
import { AlertTriangle, CalendarDays, CheckCircle2, Clock, Loader2, Mail, Save, Send, ShieldCheck } from 'lucide-react';
import { ApiService } from '../api';
import { useAuth } from '../context/AuthProvider';
import { MissingDaysEmailSettings, ResendMessagingStatus } from '../types';

const DEFAULT_TEST_MESSAGE = 'Mensaje de prueba desde MSMALL usando Resend.';
const WEEKDAY_OPTIONS = [
  { id: 0, label: 'Lun' },
  { id: 1, label: 'Mar' },
  { id: 2, label: 'Mie' },
  { id: 3, label: 'Jue' },
  { id: 4, label: 'Vie' },
  { id: 5, label: 'Sab' },
  { id: 6, label: 'Dom' },
];

const defaultSchedule = (mallId = ''): MissingDaysEmailSettings => ({
  mall_id: mallId,
  notification_type: 'missing_days_audit',
  enabled: false,
  weekdays: [],
  send_time: '08:00',
  lookback_days: 7,
  send_only_with_gaps: true,
  cc_emails: [],
});

export const ResendMessagingAdmin: React.FC = () => {
  const { session, isAdmin, user, currentMall } = useAuth();
  const token = session?.access_token || '';
  const [status, setStatus] = useState<ResendMessagingStatus | null>(null);
  const [schedule, setSchedule] = useState<MissingDaysEmailSettings>(defaultSchedule());
  const [ccEmails, setCcEmails] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [savingSchedule, setSavingSchedule] = useState(false);
  const [sendingNow, setSendingNow] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [scheduleError, setScheduleError] = useState<string | null>(null);
  const [flash, setFlash] = useState<{ kind: 'success' | 'error'; message: string } | null>(null);
  const [testTo, setTestTo] = useState(user?.email || '');
  const [subject, setSubject] = useState('Prueba de notificaciones MSMALL');
  const [message, setMessage] = useState(DEFAULT_TEST_MESSAGE);

  useEffect(() => {
    let cancelled = false;
    const mallId = currentMall?.id || '';

    const loadConfig = async () => {
      if (!token) {
        setLoading(false);
        setStatus(null);
        setSchedule(defaultSchedule(mallId));
        setCcEmails('');
        return;
      }
      setLoading(true);
      setError(null);
      setScheduleError(null);
      setSchedule(defaultSchedule(mallId));
      setCcEmails('');

      const statusPromise = ApiService.getResendMessagingStatus(token)
        .then((statusData) => {
          if (!cancelled) setStatus(statusData);
        })
        .catch((e: any) => {
          if (!cancelled) {
            setStatus(null);
            setError(e?.message || 'No se pudo cargar Resend.');
          }
        });

      const schedulePromise = mallId
        ? ApiService.getMissingDaysEmailSettings(mallId, token)
          .then((scheduleData) => {
            if (!cancelled && scheduleData.mall_id === mallId) {
              setSchedule(scheduleData);
              setCcEmails((scheduleData.cc_emails || []).join('\n'));
            }
          })
          .catch((e: any) => {
            if (!cancelled) {
              setSchedule(defaultSchedule(mallId));
              setCcEmails('');
              setScheduleError(e?.message || 'No se pudo cargar la programación de envío.');
            }
          })
        : Promise.resolve();

      try {
        await Promise.allSettled([statusPromise, schedulePromise]);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    loadConfig();
    return () => {
      cancelled = true;
    };
  }, [token, currentMall?.id]);

  const resendConfigured = status?.configured === true;
  const resendMissingKey = status?.configured === false;

  const toggleWeekday = (day: number) => {
    setSchedule((prev) => {
      const selected = new Set(prev.weekdays || []);
      if (selected.has(day)) selected.delete(day);
      else selected.add(day);
      return { ...prev, weekdays: Array.from(selected).sort() };
    });
  };

  const buildSchedulePayload = (): MissingDaysEmailSettings => {
    const parsedCcEmails = ccEmails
      .split(/[\n,;]+/)
      .map((email) => email.trim())
      .filter(Boolean);

    return {
      ...schedule,
      mall_id: currentMall?.id || schedule.mall_id,
      cc_emails: parsedCcEmails,
      lookback_days: Number(schedule.lookback_days) || 7,
    };
  };

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

  const handleSaveSchedule = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token || !currentMall?.id) {
      setFlash({ kind: 'error', message: 'Seleccione un mall antes de guardar la programación.' });
      return;
    }
    if (schedule.enabled && schedule.weekdays.length === 0) {
      setFlash({ kind: 'error', message: 'Seleccione al menos un día de envío.' });
      return;
    }

    setSavingSchedule(true);
    setFlash(null);
    try {
      const saved = await ApiService.saveMissingDaysEmailSettings(
        buildSchedulePayload(),
        token
      );
      setSchedule(saved);
      setCcEmails((saved.cc_emails || []).join('\n'));
      setScheduleError(null);
      setFlash({ kind: 'success', message: 'Programación de auditoría guardada.' });
    } catch (e: any) {
      setFlash({ kind: 'error', message: e?.message || 'No se pudo guardar la programación.' });
    } finally {
      setSavingSchedule(false);
    }
  };

  const handleSendNow = async () => {
    if (!token || !currentMall?.id) {
      setFlash({ kind: 'error', message: 'Seleccione un mall antes de enviar.' });
      return;
    }
    if (!resendConfigured) {
      setFlash({ kind: 'error', message: 'Configure RESEND_API_KEY antes de enviar auditorías.' });
      return;
    }
    if (schedule.enabled && schedule.weekdays.length === 0) {
      setFlash({ kind: 'error', message: 'Seleccione al menos un día de envío o desactive el automático.' });
      return;
    }

    setSendingNow(true);
    setFlash(null);
    try {
      const saved = await ApiService.saveMissingDaysEmailSettings(buildSchedulePayload(), token);
      setSchedule(saved);
      setCcEmails((saved.cc_emails || []).join('\n'));
      setScheduleError(null);

      const result = await ApiService.sendMissingDaysEmailNow(currentMall.id, token);
      const kind = result.failed > 0 ? 'error' : 'success';
      setFlash({
        kind,
        message: `${result.message} Periodo ${result.fecha_inicio} al ${result.fecha_fin}.`,
      });
    } catch (e: any) {
      setFlash({ kind: 'error', message: e?.message || 'No se pudo ejecutar el envío inmediato.' });
    } finally {
      setSendingNow(false);
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
        <div className={`inline-flex items-center gap-2 rounded-xl border px-4 py-2 text-sm font-bold ${resendConfigured ? 'bg-emerald-50 text-emerald-700 border-emerald-200' : 'bg-amber-50 text-amber-700 border-amber-200'}`}>
          {loading ? <Loader2 size={16} className="animate-spin" /> : resendConfigured ? <CheckCircle2 size={16} /> : <AlertTriangle size={16} />}
          {loading ? 'Verificando' : resendConfigured ? 'Activo' : 'Pendiente'}
        </div>
      </div>

      {error && (
        <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm font-medium text-red-700">
          {error}
        </div>
      )}

      {scheduleError && (
        <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm font-medium text-red-700">
          {scheduleError}
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

          {resendMissingKey && !loading && (
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
              disabled={saving || loading || !resendConfigured}
              className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-5 py-2.5 text-sm font-bold text-white shadow-lg shadow-indigo-200 transition-all hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {saving ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
              {saving ? 'Enviando...' : 'Enviar prueba'}
            </button>
          </div>
        </form>
      </div>

      <form onSubmit={handleSaveSchedule} className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6 space-y-5">
        <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-4">
          <div className="flex items-start gap-3">
            <div className="w-10 h-10 rounded-xl bg-amber-50 text-amber-600 flex items-center justify-center">
              <CalendarDays size={20} />
            </div>
            <div>
              <h3 className="font-bold text-slate-800">Programación de días faltantes</h3>
              <p className="text-xs text-slate-500">
                Se enviará una auditoría HTML por local usando el email configurado en la ficha del local.
              </p>
            </div>
          </div>

          <label className="inline-flex items-center gap-3 rounded-xl border border-slate-200 px-4 py-2 text-sm font-bold text-slate-700">
            <input
              type="checkbox"
              checked={schedule.enabled}
              onChange={(e) => setSchedule((prev) => ({ ...prev, enabled: e.target.checked }))}
            />
            Envío automático activo
          </label>
        </div>

        {!currentMall?.id && (
          <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm font-medium text-amber-800">
            Seleccione un mall para guardar esta programación.
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-[1.1fr_0.9fr] gap-5">
          <div className="space-y-3">
            <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-widest">Días de envío</label>
            <div className="grid grid-cols-4 sm:grid-cols-7 gap-2">
              {WEEKDAY_OPTIONS.map((day) => {
                const active = schedule.weekdays.includes(day.id);
                return (
                  <button
                    key={day.id}
                    type="button"
                    onClick={() => toggleWeekday(day.id)}
                    className={`h-11 rounded-xl border text-sm font-bold transition-all ${active ? 'border-indigo-600 bg-indigo-600 text-white shadow-md shadow-indigo-100' : 'border-slate-200 bg-white text-slate-600 hover:bg-slate-50'}`}
                  >
                    {day.label}
                  </button>
                );
              })}
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-widest">Hora</label>
              <div className="relative">
                <input
                  type="time"
                  value={(schedule.send_time || '08:00').slice(0, 5)}
                  onChange={(e) => setSchedule((prev) => ({ ...prev, send_time: e.target.value }))}
                  className="w-full rounded-xl border border-slate-200 px-4 py-3 text-sm outline-none focus:ring-2 focus:ring-indigo-500"
                />
                <Clock size={14} className="absolute right-3 top-3.5 text-slate-400 pointer-events-none" />
              </div>
            </div>

            <div className="space-y-1.5">
              <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-widest">Auditar últimos días</label>
              <input
                type="number"
                min={1}
                max={90}
                value={schedule.lookback_days}
                onChange={(e) => setSchedule((prev) => ({ ...prev, lookback_days: Number(e.target.value) || 7 }))}
                className="w-full rounded-xl border border-slate-200 px-4 py-3 text-sm outline-none focus:ring-2 focus:ring-indigo-500"
              />
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-[1fr_1fr] gap-5">
          <label className="flex items-center gap-3 rounded-xl border border-slate-200 bg-slate-50/60 px-4 py-3 text-sm text-slate-700">
            <input
              type="checkbox"
              checked={schedule.send_only_with_gaps}
              onChange={(e) => setSchedule((prev) => ({ ...prev, send_only_with_gaps: e.target.checked }))}
            />
            Enviar solo cuando existan días faltantes
          </label>

          <div className="space-y-1.5">
            <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-widest">Copias administrativas</label>
            <textarea
              value={ccEmails}
              onChange={(e) => setCcEmails(e.target.value)}
              className="min-h-20 w-full rounded-xl border border-slate-200 px-4 py-3 text-sm outline-none focus:ring-2 focus:ring-indigo-500"
              placeholder="correo1@empresa.com&#10;correo2@empresa.com"
            />
          </div>
        </div>

        <div className="flex flex-col sm:flex-row justify-end gap-3">
          <button
            type="button"
            onClick={handleSendNow}
            disabled={sendingNow || savingSchedule || loading || !currentMall?.id || !resendConfigured}
            className="inline-flex items-center justify-center gap-2 rounded-xl border border-indigo-200 bg-white px-5 py-2.5 text-sm font-bold text-indigo-700 shadow-sm transition-all hover:bg-indigo-50 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {sendingNow ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
            {sendingNow ? 'Enviando ahora...' : 'Enviar ahora'}
          </button>
          <button
            type="submit"
            disabled={savingSchedule || sendingNow || loading || !currentMall?.id}
            className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-5 py-2.5 text-sm font-bold text-white shadow-lg shadow-indigo-200 transition-all hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {savingSchedule ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
            {savingSchedule ? 'Guardando...' : 'Guardar programación'}
          </button>
        </div>
      </form>
    </div>
  );
};
