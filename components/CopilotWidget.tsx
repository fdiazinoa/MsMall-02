import React, { useEffect, useMemo, useRef, useState } from 'react';
import { AlertCircle, Bot, Loader2, MessageCircle, RefreshCw, Send, Settings, Sparkles, X } from 'lucide-react';
import { ApiService } from '../api';
import { useAuth } from '../context/AuthProvider';
import { CopilotChatMessage, CopilotSettings } from '../types';

interface CopilotWidgetProps {
  onOpenSettings?: () => void;
}

const SUGGESTED_PROMPTS = [
  'Resumen del monitor de carga',
  '¿Qué locales tienen días faltantes?',
  '¿Qué locales tienen fallas recientes?',
  '¿Cómo está el monitor de conexiones?',
];

export const CopilotWidget: React.FC<CopilotWidgetProps> = ({ onOpenSettings }) => {
  const { session, currentMall, isAdmin } = useAuth();
  const token = session?.access_token || '';
  const [open, setOpen] = useState(false);
  const [status, setStatus] = useState<CopilotSettings | null>(null);
  const [messages, setMessages] = useState<CopilotChatMessage[]>([]);
  const [draft, setDraft] = useState('');
  const [loadingStatus, setLoadingStatus] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  const mallId = currentMall?.id || '';
  const canAsk = Boolean(status?.available && mallId && token && !sending);

  const providerName = useMemo(() => {
    if (!status?.provider) return 'Copilot';
    return status.provider === 'gemini' ? 'Gemini' : 'ChatGPT';
  }, [status?.provider]);

  const loadStatus = async () => {
    if (!token || !mallId) {
      setStatus(null);
      return;
    }

    setLoadingStatus(true);
    setError(null);
    try {
      const data = await ApiService.getCopilotStatus(mallId, token);
      setStatus(data);
    } catch (e: any) {
      setStatus(null);
      setError(e?.message || 'No se pudo consultar Copilot.');
    } finally {
      setLoadingStatus(false);
    }
  };

  useEffect(() => {
    if (open) loadStatus();
  }, [open, mallId, token]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages, sending]);

  const askCopilot = async (text: string) => {
    const question = text.trim();
    if (!question || !token || !mallId || sending) return;

    const nextMessages: CopilotChatMessage[] = [...messages, { role: 'user', content: question }];
    setMessages(nextMessages);
    setDraft('');
    setSending(true);
    setError(null);

    try {
      const response = await ApiService.sendCopilotMessage(mallId, question, messages, token);
      setMessages([...nextMessages, { role: 'assistant', content: response.answer }]);
      if (!status) {
        setStatus({
          enabled: true,
          available: true,
          provider: response.provider,
          model: response.model,
          api_key_configured: true,
        });
      }
    } catch (e: any) {
      const message = e?.message || 'Copilot no pudo responder.';
      setError(message);
      setMessages([...nextMessages, { role: 'assistant', content: message }]);
    } finally {
      setSending(false);
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!canAsk) return;
    askCopilot(draft);
  };

  const openSettings = () => {
    setOpen(false);
    onOpenSettings?.();
  };

  if (!session) return null;

  return (
    <>
      {open && (
        <section className="fixed right-3 bottom-20 z-[90] w-[calc(100vw-1.5rem)] sm:right-6 sm:bottom-24 sm:w-[420px]">
          <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl shadow-slate-900/20">
            <div className="flex items-center justify-between gap-3 border-b border-slate-200 bg-slate-900 px-4 py-3 text-white">
              <div className="flex items-center gap-3 min-w-0">
                <div className="w-9 h-9 rounded-xl bg-white/10 flex items-center justify-center">
                  <Bot size={19} />
                </div>
                <div className="min-w-0">
                  <h3 className="text-sm font-bold leading-tight">Copilot MsMall</h3>
                  <p className="text-[11px] text-slate-300 truncate">
                    {currentMall?.nombre || 'Mall seleccionado'} · {providerName}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-1">
                <button
                  type="button"
                  onClick={loadStatus}
                  className="p-2 rounded-lg hover:bg-white/10 transition-colors"
                  title="Actualizar estado"
                >
                  <RefreshCw size={15} className={loadingStatus ? 'animate-spin' : ''} />
                </button>
                {isAdmin && (
                  <button
                    type="button"
                    onClick={openSettings}
                    className="p-2 rounded-lg hover:bg-white/10 transition-colors"
                    title="Configurar Copilot"
                  >
                    <Settings size={15} />
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => setOpen(false)}
                  className="p-2 rounded-lg hover:bg-white/10 transition-colors"
                  title="Cerrar"
                >
                  <X size={16} />
                </button>
              </div>
            </div>

            <div ref={scrollRef} className="h-[430px] max-h-[58vh] overflow-y-auto bg-slate-50 p-4 space-y-3">
              {loadingStatus && messages.length === 0 && (
                <div className="flex items-center gap-2 text-sm text-slate-500">
                  <Loader2 size={16} className="animate-spin" />
                  Preparando contexto de MsMall...
                </div>
              )}

              {!loadingStatus && !status?.available && (
                <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
                  <div className="flex items-start gap-2">
                    <AlertCircle size={18} className="mt-0.5 shrink-0" />
                    <div>
                      <p className="font-bold">Copilot no está listo.</p>
                      <p className="mt-1 text-amber-700">
                        {status?.enabled === false
                          ? 'Está desactivado en configuración.'
                          : status?.api_key_configured === false
                            ? 'Falta configurar la API key.'
                            : error || 'No se pudo confirmar el estado.'}
                      </p>
                      {isAdmin && (
                        <button
                          type="button"
                          onClick={openSettings}
                          className="mt-3 inline-flex items-center gap-2 rounded-lg bg-amber-900 px-3 py-2 text-xs font-bold text-white hover:bg-amber-800"
                        >
                          <Settings size={14} />
                          Abrir configuración
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              )}

              {messages.length === 0 && status?.available && (
                <div className="rounded-xl border border-slate-200 bg-white p-4">
                  <div className="flex items-center gap-2 text-slate-900 font-bold text-sm">
                    <Sparkles size={16} className="text-indigo-500" />
                    Preguntas rápidas
                  </div>
                  <div className="mt-3 grid grid-cols-1 gap-2">
                    {SUGGESTED_PROMPTS.map((prompt) => (
                      <button
                        key={prompt}
                        type="button"
                        onClick={() => askCopilot(prompt)}
                        className="text-left rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-semibold text-slate-700 hover:border-indigo-200 hover:bg-indigo-50 hover:text-indigo-700 transition-colors"
                      >
                        {prompt}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {messages.map((message, index) => (
                <div
                  key={`${message.role}-${index}`}
                  className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
                >
                  <div className={`max-w-[86%] rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed shadow-sm ${message.role === 'user'
                    ? 'bg-slate-900 text-white rounded-br-md'
                    : 'bg-white text-slate-700 border border-slate-200 rounded-bl-md'
                    }`}>
                    {message.content}
                  </div>
                </div>
              ))}

              {sending && (
                <div className="flex justify-start">
                  <div className="inline-flex items-center gap-2 rounded-2xl rounded-bl-md border border-slate-200 bg-white px-3.5 py-2.5 text-sm text-slate-500 shadow-sm">
                    <Loader2 size={15} className="animate-spin" />
                    Consultando MsMall...
                  </div>
                </div>
              )}
            </div>

            <form onSubmit={handleSubmit} className="border-t border-slate-200 bg-white p-3">
              <div className="flex items-end gap-2">
                <textarea
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  placeholder="Pregunta sobre cargas, locales o días de información..."
                  rows={2}
                  disabled={!status?.available || sending}
                  className="min-h-[44px] max-h-28 flex-1 resize-none rounded-xl border border-slate-300 px-3 py-2 text-sm text-slate-800 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 disabled:bg-slate-100 disabled:text-slate-400"
                />
                <button
                  type="submit"
                  disabled={!canAsk || !draft.trim()}
                  className="h-11 w-11 shrink-0 rounded-xl bg-slate-900 text-white flex items-center justify-center hover:bg-slate-800 disabled:opacity-40 disabled:cursor-not-allowed"
                  title="Enviar"
                >
                  <Send size={17} />
                </button>
              </div>
            </form>
          </div>
        </section>
      )}

      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="fixed bottom-5 right-5 z-[80] h-14 w-14 rounded-2xl bg-slate-900 text-white shadow-2xl shadow-slate-900/30 flex items-center justify-center hover:-translate-y-0.5 hover:bg-indigo-600 transition-all"
        title="Abrir Copilot MsMall"
      >
        {open ? <X size={22} /> : <MessageCircle size={23} />}
      </button>
    </>
  );
};
