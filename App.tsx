import React, { useState, Suspense } from 'react';
import { Dashboard } from './components/Dashboard';
import { Sidebar } from './components/Sidebar';
import { Header } from './components/Header';
import { useAuth } from './context/AuthProvider';
import { supabase } from './api';

// Suppress Recharts deprecation warnings (XAxis, YAxis defaultProps)
const originalConsoleError = console.error;
console.error = (...args: any[]) => {
  if (typeof args[0] === 'string' && /defaultProps/.test(args[0])) {
    return;
  }
  originalConsoleError(...args);
};

const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'upload' | 'reports' | 'analytics' | 'big-data' | 'stores' | 'users' | 'auto-import' | 'monitor' | 'insights' | 'financial' | 'cube' | 'malls' | 'comparisons'>('analytics');
  const { session, loading } = useAuth();

  // Estados para el login
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [authError, setAuthError] = useState<string | null>(null);
  const [isLoggingIn, setIsLoggingIn] = useState(false);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!supabase) {
      setAuthError("Supabase no está configurado. Revisa el archivo .env");
      return;
    }

    setIsLoggingIn(true);
    setAuthError(null);

    try {
      const { error } = await supabase.auth.signInWithPassword({
        email,
        password,
      });

      if (error) throw error;
    } catch (error: any) {
      setAuthError(error.message || "Error al iniciar sesión");
    } finally {
      setIsLoggingIn(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-slate-900">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-indigo-500"></div>
      </div>
    );
  }

  if (!session) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-slate-900 text-white p-6">
        <div className="max-w-md w-full bg-slate-800 p-8 rounded-3xl border border-slate-700 shadow-2xl">
          <div className="w-16 h-16 bg-indigo-600 rounded-2xl flex items-center justify-center font-bold text-2xl mx-auto mb-6 shadow-lg shadow-indigo-500/20">M</div>
          <h2 className="text-2xl font-bold mb-2 text-center">Bienvenido a MSMALL</h2>
          <p className="text-slate-400 mb-8 text-center">Inicia sesión para acceder al sistema de auditoría.</p>

          <form onSubmit={handleLogin} className="space-y-4">
            <div>
              <label className="block text-xs font-bold text-slate-500 uppercase mb-1.5 ml-1">Email</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="tu@email.com"
                className="w-full bg-slate-900 border border-slate-700 rounded-xl px-4 py-3 text-white placeholder:text-slate-600 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 transition-all"
                required
              />
            </div>
            <div>
              <label className="block text-xs font-bold text-slate-500 uppercase mb-1.5 ml-1">Contraseña</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                className="w-full bg-slate-900 border border-slate-700 rounded-xl px-4 py-3 text-white placeholder:text-slate-600 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 transition-all"
                required
              />
            </div>

            {authError && (
              <div className="p-3 bg-red-500/10 border border-red-500/20 rounded-xl text-red-400 text-xs">
                {authError}
              </div>
            )}

            {!supabase && (
              <div className="p-3 bg-amber-500/10 border border-amber-500/20 rounded-xl text-amber-400 text-xs">
                ⚠️ Supabase no configurado. Edita el archivo .env
              </div>
            )}

            <button
              type="submit"
              disabled={isLoggingIn || !supabase}
              className="w-full py-3 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed rounded-xl font-bold transition-all shadow-lg shadow-indigo-600/20"
            >
              {isLoggingIn ? 'Iniciando sesión...' : 'Entrar'}
            </button>
          </form>

          <div className="mt-8 pt-6 border-t border-slate-700/50 text-center">
            <button
              onClick={() => window.location.reload()}
              className="text-slate-500 hover:text-indigo-400 text-sm transition-colors"
            >
              Reintentar Conexión
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen bg-slate-50">
      <Sidebar activeTab={activeTab} setActiveTab={setActiveTab} />

      <div className="flex-1 flex flex-col">
        <Header activeTab={activeTab} setActiveTab={setActiveTab} />

        <main className="p-6 md:p-10 flex-1 overflow-y-auto">
          <div className="max-w-7xl mx-auto">
            <Suspense fallback={
              <div className="flex items-center justify-center h-64">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600"></div>
              </div>
            }>
              <Dashboard activeTab={activeTab} />
            </Suspense>
          </div>
        </main>

        <footer className="border-t border-slate-200 py-4 px-6 text-center text-sm text-slate-500">
          &copy; {new Date().getFullYear()} MSMALL Audit Systems - Prototipo MVP
        </footer>
      </div>
    </div>
  );
};

export default App;
