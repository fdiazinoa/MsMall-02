
import React, { useState, Suspense } from 'react';
import { Dashboard } from './components/Dashboard';
import { Sidebar } from './components/Sidebar';
import { Header } from './components/Header';

const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'upload' | 'reports' | 'analytics' | 'stores' | 'users' | 'auto-import'>('analytics');

  return (
    <div className="flex min-h-screen bg-slate-50">
      <Sidebar activeTab={activeTab} setActiveTab={setActiveTab} />
      
      <div className="flex-1 flex flex-col">
        <Header />
        
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
