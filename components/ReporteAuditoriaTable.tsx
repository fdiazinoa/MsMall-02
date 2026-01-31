import React, { useState } from 'react';
import { ChevronRight, ChevronDown, Loader2 } from 'lucide-react';
import { useFormatCurrency } from '../hooks/useFormatCurrency';

interface ReporteAuditoriaTableProps {
    data: any[];
    isLoading: boolean;
    detailsData: Record<string, any[]>;
    loadingDetails: Record<string, boolean>;
    toggleRow: (localId: string) => void;
    expandedLocalId: string | null;
}

export const ReporteAuditoriaTable: React.FC<ReporteAuditoriaTableProps> = ({
    data,
    isLoading,
    detailsData,
    loadingDetails,
    toggleRow,
    expandedLocalId
}) => {
    const { format, formatAmount } = useFormatCurrency();

    return (
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
                        data.map((row) => {
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
                                        <td className="px-6 py-4 text-right font-mono font-medium text-slate-700">{formatAmount(row.total_neto)}</td>
                                        <td className="px-6 py-4 text-right font-mono text-slate-400">{formatAmount(row.total_impuestos)}</td>
                                        <td className="px-6 py-4 text-right font-mono font-bold text-indigo-600">{format(row.total_bruto)}</td>
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
                                                                    <th className="px-4 py-3 text-right">Bruto</th>
                                                                    <th className="px-4 py-3 text-right">Impuesto</th>
                                                                    <th className="px-4 py-3 text-right">Neto</th>
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
                                                                        {details.map((detail) => {
                                                                            const isNegative = detail.total_bruto < 0;
                                                                            return (
                                                                                <tr key={detail.id} className={`hover:bg-slate-50/80 transition-colors ${isNegative ? 'bg-red-50/50' : ''}`}>
                                                                                    <td className="px-4 py-2.5 text-slate-600">{detail.fecha}</td>
                                                                                    <td className="px-4 py-2.5 text-slate-500">{detail.hora}</td>
                                                                                    <td className="px-4 py-2.5 font-medium text-slate-700">{detail.factura_no}</td>
                                                                                    <td className={`px-4 py-2.5 text-right font-mono ${detail.total_neto < 0 ? 'text-red-600 font-bold' : 'text-slate-600'}`}>
                                                                                        {formatAmount(detail.total_neto)}
                                                                                    </td>
                                                                                    <td className={`px-4 py-2.5 text-right font-mono ${detail.total_impuestos < 0 ? 'text-red-600 font-bold' : 'text-slate-400'}`}>
                                                                                        {formatAmount(detail.total_impuestos)}
                                                                                    </td>
                                                                                    <td className={`px-4 py-2.5 text-right font-mono font-bold ${isNegative ? 'text-red-600' : 'text-indigo-600'}`}>
                                                                                        {format(detail.total_bruto)}
                                                                                    </td>
                                                                                </tr>
                                                                            );
                                                                        })}
                                                                        {/* Summary Row */}
                                                                        <tr className="bg-slate-50 font-bold border-t-2 border-slate-200">
                                                                            <td colSpan={3} className="px-4 py-3 text-right text-slate-500 uppercase tracking-wider">Totales Detalle:</td>
                                                                            <td className="px-4 py-3 text-right font-mono text-slate-600">{formatAmount(subTotalNeto)}</td>
                                                                            <td className="px-4 py-3 text-right font-mono text-slate-500">{formatAmount(subTotalImpuestos)}</td>
                                                                            <td className="px-4 py-3 text-right font-mono text-indigo-600">{format(subTotalBruto)}</td>
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
    );
};
