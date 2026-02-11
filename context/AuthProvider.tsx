// PASO 3: Frontend (React - Contexto y Rutas)
import React, { createContext, useContext, useEffect, useState } from 'react';
import { supabase } from '../api'; // Asumiendo que supabase client está exportado en api.ts

const AuthContext = createContext();

export const AuthProvider = ({ children }) => {
    const [session, setSession] = useState(null);
    const [user, setUser] = useState(null);
    const [role, setRole] = useState(null);
    // Multi-Tenant States
    const [malls, setMalls] = useState([]);
    const [currentMall, setCurrentMall] = useState(null);
    const USER_MALLS_STORAGE_KEY = 'msmall_user_malls';

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
                fetchProfile(session.user.id);
                fetchUserMalls(session.access_token);
            }
            else setLoading(false);
        });

        // 2. Escuchar cambios de autenticación
        const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
            setSession(session);
            if (session) {
                fetchProfile(session.user.id);
                fetchUserMalls(session.access_token);
            }
            else {
                setUser(null);
                setRole(null);
                setMalls([]);
                setCurrentMall(null);
                setLoading(false);
                localStorage.removeItem('msmall_current_mall_id');
            }
        });

        return () => subscription.unsubscribe();
    }, []);

    const fetchUserMalls = async (token) => {
        try {
            const endpoint = `${import.meta.env.VITE_API_URL || ''}/api/v1/users/me/malls`;
            let res = await fetch(endpoint, {
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Accept': 'application/json'
                },
                cache: 'no-store'
            });

            // Some edge caches can still reply 304; retry with cache-busting.
            if (res.status === 304) {
                res = await fetch(`${endpoint}?_t=${Date.now()}`, {
                    headers: {
                        'Authorization': `Bearer ${token}`,
                        'Accept': 'application/json'
                    },
                    cache: 'no-store'
                });
            }

            const contentType = res.headers.get('content-type') || '';

            if (!res.ok) {
                const body = contentType.includes('application/json')
                    ? await res.json().catch(() => ({}))
                    : await res.text().catch(() => '');
                console.error("Error fetching malls:", res.status, body);
                // Keep previous selector state if request fails.
                return;
            }

            // Parse robustly in case content-type header is missing/misreported.
            const raw = await res.text();
            let data = [];
            try {
                data = contentType.includes('application/json') ? JSON.parse(raw) : JSON.parse(raw);
            } catch {
                console.error("Error fetching malls: invalid JSON payload:", raw.slice(0, 120));
                return;
            }
            if (!Array.isArray(data)) {
                console.error("Error fetching malls: unexpected payload shape", data);
                return;
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
                setRole(data.role);
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

    const value = {
        session,
        user,
        role,
        malls,
        currentMall,
        loading,
        setCurrentMall: handleSetCurrentMall,
        isAdmin: role === 'admin',
        isTic: role === 'tic',
        isAuditor: role === 'auditor',
        signOut: () => supabase?.auth.signOut(),
        refreshMalls: () => session?.access_token && fetchUserMalls(session.access_token),
    };

    return (
        <AuthContext.Provider value={value}>
            {children}
        </AuthContext.Provider>
    );
};

export const useAuth = () => useContext(AuthContext);
