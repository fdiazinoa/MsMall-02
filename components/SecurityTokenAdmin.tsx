import React, { useEffect, useMemo, useState } from 'react';
import { ApiService, type Store } from '../api';
import { useAuth } from '../context/AuthProvider';
import { SecurityApiToken, SecurityServiceAccount, SecurityTokenAuditLogEntry } from '../types';
import {
  AlertTriangle,
  Ban,
  CheckCircle2,
  Copy,
  Download,
  Eye,
  Loader2,
  Plus,
  RefreshCw,
  RotateCcw,
  Search,
  Shield,
  X,
} from 'lucide-react';

type SecurityTab = 'service_accounts' | 'tokens' | 'audit';
type SecurityStatusFilter = '' | 'active' | 'disabled' | 'revoked';
type SecurityTokenTypeFilter = '' | 'app' | 'exporter';

type RevealKind = 'service-account-secret' | 'token-pair';

interface RevealState {
  kind: RevealKind;
  title: string;
  warning: string;
  clientId?: string;
  clientSecret?: string;
  accessToken?: string;
  refreshToken?: string;
}

interface TokenCreateForm {
  token_type: 'app' | 'exporter';
  mall_id: string;
  local_id: string;
  scopes: string[];
  expires_in: string;
  custom_expires_in: string;
  note: string;
  service_account_id: string;
}

interface ServiceAccountCreateForm {
  name: string;
  mall_id: string;
  local_id: string;
  scopes: string[];
}

const SCOPE_OPTIONS = ['app:read', 'app:write', 'export:write', 'mapping:read', 'tokens:manage'] as const;
const TOKEN_PRESETS: Record<'app' | 'exporter', Array<{ label: string; seconds: number }>> = {
  app: [
    { label: '30 minutos', seconds: 30 * 60 },
    { label: '1 hora', seconds: 60 * 60 },
  ],
  exporter: [
    { label: '12 horas', seconds: 12 * 60 * 60 },
    { label: '24 horas', seconds: 24 * 60 * 60 },
    { label: '7 días', seconds: 7 * 24 * 60 * 60 },
  ],
};

const UUID_REGEX = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

const formatIso = (value?: string | null) => {
  if (!value) return '—';
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
};

const truncateMiddle = (value?: string | null, left = 8, right = 6) => {
  if (!value) return '—';
  if (value.length <= left + right + 3) return value;
  return `${value.slice(0, left)}...${value.slice(-right)}`;
};

const parseScopes = (value: string[] | string | undefined | null): string[] => {
  if (!value) return [];
  if (Array.isArray(value)) return value.map(String).filter(Boolean);
  return String(value)
    .split(/[,\s]+/)
    .map((x) => x.trim())
    .filter(Boolean);
};

const isUuid = (value?: string | null) => UUID_REGEX.test(String(value || '').trim());

const badgeClasses = (status?: string) => {
  switch ((status || '').toLowerCase()) {
    case 'active':
      return 'bg-emerald-50 text-emerald-700 border-emerald-200';
    case 'disabled':
      return 'bg-amber-50 text-amber-700 border-amber-200';
    case 'revoked':
      return 'bg-rose-50 text-rose-700 border-rose-200';
    default:
      return 'bg-slate-100 text-slate-600 border-slate-200';
  }
};

const isTokenExpired = (token: SecurityApiToken) => {
  if (!token.access_expires_at) return false;
  const ts = new Date(token.access_expires_at).getTime();
  return Number.isFinite(ts) && ts < Date.now();
};

const copyToClipboard = async (value: string) => {
  try {
    await navigator.clipboard.writeText(value);
    return true;
  } catch {
    return false;
  }
};

const downloadTxt = (filename: string, content: string) => {
  const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
};

const ModalShell: React.FC<{
  open: boolean;
  title: string;
  subtitle?: string;
  onClose: () => void;
  children: React.ReactNode;
  widthClass?: string;
}> = ({ open, title, subtitle, onClose, children, widthClass = 'max-w-3xl' }) => {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-[140] flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
      <div className={`w-full ${widthClass} bg-white rounded-2xl shadow-2xl border border-slate-200 max-h-[90vh] overflow-hidden`}>
        <div className="px-6 py-4 border-b border-slate-200 flex items-start justify-between gap-4">
          <div>
            <h3 className="text-lg font-bold text-slate-800">{title}</h3>
            {subtitle && <p className="text-sm text-slate-500 mt-1">{subtitle}</p>}
          </div>
          <button onClick={onClose} className="p-2 rounded-lg hover:bg-slate-100 text-slate-500">
            <X size={18} />
          </button>
        </div>
        <div className="p-6 overflow-y-auto max-h-[calc(90vh-80px)]">{children}</div>
      </div>
    </div>
  );
};

const ScopeMultiSelect: React.FC<{
  value: string[];
  onChange: (next: string[]) => void;
}> = ({ value, onChange }) => {
  const toggle = (scope: string) => {
    if (value.includes(scope)) onChange(value.filter((s) => s !== scope));
    else onChange([...value, scope]);
  };

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
      {SCOPE_OPTIONS.map((scope) => (
        <button
          key={scope}
          type="button"
          onClick={() => toggle(scope)}
          className={`text-left px-3 py-2 rounded-lg border text-sm transition-colors ${
            value.includes(scope)
              ? 'bg-indigo-50 border-indigo-200 text-indigo-700'
              : 'bg-white border-slate-200 text-slate-700 hover:bg-slate-50'
          }`}
        >
          <div className="flex items-center gap-2">
            <div className={`w-4 h-4 rounded border flex items-center justify-center ${value.includes(scope) ? 'border-indigo-500 bg-indigo-500' : 'border-slate-300'}`}>
              {value.includes(scope) && <CheckCircle2 size={12} className="text-white" />}
            </div>
            <span className="font-mono text-xs">{scope}</span>
          </div>
        </button>
      ))}
    </div>
  );
};

