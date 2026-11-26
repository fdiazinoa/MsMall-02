"""Arithmetic over source columns only; never evaluates user-provided code."""
import math
import re
from decimal import Decimal, InvalidOperation, localcontext

CALCULATED_FIELDS = ('total_bruto', 'total_impuestos', 'total_neto')


def calculated_fields(row, constants):
    result = {}
    decimal = constants.get('_decimal_separator', '.')
    decimal = ',' if decimal == ',' else '.'
    group = '.' if decimal == ',' else ','
    lookup = {str(key).strip().casefold(): value for key, value in row.items()}

    def number(header):
        if not header or header.strip().casefold() not in lookup:
            raise ValueError(f'Columna de cálculo no encontrada: {header or "(sin seleccionar)"}')
        raw = lookup[header.strip().casefold()]
        if isinstance(raw, (int, float, Decimal)) and not isinstance(raw, bool):
            value = Decimal(str(raw))
            if not value.is_finite():
                raise ValueError(f'Valor no numérico en columna de cálculo: {header}')
            return value
        text = str(raw).strip().strip('\'"')
        text = re.sub(r'\s+', '', text).replace('RD$', '').replace('$', '')
        pattern = rf'[+-]?(?:\d+|\d{{1,3}}(?:{re.escape(group)}\d{{3}})+)(?:{re.escape(decimal)}\d+)?'
        if len(text) > 100 or not re.fullmatch(pattern, text):
            raise ValueError(f'Valor no numérico en columna de cálculo: {header}')
        return Decimal(text.replace(group, '').replace(decimal, '.'))

    for field in CALCULATED_FIELDS:
        if constants.get(f'_{field}_mode') != 'calculated':
            continue
        try:
            left = number(str(constants.get(f'_{field}_calc_left', '')))
            right = number(str(constants.get(f'_{field}_calc_right', '')))
            operator = constants.get(f'_{field}_calc_operator')
            with localcontext() as context:
                context.prec = 40
                if operator == '+': value = left + right
                elif operator == '-': value = left - right
                elif operator == '*': value = left * right
                elif operator == '/':
                    if right == 0:
                        raise ValueError('División entre cero')
                    value = left / right
                else:
                    raise ValueError('Operación no permitida; usa +, -, * o /')
            if not value.is_finite() or not math.isfinite(float(value)):
                raise ValueError('Resultado fuera de rango')
            # The receiving importer parses using the configured decimal separator.
            result[field] = format(value, 'f').replace('.', decimal)
        except (ValueError, InvalidOperation, OverflowError) as exc:
            raise ValueError(f'Campo calculado {field}: {exc}') from exc
    return result
