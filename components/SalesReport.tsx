
import React, { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthProvider';
import { SaleReport, DateRange, SaleDetail } from '../types';
import { ApiService } from '../api';
import { MissingDaysAlert } from './MissingDaysAlert';
import { FileSpreadsheet, FileText, ChevronRight, ChevronDown, Loader2 } from 'lucide-react';
import { formatCurrency, formatNumber } from '../utils/formatters';
import { useFormatCurrency } from '../hooks/useFormatCurrency';
import { ReporteAuditoriaTable } from './ReporteAuditoriaTable';

export const SalesReport: React.FC = () => {
  const { currentMall, session } = useAuth();
  const { format } = useFormatCurrency();
  const DEFAULT_RAILWAY_BASE_URL = 'https://msmall-02-production.up.railway.app';

  const [data, setData] = useState<SaleReport[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isExporting, setIsExporting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Export Modal State
  const [showExportModal, setShowExportModal] = useState(false);
  const [exportFormat, setExportFormat] = useState<'excel' | 'pdf' | null>(null);

  // Drill-down states
  const [expandedLocalId, setExpandedLocalId] = useState<string | null>(null);
  const [detailsData, setDetailsData] = useState<Record<string, SaleDetail[]>>({});
  const [loadingDetails, setLoadingDetails] = useState<Record<string, boolean>>({});

  const [dates, setDates] = useState<DateRange>(() => {
    const now = new Date();
    const firstDay = new Date(now.getFullYear(), now.getMonth(), 1);
    return {
      startDate: firstDay.toISOString().split('T')[0],
      endDate: now.toISOString().split('T')[0]
    };
  });

  // Stores state
  const [stores, setStores] = useState<any[]>([]);
  const [selectedLocal, setSelectedLocal] = useState<string>('');

  const normalizeApiRoot = (value: string): string => {
    const trimmed = String(value || '').trim();
    if (!trimmed) return '';
    return trimmed.replace(/\/+$/, '').replace(/\/api\/v1$/i, '').replace(/\/api$/i, '');
  };

  const getExportBaseCandidates = (): string[] => {
    const configuredApiBase = normalizeApiRoot(import.meta.env.VITE_API_URL || '');
    const directApiBase = normalizeApiRoot(import.meta.env.VITE_DIRECT_BACKEND_BASE_URL || '');
    const isVercelHost = typeof window !== 'undefined' && window.location.hostname.endsWith('vercel.app');

    return Array.from(new Set([
      configuredApiBase,
      directApiBase,
      ...(isVercelHost ? [DEFAULT_RAILWAY_BASE_URL] : []),
      '' // Relative fallback via Vercel rewrite
    ]));
  };

  const fetchData = async () => {
    if (!currentMall) return;
    setIsLoading(true);
    setError(null);
    setExpandedLocalId(null);
    setDetailsData({});
    try {
      const result = await ApiService.getSalesReport({ ...dates, mallId: currentMall.id }, selectedLocal || undefined);
      setData(result);
    } catch (err) {
      console.error(err);
      setError('Error al cargar datos.');
    } finally {
      setIsLoading(false);
    }
  };

  const openExportModal = (format: 'excel' | 'pdf') => {
    setExportFormat(format);
    setShowExportModal(true);
  };

  const handleExport = async (type: 'detailed' | 'summary') => {
    if (!exportFormat || !currentMall) return;
    setIsExporting(true);
    setShowExportModal(false);
    try {
      const endpoint = exportFormat === 'excel' ? 'excel' : 'pdf';
      const ext = exportFormat === 'excel' ? 'xlsx' : 'pdf';

      const paramsObj: any = {
        fecha_inicio: dates.startDate,
        fecha_fin: dates.endDate,
        type: type
      };

      if (selectedLocal) {
        paramsObj.local_id = selectedLocal;
      }

      const params = new URLSearchParams(paramsObj);

      const token = session?.access_token;
      const headers: HeadersInit = {
        'X-Mall-Id': currentMall.id
      };
      if (token) headers['Authorization'] = `Bearer ${token}`;
      headers['Accept'] = exportFormat === 'excel'
        ? 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet, application/octet-stream'
        : 'application/pdf, application/octet-stream';

      let blob: Blob | null = null;
      let lastError = 'No se pudo exportar el reporte.';

      for (const base of getExportBaseCandidates()) {
        const exportUrl = `${base}/api/v1/export/sales-report/${endpoint}?${params.toString()}`;
        try {
          const response = await fetch(exportUrl, { headers });
          if (!response.ok) {
            lastError = `Export failed (${response.status})`;
            continue;
          }

          const contentType = (response.headers.get('content-type') || '').toLowerCase();
          const candidateBlob = await response.blob();

          const looksLikeExpectedFile = exportFormat === 'excel'
            ? contentType.includes('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet') ||
              contentType.includes('application/octet-stream')
            : contentType.includes('application/pdf') ||
              contentType.includes('application/octet-stream');

          if (!looksLikeExpectedFile) {
            const previewText = (await candidateBlob.text()).slice(0, 200).toLowerCase();
            if (previewText.includes('<!doctype html') || previewText.includes('<html')) {
              lastError = 'El servidor devolvió HTML en lugar del archivo exportable. Verifica la URL del backend/rewrite.';
              continue;
            }
            if (previewText.startsWith('{')) {
              lastError = `La API devolvió una respuesta inesperada al exportar.`;
              continue;
            }
          }

          blob = candidateBlob;
          break;
        } catch (err: any) {
          lastError = err?.message || lastError;
        }
      }

      if (!blob) throw new Error(lastError);

      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `reporte_ventas_${type}_${dates.startDate}_${dates.endDate}.${ext}`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (e) {
      console.error('Export error:', e);
      alert('Error al exportar.');
    } finally {
      setIsExporting(false);
      setExportFormat(null);
    }
  };

  const toggleRow = async (localId: string) => {
    // ... existing toggleRow implementation ...
    if (expandedLocalId === localId) {
      setExpandedLocalId(null);
      return;
    }

    setExpandedLocalId(localId);

    // Fetch details if not already cached
    if (!detailsData[localId]) {
      setLoadingDetails(prev => ({ ...prev, [localId]: true }));
      try {
        const details = await ApiService.getSaleDetails(localId, { ...dates, mallId: currentMall?.id });
        setDetailsData(prev => ({ ...prev, [localId]: details }));
      } catch (err) {
        console.error('Error fetching details:', err);
      } finally {
        setLoadingDetails(prev => ({ ...prev, [localId]: false }));
      }
    }
  };

  useEffect(() => {
    const loadStores = async () => {
      try {
        if (currentMall) {
          const locals = await ApiService.getStores(currentMall.id);
          setStores(locals);
        }
      } catch (e) {
        console.error("Error loading stores", e);
      }
    };
    loadStores();
  }, [currentMall]);

  useEffect(() => {
    fetchData();
  }, [dates, selectedLocal, currentMall]); // Refetch when dates or local changes

  const totalSales = data.reduce((sum, item) => sum + item.total_neto, 0);

  return (
    <div className="space-y-6 relative">
      {/* Export Modal */}
      {showExportModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-sm p-6 transform transition-all scale-100">
            <h3 className="text-lg font-bold text-slate-800 mb-2">Seleccionar Tipo de Reporte</h3>
            <p className="text-slate-500 text-sm mb-6">
              ¿Desea descargar un resumen consolidado o incluir el detalle de todas las facturas? {exportFormat?.toUpperCase()}
            </p>

            <div className="flex flex-col gap-3">
              <button
                onClick={() => handleExport('summary')}
                className="w-full flex items-center justify-between p-4 rounded-xl border border-slate-200 hover:border-indigo-500 hover:bg-indigo-50 transition-colors group"
              >
                <div className="text-left">
                  <span className="block font-bold text-slate-700 group-hover:text-indigo-700">Resumido</span>
                  <span className="text-xs text-slate-400">Solo totales por local</span>
                </div>
                <div className="h-2 w-2 rounded-full bg-slate-300 group-hover:bg-indigo-500"></div>
              </button>

              <button
                onClick={() => handleExport('detailed')}
                className="w-full flex items-center justify-between p-4 rounded-xl border border-slate-200 hover:border-indigo-500 hover:bg-indigo-50 transition-colors group"
              >
                <div className="text-left">
                  <span className="block font-bold text-slate-700 group-hover:text-indigo-700">Detallado</span>
                  <span className="text-xs text-slate-400">Totales + Lista de Facturas</span>
                </div>
                <div className="h-2 w-2 rounded-full bg-slate-300 group-hover:bg-indigo-500"></div>
              </button>
            </div>

            <button
              onClick={() => setShowExportModal(false)}
              className="mt-6 w-full py-2 text-sm font-medium text-slate-400 hover:text-slate-600 transition-colors"
            >
              Cancelar
            </button>
          </div>
        </div>
      )}

      {/* Filters Header */}
      <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-6 flex flex-col md:flex-row items-center justify-between gap-4">
        <div>
          <h3 className="text-xl font-bold text-slate-800">Reporte de Auditoría</h3>
          <p className="text-slate-500 text-sm">Resumen de ventas por local en el periodo seleccionado.</p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2">
            <span className="text-xs font-medium text-slate-400">Desde:</span>
            <input
              type="date"
              value={dates.startDate}
              onChange={(e) => setDates({ ...dates, startDate: e.target.value })}
              className="px-3 py-2 rounded-lg border border-slate-200 text-sm focus:ring-2 focus:ring-indigo-500 outline-none"
            />
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs font-medium text-slate-400">Hasta:</span>
            <input
              type="date"
              value={dates.endDate}
              onChange={(e) => setDates({ ...dates, endDate: e.target.value })}
              className="px-3 py-2 rounded-lg border border-slate-200 text-sm focus:ring-2 focus:ring-indigo-500 outline-none"
            />
          </div>

          <div className="flex items-center gap-2">
            <span className="text-xs font-medium text-slate-400">Local:</span>
            <select
              value={selectedLocal}
              onChange={(e) => setSelectedLocal(e.target.value)}
              className="px-3 py-2 rounded-lg border border-slate-200 text-sm focus:ring-2 focus:ring-indigo-500 outline-none min-w-[150px]"
            >
              <option value="">Todos los Locales</option>
              {stores.map((store) => (
                <option key={store.id} value={store.id}>
                  {store.nombre}
                </option>
              ))}
            </select>
          </div>

          <button
            onClick={fetchData}
            className="bg-indigo-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-indigo-700 transition-colors"
          >
            Actualizar
          </button>

          <div className="h-6 w-px bg-slate-200 mx-1"></div>

          <button
            onClick={() => openExportModal('excel')}
            disabled={isExporting}
            className="flex items-center gap-2 px-3 py-2 bg-emerald-600 text-white rounded-lg text-sm font-medium hover:bg-emerald-700 transition-colors disabled:opacity-50"
            title="Exportar Excel"
          >
            {isExporting ? <Loader2 size={16} className="animate-spin" /> : <FileSpreadsheet size={16} />}
          </button>

          <button
            onClick={() => openExportModal('pdf')}
            disabled={isExporting}
            className="flex items-center gap-2 px-3 py-2 bg-rose-600 text-white rounded-lg text-sm font-medium hover:bg-rose-700 transition-colors disabled:opacity-50"
            title="Exportar PDF"
          >
            {isExporting ? <Loader2 size={16} className="animate-spin" /> : <FileText size={16} />}
          </button>
        </div>
      </div>

      {/* Global & Local Gap Analysis Alert */}
      <MissingDaysAlert
        localId={selectedLocal || null}
        startDate={dates.startDate}
        endDate={dates.endDate}
        onSelectLocal={setSelectedLocal}
      />

      {/* Stats Overview */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="bg-indigo-600 rounded-2xl p-6 text-white shadow-md">
          <p className="text-indigo-100 text-sm font-medium">Ventas Totales (Neto)</p>
          <p className="text-3xl font-bold mt-2">{format(totalSales)}</p>
        </div>
        <div className="bg-white rounded-2xl p-6 border border-slate-200 shadow-sm">
          <p className="text-slate-400 text-sm font-medium">Locales Auditados</p>
          <p className="text-3xl font-bold mt-2 text-slate-800">{data.length}</p>
        </div>
        <div className="bg-white rounded-2xl p-6 border border-slate-200 shadow-sm">
          <p className="text-slate-400 text-sm font-medium">Malls Reportando</p>
          <p className="text-3xl font-bold mt-2 text-slate-800">{new Set(data.map(d => d.mall_nombre)).size}</p>
        </div>
      </div>

      {/* Main Table */}
      <div className="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden">
        {error && (
          <div className="bg-amber-50 border-b border-amber-100 p-4 text-amber-700 text-sm flex items-center gap-2">
            ⚠️ <span>{error}</span>
          </div>
        )}

        <ReporteAuditoriaTable
          data={data}
          isLoading={isLoading}
          detailsData={detailsData}
          loadingDetails={loadingDetails}
          toggleRow={toggleRow}
          expandedLocalId={expandedLocalId}
        />
      </div>
    </div>
  );
};