const RevealModal: React.FC<{
  state: RevealState | null;
  onClose: () => void;
  onNotify: (msg: string, kind?: 'success' | 'error') => void;
}> = ({ state, onClose, onNotify }) => {
  if (!state) return null;

  const copyField = async (label: string, value?: string) => {
    if (!value) return;
    const ok = await copyToClipboard(value);
    onNotify(ok ? `${label} copiado` : `No se pudo copiar ${label.toLowerCase()}`, ok ? 'success' : 'error');
  };

  const downloadAll = () => {
    const lines = [
      `Título: ${state.title}`,
      state.clientId ? `client_id=${state.clientId}` : '',
      state.clientSecret ? `client_secret=${state.clientSecret}` : '',
      state.accessToken ? `access_token=${state.accessToken}` : '',
      state.refreshToken ? `refresh_token=${state.refreshToken}` : '',
      `warning=${state.warning}`,
    ].filter(Boolean);
    downloadTxt(`msmall-security-reveal-${Date.now()}.txt`, lines.join('\n'));
    onNotify('Archivo descargado', 'success');
  };

  return (
    <ModalShell
      open={Boolean(state)}
      onClose={onClose}
      title={state.title}
      subtitle="One-time reveal. Guarde esta información en un lugar seguro."
      widthClass="max-w-2xl"
    >
      <div className="space-y-4">
        <div className="p-4 rounded-xl border border-amber-200 bg-amber-50 text-amber-900 text-sm">
          <div className="flex items-start gap-2">
            <AlertTriangle size={16} className="mt-0.5" />
            <span>{state.warning}</span>
          </div>
        </div>

        {state.clientId && (
          <div className="space-y-1">
            <label className="block text-xs font-bold uppercase tracking-widest text-slate-500">Client ID</label>
            <div className="flex gap-2">
              <input readOnly value={state.clientId} className="flex-1 border border-slate-300 rounded-lg px-3 py-2 font-mono text-xs" />
              <button type="button" onClick={() => copyField('Client ID', state.clientId)} className="px-3 py-2 rounded-lg border border-slate-300 hover:bg-slate-50">
                <Copy size={16} />
              </button>
            </div>
          </div>
        )}

        {state.clientSecret && (
          <div className="space-y-1">
            <label className="block text-xs font-bold uppercase tracking-widest text-slate-500">Client Secret</label>
            <div className="flex gap-2">
              <textarea readOnly value={state.clientSecret} className="flex-1 border border-slate-300 rounded-lg px-3 py-2 font-mono text-xs min-h-[84px]" />
              <button type="button" onClick={() => copyField('Client Secret', state.clientSecret)} className="px-3 py-2 rounded-lg border border-slate-300 hover:bg-slate-50 h-fit">
                <Copy size={16} />
              </button>
            </div>
          </div>
        )}

        {state.accessToken && (
          <div className="space-y-1">
            <label className="block text-xs font-bold uppercase tracking-widest text-slate-500">Access Token</label>
            <div className="flex gap-2">
              <textarea readOnly value={state.accessToken} className="flex-1 border border-slate-300 rounded-lg px-3 py-2 font-mono text-xs min-h-[92px]" />
              <button type="button" onClick={() => copyField('Access Token', state.accessToken)} className="px-3 py-2 rounded-lg border border-slate-300 hover:bg-slate-50 h-fit">
                <Copy size={16} />
              </button>
            </div>
          </div>
        )}

        {state.refreshToken && (
          <div className="space-y-1">
            <label className="block text-xs font-bold uppercase tracking-widest text-slate-500">Refresh Token</label>
            <div className="flex gap-2">
              <textarea readOnly value={state.refreshToken} className="flex-1 border border-slate-300 rounded-lg px-3 py-2 font-mono text-xs min-h-[84px]" />
              <button type="button" onClick={() => copyField('Refresh Token', state.refreshToken)} className="px-3 py-2 rounded-lg border border-slate-300 hover:bg-slate-50 h-fit">
                <Copy size={16} />
              </button>
            </div>
          </div>
        )}

        <div className="flex justify-end gap-2 pt-2">
          <button type="button" onClick={downloadAll} className="px-4 py-2 rounded-lg border border-slate-300 hover:bg-slate-50 flex items-center gap-2">
            <Download size={16} /> Descargar .txt
          </button>
          <button type="button" onClick={onClose} className="px-4 py-2 rounded-lg bg-indigo-600 text-white hover:bg-indigo-700">
            Entendido
          </button>
        </div>
      </div>
    </ModalShell>
  );
};

