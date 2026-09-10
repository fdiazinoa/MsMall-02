// PASO 3: Frontend (React - Contexto y Rutas)
import React, { createContext, useContext, useEffect, useState, useRef } from 'react';
import { fetchAuthJson, parseMallsPayload } from '../utils/authRequests.js';
import { supabase } from '../api'; // Asumiendo que supabase client está exportado en api.ts

const AuthContext = createContext();
const SYSTEM_ADMIN_EMAIL = 'fdiaz@mercasend.net';
const DEFAULT_RAILWAY_API_ROOT = 'https://msmall-02-production.up.railway.app';
const PASSWORD_RECOVERY_QUERY_PARAM = 'password_recovery';

const normalizeRole = (roleValue) => (roleValue || '').toString().trim().toLowerCase().replace(/[-\s]+/g, '_');

const isPasswordRecoveryUrl = () => {
    if (typeof window === 'undefined') return false;
    const url = new URL(window.location.href);
    return (
        url.searchParams.get(PASSWORD_RECOVERY_QUERY_PARAM) === '1' ||
        url.searchParams.get('type') === 'recovery' ||
        new URLSearchParams(url.hash.replace(/^#/, '')).get('type') === 'recovery'
    );
};

const passwordRecoveryRedirectUrl = () => {
    const url = new URL(window.location.origin);
    url.searchParams.set(PASSWORD_RECOVERY_QUERY_PARAM, '1');
    return url.toString();
};

const clearPasswordRecoveryUrl = () => {
    if (typeof window === 'undefined') return;
    const url = new URL(window.location.href);
    [
        PASSWORD_RECOVERY_QUERY_PARAM,
        'type',
        'code',
        'error',
        'error_code',
        'error_description',
    ].forEach((key) => url.searchParams.delete(key));
    url.hash = '';
    window.history.replaceState({}, document.title, `${url.pathname}${url.search}`);
};

export const AuthProvider = ({ children }) => {
    const [session, setSession] = useState(null);
    const [user, setUser] = useState(null);
    const [role, setRole] = useState(null);
    const [permissions, setPermissions] = useState({});
    const [isPasswordRecovery, setIsPasswordRecovery] = useState(isPasswordRecoveryUrl);
    // Multi-Tenant States
    const [malls, setMalls] = useState([]);
    const [currentMall, setCurrentMall] = useState(null);
    const [mallsError, setMallsError] = useState(null);
    const [mallsLoading, setMallsLoading] = useState(false);
    const mallsRequest = useRef(0);
    const RAW_API_URL = (import.meta.env.VITE_API_URL || '').trim();
    const RAW_DIRECT_BACKEND_URL = (import.meta.env.VITE_DIRECT_BACKEND_BASE_URL || '').trim();

    const [loading, setLoading] = useState(true);

    useEffect(() => {
        if (!supabase) {
            setLoading(false);
            return;
        }

        // INITIAL_SESSION bootstraps persisted sessions; avoid a second getSession load.
        let lastAccessToken = null;
        let pendingLoad: ReturnType<typeof setTimeout> | undefined;

        // 2. Escuchar cambios de autenticación
        const { data: { subscription } } = supabase.auth.onAuthStateChange((event, session) => {
            if (event === 'PASSWORD_RECOVERY') {
                setIsPasswordRecovery(true);
            }
            setSession(session);
            if (session) {
                if (lastAccessToken === session.access_token && event !== 'USER_UPDATED') return;
                lastAccessToken = session.access_token;
                clearTimeout(pendingLoad);
                // Start Supabase queries after the auth callback releases its lock.
                pendingLoad = setTimeout(() => {
                    fetchEffectiveAccessRole(session.access_token);
                    fetchProfile(session.user.id);
                    fetchUserMalls(session.access_token, session.user.id);
                }, 0);
            }
            else {
                lastAccessToken = null;
                clearTimeout(pendingLoad);
                mallsRequest.current += 1;
                setMallsError(null);
                setMallsLoading(false);
                setUser(null);
                setRole(null);
                setPermissions({});
                setMalls([]);
                setCurrentMall(null);
                setLoading(false);
                localStorage.removeItem('msmall_current_mall_id');
            }
        });

        return () => {
            clearTimeout(pendingLoad);
            mallsRequest.current += 1;
            subscription.unsubscribe();
        };
    }, []);

    const getApiBaseCandidates = () => {
        const normalizeApiRoot = (value) => {
            const root = (value || '').trim().replace(/\/+$/, '')
                .replace(/\/api\/v1$/i, '').replace(/\/api$/i, '');
            if (!root || root.startsWith('/') || /^https?:\/\//i.test(root)) return root;
            return `https://${root}`;
        };

        const normalizedEnv = normalizeApiRoot(RAW_API_URL);
        const normalizedDirect = normalizeApiRoot(RAW_DIRECT_BACKEND_URL);
        const isVercelHost = typeof window !== 'undefined' && window.location.hostname.endsWith('vercel.app');

        const candidates = [];
        if (normalizedEnv) candidates.push(normalizedEnv);
        if (normalizedDirect) candidates.push(normalizedDirect);
        if (isVercelHost) candidates.push(DEFAULT_RAILWAY_API_ROOT);
        // Always include relative fallback (Vercel rewrite: /api/* -> Railway).
        candidates.push('');
        return [...new Set(candidates)];
    };

    const fetchJsonFromCandidates = (path, token) =>
        fetchAuthJson(getApiBaseCandidates(), path, token);

    const fetchEffectiveAccessRole = async (token) => {
        try {
            const payload = await fetchJsonFromCandidates('/api/v1/users/me/access', token);
            const effectiveRole = normalizeRole(payload?.role);
            if (effectiveRole) {
                setRole(effectiveRole);
            }
            if (payload?.permissions && typeof payload.permissions === 'object') setPermissions(payload.permissions);
        } catch (error) {
            // Fallbacks (profile/metadata/mall roles) still apply.
            console.warn('No se pudo resolver el rol efectivo:', error);
        }
    };

    const fetchUserMalls = async (token, userId) => {
        const requestId = ++mallsRequest.current;
        setMallsLoading(true);
        setMallsError(null);
        try {
            const data = parseMallsPayload(
                await fetchJsonFromCandidates('/api/v1/users/me/malls', token)
            );
            if (requestId !== mallsRequest.current) return;
            setMalls(data);
            const savedMallId = localStorage.getItem('msmall_current_mall_id');
            const selected = data.find(m => m.id === savedMallId) || data[0] || null;
            setCurrentMall(selected);
            if (selected) localStorage.setItem('msmall_current_mall_id', selected.id);
            else localStorage.removeItem('msmall_current_mall_id');
        } catch (error) {
            if (requestId !== mallsRequest.current) return;
            // Keep only the current session's in-memory selection on transient failure.
            setMallsError(error.message || 'No se pudieron cargar los Malls.');
        } finally {
            if (requestId === mallsRequest.current) setMallsLoading(false);
        }
    };

    const fetchProfile = async (userId) => {
        if (!supabase) return;
        try {
            const { data, error } = await supabase
                .from('profiles')
                .select('*')
                .eq('id', userId)
                .single();

            if (data) {
                setUser(data);
                setRole(normalizeRole(data.role));
            }
        } catch (error) {
            console.error('Error fetching profile:', error);
        } finally {
            setLoading(false);
        }
    };

    const handleSetCurrentMall = (mall) => {
        setCurrentMall(mall);
        if (mall) {
            localStorage.setItem('msmall_current_mall_id', mall.id);
        }
    };

    const changePassword = async (currentPassword, newPassword) => {
        if (!supabase) {
            throw new Error('Supabase no está configurado.');
        }

        const email = session?.user?.email;
        if (!email) {
            throw new Error('No se pudo validar el usuario actual.');
        }

        if (!currentPassword || !newPassword) {
            throw new Error('Debe completar ambos campos de contraseña.');
        }

        if (newPassword.length < 8) {
            throw new Error('La nueva contraseña debe tener al menos 8 caracteres.');
        }

        if (currentPassword === newPassword) {
            throw new Error('La nueva contraseña debe ser distinta a la actual.');
        }

        // Re-authenticate to ensure the current password is correct before update.
        const { error: verifyError } = await supabase.auth.signInWithPassword({
            email,
            password: currentPassword,
        });
        if (verifyError) {
            throw new Error('La contraseña actual no es correcta.');
        }

        const { error: updateError } = await supabase.auth.updateUser({
            password: newPassword,
        });
        if (updateError) {
            throw new Error(updateError.message || 'No se pudo actualizar la contraseña.');
        }

        return true;
    };

    const requestPasswordRecovery = async (email) => {
        if (!supabase) {
            throw new Error('Supabase no está configurado.');
        }

        const normalizedEmail = String(email || '').trim().toLowerCase();
        if (!normalizedEmail) {
            throw new Error('Ingresa el correo asociado a tu cuenta.');
        }

        const { error } = await supabase.auth.resetPasswordForEmail(normalizedEmail, {
            redirectTo: passwordRecoveryRedirectUrl(),
        });

        if (error) {
            // Do not reveal whether the email belongs to an account.
            console.error('No se pudo solicitar la recuperación de contraseña:', error.message);
            if (error.status === 429) {
                throw new Error('Espera un minuto antes de solicitar otro enlace.');
            }
            throw new Error('No se pudo enviar el enlace en este momento. Intenta nuevamente más tarde.');
        }

        return true;
    };

    const completePasswordRecovery = async (newPassword) => {
        if (!supabase || !session) {
            throw new Error('El enlace de recuperación es inválido o expiró. Solicita uno nuevo.');
        }
        if (!newPassword || newPassword.length < 8) {
            throw new Error('La nueva contraseña debe tener al menos 8 caracteres.');
        }

        const { error: updateError } = await supabase.auth.updateUser({
            password: newPassword,
        });
        if (updateError) {
            throw new Error(updateError.message || 'No se pudo actualizar la contraseña.');
        }

        const { error: signOutError } = await supabase.auth.signOut({ scope: 'global' });
        if (signOutError) {
            console.warn('La contraseña cambió, pero no se pudieron cerrar todas las sesiones:', signOutError.message);
            await supabase.auth.signOut({ scope: 'local' });
        }
        return true;
    };

    const finishPasswordRecovery = async () => {
        clearPasswordRecoveryUrl();
        setIsPasswordRecovery(false);
        if (supabase) {
            await supabase.auth.signOut({ scope: 'local' });
        }
    };

    const normalizedRole = normalizeRole(
        role ||
        currentMall?.rol ||
        malls?.[0]?.rol ||
        session?.user?.user_metadata?.rol ||
        session?.user?.user_metadata?.role
    );
    if (typeof window !== 'undefined') {
        console.log('[AuthProvider] role debug', {
            effectiveRoleState: role,
            currentMallRole: currentMall?.rol || null,
            firstMallRole: malls?.[0]?.rol || null,
            metadataRol: session?.user?.user_metadata?.rol || null,
            metadataRole: session?.user?.user_metadata?.role || null,
            normalizedRole,
            email: session?.user?.email || null
        });
    }
    const currentEmail = (session?.user?.email || '').toLowerCase();
    const isSystemAdmin = currentEmail === SYSTEM_ADMIN_EMAIL;
    const canAccess = (moduleKey, action = 'view') => isSystemAdmin || Boolean(permissions?.[moduleKey]?.[action]);

    const value = {
        session,
        user,
        role: normalizedRole || role,
        permissions,
        canAccess,
        malls,
        currentMall,
        mallsError,
        mallsLoading,
        loading,
        setCurrentMall: handleSetCurrentMall,
        isAdmin: isSystemAdmin || ['admin', 'superadmin', 'super_admin', 'administrador'].includes(normalizedRole),
        isTic: ['tic', 'it'].includes(normalizedRole),
        isAuditor: normalizedRole === 'auditor',
        signOut: () => supabase?.auth.signOut(),
        changePassword,
        isPasswordRecovery,
        requestPasswordRecovery,
        completePasswordRecovery,
        finishPasswordRecovery,
        refreshMalls: () => session?.access_token && fetchUserMalls(session.access_token, session?.user?.id),
    };

    return (
        <AuthContext.Provider value={value}>
            {children}
        </AuthContext.Provider>
    );
};

export const useAuth = () => useContext(AuthContext);
