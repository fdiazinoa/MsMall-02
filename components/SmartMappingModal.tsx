import React, { useState, useRef } from 'react';
import { Upload, FileUp, CheckCircle2, AlertTriangle, ArrowRight, X, Wand2, ArrowRightLeft } from 'lucide-react';
import { ApiService } from '../api';

interface SmartMappingModalProps {
    isOpen: boolean;
    onClose: () => void;
    onConfirm: (mapping: Record<string, string>, sampleData?: any) => void;
    systemFields: { key: string; label: string; required?: boolean }[];
}

export const SmartMappingModal: React.FC<SmartMappingModalProps> = ({ isOpen, onClose, onConfirm, systemFields }) => {
    const [step, setStep] = useState(1);
    const [analyzing, setAnalyzing] = useState(false);
    const [mapping, setMapping] = useState<Record<string, string>>({});
    const [confidence, setConfidence] = useState<Record<string, { score: number; isConfident: boolean }>>({});
    const [csvHeaders, setCsvHeaders] = useState<string[]>([]);
    const [sampleRow, setSampleRow] = useState<Record<string, any>>({});
    const fileInputRef = useRef<HTMLInputElement>(null);

    if (!isOpen) return null;

    const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (!file) return;

        setAnalyzing(true);
        try {
            const result = await ApiService.analyzeMapping(file);

            setCsvHeaders(result.csv_headers);
            setSampleRow(result.sample_row || {});

            const newMapping: Record<string, string> = {};
            const newConfidence: Record<string, any> = {};

            // Pre-fill mapping based on backend suggestions
            Object.entries(result.suggested_mapping).forEach(([sysField, suggestion]: [string, any]) => {
                newMapping[sysField] = suggestion.csv_header;
                newConfidence[sysField] = {
                    score: suggestion.confidence,
                    isConfident: suggestion.is_confident
                };
            });

            setMapping(newMapping);
            setConfidence(newConfidence);
            setStep(2);
        } catch (error: any) {
            alert("Error analizando archivo: " + error.message);
        } finally {
            setAnalyzing(false);
        }
    };

    const handleDragOver = (e: React.DragEvent) => {
        e.preventDefault();
        e.stopPropagation();
    };

    const handleDrop = (e: React.DragEvent) => {
        e.preventDefault();
        e.stopPropagation();
        // Implementation for drag and drop would be similar to file upload
        if (e.dataTransfer.files && e.dataTransfer.files[0]) {
            // Ideally reuse logic, for now simple alert or mock
            alert("Por favor use el selector de archivos por ahora.");
        }
    };

    const handleConfirm = () => {
        onConfirm(mapping, sampleRow);
        onClose();
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm animate-in fade-in duration-200">
            <div className="bg-white rounded-2xl shadow-2xl w-full max-w-4xl overflow-hidden flex flex-col max-h-[90vh]">
                {/* Header */}
                <div className="bg-indigo-600 p-6 text-white flex justify-between items-center shrink-0">
                    <div>
                        <h3 className="text-xl font-bold flex items-center gap-2">
                            <Wand2 size={24} className="text-indigo-200" />
                            Auto-Mapeo Inteligente
                        </h3>
                        <p className="text-indigo-100 text-sm mt-1">
                            {step === 1 ? 'Sube un archivo de ejemplo para detectar automáticamente las columnas.' : 'Confirma la sugerencia de mapeo realizada por IA.'}
                        </p>
                    </div>
                    <button onClick={onClose} className="p-2 hover:bg-white/10 rounded-lg transition-colors"><X size={20} /></button>
                </div>

                {/* Content */}
                <div className="p-8 overflow-y-auto grow">
                    {step === 1 ? (
                        <div
                            className="border-2 border-dashed border-slate-300 rounded-3xl p-12 text-center flex flex-col items-center justify-center gap-4 hover:border-indigo-400 hover:bg-indigo-50/30 transition-all cursor-pointer group"
                            onDragOver={handleDragOver}
                            onDrop={handleDrop}
                            onClick={() => fileInputRef.current?.click()}
                        >
                            <input
                                type="file"
                                ref={fileInputRef}
                                className="hidden"
                                accept=".csv,.txt,.json,.xml"
                                onChange={handleFileUpload}
                            />

                            {analyzing ? (
                                <>
                                    <div className="w-16 h-16 border-4 border-indigo-200 border-t-indigo-600 rounded-full animate-spin mb-4"></div>
                                    <h4 className="text-lg font-bold text-slate-700">Analizando estructura...</h4>
                                    <p className="text-slate-400">Detectando patrones y similitudes en los encabezados</p>
                                </>
                            ) : (
                                <>
                                    <div className="w-20 h-20 bg-indigo-100 text-indigo-600 rounded-full flex items-center justify-center group-hover:scale-110 transition-transform mb-2">
                                        <FileUp size={32} />
                                    </div>
                                    <h4 className="text-xl font-bold text-slate-700">Arrastra tu archivo aquí</h4>
                                    <p className="text-slate-400 text-sm max-w-sm">
                                        O haz clic para seleccionar un archivo CSV, JSON o XML de tu ordenador.
                                    </p>
                                    <button className="mt-4 px-6 py-2.5 bg-white border border-slate-200 shadow-sm rounded-xl font-bold text-slate-600 text-sm group-hover:border-indigo-300 group-hover:text-indigo-600">
                                        Explorar Archivos
                                    </button>
                                </>
                            )}
                        </div>
                    ) : (
                        <div className="space-y-6">
                            <div className="bg-amber-50 border border-amber-100 rounded-xl p-4 flex gap-3 text-amber-800 text-xs">
                                <AlertTriangle size={16} className="shrink-0 mt-0.5" />
                                <p>
                                    El sistema ha analizado el archivo y sugiere el siguiente mapeo.
                                    Por favor revisa cuidadosamente, especialmente los campos marcados con ⚠️.
                                </p>
                            </div>

                            <div className="border border-slate-200 rounded-xl overflow-hidden">
                                <table className="w-full text-sm">
                                    <thead className="bg-slate-50 text-slate-500 font-bold uppercase text-xs">
                                        <tr>
                                            <th className="px-5 py-3 text-left w-1/3">Campo de Sistema</th>
                                            <th className="px-5 py-3 text-left w-1/3">Columna Detectada (Archivo)</th>
                                            <th className="px-5 py-3 text-left w-1/3 bg-slate-100/50">Vista Previa (Fila 1)</th>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-slate-100">
                                        {systemFields.map((field) => {
                                            const match = confidence[field.key];
                                            const selectedHeader = mapping[field.key] || '';
                                            const sampleValue = sampleRow[selectedHeader];

                                            return (
                                                <tr key={field.key} className="group hover:bg-slate-50 transition-colors">
                                                    <td className="px-5 py-3">
                                                        <div className="font-bold text-slate-700 flex items-center gap-2">
                                                            {field.label}
                                                            {field.required && <span className="text-rose-500">*</span>}
                                                        </div>
                                                        <div className="text-[10px] text-slate-400 font-mono">{field.key}</div>
                                                    </td>
                                                    <td className="px-5 py-3">
                                                        <div className="relative">
                                                            <select
                                                                className={`w-full appearance-none pl-3 pr-8 py-2 rounded-lg border text-sm font-medium outline-none transition-all ${selectedHeader
                                                                        ? (match?.isConfident ? 'border-green-200 bg-green-50 text-green-700' : 'border-slate-300 bg-white text-slate-700')
                                                                        : 'border-orange-200 bg-orange-50 text-orange-700'
                                                                    }`}
                                                                value={selectedHeader}
                                                                onChange={(e) => {
                                                                    setMapping({ ...mapping, [field.key]: e.target.value });
                                                                    // Reset confidence on manual change
                                                                    setConfidence({ ...confidence, [field.key]: { score: 100, isConfident: true } });
                                                                }}
                                                            >
                                                                <option value="">-- Sin asignar --</option>
                                                                {csvHeaders.map(h => (
                                                                    <option key={h} value={h}>{h}</option>
                                                                ))}
                                                            </select>
                                                            <div className="absolute right-3 top-2.5 pointer-events-none">
                                                                {selectedHeader ? (
                                                                    match?.isConfident ? <CheckCircle2 size={16} className="text-green-500" /> : <AlertTriangle size={16} className="text-amber-500" />
                                                                ) : (
                                                                    <AlertTriangle size={16} className="text-orange-400" />
                                                                )}
                                                            </div>
                                                        </div>
                                                    </td>
                                                    <td className="px-5 py-3 bg-slate-50/50">
                                                        {selectedHeader ? (
                                                            <div className="font-mono text-xs text-slate-600 truncate max-w-[200px]" title={String(sampleValue)}>
                                                                {sampleValue !== undefined && sampleValue !== null ? String(sampleValue) : <span className="text-slate-300 italic">Vacío</span>}
                                                            </div>
                                                        ) : (
                                                            <span className="text-slate-300 text-xs italic">--</span>
                                                        )}
                                                    </td>
                                                </tr>
                                            );
                                        })}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    )}
                </div>

                {/* Footer */}
                <div className="bg-slate-50 p-6 border-t border-slate-100 flex justify-between items-center shrink-0">
                    {step === 1 ? (
                        <button onClick={onClose} className="px-6 py-2.5 text-slate-500 font-bold hover:text-slate-700">Cancelar</button>
                    ) : (
                        <button onClick={() => setStep(1)} className="px-6 py-2.5 text-slate-500 font-bold hover:text-slate-700">Atrás</button>
                    )}

                    {step === 2 && (
                        <button
                            onClick={handleConfirm}
                            className="flex items-center gap-2 px-8 py-3 bg-indigo-600 text-white rounded-xl font-bold shadow-lg shadow-indigo-200 hover:bg-indigo-700 transition-all hover:scale-105 active:scale-95"
                        >
                            Guardar Configuración <ArrowRight size={18} />
                        </button>
                    )}
                </div>
            </div>
        </div>
    );
};