export const SecurityTokenAdmin: React.FC = () => {
  const { session, isAdmin, isTic, malls, currentMall } = useAuth();
  const token = session?.access_token || '';

  const [activeTab, setActiveTab] = useState<SecurityTab>('service_accounts');
  const [loading, setLoading] = useState(false);
  const [reloading, setReloading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [flash, setFlash] = useState<{ kind: 'success' | 'error'; message: string } | null>(null);

  const [serviceAccounts, setServiceAccounts] = useState<SecurityServiceAccount[]>([]);
  const [tokens, setTokens] = useState<SecurityApiToken[]>([]);
  const [auditLogs, setAuditLogs] = useState<SecurityTokenAuditLogEntry[]>([]);
  const [auditAvailable, setAuditAvailable] = useState(true);
  const [storeDirectory, setStoreDirectory] = useState<Record<string, Store>>({});

  const [filters, setFilters] = useState({
    mall_id: '',
    local_id: '',
    token_type: '' as SecurityTokenTypeFilter,
    status: '' as SecurityStatusFilter,
    q: '',
  });

  const [showCreateSaModal, setShowCreateSaModal] = useState(false);
  const [showCreateTokenModal, setShowCreateTokenModal] = useState(false);
  const [savingAction, setSavingAction] = useState(false);
  const [createServiceAccountError, setCreateServiceAccountError] = useState<string | null>(null);
  const [createTokenError, setCreateTokenError] = useState<string | null>(null);
  const [storeOptionsByMall, setStoreOptionsByMall] = useState<Record<string, Store[]>>({});
  const [storesLoadingMall, setStoresLoadingMall] = useState<string | null>(null);
  const [storesLoadError, setStoresLoadError] = useState<string | null>(null);
  const [selectedTokenDetail, setSelectedTokenDetail] = useState<SecurityApiToken | null>(null);
  const [revealState, setRevealState] = useState<RevealState | null>(null);

  const [serviceAccountForm, setServiceAccountForm] = useState<ServiceAccountCreateForm>({
    name: '',
    mall_id: '',
    local_id: '',
    scopes: ['export:write', 'mapping:read'],
  });

  const [tokenForm, setTokenForm] = useState<TokenCreateForm>({
    token_type: 'exporter',
    mall_id: '',
    local_id: '',
    scopes: ['export:write', 'mapping:read'],
    expires_in: String(TOKEN_PRESETS.exporter[0].seconds),
    custom_expires_in: '',
    note: '',
    service_account_id: '',
  });

  const selectedMallId = filters.mall_id || currentMall?.id || '';
  const serviceAccountStoreOptions = storeOptionsByMall[serviceAccountForm.mall_id] || [];
  const tokenStoreOptions = storeOptionsByMall[tokenForm.mall_id] || [];
  const mallNameById = useMemo(() => {
    const entries = (malls || []).map((mall: any) => [String(mall.id), String(mall.nombre || mall.id)]);
    return new Map<string, string>(entries);
  }, [malls]);

  useEffect(() => {
    let cancelled = false;

    const loadStores = async () => {
      const mallRows = Array.isArray(malls) ? malls : [];
      if (mallRows.length === 0) {
        setStoreDirectory({});
        return;
      }

      const storeLists = await Promise.all(
        mallRows.map(async (mall: any) => {
          try {
            return await ApiService.getStores(mall.id);
          } catch {
            return [];
          }
        })
      );

      if (cancelled) return;

      const next: Record<string, Store> = {};
      for (const store of storeLists.flat()) {
        next[`${store.mall_id}::${store.id}`] = store;
      }
      setStoreDirectory(next);
    };

    loadStores();
    return () => {
      cancelled = true;
    };
  }, [malls]);

  const resolveMallName = (mallId?: string | null, mallName?: string | null) => {
    if (mallName && mallName.trim()) return mallName;
    if (mallId && mallNameById.has(mallId)) return mallNameById.get(mallId) || mallId;
    return truncateMiddle(mallId || '', 10, 6);
  };

  const resolveLocalName = (mallId?: string | null, localId?: string | null, localName?: string | null) => {
    if (localName && localName.trim()) return localName;
    if (mallId && localId) {
      const direct = storeDirectory[`${mallId}::${localId}`];
      if (direct?.nombre) return direct.nombre;
    }
    if (localId) {
      const anyStore = Object.values(storeDirectory).find((store) => store.id === localId);
      if (anyStore?.nombre) return anyStore.nombre;
    }
    return truncateMiddle(localId || '', 10, 6);
  };

  const renderMallIdentity = (mallId?: string | null, mallName?: string | null) => (
    <div>
      <div className="font-medium text-slate-800">{resolveMallName(mallId, mallName)}</div>
      <div className="text-xs font-mono text-slate-500">{mallId ? truncateMiddle(mallId, 10, 6) : '—'}</div>
    </div>
  );

  const renderLocalIdentity = (mallId?: string | null, localId?: string | null, localName?: string | null) => (
    <div>
      <div className="font-medium text-slate-800">{resolveLocalName(mallId, localId, localName)}</div>
      <div className="text-xs font-mono text-slate-500">{localId ? truncateMiddle(localId, 10, 6) : '—'}</div>
    </div>
  );

  useEffect(() => {
    if (currentMall?.id) {
      setFilters((prev) => (prev.mall_id ? prev : { ...prev, mall_id: currentMall.id }));
      setServiceAccountForm((prev) => (prev.mall_id ? prev : { ...prev, mall_id: currentMall.id }));
      setTokenForm((prev) => (prev.mall_id ? prev : { ...prev, mall_id: currentMall.id }));
    }
  }, [currentMall?.id]);

  const loadStoresForMall = async (mallId: string) => {
    const normalizedMallId = String(mallId || '').trim();
    if (!normalizedMallId || storeOptionsByMall[normalizedMallId]) return;
    setStoresLoadingMall(normalizedMallId);
    setStoresLoadError(null);
    try {
      const stores = await ApiService.getStores(normalizedMallId);
      setStoreOptionsByMall((prev) => ({ ...prev, [normalizedMallId]: stores || [] }));
    } catch (err: any) {
      setStoresLoadError(err?.message || 'No se pudieron cargar los locales del mall seleccionado.');
    } finally {
      setStoresLoadingMall((prev) => (prev === normalizedMallId ? null : prev));
    }
  };

  useEffect(() => {
    if (showCreateSaModal && isUuid(serviceAccountForm.mall_id)) {
      loadStoresForMall(serviceAccountForm.mall_id);
    }
  }, [showCreateSaModal, serviceAccountForm.mall_id]);

  useEffect(() => {
    if (showCreateTokenModal && isUuid(tokenForm.mall_id)) {
      loadStoresForMall(tokenForm.mall_id);
    }
  }, [showCreateTokenModal, tokenForm.mall_id]);

  useEffect(() => {
    if (!flash) return;
    const t = window.setTimeout(() => setFlash(null), 3500);
    return () => window.clearTimeout(t);
  }, [flash]);

  const notify = (message: string, kind: 'success' | 'error' = 'success') => {
    setFlash({ message, kind });
  };

  const loadData = async (opts?: { silent?: boolean }) => {
    if (!token) return;
    if (opts?.silent) setReloading(true);
    else setLoading(true);
    setError(null);
    try {
      const baseFilters = {
        mall_id: filters.mall_id || undefined,
        local_id: filters.local_id || undefined,
        token_type: filters.token_type || undefined,
        status: filters.status || undefined,
        q: filters.q || undefined,
      };

      const [saRows, tokenRows] = await Promise.all([
        ApiService.getSecurityServiceAccounts(token, {
          ...baseFilters,
          token_type: baseFilters.token_type === 'app' ? undefined : 'exporter',
        }),
        ApiService.getSecurityTokens(token, baseFilters),
      ]);

      setServiceAccounts(saRows || []);
      setTokens(tokenRows || []);

      try {
        const auditRows = await ApiService.getSecurityTokenAudit(token, {
          mall_id: baseFilters.mall_id,
          local_id: baseFilters.local_id,
          q: baseFilters.q,
          limit: 200,
        });
        setAuditLogs(auditRows || []);
        setAuditAvailable(true);
      } catch (auditErr: any) {
        const msg = String(auditErr?.message || '');
        if (msg.includes('404') || msg.toLowerCase().includes('not found')) {
          setAuditAvailable(false);
          setAuditLogs([]);
        } else {
          throw auditErr;
        }
      }
    } catch (err: any) {
      setError(err?.message || 'No se pudo cargar el módulo de seguridad.');
    } finally {
      setLoading(false);
      setReloading(false);
    }
  };

  useEffect(() => {
    if (!token) return;
    loadData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, filters.mall_id, filters.local_id, filters.token_type, filters.status, filters.q]);

  const allowedCreateTokenServiceAccounts = useMemo(() => {
    const mallId = tokenForm.mall_id;
    const localId = tokenForm.local_id;
    return serviceAccounts.filter((sa) => {
      if (sa.status !== 'active') return false;
      if (mallId && sa.mall_id !== mallId) return false;
      if (tokenForm.token_type === 'exporter' && localId && sa.local_id !== localId) return false;
      return true;
    });
  }, [serviceAccounts, tokenForm.mall_id, tokenForm.local_id, tokenForm.token_type]);

  const tokenRowsForDisplay = useMemo(() => {
    return tokens.map((row) => ({
      ...row,
      __expired: isTokenExpired(row),
      __scopes: parseScopes(row.scopes),
    }));
  }, [tokens]);

  const resetServiceAccountForm = () => {
    setCreateServiceAccountError(null);
    setServiceAccountForm({
      name: '',
      mall_id: selectedMallId || '',
      local_id: '',
      scopes: ['export:write', 'mapping:read'],
    });
  };

  const resetTokenForm = () => {
    setCreateTokenError(null);
    setTokenForm({
      token_type: 'exporter',
      mall_id: selectedMallId || '',
      local_id: '',
      scopes: ['export:write', 'mapping:read'],
      expires_in: String(TOKEN_PRESETS.exporter[0].seconds),
      custom_expires_in: '',
      note: '',
      service_account_id: '',
    });
  };

  const handleCreateServiceAccount = async () => {
    if (!token) return;
    const name = serviceAccountForm.name.trim();
    const mallId = serviceAccountForm.mall_id.trim();
    const localId = serviceAccountForm.local_id.trim();
    setCreateServiceAccountError(null);
    if (!name) {
      setCreateServiceAccountError('El nombre es requerido.');
      return;
    }
    if (!mallId || !localId) {
      setCreateServiceAccountError('Mall y local son requeridos.');
      return;
    }
    if (!isUuid(mallId)) {
      setCreateServiceAccountError('Mall inválido. Selecciona un mall válido.');
      return;
    }
    if (!isUuid(localId)) {
      setCreateServiceAccountError('Local inválido. Debes seleccionar un local real del mall.');
      return;
    }
    if (serviceAccountForm.scopes.length === 0) {
      setCreateServiceAccountError('Debe seleccionar al menos un scope.');
      return;
    }
    if (!window.confirm('¿Crear Service Account para MsExportador?')) return;

    setSavingAction(true);
    try {
      const created = await ApiService.createSecurityServiceAccount(
        {
          name,
          mall_id: mallId,
          local_id: localId,
          scopes: serviceAccountForm.scopes,
        },
        token
      );
      setShowCreateSaModal(false);
      resetServiceAccountForm();
      setRevealState({
        kind: 'service-account-secret',
        title: 'Service Account creado',
        warning: created.warning || 'Este secreto no volverá a mostrarse completo.',
        clientId: created.client_id,
        clientSecret: created.client_secret,
      });
      notify('Service Account creado correctamente.');
      await loadData({ silent: true });
    } catch (err: any) {
      const message = err?.message || 'No se pudo crear el service account.';
      setCreateServiceAccountError(message);
      notify(message, 'error');
    } finally {
      setSavingAction(false);
    }
  };

  const resolveTokenExpiresIn = (): number | undefined => {
    const fromPreset = Number(tokenForm.expires_in);
    if (tokenForm.expires_in === 'custom') {
      const custom = Number(tokenForm.custom_expires_in);
      return Number.isFinite(custom) && custom > 0 ? custom : undefined;
    }
    return Number.isFinite(fromPreset) && fromPreset > 0 ? fromPreset : undefined;
  };

  const handleCreateToken = async () => {
    if (!token) return;
    const mallId = tokenForm.mall_id.trim();
    const localId = tokenForm.local_id.trim();
    setCreateTokenError(null);
    if (!mallId) {
      setCreateTokenError('Mall es requerido.');
      return;
    }
    if (!isUuid(mallId)) {
      setCreateTokenError('Mall inválido. Selecciona un mall válido.');
      return;
    }
    if (tokenForm.token_type === 'exporter' && !localId) {
      setCreateTokenError('Local es requerido para token exporter.');
      return;
    }
    if (tokenForm.token_type === 'exporter' && !isUuid(localId)) {
      setCreateTokenError('Local inválido. Debes seleccionar un local real del mall.');
      return;
    }
    if (tokenForm.scopes.length === 0) {
      setCreateTokenError('Debe seleccionar al menos un scope.');
      return;
    }
    const expiresIn = resolveTokenExpiresIn();
    if (tokenForm.expires_in === 'custom' && !expiresIn) {
      setCreateTokenError('expires_in personalizado inválido.');
      return;
    }
    if (!window.confirm(`¿Crear token ${tokenForm.token_type} para ${mallId}${localId ? ` / ${localId}` : ''}?`)) return;

    setSavingAction(true);
    try {
      const created = await ApiService.createSecurityToken(
        {
          token_type: tokenForm.token_type,
          mall_id: mallId,
          local_id: tokenForm.token_type === 'exporter' ? localId : undefined,
          scopes: tokenForm.scopes,
          expires_in: expiresIn,
          service_account_id: tokenForm.service_account_id || undefined,
        },
        token
      );
      setShowCreateTokenModal(false);
      resetTokenForm();
      setRevealState({
        kind: 'token-pair',
        title: 'Token creado',
        warning: 'Los tokens completos solo se muestran una vez. Guárdelos de forma segura.',
        accessToken: created.access_token,
        refreshToken: created.refresh_token,
      });
      notify('Token creado correctamente.');
      await loadData({ silent: true });
    } catch (err: any) {
      const message = err?.message || 'No se pudo crear el token.';
      setCreateTokenError(message);
      notify(message, 'error');
    } finally {
      setSavingAction(false);
    }
  };

  const handleServiceAccountStatusToggle = async (row: SecurityServiceAccount) => {
    if (!token) return;
    const next = row.status === 'active' ? 'disabled' : 'active';
    if (!window.confirm(`¿Cambiar estado del service account a ${next}?`)) return;
    try {
      await ApiService.updateSecurityServiceAccountStatus(row.id, next, token);
      notify(`Service account ${next === 'active' ? 'activado' : 'desactivado'}.`);
      await loadData({ silent: true });
    } catch (err: any) {
      notify(err?.message || 'No se pudo actualizar el estado.', 'error');
    }
  };

  const handleServiceAccountRegenerate = async (row: SecurityServiceAccount) => {
    if (!token) return;
    if (!window.confirm('¿Regenerar el client_secret? Esto revocará tokens activos asociados.')) return;
    try {
      const regenerated = await ApiService.regenerateSecurityServiceAccount(row.id, token);
      setRevealState({
        kind: 'service-account-secret',
        title: `Secreto regenerado (${row.name || row.client_id})`,
        warning: regenerated.warning || 'Este secreto no volverá a mostrarse completo.',
        clientId: regenerated.client_id,
        clientSecret: regenerated.client_secret,
      });
      notify('Secreto regenerado.');
      await loadData({ silent: true });
    } catch (err: any) {
      notify(err?.message || 'No se pudo regenerar el secreto.', 'error');
    }
  };

  const handleServiceAccountRevokeTokens = async (row: SecurityServiceAccount) => {
    if (!token) return;
    if (!window.confirm('¿Revocar todos los tokens asociados a este Service Account?')) return;
    try {
      const result = await ApiService.revokeTokensBySecurityServiceAccount(row.id, token, 'ui_service_account_bulk_revoke');
      notify(`Tokens revocados: ${result.revoked_count}.`);
      await loadData({ silent: true });
    } catch (err: any) {
      notify(err?.message || 'No se pudieron revocar los tokens asociados.', 'error');
    }
  };

  const handleCopyClientId = async (row: SecurityServiceAccount) => {
    const ok = await copyToClipboard(row.client_id);
    notify(ok ? 'client_id copiado' : 'No se pudo copiar client_id', ok ? 'success' : 'error');
  };

  const handleTokenStatusToggle = async (row: SecurityApiToken) => {
    if (!token) return;
    if (row.status === 'revoked') {
      notify('Un token revocado no puede reactivarse desde esta acción.', 'error');
      return;
    }
    const next = row.status === 'active' ? 'disabled' : 'active';
    if (!window.confirm(`¿Cambiar estado del token a ${next}?`)) return;
    try {
      await ApiService.updateSecurityTokenStatus(row.id, next, token);
      notify(`Token ${next === 'active' ? 'activado' : 'desactivado'}.`);
      await loadData({ silent: true });
    } catch (err: any) {
      notify(err?.message || 'No se pudo actualizar el estado del token.', 'error');
    }
  };

  const handleTokenRevoke = async (row: SecurityApiToken) => {
    if (!token) return;
    if (!window.confirm('¿Revocar este token?')) return;
    try {
      await ApiService.revokeSecurityToken({ token_id: row.id, reason: 'ui_manual_revoke' }, token);
      notify('Token revocado.');
      await loadData({ silent: true });
    } catch (err: any) {
      notify(err?.message || 'No se pudo revocar el token.', 'error');
    }
  };

  const handleTokenRegenerate = async (row: SecurityApiToken) => {
    if (!token) return;
    if (!window.confirm('¿Regenerar token? El token actual será revocado y se mostrará el nuevo solo una vez.')) return;
    try {
      const regenerated = await ApiService.regenerateSecurityToken(row.id, token);
      setRevealState({
        kind: 'token-pair',
        title: `Token regenerado (${row.token_type})`,
        warning: 'Los tokens completos solo se muestran una vez. Guárdelos de forma segura.',
        accessToken: regenerated.access_token,
        refreshToken: regenerated.refresh_token,
      });
      notify('Token regenerado.');
      await loadData({ silent: true });
    } catch (err: any) {
      notify(err?.message || 'No se pudo regenerar el token.', 'error');
    }
  };

  const handleBulkRevokeByLocal = async () => {
    if (!token) return;
    if (!filters.mall_id || !filters.local_id) {
      notify('Para revocar por local debe indicar mall y local en los filtros.', 'error');
      return;
    }
    if (!window.confirm(`¿Revocar todos los tokens del local ${filters.local_id}?`)) return;
    try {
      const res = await ApiService.revokeSecurityTokensByLocal({ mall_id: filters.mall_id, local_id: filters.local_id }, token);
      notify(`Tokens revocados (local): ${res.revoked_count}.`);
      await loadData({ silent: true });
    } catch (err: any) {
      notify(err?.message || 'No se pudo revocar por local.', 'error');
    }
  };

  const handleBulkRevokeByMall = async () => {
    if (!token) return;
    if (!filters.mall_id) {
      notify('Para revocar por mall debe indicar mall en los filtros.', 'error');
      return;
    }
    if (!window.confirm(`¿Revocar todos los tokens del mall ${filters.mall_id}?`)) return;
    try {
      const res = await ApiService.revokeSecurityTokensByMall({ mall_id: filters.mall_id }, token);
      notify(`Tokens revocados (mall): ${res.revoked_count}.`);
      await loadData({ silent: true });
    } catch (err: any) {
      notify(err?.message || 'No se pudo revocar por mall.', 'error');
    }
  };

  if (!isAdmin && !isTic) {
    return (
      <div className="bg-amber-50 border border-amber-200 text-amber-900 rounded-xl p-4 text-sm">
        Solo usuarios con rol ADMIN o IT pueden acceder a la gestión de seguridad de tokens.
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
      <div className="flex flex-col lg:flex-row justify-between items-start lg:items-center gap-4">
        <div>
          <h2 className="text-2xl font-bold text-slate-800">Seguridad &gt; Service Accounts y Tokens</h2>
          <p className="text-slate-500 text-sm">
            Gestión central de credenciales para MsMall Web y MsExportador. Los secretos se muestran una sola vez.
          </p>
        </div>

        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => loadData({ silent: true })}
            className="px-4 py-2 rounded-lg border border-slate-300 bg-white hover:bg-slate-50 flex items-center gap-2"
            disabled={loading || reloading}
          >
            {reloading ? <Loader2 size={16} className="animate-spin" /> : <RefreshCw size={16} />}
            Recargar
          </button>
          <button
            type="button"
            onClick={() => {
              resetServiceAccountForm();
              setShowCreateSaModal(true);
            }}
            className="px-4 py-2 rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 flex items-center gap-2"
          >
            <Plus size={16} />
            Crear Service Account
          </button>
          <button
            type="button"
            onClick={() => {
              resetTokenForm();
              setShowCreateTokenModal(true);
            }}
            className="px-4 py-2 rounded-lg bg-slate-900 text-white hover:bg-slate-800 flex items-center gap-2"
          >
            <Shield size={16} />
            Crear Token
          </button>
        </div>
      </div>

      {flash && (
        <div className={`rounded-xl border px-4 py-3 text-sm flex items-center gap-2 ${flash.kind === 'success' ? 'bg-emerald-50 border-emerald-200 text-emerald-800' : 'bg-rose-50 border-rose-200 text-rose-800'}`}>
          {flash.kind === 'success' ? <CheckCircle2 size={16} /> : <AlertTriangle size={16} />}
          <span>{flash.message}</span>
        </div>
      )}

      <div className="bg-white border border-slate-200 rounded-2xl shadow-sm">
        <div className="p-4 md:p-5 border-b border-slate-200">
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-5 gap-3">
            <div>
              <label className="block text-xs font-bold uppercase tracking-widest text-slate-500 mb-1">Mall</label>
              <select
                value={filters.mall_id}
                onChange={(e) => setFilters((prev) => ({ ...prev, mall_id: e.target.value }))}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm bg-white"
              >
                <option value="">Todos</option>
                {(malls || []).map((mall: any) => (
                  <option key={mall.id} value={mall.id}>
                    {mall.nombre} ({truncateMiddle(mall.id, 8, 4)})
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-xs font-bold uppercase tracking-widest text-slate-500 mb-1">Local ID</label>
              <input
                value={filters.local_id}
                onChange={(e) => setFilters((prev) => ({ ...prev, local_id: e.target.value }))}
                placeholder="UUID local"
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
              />
            </div>

            <div>
              <label className="block text-xs font-bold uppercase tracking-widest text-slate-500 mb-1">Tipo de Token</label>
              <select
                value={filters.token_type}
                onChange={(e) => setFilters((prev) => ({ ...prev, token_type: e.target.value as SecurityTokenTypeFilter }))}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm bg-white"
              >
                <option value="">Todos</option>
                <option value="app">app</option>
                <option value="exporter">exporter</option>
              </select>
            </div>

            <div>
              <label className="block text-xs font-bold uppercase tracking-widest text-slate-500 mb-1">Estado</label>
              <select
                value={filters.status}
                onChange={(e) => setFilters((prev) => ({ ...prev, status: e.target.value as SecurityStatusFilter }))}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm bg-white"
              >
                <option value="">Todos</option>
                <option value="active">Activo</option>
                <option value="disabled">Inactivo</option>
                <option value="revoked">Revocado</option>
              </select>
            </div>

            <div>
              <label className="block text-xs font-bold uppercase tracking-widest text-slate-500 mb-1">Buscar</label>
              <div className="relative">
                <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                <input
                  value={filters.q}
                  onChange={(e) => setFilters((prev) => ({ ...prev, q: e.target.value }))}
                  placeholder="nombre / jti / creador"
                  className="w-full rounded-lg border border-slate-300 pl-9 pr-3 py-2 text-sm"
                />
              </div>
            </div>
          </div>
        </div>

        <div className="px-4 md:px-5 pt-4">
          <div className="flex flex-wrap gap-2 border-b border-slate-200">
            {[
              { id: 'service_accounts', label: 'Service Accounts' },
              { id: 'tokens', label: 'Tokens' },
              { id: 'audit', label: 'Auditoría' },
            ].map((tab) => (
              <button
                key={tab.id}
                type="button"
                onClick={() => setActiveTab(tab.id as SecurityTab)}
                className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
                  activeTab === tab.id
                    ? 'border-indigo-600 text-indigo-700'
                    : 'border-transparent text-slate-500 hover:text-slate-700'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>
        </div>

        <div className="p-4 md:p-5">
          {loading ? (
            <div className="flex items-center justify-center py-16 text-slate-500">
              <Loader2 size={18} className="animate-spin mr-2" /> Cargando módulo de seguridad...
            </div>
          ) : error ? (
            <div className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-rose-800">
              <div className="font-semibold mb-1">No se pudo cargar la información</div>
              <div className="text-sm mb-3">{error}</div>
              <button type="button" onClick={() => loadData()} className="px-3 py-2 rounded-lg bg-rose-600 text-white hover:bg-rose-700 text-sm">
                Reintentar
              </button>
            </div>
          ) : (
            <>
              {activeTab === 'service_accounts' && (
                <div className="space-y-4">
                  <div className="text-sm text-slate-500">
                    Service Accounts para MsExportador por mall + local, con client secret one-time reveal.
                  </div>
                  <div className="overflow-x-auto rounded-xl border border-slate-200">
                    <table className="w-full text-left min-w-[1100px]">
                      <thead className="bg-slate-50 text-[11px] uppercase tracking-wider text-slate-500 border-b border-slate-200">
                        <tr>
                          <th className="px-4 py-3">Nombre</th>
                          <th className="px-4 py-3">Mall</th>
                          <th className="px-4 py-3">Local</th>
                          <th className="px-4 py-3">Estado</th>
                          <th className="px-4 py-3">Scopes</th>
                          <th className="px-4 py-3">Creado</th>
                          <th className="px-4 py-3">Último uso</th>
                          <th className="px-4 py-3">Tokens</th>
                          <th className="px-4 py-3 text-right">Acciones</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100 bg-white">
                        {serviceAccounts.length === 0 ? (
                          <tr>
                            <td colSpan={9} className="px-4 py-12 text-center text-slate-400">
                              No hay service accounts para los filtros seleccionados.
                            </td>
                          </tr>
                        ) : (
                          serviceAccounts.map((row) => (
                            <tr key={row.id} className="hover:bg-slate-50">
                              <td className="px-4 py-3">
                                <div className="font-medium text-slate-800">{row.name || '(sin nombre)'}</div>
                                <div className="text-xs font-mono text-slate-500">{row.client_id}</div>
                              </td>
                              <td className="px-4 py-3">{renderMallIdentity(row.mall_id)}</td>
                              <td className="px-4 py-3">{renderLocalIdentity(row.mall_id, row.local_id)}</td>
                              <td className="px-4 py-3">
                                <span className={`inline-flex items-center px-2.5 py-1 rounded-full border text-xs font-semibold ${badgeClasses(row.status)}`}>
                                  {row.status}
                                </span>
                              </td>
                              <td className="px-4 py-3">
                                <div className="flex flex-wrap gap-1 max-w-[220px]">
                                  {parseScopes(row.scopes).map((scope) => (
                                    <span key={scope} className="px-2 py-0.5 rounded-md bg-indigo-50 text-indigo-700 text-[11px] font-mono">
                                      {scope}
                                    </span>
                                  ))}
                                </div>
                              </td>
                              <td className="px-4 py-3 text-xs text-slate-600">
                                <div>{formatIso(row.created_at)}</div>
                                <div className="text-slate-400">by {truncateMiddle(row.created_by || '', 6, 4)}</div>
                              </td>
                              <td className="px-4 py-3 text-xs text-slate-600">
                                <div>{formatIso(row.last_used_at)}</div>
                                {row.last_used_ip && <div className="text-slate-400">{row.last_used_ip}</div>}
                              </td>
                              <td className="px-4 py-3 text-xs text-slate-700">
                                <div>Activos: {row.active_tokens ?? 0}</div>
                                <div className="text-slate-500">Total: {row.total_tokens ?? 0}</div>
                              </td>
                              <td className="px-4 py-3">
                                <div className="flex justify-end flex-wrap gap-2">
                                  <button type="button" onClick={() => handleCopyClientId(row)} className="px-2.5 py-1.5 rounded-lg border border-slate-300 hover:bg-slate-50 text-xs flex items-center gap-1">
                                    <Copy size={13} /> client_id
                                  </button>
                                  <button type="button" onClick={() => handleServiceAccountStatusToggle(row)} className="px-2.5 py-1.5 rounded-lg border border-slate-300 hover:bg-slate-50 text-xs">
                                    {row.status === 'active' ? 'Desactivar' : 'Activar'}
                                  </button>
                                  <button type="button" onClick={() => handleServiceAccountRegenerate(row)} className="px-2.5 py-1.5 rounded-lg border border-indigo-200 text-indigo-700 hover:bg-indigo-50 text-xs flex items-center gap-1">
                                    <RotateCcw size={13} /> Regenerar
                                  </button>
                                  <button type="button" onClick={() => handleServiceAccountRevokeTokens(row)} className="px-2.5 py-1.5 rounded-lg border border-amber-200 text-amber-700 hover:bg-amber-50 text-xs flex items-center gap-1">
                                    <Ban size={13} /> Revocar tokens
                                  </button>
                                </div>
                              </td>
                            </tr>
                          ))
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {activeTab === 'tokens' && (
                <div className="space-y-4">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <p className="text-sm text-slate-500">Tokens emitidos (app / exporter). El token completo solo se muestra al crear o regenerar.</p>
                    <div className="flex flex-wrap gap-2">
                      <button type="button" onClick={handleBulkRevokeByLocal} className="px-3 py-2 rounded-lg border border-amber-200 text-amber-700 hover:bg-amber-50 text-sm">
                        Revocar por local
                      </button>
                      <button type="button" onClick={handleBulkRevokeByMall} className="px-3 py-2 rounded-lg border border-rose-200 text-rose-700 hover:bg-rose-50 text-sm">
                        Revocar por mall
                      </button>
                    </div>
                  </div>

                  <div className="overflow-x-auto rounded-xl border border-slate-200">
                    <table className="w-full text-left min-w-[1180px]">
                      <thead className="bg-slate-50 text-[11px] uppercase tracking-wider text-slate-500 border-b border-slate-200">
                        <tr>
                          <th className="px-4 py-3">Tipo</th>
                          <th className="px-4 py-3">Mall</th>
                          <th className="px-4 py-3">Local</th>
                          <th className="px-4 py-3">Scopes</th>
                          <th className="px-4 py-3">Expira</th>
                          <th className="px-4 py-3">Estado</th>
                          <th className="px-4 py-3">Último uso</th>
                          <th className="px-4 py-3">JTI</th>
                          <th className="px-4 py-3 text-right">Acciones</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100 bg-white">
                        {tokenRowsForDisplay.length === 0 ? (
                          <tr>
                            <td colSpan={9} className="px-4 py-12 text-center text-slate-400">
                              No hay tokens para los filtros seleccionados.
                            </td>
                          </tr>
                        ) : (
                          tokenRowsForDisplay.map((row) => (
                            <tr key={row.id} className="hover:bg-slate-50">
                              <td className="px-4 py-3">
                                <div className="font-medium text-slate-800">{row.token_type}</div>
                                {row.service_account_id && (
                                  <div className="text-xs text-slate-500">SA: {truncateMiddle(row.service_account_id, 8, 4)}</div>
                                )}
                              </td>
                              <td className="px-4 py-3">{renderMallIdentity(row.mall_id)}</td>
                              <td className="px-4 py-3">{renderLocalIdentity(row.mall_id, row.local_id)}</td>
                              <td className="px-4 py-3">
                                <div className="flex flex-wrap gap-1 max-w-[220px]">
                                  {row.__scopes.map((scope) => (
                                    <span key={scope} className="px-2 py-0.5 rounded-md bg-slate-100 text-slate-700 text-[11px] font-mono">
                                      {scope}
                                    </span>
                                  ))}
                                </div>
                              </td>
                              <td className="px-4 py-3 text-xs text-slate-600">
                                <div>{formatIso(row.access_expires_at || '')}</div>
                                {row.__expired && row.status === 'active' && (
                                  <div className="text-rose-600 font-medium">Expirado</div>
                                )}
                              </td>
                              <td className="px-4 py-3">
                                <span className={`inline-flex items-center px-2.5 py-1 rounded-full border text-xs font-semibold ${badgeClasses(row.status)}`}>
                                  {row.status}
                                </span>
                              </td>
                              <td className="px-4 py-3 text-xs text-slate-600">
                                <div>{formatIso(row.last_used_at)}</div>
                                {row.last_used_ip && <div className="text-slate-400">{row.last_used_ip}</div>}
                              </td>
                              <td className="px-4 py-3 font-mono text-xs text-slate-600">{truncateMiddle(row.jti, 10, 6)}</td>
                              <td className="px-4 py-3">
                                <div className="flex justify-end flex-wrap gap-2">
                                  <button type="button" onClick={() => setSelectedTokenDetail(row)} className="px-2.5 py-1.5 rounded-lg border border-slate-300 hover:bg-slate-50 text-xs flex items-center gap-1">
                                    <Eye size={13} /> Detalle
                                  </button>
                                  <button type="button" onClick={() => handleTokenStatusToggle(row)} disabled={row.status === 'revoked'} className="px-2.5 py-1.5 rounded-lg border border-slate-300 hover:bg-slate-50 disabled:opacity-50 text-xs">
                                    {row.status === 'active' ? 'Desactivar' : 'Activar'}
                                  </button>
                                  <button type="button" onClick={() => handleTokenRegenerate(row)} className="px-2.5 py-1.5 rounded-lg border border-indigo-200 text-indigo-700 hover:bg-indigo-50 text-xs flex items-center gap-1">
                                    <RotateCcw size={13} /> Regenerar
                                  </button>
                                  <button type="button" onClick={() => handleTokenRevoke(row)} className="px-2.5 py-1.5 rounded-lg border border-rose-200 text-rose-700 hover:bg-rose-50 text-xs flex items-center gap-1">
                                    <Ban size={13} /> Revocar
                                  </button>
                                </div>
                              </td>
                            </tr>
                          ))
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {activeTab === 'audit' && (
                <div className="space-y-4">
                  {!auditAvailable ? (
                    <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
                      <div className="font-semibold mb-1">Auditoría no disponible en este ambiente</div>
                      <div>
                        TODO técnico: habilitar endpoint de auditoría dedicado. Mientras tanto, use la última actividad visible en tablas de tokens/service accounts.
                      </div>
                    </div>
                  ) : (
                    <div className="overflow-x-auto rounded-xl border border-slate-200">
                      <table className="w-full text-left min-w-[980px]">
                        <thead className="bg-slate-50 text-[11px] uppercase tracking-wider text-slate-500 border-b border-slate-200">
                          <tr>
                            <th className="px-4 py-3">Evento</th>
                            <th className="px-4 py-3">Mall</th>
                            <th className="px-4 py-3">Local</th>
                            <th className="px-4 py-3">IP</th>
                            <th className="px-4 py-3">User-Agent</th>
                            <th className="px-4 py-3">Token ID</th>
                            <th className="px-4 py-3">Fecha</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100 bg-white">
                          {auditLogs.length === 0 ? (
                            <tr>
                              <td colSpan={7} className="px-4 py-12 text-center text-slate-400">
                                No hay eventos de auditoría para los filtros seleccionados.
                              </td>
                            </tr>
                          ) : (
                            auditLogs.map((row) => (
                              <tr key={`${row.id}-${row.created_at}`} className="hover:bg-slate-50">
                                <td className="px-4 py-3">
                                  <span className={`inline-flex items-center px-2.5 py-1 rounded-full border text-xs font-semibold ${badgeClasses(row.event_type === 'failed' ? 'revoked' : row.event_type === 'used' ? 'active' : 'disabled')}`}>
                                    {row.event_type}
                                  </span>
                                </td>
                                <td className="px-4 py-3">{renderMallIdentity(row.mall_id, row.mall_nombre)}</td>
                                <td className="px-4 py-3">{renderLocalIdentity(row.mall_id, row.local_id, row.local_nombre)}</td>
                                <td className="px-4 py-3 text-xs text-slate-600">{row.ip || '—'}</td>
                                <td className="px-4 py-3 text-xs text-slate-600 max-w-[320px] truncate" title={row.ua || ''}>
                                  {row.ua || '—'}
                                </td>
                                <td className="px-4 py-3">
                                  <div className="font-mono text-xs text-slate-700" title={row.token_id || ''}>
                                    {truncateMiddle(row.token_id || '', 10, 6)}
                                  </div>
                                  {row.metadata?.jti && (
                                    <div className="text-[11px] text-slate-500 mt-1" title={String(row.metadata.jti)}>
                                      JTI: {truncateMiddle(String(row.metadata.jti), 10, 6)}
                                    </div>
                                  )}
                                </td>
                                <td className="px-4 py-3 text-xs text-slate-600">{formatIso(row.created_at)}</td>
                              </tr>
                            ))
                          )}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              )}
            </>
          )}
        </div>
      </div>

      <ModalShell
        open={showCreateSaModal}
        onClose={() => setShowCreateSaModal(false)}
        title="Crear Service Account (MsExportador)"
        subtitle="Vinculado a un mall y un local. El client_secret se mostrará una sola vez."
        widthClass="max-w-2xl"
      >
        <div className="space-y-4">
          {createServiceAccountError && (
            <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800">
              <div className="font-semibold mb-1">No se pudo crear el Service Account</div>
              <div>{createServiceAccountError}</div>
            </div>
          )}

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="md:col-span-2">
              <label className="block text-sm font-medium text-slate-700 mb-1">Nombre *</label>
              <input
                value={serviceAccountForm.name}
                onChange={(e) => {
                  setCreateServiceAccountError(null);
                  setServiceAccountForm((prev) => ({ ...prev, name: e.target.value }));
                }}
                placeholder="Ej: Exportador Local 01"
                className="w-full rounded-lg border border-slate-300 px-3 py-2"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Mall *</label>
              <select
                value={serviceAccountForm.mall_id}
                onChange={(e) => {
                  setCreateServiceAccountError(null);
                  setStoresLoadError(null);
                  setServiceAccountForm((prev) => ({ ...prev, mall_id: e.target.value, local_id: '' }));
                }}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 bg-white"
              >
                <option value="">Selecciona un mall</option>
                {(malls || []).map((mall: any) => (
                  <option key={mall.id} value={mall.id}>
                    {mall.nombre} ({truncateMiddle(mall.id, 8, 4)})
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Local *</label>
              <select
                value={serviceAccountForm.local_id}
                onChange={(e) => {
                  setCreateServiceAccountError(null);
                  setServiceAccountForm((prev) => ({ ...prev, local_id: e.target.value }));
                }}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 bg-white"
                disabled={!serviceAccountForm.mall_id || storesLoadingMall === serviceAccountForm.mall_id}
              >
                <option value="">
                  {!serviceAccountForm.mall_id
                    ? 'Selecciona un mall primero'
                    : storesLoadingMall === serviceAccountForm.mall_id
                      ? 'Cargando locales...'
                      : serviceAccountStoreOptions.length === 0
                        ? 'No hay locales disponibles'
                        : 'Selecciona un local'}
                </option>
                {serviceAccountStoreOptions.map((store) => (
                  <option key={store.id} value={store.id}>
                    {store.nombre} {store.codigo_interno ? `(${store.codigo_interno})` : ''} · {truncateMiddle(store.id, 8, 4)}
                  </option>
                ))}
              </select>
              <p className="mt-1 text-xs text-slate-500">
                Selecciona el local por nombre/código. Internamente se usará el <span className="font-mono">UUID</span> real de <span className="font-mono">locales.id</span>.
              </p>
            </div>
          </div>

          {storesLoadError && (
            <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
              {storesLoadError}
            </div>
          )}

          <div>
            <label className="block text-sm font-medium text-slate-700 mb-2">Scopes por defecto</label>
            <ScopeMultiSelect
              value={serviceAccountForm.scopes}
              onChange={(scopes) => setServiceAccountForm((prev) => ({ ...prev, scopes }))}
            />
          </div>

          <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-600">
            Los campos de expiración por defecto de exporter quedan como TODO de backend (configurable por variables de entorno del servicio). Esta UI usa scopes + vínculo mall/local.
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <button type="button" onClick={() => setShowCreateSaModal(false)} className="px-4 py-2 rounded-lg border border-slate-300 hover:bg-slate-50">
              Cancelar
            </button>
            <button type="button" onClick={handleCreateServiceAccount} disabled={savingAction} className="px-4 py-2 rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50">
              {savingAction ? 'Creando...' : 'Crear Service Account'}
            </button>
          </div>
        </div>
      </ModalShell>

      <ModalShell
        open={showCreateTokenModal}
        onClose={() => setShowCreateTokenModal(false)}
        title="Crear Token"
        subtitle="Crea tokens app o exporter con scopes y expiración. El token completo se mostrará una sola vez."
        widthClass="max-w-3xl"
      >
        <div className="space-y-4">
          {createTokenError && (
            <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800">
              <div className="font-semibold mb-1">No se pudo crear el token</div>
              <div>{createTokenError}</div>
            </div>
          )}

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">token_type *</label>
              <select
                value={tokenForm.token_type}
                onChange={(e) => {
                  const nextType = e.target.value as 'app' | 'exporter';
                  setCreateTokenError(null);
                  setTokenForm((prev) => ({
                    ...prev,
                    token_type: nextType,
                    scopes: nextType === 'app' ? ['app:read'] : ['export:write', 'mapping:read'],
                    expires_in: String(TOKEN_PRESETS[nextType][0].seconds),
                    local_id: nextType === 'app' ? '' : prev.local_id,
                    service_account_id: nextType === 'app' ? '' : prev.service_account_id,
                  }));
                }}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 bg-white"
              >
                <option value="app">app</option>
                <option value="exporter">exporter</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Mall *</label>
              <select
                value={tokenForm.mall_id}
                onChange={(e) => {
                  setCreateTokenError(null);
                  setStoresLoadError(null);
                  setTokenForm((prev) => ({ ...prev, mall_id: e.target.value, local_id: '', service_account_id: '' }));
                }}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 bg-white"
              >
                <option value="">Selecciona un mall</option>
                {(malls || []).map((mall: any) => (
                  <option key={mall.id} value={mall.id}>
                    {mall.nombre} ({truncateMiddle(mall.id, 8, 4)})
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">
                Local {tokenForm.token_type === 'exporter' ? '*' : '(opcional)'}
              </label>
              <select
                value={tokenForm.local_id}
                onChange={(e) => {
                  setCreateTokenError(null);
                  setTokenForm((prev) => ({ ...prev, local_id: e.target.value }));
                }}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 bg-white"
                disabled={tokenForm.token_type !== 'exporter' || !tokenForm.mall_id || storesLoadingMall === tokenForm.mall_id}
              >
                <option value="">
                  {tokenForm.token_type !== 'exporter'
                    ? 'No requerido para token app'
                    : !tokenForm.mall_id
                      ? 'Selecciona un mall primero'
                      : storesLoadingMall === tokenForm.mall_id
                        ? 'Cargando locales...'
                        : tokenStoreOptions.length === 0
                          ? 'No hay locales disponibles'
                          : 'Selecciona un local'}
                </option>
                {tokenStoreOptions.map((store) => (
                  <option key={store.id} value={store.id}>
                    {store.nombre} {store.codigo_interno ? `(${store.codigo_interno})` : ''} · {truncateMiddle(store.id, 8, 4)}
                  </option>
                ))}
              </select>
              {tokenForm.token_type === 'exporter' && (
                <p className="mt-1 text-xs text-slate-500">
                  Selecciona el local por nombre/código. Internamente se usará el <span className="font-mono">UUID</span> real de <span className="font-mono">locales.id</span>.
                </p>
              )}
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Expiración access token *</label>
              <div className="space-y-2">
                <select
                  value={tokenForm.expires_in}
                  onChange={(e) => setTokenForm((prev) => ({ ...prev, expires_in: e.target.value }))}
                  className="w-full rounded-lg border border-slate-300 px-3 py-2 bg-white"
                >
                  {TOKEN_PRESETS[tokenForm.token_type].map((preset) => (
                    <option key={preset.seconds} value={String(preset.seconds)}>
                      {preset.label}
                    </option>
                  ))}
                  <option value="custom">Custom (segundos)</option>
                </select>
                {tokenForm.expires_in === 'custom' && (
                  <input
                    type="number"
                    min={60}
                    step={60}
                    value={tokenForm.custom_expires_in}
                    onChange={(e) => setTokenForm((prev) => ({ ...prev, custom_expires_in: e.target.value }))}
                    className="w-full rounded-lg border border-slate-300 px-3 py-2"
                    placeholder="Ej: 7200"
                  />
                )}
              </div>
            </div>

            {tokenForm.token_type === 'exporter' && (
              <div className="md:col-span-2">
                <label className="block text-sm font-medium text-slate-700 mb-1">Service Account (opcional)</label>
                <select
                  value={tokenForm.service_account_id}
                  onChange={(e) => setTokenForm((prev) => ({ ...prev, service_account_id: e.target.value }))}
                  className="w-full rounded-lg border border-slate-300 px-3 py-2 bg-white"
                >
                  <option value="">Ninguno (token manual)</option>
                  {allowedCreateTokenServiceAccounts.map((sa) => (
                    <option key={sa.id} value={sa.id}>
                      {(sa.name || sa.client_id)} · {truncateMiddle(sa.local_id || '', 8, 4)}
                    </option>
                  ))}
                </select>
              </div>
            )}
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-700 mb-2">Scopes *</label>
            <ScopeMultiSelect value={tokenForm.scopes} onChange={(scopes) => setTokenForm((prev) => ({ ...prev, scopes }))} />
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Nota interna / motivo (opcional)</label>
            <input
              value={tokenForm.note}
              onChange={(e) => setTokenForm((prev) => ({ ...prev, note: e.target.value }))}
              className="w-full rounded-lg border border-slate-300 px-3 py-2"
              placeholder="Se registra como motivo interno de operación"
            />
            <p className="text-xs text-slate-500 mt-1">La nota se usa solo como confirmación operativa en UI (no se persiste aún en backend de tokens).</p>
          </div>

          {tokenForm.token_type === 'exporter' && !tokenForm.local_id.trim() && (
            <div className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">
              Exporter token requiere seleccionar un <span className="font-medium">local</span>. El submit está bloqueado hasta completarlo.
            </div>
          )}

          <div className="flex justify-end gap-2 pt-2">
            <button type="button" onClick={() => setShowCreateTokenModal(false)} className="px-4 py-2 rounded-lg border border-slate-300 hover:bg-slate-50">
              Cancelar
            </button>
            <button
              type="button"
              onClick={handleCreateToken}
              disabled={savingAction || (tokenForm.token_type === 'exporter' && !tokenForm.local_id.trim())}
              className="px-4 py-2 rounded-lg bg-slate-900 text-white hover:bg-slate-800 disabled:opacity-50"
            >
              {savingAction ? 'Creando...' : 'Crear Token'}
            </button>
          </div>
        </div>
      </ModalShell>

      <ModalShell
        open={Boolean(selectedTokenDetail)}
        onClose={() => setSelectedTokenDetail(null)}
        title="Detalle de Token"
        subtitle="No se muestra el token completo histórico por seguridad."
        widthClass="max-w-2xl"
      >
        {selectedTokenDetail && (
          <div className="space-y-3 text-sm">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div className="rounded-lg bg-slate-50 border border-slate-200 p-3">
                <div className="text-xs text-slate-500 uppercase font-bold tracking-wider mb-1">token_type</div>
                <div className="font-medium text-slate-800">{selectedTokenDetail.token_type}</div>
              </div>
              <div className="rounded-lg bg-slate-50 border border-slate-200 p-3">
                <div className="text-xs text-slate-500 uppercase font-bold tracking-wider mb-1">status</div>
                <div className="font-medium text-slate-800">{selectedTokenDetail.status}</div>
              </div>
              <div className="rounded-lg bg-slate-50 border border-slate-200 p-3">
                <div className="text-xs text-slate-500 uppercase font-bold tracking-wider mb-1">Mall</div>
                <div className="font-medium text-slate-800">{resolveMallName(selectedTokenDetail.mall_id)}</div>
                <div className="font-mono text-xs text-slate-500 break-all mt-1">{selectedTokenDetail.mall_id}</div>
              </div>
              <div className="rounded-lg bg-slate-50 border border-slate-200 p-3">
                <div className="text-xs text-slate-500 uppercase font-bold tracking-wider mb-1">Local</div>
                <div className="font-medium text-slate-800">{resolveLocalName(selectedTokenDetail.mall_id, selectedTokenDetail.local_id)}</div>
                <div className="font-mono text-xs text-slate-500 break-all mt-1">{selectedTokenDetail.local_id || '—'}</div>
              </div>
            </div>
            <div className="rounded-lg bg-slate-50 border border-slate-200 p-3">
              <div className="text-xs text-slate-500 uppercase font-bold tracking-wider mb-1">JTI</div>
              <div className="font-mono text-xs text-slate-800 break-all">{selectedTokenDetail.jti}</div>
            </div>
            <div className="rounded-lg bg-slate-50 border border-slate-200 p-3">
              <div className="text-xs text-slate-500 uppercase font-bold tracking-wider mb-1">Scopes</div>
              <div className="flex flex-wrap gap-1">
                {parseScopes(selectedTokenDetail.scopes).map((scope) => (
                  <span key={scope} className="px-2 py-1 rounded-md bg-indigo-50 text-indigo-700 text-xs font-mono">{scope}</span>
                ))}
              </div>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div className="rounded-lg bg-slate-50 border border-slate-200 p-3">
                <div className="text-xs text-slate-500 uppercase font-bold tracking-wider mb-1">Creado</div>
                <div className="text-slate-800">{formatIso(selectedTokenDetail.created_at)}</div>
                <div className="text-xs text-slate-500 mt-1">by {selectedTokenDetail.created_by || '—'}</div>
              </div>
              <div className="rounded-lg bg-slate-50 border border-slate-200 p-3">
                <div className="text-xs text-slate-500 uppercase font-bold tracking-wider mb-1">Último uso</div>
                <div className="text-slate-800">{formatIso(selectedTokenDetail.last_used_at)}</div>
                <div className="text-xs text-slate-500 mt-1">{selectedTokenDetail.last_used_ip || '—'}</div>
              </div>
            </div>
          </div>
        )}
      </ModalShell>

      <RevealModal state={revealState} onClose={() => setRevealState(null)} onNotify={notify} />
    </div>
  );
};
