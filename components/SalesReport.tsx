
import React, { useState, useEffect } from 'react';
import { SaleReport, DateRange } from '../types';
import { ApiService } from '../api';

export const SalesReport: React.FC = () => {
  const [data, setData] = useState<SaleReport[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  const [dates, setDates] = useState<DateRange>({
    startDate: '2024-01-01',
    endDate: '2024-12-31'
  });

  const fetchData = async () => {
    setIsLoading(true);
    setError(null);
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
          <p className="text-indigo-100 text-sm font-medium">Ventas Totales (Bruto)</p>
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
                  <td colSpan={5} className="px-6 py-20 text-center text-slate-400">Cargando datos...</td>
                </tr>
              ) : data.length > 0 ? (
                data.map((row, idx) => (
                  <tr key={idx} className="hover:bg-slate-50 transition-colors">
                    <td className="px-6 py-4 font-medium text-slate-800">{row.local_nombre}</td>
                    <td className="px-6 py-4 text-slate-500">{row.mall_nombre}</td>
                    <td className="px-6 py-4 text-right font-mono font-medium text-slate-700">${row.total_bruto.toFixed(2)}</td>
                    <td className="px-6 py-4 text-right font-mono text-slate-400">${row.total_impuestos.toFixed(2)}</td>
                    <td className="px-6 py-4 text-right font-mono font-bold text-indigo-600">${row.total_neto.toFixed(2)}</td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={5} className="px-6 py-20 text-center text-slate-400">No hay ventas registradas en este periodo.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
