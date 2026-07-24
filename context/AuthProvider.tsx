// PASO 3: Frontend (React - Contexto y Rutas)
import React, { createContext, useContext, useEffect, useState } from 'react';
import { supabase } from '../api'; // Asumiendo que supabase client está exportado en api.ts

const AuthContext = createContext();
const SYSTEM_ADMIN_EMAIL = 'fdiaz@mercasend.net';
const DEFAULT_RAILWAY_API_ROOT = 'https://msmall-02-production.up.railway.app';

const normalizeRole = (roleValue) => (roleValue || '').toString().trim().toLowerCase().replace(/[-\s]+/g, '_');

export const AuthProvider = ({ children }) => {
    const [session, setSession] = useState(null);
    const [user, setUser] = useState(null);
    const [role, setRole] = useState(null);
    const [permissions, setPermissions] = useState({});
    // Multi-Tenant States
    const [malls, setMalls] = useState([]);
    const [currentMall, setCurrentMall] = useState(null);
    const USER_MALLS_STORAGE_KEY = 'msmall_user_malls';
    const RAW_API_URL = (import.meta.env.VITE_API_URL || '').trim();
    const RAW_DIRECT_BACKEND_URL = (import.meta.env.VITE_DIRECT_BACKEND_BASE_URL || '').trim();

    const [loading, setLoading] = useState(true);

    useEffect(() => {
        if (!supabase) {
            setLoading(false);
            return;
        }

        // 1. Obtener sesión inicial
        supabase.auth.getSession().then(({ data: { session }, error }) => {
            if (error) {
                console.error("Error validando sesión:", error);
                supabase.auth.signOut();
                setLoading(false);
                return;
            }

            setSession(session);
            if (session) {
                fetchEffectiveAccessRole(session.access_token);
                fetchProfile(session.user.id);
                fetchUserMalls(session.access_token, session.user.id);
            }
            else setLoading(false);
        });

        // 2. Escuchar cambios de autenticación
        const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
            setSession(session);
            if (session) {
                fetchEffectiveAccessRole(session.access_token);
                fetchProfile(session.user.id);
                fetchUserMalls(session.access_token, session.user.id);
            }
            else {
                setUser(null);
                setRole(null);
                setPermissions({});
                setMalls([]);
                setCurrentMall(null);
                setLoading(false);
                localStorage.removeItem('msmall_current_mall_id');
            }
        });

        return () => subscription.unsubscribe();
    }, []);

    const normalizeMallsPayload = (payload) => {
        if (Array.isArray(payload)) return payload;
        if (payload && Array.isArray(payload.data)) return payload.data;
        if (payload && Array.isArray(payload.malls)) return payload.malls;
        return [];
    };

    const getApiBaseCandidates = () => {
        const normalizeApiRoot = (value) => (value || '')
            .trim()
            .replace(/\/+$/, '')
            .replace(/\/api\/v1$/i, '')
            .replace(/\/api$/i, '');

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

    const fetchJsonFromCandidates = async (path, token) => {
        const bases = getApiBaseCandidates();

        for (const base of bases) {
            const endpoint = `${base}${path}`;
            try {
                let res = await fetch(endpoint, {
                    headers: {
                        'Authorization': `Bearer ${token}`,
                        'Accept': 'application/json'
                    },
                    cache: 'no-store'
                });

                if (res.status === 304) {
                    res = await fetch(`${endpoint}?_t=${Date.now()}`, {
                        headers: {
                            'Authorization': `Bearer ${token}`,
                            'Accept': 'application/json'
                        },
                        cache: 'no-store'
                    });
                }

                if (!res.ok) continue;

                const raw = await res.text();
                if (!raw || raw.trim().startsWith('<')) {
                    // HTML payload, try next candidate.
                    continue;
                }

                try {
                    return JSON.parse(raw);
                } catch {
                    continue;
                }
            } catch {
                // Try next candidate
            }
        }

        return null;
    };

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

    const fetchMallsFromAdminFallback = async (token, userId) => {
        if (!userId) return [];
        try {
            const [usersPayload, mallsPayload] = await Promise.all([
                fetchJsonFromCandidates('/api/v1/admin/users', token),
                fetchJsonFromCandidates('/api/v1/malls/all', token)
            ]);

            const users = normalizeMallsPayload(usersPayload || []);
            const allMalls = normalizeMallsPayload(mallsPayload || []);
            if (!users.length || !allMalls.length) return [];
            const byId = new Map(allMalls.map((m) => [m.id, m]));
            const me = users.find((u) => u.id === userId);
            const links = Array.isArray(me?.malls) ? me.malls : [];

            const resolved = links
                .map((link) => {
                    const mall = byId.get(link.mall_id);
                    if (!mall) return null;
                    return {
                        id: link.mall_id,
                        nombre: mall.nombre,
                        rol: link.rol || 'auditor'
                    };
                })
                .filter(Boolean);

            return resolved;
        } catch {
            return [];
        }
    };

    const fetchUserMalls = async (token, userId) => {
        try {
            let data = normalizeMallsPayload(
                await fetchJsonFromCandidates('/api/v1/users/me/malls', token)
            );

            if (!Array.isArray(data)) {
                console.error("Error fetching malls: unexpected payload shape", data);
                data = [];
            }

            if (data.length === 0) {
                const fallback = await fetchMallsFromAdminFallback(token, userId);
                if (fallback.length > 0) {
                    data = fallback;
                }
            }

            setMalls(data);
            localStorage.setItem(USER_MALLS_STORAGE_KEY, JSON.stringify(data));

            // Logic to select initial mall
            if (data.length > 0) {
                const savedMallId = localStorage.getItem('msmall_current_mall_id');
                const savedMall = data.find(m => m.id === savedMallId);

                if (savedMall) {
                    setCurrentMall(savedMall);
                } else {
                    // Default to first
                    setCurrentMall(data[0]);
                    localStorage.setItem('msmall_current_mall_id', data[0].id);
                }
            } else {
                setCurrentMall(null);
                localStorage.removeItem('msmall_current_mall_id');
            }
        } catch (error) {
            console.error("Error fetching malls:", error);
            // Fallback to last known malls to avoid losing selector on transient errors.
            try {
                const cached = localStorage.getItem(USER_MALLS_STORAGE_KEY);
                if (cached) {
                    const parsed = JSON.parse(cached);
                    if (Array.isArray(parsed) && parsed.length > 0) {
                        setMalls(parsed);
                    }
                }
            } catch (_) {
                // ignore cache parse errors
            }
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
            // Optional: Reload page to force refresh of all components
            window.location.reload();
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
        loading,
        setCurrentMall: handleSetCurrentMall,
        isAdmin: isSystemAdmin || ['admin', 'superadmin', 'super_admin', 'administrador'].includes(normalizedRole),
        isTic: ['tic', 'it'].includes(normalizedRole),
        isAuditor: normalizedRole === 'auditor',
        signOut: () => supabase?.auth.signOut(),
        changePassword,
        refreshMalls: () => session?.access_token && fetchUserMalls(session.access_token, session?.user?.id),
    };

    return (
        <AuthContext.Provider value={value}>
            {children}
        </AuthContext.Provider>
    );
};

export const useAuth = () => useContext(AuthContext);
