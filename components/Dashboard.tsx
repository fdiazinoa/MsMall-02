
import React from 'react';
import { UploadForm } from './UploadForm';
import { SalesReport } from './SalesReport';
import { DashboardKPIs } from './DashboardKPIs';
import { StoreMaintenance } from './StoreMaintenance';
import { UserManagement } from './UserManagement';
import { ImportManager } from './ImportManager';

interface DashboardProps {
  activeTab: 'upload' | 'reports' | 'analytics' | 'stores' | 'users' | 'auto-import';
}

export const Dashboard: React.FC<DashboardProps> = ({ activeTab }) => {
  return (
    <div className="space-y-6">
      {activeTab === 'analytics' && <DashboardKPIs />}
      {activeTab === 'reports' && <SalesReport />}
      {activeTab === 'upload' && <UploadForm />}
      {activeTab === 'stores' && <StoreMaintenance />}
      {activeTab === 'users' && <UserManagement />}
      {activeTab === 'auto-import' && <ImportManager />}
    </div>
  );
};
