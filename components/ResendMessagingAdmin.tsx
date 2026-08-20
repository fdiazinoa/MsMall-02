import React, { useEffect, useState } from 'react';
import { AlertTriangle, Building2, CalendarDays, CheckCircle2, Clock, Loader2, Mail, Save, Send, ShieldCheck, Store } from 'lucide-react';
import { ApiService } from '../api';
import { useAuth } from '../context/AuthProvider';
import { MissingDaysEmailSettings, ResendMessagingStatus, ResendSenderConfigPayload } from '../types';

const DEFAULT_TEST_MESSAGE = 'Mensaje de prueba desde MSMALL usando Resend.';
const DEFAULT_SUBJECT_TEMPLATE = 'Auditoria de dias faltantes: {local_name} ({missing_count} dias)';
const DEFAULT_BODY_TEMPLATE = `Hola {local_name},

Detectamos {missing_count} dias sin ventas registradas para el periodo {fecha_inicio} al {fecha_fin}. Favor revisar la carga de informacion en MSMALL.`;
const DEFAULT_CONSOLIDATED_SUBJECT_TEMPLATE = 'Auditoria consolidada: {mall_name} ({locals_count} locales con faltantes)';
const DEFAULT_CONSOLIDATED_BODY_TEMPLATE = 'Se detectaron {total_missing_days} dias sin ventas en {locals_count} locales del mall {mall_name}, para el periodo {fecha_inicio} al {fecha_fin}.';
type ScheduleMode = MissingDaysEmailSettings['notification_type'];
const WEEKDAY_OPTIONS = [
  { id: 0, label: 'Lun' },
  { id: 1, label: 'Mar' },
  { id: 2, label: 'Mie' },
  { id: 3, label: 'Jue' },
  { id: 4, label: 'Vie' },
  { id: 5, label: 'Sab' },
  { id: 6, label: 'Dom' },
];

const defaultSchedule = (mallId = '', notificationType: ScheduleMode = 'missing_days_audit'): MissingDaysEmailSettings => ({
  mall_id: mallId,
  notification_type: notificationType,
  enabled: false,
  weekdays: [],
  send_time: '08:00',
  lookback_days: 7,
  send_only_with_gaps: true,
  cc_emails: [],
  subject_template: notificationType === 'missing_days_audit_consolidated' ? DEFAULT_CONSOLIDATED_SUBJECT_TEMPLATE : DEFAULT_SUBJECT_TEMPLATE,
  body_template: notificationType === 'missing_days_audit_consolidated' ? DEFAULT_CONSOLIDATED_BODY_TEMPLATE : DEFAULT_BODY_TEMPLATE,
});

const normalizeSchedule = (
  mallId: string,
  saved?: Partial<MissingDaysEmailSettings> | null,
  fallback?: Partial<MissingDaysEmailSettings>
): MissingDaysEmailSettings => {
  const notificationType = saved?.notification_type || fallback?.notification_type || 'missing_days_audit';
  const defaults = defaultSchedule(mallId, notificationType);
  return {
    ...defaults,
    ...(fallback || {}),
    ...(saved || {}),
    mall_id: saved?.mall_id || fallback?.mall_id || mallId,
    weekdays: saved?.weekdays || fallback?.weekdays || [],
    send_time: saved?.send_time || fallback?.send_time || '08:00',
    subject_template: saved?.subject_template || fallback?.subject_template || defaults.subject_template,
    body_template: saved?.body_template || fallback?.body_template || defaults.body_template,
    cc_emails: saved?.cc_emails || fallback?.cc_emails || [],
  };
};

