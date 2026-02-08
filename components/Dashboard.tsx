
import React from 'react';
import { UploadForm } from './UploadForm';
import { SalesReport } from './SalesReport';
import { DashboardKPIs } from './DashboardKPIs';
import { StoreMaintenance } from './StoreMaintenance';
import { UserManagement } from './UserManagement';
import { ImportManager } from './ImportManager';

import { LoadMonitor } from './LoadMonitor';
import { SmartInsights } from './SmartInsights';
import { FinancialDashboard } from './FinancialDashboard';
import { SalesCube } from './SalesCube';
import { MallManager } from './MallManager';
import { PeriodComparison } from './PeriodComparison';

interface DashboardProps {
  activeTab: 'upload' | 'reports' | 'analytics' | 'stores' | 'users' | 'auto-import' | 'monitor' | 'insights' | 'financial' | 'cube' | 'malls' | 'comparisons';
}

export const Dashboard: React.FC<DashboardProps> = ({ activeTab }) => {
  switch (activeTab) {
    case 'analytics':
      return <DashboardKPIs />;
    case 'reports':
      return <SalesReport />;
    case 'upload':
      return <UploadForm />;
    case 'stores':
      return <StoreMaintenance />;
    case 'users':
      return <UserManagement />;
    case 'auto-import':
      return <ImportManager />;
    case 'monitor':
      return <LoadMonitor />;
    case 'financial':
      return <FinancialDashboard />;
    case 'insights':
      return <SmartInsights />;
    case 'cube':
      return <SalesCube />;
    case 'malls':
      return <MallManager />;
    case 'comparisons':
      return <PeriodComparison />;
    default:
      return <DashboardKPIs />;
  }
};
