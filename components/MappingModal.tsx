import React, { useState, useEffect } from 'react';
import { X, Check, AlertCircle } from 'lucide-react';
import PreviewCard from './PreviewCard';

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

const SYSTEM_FIELDS: { key: string; label: string; required: boolean }[] = [
    { key: 'factura_numero', label: 'Número de Factura', required: true },
    { key: 'fecha_venta', label: 'Fecha de Venta', required: true },
    { key: 'local_codigo', label: 'Código del Local', required: true },
    { key: 'total_bruto', label: 'Total Bruto', required: true },
    { key: 'total_impuestos', label: 'Total Impuestos', required: false },
    { key: 'total_neto', label: 'Total Neto', required: false },
    { key: 'comprobante', label: 'Comprobante (NCF)', required: false },
    { key: 'hora_transaccion', label: 'Hora de Transacción', required: false },
];

const TRANSFORM_MODES = {
    CONCAT: 'concat',
    GENERATED_SEQUENCE: 'generated_sequence'
} as const;

const splitTransformFields = (value?: string) =>
    String(value || '')
        .split(',')
        .map(part => part.trim())
        .filter(Boolean);

const fieldModeKey = (fieldKey: string) => `_${fieldKey}_mode`;
const concatFieldsKey = (fieldKey: string) => `_${fieldKey}_concat_fields`;
const concatSeparatorKey = (fieldKey: string) => `_${fieldKey}_concat_separator`;

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
    const [fieldModes, setFieldModes] = useState<Record<string, string>>({});
    const [dateFormat, setDateFormat] = useState<string>('auto');

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
        setFieldModes({});
    }, [currentMapping, suggestedMapping]);

    const handleMappingChange = (systemField: string, csvHeader: string) => {
        setMapping({ ...mapping, [systemField]: csvHeader });
        if (csvHeader) {
            setConstants({ ...constants, [systemField]: '' });
        }
    };

    const handleConstantChange = (systemField: string, value: string) => {
        setConstants({ ...constants, [systemField]: value });
    };

    const clearFieldConfig = (systemField: string) => {
        const nextMapping = { ...mapping };
        const nextConstants = { ...constants };
        delete nextMapping[systemField];
        delete nextConstants[systemField];
        delete nextConstants[fieldModeKey(systemField)];
        delete nextConstants[concatFieldsKey(systemField)];
        delete nextConstants[concatSeparatorKey(systemField)];
        return { nextMapping, nextConstants };
    };

    const getMode = (systemField: string) => fieldModes[systemField] || 'VARIABLE';

    const handleModeChange = (systemField: string, mode: string) => {
        const { nextMapping, nextConstants } = clearFieldConfig(systemField);
        if (mode === 'CONSTANT') {
            nextConstants[systemField] = '';
        } else if (mode === 'CONCAT') {
            nextConstants[fieldModeKey(systemField)] = TRANSFORM_MODES.CONCAT;
            nextConstants[concatFieldsKey(systemField)] = systemField === 'factura_numero' ? 'local_codigo,fecha_venta,numero_registro' : '';
            nextConstants[concatSeparatorKey(systemField)] = '-';
        } else if (mode === 'GENERATED_SEQUENCE') {
            nextConstants[fieldModeKey(systemField)] = TRANSFORM_MODES.GENERATED_SEQUENCE;
        }

        setMapping(nextMapping);
        setConstants(nextConstants);
        setFieldModes({ ...fieldModes, [systemField]: mode });
    };

    const validate = () => {
        const missing = SYSTEM_FIELDS.filter(f => {
            if (!f.required) return false;
            const mode = getMode(f.key);
            if (mode === 'CONCAT') return splitTransformFields(constants[concatFieldsKey(f.key)]).length === 0;
            if (mode === 'GENERATED_SEQUENCE') return false;
            return !mapping[f.key] && !constants[f.key];
        });
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
        console.log("Date Format:", dateFormat);

        // Pass date format as part of constants for backend processing
        const finalConstants = { ...constants, _date_format: dateFormat };
        onConfirm(cleanMapping, finalConstants);
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
                        {(SYSTEM_FIELDS || []).map(field => {
                            const isRequired = field.required;
                            const suggestion = (suggestedMapping || {})[field.key];
                            const isConfident = suggestion?.is_confident;
                            const mode = getMode(field.key);
                            const isUsingConstant = mode === 'CONSTANT';
                            const isConcat = mode === 'CONCAT';
                            const isGeneratedSequence = mode === 'GENERATED_SEQUENCE';
                            const concatFields = splitTransformFields(constants[concatFieldsKey(field.key)]);
                            const transformOptions = [
                                ...SYSTEM_FIELDS.map(item => ({ value: item.key, label: item.label })),
                                { value: 'numero_registro', label: 'Número de registro' },
                                ...(fileHeaders || [])
                                    .filter(header => !SYSTEM_FIELDS.some(item => item.key === header))
                                    .map(header => ({ value: header, label: `Columna: ${header}` }))
                            ];

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
                                        <select
                                            value={mode}
                                            onChange={(e) => handleModeChange(field.key, e.target.value)}
                                            className="text-xs px-3 py-1 rounded-lg border border-gray-200 bg-white text-gray-700 outline-none"
                                        >
                                            <option value="VARIABLE">Columna CSV</option>
                                            <option value="CONSTANT">Valor constante</option>
                                            <option value="CONCAT">Concatenar campos</option>
                                            {field.key === 'factura_numero' && (
                                                <option value="GENERATED_SEQUENCE">Consecutivo Local + Fecha</option>
                                            )}
                                        </select>
                                    </div>

                                    {isUsingConstant ? (
                                        <input
                                            type="text"
                                            value={constants[field.key] || ''}
                                            onChange={(e) => handleConstantChange(field.key, e.target.value)}
                                            placeholder="Ingrese valor constante..."
                                            className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                                        />
                                    ) : isConcat ? (
                                        <div className="space-y-3">
                                            <div className="flex flex-col sm:flex-row gap-2">
                                                <select
                                                    value=""
                                                    onChange={(e) => {
                                                        const nextValue = e.target.value;
                                                        if (!nextValue || concatFields.includes(nextValue)) return;
                                                        setConstants({
                                                            ...constants,
                                                            [concatFieldsKey(field.key)]: [...concatFields, nextValue].join(',')
                                                        });
                                                    }}
                                                    className="flex-1 px-4 py-2 border border-indigo-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent bg-white"
                                                >
                                                    <option value="">Agregar campo a concatenar...</option>
                                                    {transformOptions.map(option => (
                                                        <option key={`${field.key}-${option.value}`} value={option.value}>{option.label}</option>
                                                    ))}
                                                </select>
                                                <input
                                                    type="text"
                                                    value={constants[concatSeparatorKey(field.key)] ?? '-'}
                                                    onChange={(e) => setConstants({
                                                        ...constants,
                                                        [concatSeparatorKey(field.key)]: e.target.value
                                                    })}
                                                    placeholder="Separador"
                                                    className="w-full sm:w-28 px-4 py-2 border border-indigo-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent bg-white"
                                                />
                                            </div>
                                            <div className="flex flex-wrap gap-2">
                                                {concatFields.length === 0 ? (
                                                    <span className="text-xs text-amber-700 font-semibold">Agrega al menos un campo.</span>
                                                ) : concatFields.map(part => (
                                                    <button
                                                        key={`${field.key}-${part}`}
                                                        type="button"
                                                        onClick={() => setConstants({
                                                            ...constants,
                                                            [concatFieldsKey(field.key)]: concatFields.filter(item => item !== part).join(',')
                                                        })}
                                                        className="px-2.5 py-1 rounded-full bg-indigo-100 text-indigo-700 text-xs font-bold hover:bg-indigo-200"
                                                    >
                                                        {part} ×
                                                    </button>
                                                ))}
                                            </div>
                                        </div>
                                    ) : isGeneratedSequence ? (
                                        <div className="rounded-lg border border-indigo-200 bg-indigo-50 px-4 py-3 text-sm text-indigo-800">
                                            <p className="font-bold">Formato generado: LOCAL-FECHA-SECUENCIA</p>
                                            <p className="text-xs mt-1">Ejemplo: PABT-01-20260601-000034.</p>
                                        </div>
                                    ) : (
                                        <>
                                            <select
                                                value={mapping[field.key] || ''}
                                                onChange={(e) => handleMappingChange(field.key, e.target.value)}
                                                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                                            >
                                                <option value="">-- Seleccionar columna --</option>
                                                {(fileHeaders || []).map(header => (
                                                    <option key={header} value={header}>{header}</option>
                                                ))}
                                            </select>

                                            {/* Date Format Selector for fecha_venta */}
                                            {field.key === 'fecha_venta' && mapping[field.key] && (
                                                <div className="mt-3">
                                                    <label className="block text-xs font-semibold text-gray-600 mb-1">Formato de Fecha</label>
                                                    <select
                                                        value={dateFormat}
                                                        onChange={(e) => setDateFormat(e.target.value)}
                                                        className="w-full px-4 py-2 border border-indigo-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent bg-indigo-50 text-sm"
                                                    >
                                                        <option value="auto">🔍 Autodetectar (recomendado)</option>
                                                        <option value="DD/MM/YYYY">📅 DD/MM/YYYY (02/01 = 2 de Enero)</option>
                                                        <option value="DDmmYYYY">🔢 DDmmYYYY (02012026 = 2 de Enero)</option>
                                                        <option value="YYYYmmDD">🧮 YYYYmmDD (20260102 = 2 de Enero)</option>
                                                        <option value="MM/DD/YYYY">🇺🇸 MM/DD/YYYY (02/01 = 1 de Febrero)</option>
                                                        <option value="YYYY-MM-DD">🌐 YYYY-MM-DD (ISO 8601)</option>
                                                        <option value="YYYY/MM/DD">📆 YYYY/MM/DD (2026/01/01)</option>
                                                        <option value="timestamp">⏰ Con hora (ISO timestamp)</option>
                                                    </select>
                                                    <p className="text-xs text-gray-500 mt-1">Elige el formato para evitar ambigüedad en fechas como 2/1/2026</p>
                                                </div>
                                            )}

                                            {mapping[field.key] && sampleRow[mapping[field.key]] !== undefined && sampleRow[mapping[field.key]] !== null && (
                                                <div className="mt-2 text-sm text-gray-600 bg-white px-3 py-2 rounded border border-gray-200">
                                                    <span className="font-medium">Vista previa:</span> {String(sampleRow[mapping[field.key]])}
                                                </div>
                                            )}
                                        </>
                                    )}
                                </div>
                            );
                        })}
                    </div>

                    <PreviewCard
                        mapping={mapping}
                        constants={constants}
                        sampleRow={sampleRow}
                        systemFields={SYSTEM_FIELDS}
                    />

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