export const ResendMessagingAdmin: React.FC = () => {
  const { session, isAdmin, user, currentMall } = useAuth();
  const token = session?.access_token || '';
  const [status, setStatus] = useState<ResendMessagingStatus | null>(null);
  const [activeScheduleMode, setActiveScheduleMode] = useState<ScheduleMode>('missing_days_audit');
  const [schedules, setSchedules] = useState<Record<ScheduleMode, MissingDaysEmailSettings>>({
    missing_days_audit: defaultSchedule(),
    missing_days_audit_consolidated: defaultSchedule('', 'missing_days_audit_consolidated'),
  });
  const [ccEmailsByMode, setCcEmailsByMode] = useState<Record<ScheduleMode, string>>({
    missing_days_audit: '',
    missing_days_audit_consolidated: '',
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [savingSender, setSavingSender] = useState(false);
  const [savingSchedule, setSavingSchedule] = useState(false);
  const [sendingNow, setSendingNow] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [scheduleError, setScheduleError] = useState<string | null>(null);
  const [flash, setFlash] = useState<{ kind: 'success' | 'error'; message: string } | null>(null);
  const [testTo, setTestTo] = useState(user?.email || '');
  const [subject, setSubject] = useState('Prueba de notificaciones MSMALL');
  const [message, setMessage] = useState(DEFAULT_TEST_MESSAGE);
  const [senderDraft, setSenderDraft] = useState<ResendSenderConfigPayload>({
    from_email: 'notificaciones@mercasend.net',
    from_name: 'MercaSend Notificaciones',
  });
  const schedule = schedules[activeScheduleMode];
  const scheduleDefaults = defaultSchedule(currentMall?.id || schedule.mall_id, activeScheduleMode);
  const ccEmails = ccEmailsByMode[activeScheduleMode];
  const setSchedule = (updater: React.SetStateAction<MissingDaysEmailSettings>) => {
    setSchedules((prev) => ({
      ...prev,
      [activeScheduleMode]: typeof updater === 'function' ? updater(prev[activeScheduleMode]) : updater,
    }));
  };
  const setCcEmails = (value: string) => {
    setCcEmailsByMode((prev) => ({ ...prev, [activeScheduleMode]: value }));
  };

  useEffect(() => {
    let cancelled = false;
    const mallId = currentMall?.id || '';

    const loadConfig = async () => {
      if (!token) {
        setLoading(false);
        setStatus(null);
        setSchedules({
          missing_days_audit: defaultSchedule(mallId),
          missing_days_audit_consolidated: defaultSchedule(mallId, 'missing_days_audit_consolidated'),
        });
        setCcEmailsByMode({ missing_days_audit: '', missing_days_audit_consolidated: '' });
        return;
      }
      setLoading(true);
      setError(null);
      setScheduleError(null);
      setSchedules({
        missing_days_audit: defaultSchedule(mallId),
        missing_days_audit_consolidated: defaultSchedule(mallId, 'missing_days_audit_consolidated'),
      });
      setCcEmailsByMode({ missing_days_audit: '', missing_days_audit_consolidated: '' });

      const statusPromise = ApiService.getResendMessagingStatus(token)
        .then((statusData) => {
          if (!cancelled) {
            setStatus(statusData);
            setSenderDraft({
              from_email: statusData.from_email || 'notificaciones@mercasend.net',
              from_name: statusData.from_name || 'MercaSend Notificaciones',
            });
          }
        })
        .catch((e: any) => {
          if (!cancelled) {
            setStatus(null);
            setError(e?.message || 'No se pudo cargar Resend.');
          }
        });

      const schedulePromise = mallId
        ? Promise.allSettled([
          ApiService.getMissingDaysEmailSettings(mallId, token, 'missing_days_audit'),
          ApiService.getMissingDaysEmailSettings(mallId, token, 'missing_days_audit_consolidated'),
        ])
          .then(([localResult, consolidatedResult]) => {
            if (cancelled) return;
            const localSchedule = localResult.status === 'fulfilled'
              ? localResult.value
              : defaultSchedule(mallId, 'missing_days_audit');
            const consolidatedSchedule = consolidatedResult.status === 'fulfilled'
              ? consolidatedResult.value
              : defaultSchedule(mallId, 'missing_days_audit_consolidated');
            setSchedules({
              missing_days_audit: normalizeSchedule(mallId, localSchedule),
              missing_days_audit_consolidated: normalizeSchedule(mallId, consolidatedSchedule),
            });
            setCcEmailsByMode({
              missing_days_audit: (localSchedule.cc_emails || []).join('\n'),
              missing_days_audit_consolidated: (consolidatedSchedule.cc_emails || []).join('\n'),
            });
            const failedResult = [localResult, consolidatedResult].find((result) => result.status === 'rejected');
            if (failedResult?.status === 'rejected') {
              const reason = failedResult.reason as any;
              setScheduleError(reason?.message || 'No se pudo cargar una de las programaciones de envío.');
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
    const defaults = defaultSchedule(currentMall?.id || schedule.mall_id, schedule.notification_type);
    const parsedCcEmails = ccEmails
      .split(/[\n,;]+/)
      .map((email) => email.trim())
      .filter(Boolean);

    return {
      ...schedule,
      mall_id: currentMall?.id || schedule.mall_id,
      cc_emails: parsedCcEmails,
      lookback_days: Number(schedule.lookback_days) || 7,
      subject_template: (schedule.subject_template || defaults.subject_template || '').trim(),
      body_template: (schedule.body_template || defaults.body_template || '').trim(),
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

  const handleSaveSender = async () => {
    if (!token) {
      setFlash({ kind: 'error', message: 'Sesión no disponible para guardar el remitente.' });
      return;
    }
    const payload = {
      from_email: senderDraft.from_email.trim().toLowerCase(),
      from_name: senderDraft.from_name.trim(),
    };
    if (!payload.from_email || !payload.from_name) {
      setFlash({ kind: 'error', message: 'Correo y nombre del remitente son requeridos.' });
      return;
    }

    setSavingSender(true);
    setFlash(null);
    try {
      const saved = await ApiService.saveResendSenderConfig(payload, token);
      setStatus(saved);
      setSenderDraft({
        from_email: saved.from_email || payload.from_email,
        from_name: saved.from_name || payload.from_name,
      });
      setFlash({ kind: 'success', message: 'Remitente de Resend guardado.' });
    } catch (e: any) {
      setFlash({ kind: 'error', message: e?.message || 'No se pudo guardar el remitente.' });
    } finally {
      setSavingSender(false);
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
    const payload = buildSchedulePayload();
    if (schedule.notification_type === 'missing_days_audit_consolidated' && schedule.enabled && payload.cc_emails.length === 0) {
      setFlash({ kind: 'error', message: 'Agregue al menos un correo administrativo para activar el consolidado.' });
      return;
    }

    setSavingSchedule(true);
    setFlash(null);
    try {
      const saved = await ApiService.saveMissingDaysEmailSettings(payload, token);
      const normalized = normalizeSchedule(currentMall.id, saved, payload);
      setSchedule(normalized);
      setCcEmails((normalized.cc_emails || []).join('\n'));
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
    const payload = buildSchedulePayload();
    if (schedule.notification_type === 'missing_days_audit_consolidated' && payload.cc_emails.length === 0) {
      setFlash({ kind: 'error', message: 'Agregue al menos un correo administrativo antes de enviar el consolidado.' });
      return;
    }

    setSendingNow(true);
    setFlash(null);
    try {
      const saved = await ApiService.saveMissingDaysEmailSettings(payload, token);
      const normalized = normalizeSchedule(currentMall.id, saved, payload);
      setSchedule(normalized);
      setCcEmails((normalized.cc_emails || []).join('\n'));
      setScheduleError(null);

      const result = await ApiService.sendMissingDaysEmailNow(currentMall.id, token, schedule.notification_type);
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

          <div className="space-y-4 text-sm">
            <div className="flex justify-between gap-4 border-b border-slate-100 pb-3">
              <span className="text-slate-500">Dominio</span>
              <span className="font-mono font-bold text-slate-800">{status?.domain || 'mercasend.net'}</span>
            </div>

            <div className="space-y-1.5">
              <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-widest">Correo remitente</label>
              <input
                type="email"
                value={senderDraft.from_email}
                onChange={(e) => setSenderDraft((prev) => ({ ...prev, from_email: e.target.value }))}
                className="w-full rounded-xl border border-slate-200 px-4 py-3 font-mono text-sm outline-none focus:ring-2 focus:ring-indigo-500"
                placeholder="notificaciones@mercasend.net"
              />
            </div>

            <div className="space-y-1.5">
              <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-widest">Nombre remitente</label>
              <input
                type="text"
                value={senderDraft.from_name}
                onChange={(e) => setSenderDraft((prev) => ({ ...prev, from_name: e.target.value }))}
                className="w-full rounded-xl border border-slate-200 px-4 py-3 text-sm font-bold text-slate-800 outline-none focus:ring-2 focus:ring-indigo-500"
                placeholder="MercaSend Notificaciones"
                maxLength={80}
              />
            </div>

            <div className="flex justify-between gap-4 border-t border-slate-100 pt-3">
              <span className="text-slate-500">Secreto</span>
              <span className="font-mono font-bold text-slate-800">{status?.api_key_env || 'RESEND_API_KEY'}</span>
            </div>
          </div>

          <div className="flex justify-end">
            <button
              type="button"
              onClick={handleSaveSender}
              disabled={savingSender || loading}
              className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-bold text-slate-700 shadow-sm transition-all hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {savingSender ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
              {savingSender ? 'Guardando...' : 'Guardar remitente'}
            </button>
          </div>

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
            <p className="text-xs text-slate-500">El mensaje saldrá desde {status?.from_email || senderDraft.from_email}.</p>
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
        <div className="inline-flex w-full sm:w-auto rounded-lg border border-slate-200 bg-slate-50 p-1" role="tablist" aria-label="Modalidad de envío">
          <button
            type="button"
            role="tab"
            aria-selected={activeScheduleMode === 'missing_days_audit'}
            onClick={() => setActiveScheduleMode('missing_days_audit')}
            className={`inline-flex flex-1 sm:flex-none items-center justify-center gap-2 rounded-md px-4 py-2 text-sm font-bold transition-colors ${activeScheduleMode === 'missing_days_audit' ? 'bg-white text-indigo-700 shadow-sm' : 'text-slate-600 hover:text-slate-900'}`}
          >
            <Store size={16} />
            Por local
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeScheduleMode === 'missing_days_audit_consolidated'}
            onClick={() => setActiveScheduleMode('missing_days_audit_consolidated')}
            className={`inline-flex flex-1 sm:flex-none items-center justify-center gap-2 rounded-md px-4 py-2 text-sm font-bold transition-colors ${activeScheduleMode === 'missing_days_audit_consolidated' ? 'bg-white text-indigo-700 shadow-sm' : 'text-slate-600 hover:text-slate-900'}`}
          >
            <Building2 size={16} />
            Consolidar locales
          </button>
        </div>

        <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-4">
          <div className="flex items-start gap-3">
            <div className="w-10 h-10 rounded-xl bg-amber-50 text-amber-600 flex items-center justify-center">
              <CalendarDays size={20} />
            </div>
            <div>
              <h3 className="font-bold text-slate-800">Programación de días faltantes</h3>
              <p className="text-xs text-slate-500">
                {activeScheduleMode === 'missing_days_audit_consolidated'
                  ? 'Se enviará un solo correo por mall exclusivamente a los correos administrativos configurados aquí.'
                  : 'Se enviará una auditoría HTML por local usando el email configurado en la ficha del local.'}
              </p>
            </div>
          </div>

          <label className="inline-flex items-center gap-3 rounded-xl border border-slate-200 px-4 py-2 text-sm font-bold text-slate-700">
            <input
              type="checkbox"
              checked={schedule.enabled}
              onChange={(e) => setSchedule((prev) => ({ ...prev, enabled: e.target.checked }))}
            />
            {activeScheduleMode === 'missing_days_audit_consolidated' ? 'Consolidar locales automáticamente' : 'Envío automático activo'}
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
            {activeScheduleMode === 'missing_days_audit_consolidated' && (
              <p className="text-xs text-slate-500">El primer correo será el destinatario y los demás recibirán copia. No se usarán correos de locales.</p>
            )}
          </div>
        </div>

        <div className="rounded-xl border border-slate-200 bg-slate-50/60 p-4 space-y-4">
          <div>
            <h4 className="font-bold text-slate-800">Plantilla del correo</h4>
            <p className="text-xs text-slate-500">
              Variables disponibles: {'{mall_name}'}, {'{fecha_inicio}'}, {'{fecha_fin}'}, {'{report_url}'}
              {activeScheduleMode === 'missing_days_audit_consolidated'
                ? <>, {'{locals_count}'}, {'{total_missing_days}'}.</>
                : <>, {'{local_name}'}, {'{missing_count}'}.</>}
            </p>
          </div>

          <div className="space-y-1.5">
            <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-widest">Asunto automático</label>
            <input
              type="text"
              value={schedule.subject_template || scheduleDefaults.subject_template}
              onChange={(e) => setSchedule((prev) => ({ ...prev, subject_template: e.target.value }))}
              className="w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm outline-none focus:ring-2 focus:ring-indigo-500"
              maxLength={160}
            />
          </div>

          <div className="space-y-1.5">
            <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-widest">Cuerpo automático</label>
            <textarea
              value={schedule.body_template || scheduleDefaults.body_template}
              onChange={(e) => setSchedule((prev) => ({ ...prev, body_template: e.target.value }))}
              className="min-h-32 w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm outline-none focus:ring-2 focus:ring-indigo-500"
              maxLength={2000}
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
