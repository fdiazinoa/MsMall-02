import React, { useEffect, useState } from 'react';
import { AlertCircle, Bot, CheckCircle2, KeyRound, Loader2, Save, ShieldCheck, Trash2 } from 'lucide-react';
import { ApiService } from '../api';
import { useAuth } from '../context/AuthProvider';
import { CopilotProvider, CopilotSettings as CopilotSettingsType } from '../types';

const DEFAULT_MODEL_BY_PROVIDER: Record<CopilotProvider, string> = {
  openai: 'gpt-4o-mini',
  gemini: 'gemini-1.5-flash',
};

const providerLabel = (provider: CopilotProvider) => (
  provider === 'gemini' ? 'Gemini' : 'ChatGPT / OpenAI'
);

export const CopilotSettings: React.FC = () => {
  const { session, isAdmin } = useAuth();
  const token = session?.access_token || '';
  const [settings, setSettings] = useState<CopilotSettingsType | null>(null);
  const [enabled, setEnabled] = useState(false);
  const [provider, setProvider] = useState<CopilotProvider>('openai');
  const [model, setModel] = useState(DEFAULT_MODEL_BY_PROVIDER.openai);
  const [apiKey, setApiKey] = useState('');
  const [clearApiKey, setClearApiKey] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [flash, setFlash] = useState<{ kind: 'success' | 'error'; message: string } | null>(null);

  useEffect(() => {
    let cancelled = false;

    const loadSettings = async () => {
      if (!token || !isAdmin) {
        setLoading(false);
        return;
      }

      setLoading(true);
      setFlash(null);
      try {
        const data = await ApiService.getCopilotSettings(token);
        if (cancelled) return;
        setSettings(data);
        setEnabled(data.enabled);
        setProvider(data.provider);
        setModel(data.model || DEFAULT_MODEL_BY_PROVIDER[data.provider]);
        setApiKey('');
        setClearApiKey(false);
      } catch (error: any) {
        if (!cancelled) {
          setFlash({ kind: 'error', message: error?.message || 'No se pudo cargar Copilot.' });
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    loadSettings();
    return () => {
      cancelled = true;
    };
  }, [token, isAdmin]);

  const handleProviderChange = (value: CopilotProvider) => {
    setProvider(value);
    setModel(DEFAULT_MODEL_BY_PROVIDER[value]);
    setApiKey('');
    setClearApiKey(false);
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token) return;

    setSaving(true);
    setFlash(null);
    try {
      const saved = await ApiService.saveCopilotSettings(
        {
          enabled,
          provider,
          model: model.trim() || DEFAULT_MODEL_BY_PROVIDER[provider],
          api_key: apiKey.trim() || undefined,
          clear_api_key: clearApiKey,
        },
        token
      );
      setSettings(saved);
      setEnabled(saved.enabled);
      setProvider(saved.provider);
      setModel(saved.model || DEFAULT_MODEL_BY_PROVIDER[saved.provider]);
      setApiKey('');
      setClearApiKey(false);
      setFlash({ kind: 'success', message: 'Configuración de Copilot guardada.' });
    } catch (error: any) {
      setFlash({ kind: 'error', message: error?.message || 'No se pudo guardar Copilot.' });
    } finally {
      setSaving(false);
    }
  };

  if (!isAdmin) {
    return (
      <div className="bg-white border border-slate-200 rounded-2xl p-8 shadow-sm">
        <div className="flex items-center gap-3 text-slate-800">
          <ShieldCheck className="w-6 h-6 text-amber-500" />
          <h2 className="text-xl font-bold">Copilot MsMall</h2>
        </div>
        <p className="mt-3 text-sm text-slate-500">
          Solo usuarios ADMIN pueden administrar la API key del Copilot.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <div className="w-11 h-11 rounded-2xl bg-slate-900 text-white flex items-center justify-center shadow-lg shadow-slate-900/15">
              <Bot size={22} />
            </div>
            <div>
              <h2 className="text-2xl font-bold text-slate-900">Copilot MsMall</h2>
              <p className="text-sm text-slate-500">Proveedor, modelo y clave privada del asistente operativo.</p>
            </div>
          </div>
        </div>

        <div className={`inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-bold ${settings?.available
          ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
          : 'bg-amber-50 text-amber-700 border-amber-200'
          }`}>
          {settings?.available ? <CheckCircle2 size={14} /> : <AlertCircle size={14} />}
          {settings?.available ? 'Disponible' : 'Pendiente'}
        </div>
      </div>

      {flash && (
        <div className={`rounded-xl border px-4 py-3 text-sm font-semibold ${flash.kind === 'success'
          ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
          : 'border-red-200 bg-red-50 text-red-700'
          }`}>
          {flash.message}
        </div>
      )}

      <form onSubmit={handleSave} className="bg-white border border-slate-200 rounded-2xl shadow-sm overflow-hidden">
        <div className="p-6 border-b border-slate-100">
          <div className="flex items-center justify-between gap-4">
            <div>
              <h3 className="text-lg font-bold text-slate-900">Configuración</h3>
              <p className="text-sm text-slate-500">La clave se guarda en backend y nunca se expone al navegador.</p>
            </div>
            <label className="inline-flex items-center gap-2 cursor-pointer">
              <span className="text-sm font-bold text-slate-700">Activo</span>
              <input
                type="checkbox"
                checked={enabled}
                onChange={(e) => setEnabled(e.target.checked)}
                className="h-5 w-5 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
              />
            </label>
          </div>
        </div>

        {loading ? (
          <div className="p-10 flex items-center justify-center gap-3 text-slate-500">
            <Loader2 size={18} className="animate-spin" />
            Cargando configuración...
          </div>
        ) : (
          <div className="p-6 grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="space-y-2">
              <label className="block text-xs font-bold uppercase tracking-wide text-slate-500">Proveedor</label>
              <select
                value={provider}
                onChange={(e) => handleProviderChange(e.target.value as CopilotProvider)}
                className="w-full rounded-xl border border-slate-300 bg-white px-3 py-2.5 text-sm font-semibold text-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-500/20"
              >
                <option value="openai">ChatGPT / OpenAI</option>
                <option value="gemini">Gemini</option>
              </select>
            </div>

            <div className="space-y-2">
              <label className="block text-xs font-bold uppercase tracking-wide text-slate-500">Modelo</label>
              <input
                value={model}
                onChange={(e) => setModel(e.target.value)}
                placeholder={DEFAULT_MODEL_BY_PROVIDER[provider]}
                className="w-full rounded-xl border border-slate-300 px-3 py-2.5 text-sm font-semibold text-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-500/20"
              />
            </div>

            <div className="lg:col-span-2 space-y-2">
              <label className="block text-xs font-bold uppercase tracking-wide text-slate-500">
                API key de {providerLabel(provider)}
              </label>
              <div className="relative">
                <KeyRound size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                <input
                  type="password"
                  value={apiKey}
                  onChange={(e) => {
                    setApiKey(e.target.value);
                    if (e.target.value.trim()) setClearApiKey(false);
                  }}
                  placeholder={settings?.api_key_configured ? `Actual: ${settings.api_key_masked}` : 'Pegar nueva API key'}
                  className="w-full rounded-xl border border-slate-300 pl-10 pr-3 py-2.5 text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-500/20"
                />
              </div>
            </div>

            <div className="lg:col-span-2 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 rounded-xl bg-slate-50 border border-slate-200 p-4">
              <label className="inline-flex items-center gap-2 text-sm font-semibold text-slate-700">
                <input
                  type="checkbox"
                  checked={clearApiKey}
                  disabled={!settings?.api_key_configured || Boolean(apiKey.trim())}
                  onChange={(e) => setClearApiKey(e.target.checked)}
                  className="h-4 w-4 rounded border-slate-300 text-red-600 focus:ring-red-500"
                />
                Quitar API key actual
              </label>
              <div className="flex items-center gap-2 text-xs font-bold text-slate-500">
                <Trash2 size={14} />
                {settings?.api_key_configured ? settings.api_key_masked : 'Sin clave guardada'}
              </div>
            </div>
          </div>
        )}

        <div className="px-6 py-4 border-t border-slate-100 flex justify-end">
          <button
            type="submit"
            disabled={loading || saving}
            className="inline-flex items-center gap-2 rounded-xl bg-slate-900 px-4 py-2.5 text-sm font-bold text-white hover:bg-slate-800 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {saving ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
            {saving ? 'Guardando...' : 'Guardar Copilot'}
          </button>
        </div>
      </form>
    </div>
  );
};
