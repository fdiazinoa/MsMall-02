import { useAuth } from '../context/AuthProvider';
import { formatCurrency, formatNumber } from '../utils/formatters';

/**
 * Custom hook to format currency and numbers based on the currently selected mall's configuration.
 * Defaults to 'en-US' and 'USD' if no mall is selected or configuration is missing.
 */
export const useFormatCurrency = () => {
    const { currentMall } = useAuth();

    // Use values from currentMall or fallback to defaults
    const locale = currentMall?.conf_locale || 'en-US';
    const currency = currentMall?.conf_moneda || 'USD';

    /**
     * Formats a numeric value as currency.
     */
    const format = (value: number) => {
        return formatCurrency(value, locale, currency);
    };

    /**
     * Formats a numeric value with locale-specific separators but no currency symbol.
     */
    const formatAmount = (value: number) => {
        return formatNumber(value, locale);
    };

    return {
        format,
        formatAmount,
        locale,
        currency
    };
};
