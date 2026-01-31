import React, { useState, useEffect } from 'react';
import { X, Check, AlertCircle } from 'lucide-react';

interface MappingModalProps {
    isOpen: boolean;
    onClose: () => void;
    onConfirm: (mapping: Record<string, string>, constants: Record<string, string>) => void;
    fileHeaders: string[];
    suggestedMapping: Record<string, any>;
    currentMapping: Record<string, string>;
    sampleRow: Record<string, any>;
    filename: string;
}

const SYSTEM_FIELDS = [
    { key: 'factura_numero', label: 'Número de Factura', required: true },
    { key: 'fecha_venta', label: 'Fecha de Venta', required: true },
    { key: 'local_codigo', label: 'Código del Local', required: true },
    { key: 'total_bruto', label: 'Total Bruto', required: true },
    { key: 'total_impuestos', label: 'Total Impuestos', required: false },
    { key: 'total_neto', label: 'Total Neto', required: false },
    { key: 'comprobante', label: 'Comprobante (NCF)', required: false },
    { key: 'hora_transaccion', label: 'Hora de Transacción', required: false },
];

export default function MappingModal({
    isOpen,
    onClose,
    onConfirm,
    fileHeaders,
    suggestedMapping,
    currentMapping,
    sampleRow,
    filename
}: MappingModalProps) {
    const [mapping, setMapping] = useState<Record<string, string>>({});
    const [constants, setConstants] = useState<Record<string, string>>({});
    const [useConstant, setUseConstant] = useState<Record<string, boolean>>({});

    useEffect(() => {
        // Initialize with current or suggested mapping
        const initialMapping: Record<string, string> = {};
        SYSTEM_FIELDS.forEach(field => {
            if (currentMapping[field.key]) {
                initialMapping[field.key] = currentMapping[field.key];
            } else if (suggestedMapping[field.key]?.csv_header) {
                initialMapping[field.key] = suggestedMapping[field.key].csv_header;
            } else {
                initialMapping[field.key] = '';
            }
        });
        setMapping(initialMapping);
    }, [currentMapping, suggestedMapping]);

    const handleMappingChange = (systemField: string, csvHeader: string) => {
        setMapping({ ...mapping, [systemField]: csvHeader });
        if (csvHeader) {
            setUseConstant({ ...useConstant, [systemField]: false });
            setConstants({ ...constants, [systemField]: '' });
        }
    };

    const handleConstantChange = (systemField: string, value: string) => {
        setConstants({ ...constants, [systemField]: value });
    };

    const toggleConstant = (systemField: string) => {
        const newUseConstant = !useConstant[systemField];
        setUseConstant({ ...useConstant, [systemField]: newUseConstant });
        if (newUseConstant) {
            setMapping({ ...mapping, [systemField]: '' });
        } else {
            setConstants({ ...constants, [systemField]: '' });
        }
    };

    const validate = () => {
        const missing = SYSTEM_FIELDS.filter(f => f.required && !mapping[f.key] && !constants[f.key]);
        return missing.length === 0;
    };

    const handleConfirm = () => {
        if (!validate()) {
            alert('Faltan campos obligatorios por mapear');
            return;
        }

        // Remove empty strings from mapping
        const cleanMapping: Record<string, string> = {};
        Object.entries(mapping).forEach(([key, value]) => {
            if (typeof value === 'string' && value.trim() !== '') {
                cleanMapping[key] = value;
            }
        });

        console.log("Mapping limpio (sin vacíos):", cleanMapping);
        console.log("Constants:", constants);

        onConfirm(cleanMapping, constants);
    };

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-[9999] p-4">
            <div className="bg-white rounded-2xl shadow-2xl max-w-4xl w-full max-h-[90vh] overflow-hidden flex flex-col">
                {/* Header */}
                <div className="bg-gradient-to-r from-indigo-600 to-purple-600 text-white p-6 flex justify-between items-center">
                    <div>
                        <h2 className="text-2xl font-bold">Configurar Mapeo de Campos</h2>
                        <p className="text-indigo-100 text-sm mt-1">Archivo: {filename}</p>
                    </div>
                    <button
                        onClick={onClose}
                        className="bg-white/20 hover:bg-white/30 rounded-lg p-2 transition-colors"
                    >
                        <X size={24} />
                    </button>
                </div>

                {/* Content */}
                <div className="flex-1 overflow-y-auto p-6">
                    <div className="space-y-4">
                        {SYSTEM_FIELDS.map(field => {
                            const isRequired = field.required;
                            const suggestion = suggestedMapping[field.key];
                            const isConfident = suggestion?.is_confident;
                            const isUsingConstant = useConstant[field.key];

                            return (
                                <div key={field.key} className="bg-gray-50 rounded-xl p-4 border border-gray-200">
                                    <div className="flex items-start justify-between mb-3">
                                        <div className="flex items-center gap-2">
                                            <span className="font-semibold text-gray-800">{field.label}</span>
                                            {isRequired && (
                                                <span className="bg-red-100 text-red-700 text-xs px-2 py-0.5 rounded-full">
                                                    Obligatorio
                                                </span>
                                            )}
                                            {isConfident && !isUsingConstant && (
                                                <span className="bg-green-100 text-green-700 text-xs px-2 py-0.5 rounded-full flex items-center gap-1">
                                                    <Check size={12} /> Auto-detectado
                                                </span>
                                            )}
                                        </div>
                                        <button
                                            onClick={() => toggleConstant(field.key)}
                                            className={`text-xs px-3 py-1 rounded-lg transition-colors ${isUsingConstant
                                                ? 'bg-blue-600 text-white'
                                                : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
                                                }`}
                                        >
                                            {isUsingConstant ? 'Usando valor fijo' : 'Usar valor fijo'}
                                        </button>
                                    </div>

                                    {isUsingConstant ? (
                                        <input
                                            type="text"
                                            value={constants[field.key] || ''}
                                            onChange={(e) => handleConstantChange(field.key, e.target.value)}
                                            placeholder="Ingrese valor constante..."
                                            className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                                        />
                                    ) : (
                                        <>
                                            <select
                                                value={mapping[field.key] || ''}
                                                onChange={(e) => handleMappingChange(field.key, e.target.value)}
                                                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                                            >
                                                <option value="">-- Seleccionar columna --</option>
                                                {fileHeaders.map(header => (
                                                    <option key={header} value={header}>{header}</option>
                                                ))}
                                            </select>
                                            {mapping[field.key] && sampleRow[mapping[field.key]] && (
                                                <div className="mt-2 text-sm text-gray-600 bg-white px-3 py-2 rounded border border-gray-200">
                                                    <span className="font-medium">Vista previa:</span> {sampleRow[mapping[field.key]]}
                                                </div>
                                            )}
                                        </>
                                    )}
                                </div>
                            );
                        })}
                    </div>

                    {!validate() && (
                        <div className="mt-6 bg-yellow-50 border border-yellow-200 rounded-xl p-4 flex items-start gap-3">
                            <AlertCircle className="text-yellow-600 flex-shrink-0 mt-0.5" size={20} />
                            <div>
                                <p className="font-semibold text-yellow-800">Faltan campos obligatorios</p>
                                <p className="text-sm text-yellow-700 mt-1">
                                    Debes mapear o asignar valores fijos a todos los campos obligatorios antes de confirmar.
                                </p>
                            </div>
                        </div>
                    )}
                </div>

                {/* Footer */}
                <div className="bg-gray-50 p-6 flex justify-end gap-3 border-t border-gray-200">
                    <button
                        onClick={onClose}
                        className="px-6 py-2.5 border border-gray-300 rounded-xl text-gray-700 hover:bg-gray-100 transition-colors font-medium"
                    >
                        Cancelar
                    </button>
                    <button
                        onClick={handleConfirm}
                        disabled={!validate()}
                        className={`px-6 py-2.5 rounded-xl font-medium transition-all ${validate()
                            ? 'bg-indigo-600 text-white hover:bg-indigo-700 shadow-lg shadow-indigo-200'
                            : 'bg-gray-300 text-gray-500 cursor-not-allowed'
                            }`}
                    >
                        Confirmar y Procesar
                    </button>
                </div>
            </div>
        </div>
    );
}
