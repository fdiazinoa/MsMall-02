
import React from 'react';
import { AppTab } from './appTabs';
import { UploadForm } from './UploadForm';
import { StoreImportTool } from './StoreImportTool';
import { SalesReport } from './SalesReport';
import { DashboardKPIs } from './DashboardKPIs';
import { StoreMaintenance } from './StoreMaintenance';
import { StoreCatalogManager } from './StoreCatalogManager';
import { UserManagement } from './UserManagement';
import { ImportManager } from './ImportManager';

import { LoadMonitor } from './LoadMonitor';
import { SmartInsights } from './SmartInsights';
import { FinancialDashboard } from './FinancialDashboard';
import { SalesCube } from './SalesCube';
import { MallManager } from './MallManager';
import { PeriodComparison } from './PeriodComparison';
import { ResendMessagingAdmin } from './ResendMessagingAdmin';
import { SecurityTokenAdmin } from './SecurityTokenAdmin';
import { CopilotSettings } from './CopilotSettings';
import { OperationsCenter } from './OperationsCenter';

interface DashboardProps {
  activeTab: AppTab;
  setActiveTab: (tab: AppTab) => void;
}

export const Dashboard: React.FC<DashboardProps> = ({ activeTab, setActiveTab }) => {
  switch (activeTab) {
    case 'analytics':
      return <DashboardKPIs />;
    case 'reports':
      return <SalesReport />;
    case 'upload':
      return <UploadForm />;
    case 'store-import':
      return <StoreImportTool />;
    case 'stores':
      return <StoreMaintenance onOpenCatalogs={() => setActiveTab('store-catalogs')} />;
    case 'store-catalogs':
      return <StoreCatalogManager />;
    case 'users':
      return <UserManagement />;
    case 'security':
      return <SecurityTokenAdmin />;
    case 'auto-import':
      return <ImportManager initialSection="ftp" />;
    case 'erp-webservice':
      return <ImportManager initialSection="webservice" onCloseWebserviceModal={() => setActiveTab('auto-import')} />;
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
    case 'messaging':
      return <ResendMessagingAdmin />;
    case 'operations':
      return <OperationsCenter />;
    case 'copilot':
      return <CopilotSettings />;
    default:
      return <DashboardKPIs />;
  }
};
