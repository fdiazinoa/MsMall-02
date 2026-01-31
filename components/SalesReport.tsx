
import React, { useState, useEffect } from 'react';
import { SaleReport, DateRange, SaleDetail } from '../types';
import { ApiService } from '../api';
import { ChevronDown, ChevronRight, Loader2 } from 'lucide-react';

export const SalesReport: React.FC = () => {
  const [data, setData] = useState<SaleReport[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

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

  const fetchData = async () => {
    setIsLoading(true);
    setError(null);
    setExpandedLocalId(null); // Reset expansion on refresh
    setDetailsData({}); // Clear details cache on refresh to ensure new dates are respected
    try {
      const result = await ApiService.getSalesReport(dates);
      setData(result);
    } catch (err) {
      console.error(err);
      setError('Error al cargar datos. Mostrando demo local.');
    } finally {
      setIsLoading(false);
    }
  };

  const toggleRow = async (localId: string) => {
    if (expandedLocalId === localId) {
      setExpandedLocalId(null);
      return;
    }

    setExpandedLocalId(localId);

    // Fetch details if not already cached
    if (!detailsData[localId]) {
      setLoadingDetails(prev => ({ ...prev, [localId]: true }));
      try {
        const details = await ApiService.getSaleDetails(localId, dates);
        setDetailsData(prev => ({ ...prev, [localId]: details }));
      } catch (err) {
        console.error('Error fetching details:', err);
      } finally {
        setLoadingDetails(prev => ({ ...prev, [localId]: false }));
      }
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const totalSales = data.reduce((sum, item) => sum + item.total_bruto, 0);

  return (
    <div className="space-y-6">
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
          <button
            onClick={fetchData}
            className="bg-indigo-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-indigo-700 transition-colors"
          >
            Actualizar
          </button>
        </div>
      </div>

      {/* Stats Overview */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="bg-indigo-600 rounded-2xl p-6 text-white shadow-md">
          <p className="text-indigo-100 text-sm font-medium">Ventas Totales (Neto)</p>
          <p className="text-3xl font-bold mt-2">${totalSales.toLocaleString('es-CL', { minimumFractionDigits: 2 })}</p>
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

        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead className="bg-slate-50 border-b border-slate-200">
              <tr>
                <th className="w-10 px-4 py-4"></th>
                <th className="px-6 py-4 text-xs font-semibold text-slate-500 uppercase tracking-wider">Local</th>
                <th className="px-6 py-4 text-xs font-semibold text-slate-500 uppercase tracking-wider">Centro Comercial</th>
                <th className="px-6 py-4 text-xs font-semibold text-slate-500 uppercase tracking-wider text-right">Total Bruto</th>
                <th className="px-6 py-4 text-xs font-semibold text-slate-500 uppercase tracking-wider text-right">Impuestos</th>
                <th className="px-6 py-4 text-xs font-semibold text-slate-500 uppercase tracking-wider text-right">Total Neto</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {isLoading ? (
                <tr>
                  <td colSpan={6} className="px-6 py-20 text-center text-slate-400">Cargando datos...</td>
                </tr>
              ) : data.length > 0 ? (
                data.map((row, idx) => {
                  const details = detailsData[row.local_id] || [];
                  const subTotalBruto = details.reduce((sum, d) => sum + d.total_bruto, 0);
                  const subTotalImpuestos = details.reduce((sum, d) => sum + d.total_impuestos, 0);
                  const subTotalNeto = details.reduce((sum, d) => sum + d.total_neto, 0);

                  return (
                    <React.Fragment key={row.local_id}>
                      <tr
                        className={`hover:bg-slate-50 transition-colors cursor-pointer ${expandedLocalId === row.local_id ? 'bg-slate-50/80' : ''}`}
                        onClick={() => toggleRow(row.local_id)}
                      >
                        <td className="px-4 py-4 text-center">
                          {expandedLocalId === row.local_id ? (
                            <ChevronDown size={18} className="text-indigo-600" />
                          ) : (
                            <ChevronRight size={18} className="text-slate-400" />
                          )}
                        </td>
                        <td className="px-6 py-4 font-medium text-slate-800">{row.local_nombre}</td>
                        <td className="px-6 py-4 text-slate-500">{row.mall_nombre}</td>
                        <td className="px-6 py-4 text-right font-mono font-medium text-slate-700">${row.total_neto.toLocaleString('es-CL', { minimumFractionDigits: 2 })}</td>
                        <td className="px-6 py-4 text-right font-mono text-slate-400">${row.total_impuestos.toLocaleString('es-CL', { minimumFractionDigits: 2 })}</td>
                        <td className="px-6 py-4 text-right font-mono font-bold text-indigo-600">${row.total_bruto.toLocaleString('es-CL', { minimumFractionDigits: 2 })}</td>
                      </tr>

                      {/* Expandable Detail Row */}
                      {expandedLocalId === row.local_id && (
                        <tr>
                          <td colSpan={6} className="px-0 py-0 bg-slate-50/50">
                            <div className="p-6 border-l-4 border-indigo-500 animate-in slide-in-from-top-2 duration-200">
                              <h4 className="text-sm font-bold text-slate-700 mb-4 flex items-center gap-2">
                                Detalle de Facturas - {row.local_nombre}
                                {loadingDetails[row.local_id] && <Loader2 size={14} className="animate-spin text-indigo-500" />}
                              </h4>

                              <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
                                <table className="w-full text-left text-xs">
                                  <thead className="bg-slate-100/80 border-b border-slate-200 text-slate-500 font-bold uppercase tracking-tighter">
                                    <tr>
                                      <th className="px-4 py-3">Fecha</th>
                                      <th className="px-4 py-3">Hora</th>
                                      <th className="px-4 py-3">Nro Factura</th>
                                      <th className="px-4 py-3 text-right">Neto</th>
                                      <th className="px-4 py-3 text-right">Impuesto</th>
                                      <th className="px-4 py-3 text-right">Bruto</th>
                                    </tr>
                                  </thead>
                                  <tbody className="divide-y divide-slate-100">
                                    {loadingDetails[row.local_id] ? (
                                      <tr>
                                        <td colSpan={6} className="px-4 py-8 text-center text-slate-400 italic">
                                          Cargando boletas...
                                        </td>
                                      </tr>
                                    ) : details.length > 0 ? (
                                      <>
                                        {details.map((detail) => (
                                          <tr key={detail.id} className="hover:bg-slate-50/80 transition-colors">
                                            <td className="px-4 py-2.5 text-slate-600">{detail.fecha}</td>
                                            <td className="px-4 py-2.5 text-slate-500">{detail.hora}</td>
                                            <td className="px-4 py-2.5 font-medium text-slate-700">{detail.factura_no}</td>
                                            <td className="px-4 py-2.5 text-right font-mono">${detail.total_bruto.toLocaleString('es-CL', { minimumFractionDigits: 2 })}</td>
                                            <td className="px-4 py-2.5 text-right font-mono text-slate-400">${detail.total_impuestos.toLocaleString('es-CL', { minimumFractionDigits: 2 })}</td>
                                            <td className="px-4 py-2.5 text-right font-mono font-bold text-slate-700">${detail.total_neto.toLocaleString('es-CL', { minimumFractionDigits: 2 })}</td>
                                          </tr>
                                        ))}
                                        {/* Summary Row */}
                                        <tr className="bg-slate-50 font-bold border-t-2 border-slate-200">
                                          <td colSpan={3} className="px-4 py-3 text-right text-slate-500 uppercase tracking-wider">Totales Detalle:</td>
                                          <td className="px-4 py-3 text-right font-mono text-slate-800">${subTotalBruto.toLocaleString('es-CL', { minimumFractionDigits: 2 })}</td>
                                          <td className="px-4 py-3 text-right font-mono text-slate-500">${subTotalImpuestos.toLocaleString('es-CL', { minimumFractionDigits: 2 })}</td>
                                          <td className="px-4 py-3 text-right font-mono text-indigo-600">${subTotalNeto.toLocaleString('es-CL', { minimumFractionDigits: 2 })}</td>
                                        </tr>
                                      </>
                                    ) : (
                                      <tr>
                                        <td colSpan={6} className="px-4 py-8 text-center text-slate-400 italic">
                                          No se encontraron facturas detalladas.
                                        </td>
                                      </tr>
                                    )}
                                  </tbody>
                                </table>
                              </div>
                            </div>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  );
                })
              ) : (
                <tr>
                  <td colSpan={6} className="px-6 py-20 text-center text-slate-400">No hay ventas registradas en este periodo.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
