
/**
 * Formats a number as currency based on a locale and currency code.
 * @param value The numeric value to format
 * @param locale The locale string (e.g., 'es-CL', 'en-US')
 * @param currency The currency code (e.g., 'CLP', 'USD')
 */
export const formatCurrency = (value: number, locale: string = 'es-CL', currency: string = 'CLP'): string => {
    return new Intl.NumberFormat(locale, {
        style: 'currency',
        currency: currency,
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    }).format(value);
};

/**
 * Formats a number with locale-specific separators but without currency symbol.
 */
export const formatNumber = (value: number, locale: string = 'es-CL'): string => {
    return new Intl.NumberFormat(locale, {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    }).format(value);
};
