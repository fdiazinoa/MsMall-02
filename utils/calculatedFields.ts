export const CALCULATED_FIELDS = ['total_bruto', 'total_impuestos', 'total_neto'];
export const calcKey = (field: string, part: 'left' | 'operator' | 'right') => `_${field}_calc_${part}`;

export function calculatedPreview(field: string, row: Record<string, unknown>, constants: Record<string, string>): string {
  const decimal = constants._decimal_separator === ',' ? ',' : '.';
  const group = decimal === ',' ? '.' : ',';
  const lookup = Object.fromEntries(Object.entries(row).map(([key, value]) => [key.trim().toLowerCase(), value]));
  const parse = (header: string) => {
    if (!header || !(header.trim().toLowerCase() in lookup)) throw new Error('Selecciona ambas columnas');
    const raw = lookup[header.trim().toLowerCase()];
    if (typeof raw === 'number') {
      if (!Number.isFinite(raw)) throw new Error('Valor fuera de rango');
      return raw;
    }
    const text = String(raw).trim().replace(/^['"]|['"]$/g, '').replace(/\s+/g, '').replace(/RD\$|\$/g, '');
    const escape = (value: string) => value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const pattern = new RegExp(`^[+-]?(?:\\d+|\\d{1,3}(?:${escape(group)}\\d{3})+)(?:${escape(decimal)}\\d+)?$`);
    if (text.length > 100 || !pattern.test(text)) throw new Error('La columna contiene un valor no numérico');
    const number = Number(text.split(group).join('').replace(decimal, '.'));
    if (!Number.isFinite(number)) throw new Error('Valor fuera de rango');
    return number;
  };
  try {
    const a = parse(constants[calcKey(field, 'left')]);
    const b = parse(constants[calcKey(field, 'right')]);
    let result: number;
    switch (constants[calcKey(field, 'operator')]) {
      case '+': result = a + b; break;
      case '-': result = a - b; break;
      case '*': result = a * b; break;
      case '/': if (b === 0) throw new Error('División entre cero'); result = a / b; break;
      default: throw new Error('Operación no permitida');
    }
    if (!Number.isFinite(result)) throw new Error('Resultado fuera de rango');
    return result.toLocaleString('es-DO', { useGrouping: false, maximumFractionDigits: 10 });
  } catch (error) { return error instanceof Error ? error.message : 'Cálculo inválido'; }
}
