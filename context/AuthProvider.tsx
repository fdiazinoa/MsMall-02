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
            const res = await fetch(`${import.meta.env.VITE_API_URL || ''}/api/v1/users/me/malls`, {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            if (res.ok) {
                const data = await res.json();
                setMalls(data);

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
                }
            }
        } catch (error) {
            console.error("Error fetching malls:", error);
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
