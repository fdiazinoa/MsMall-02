import React from 'react';
import { Eye } from 'lucide-react';

interface PreviewCardProps {
    mapping: Record<string, string>;
    constants?: Record<string, string>;
    sampleRow: Record<string, any>;
    systemFields: { key: string; label: string }[];
}

const PreviewCard: React.FC<PreviewCardProps> = ({ mapping, constants = {}, sampleRow, systemFields }) => {
    const getValue = (key: string) => {
        // 1. Check if using constant
        if (constants[key]) return constants[key];

        // 2. Check mapping
        const mappedHeader = mapping[key];
        if (mappedHeader && sampleRow[mappedHeader] !== undefined && sampleRow[mappedHeader] !== null) {
            return String(sampleRow[mappedHeader]);
        }

        return null;
    };

    return (
        <div className="bg-slate-50 rounded-xl border border-indigo-100 overflow-hidden mt-6 animate-in slide-in-from-bottom-4 duration-300">
            <div className="bg-indigo-50 px-4 py-2 border-b border-indigo-100 flex items-center gap-2">
                <Eye size={16} className="text-indigo-600" />
                <h3 className="text-sm font-bold text-indigo-900 uppercase tracking-wider">Vista Previa del Resultado (Fila 1)</h3>
            </div>
            <div className="p-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-3">
                    {systemFields.map(field => {
                        const val = getValue(field.key);
                        const isPrimary = ['total_bruto', 'factura_numero'].includes(field.key);

                        return (
                            <div key={field.key} className="flex flex-col border-b border-slate-200/60 pb-1">
                                <span className="text-[10px] font-bold text-slate-400 uppercase">{field.label}</span>
                                <span className={`font-mono text-sm truncate ${val
                                        ? isPrimary ? 'text-indigo-600 font-bold' : 'text-slate-700'
                                        : 'text-slate-300 italic'
                                    }`}>
                                    {val || '--'}
                                </span>
                            </div>
                        );
                    })}
                </div>
                <div className="mt-4 pt-3 border-t border-slate-200 flex items-center justify-between">
                    <span className="text-[10px] text-slate-400 italic">Simulación de inserción en base de datos</span>
                    <div className="h-1.5 w-1.5 rounded-full bg-green-500 animate-pulse"></div>
                </div>
            </div>
        </div>
    );
};

export default PreviewCard;
