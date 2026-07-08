import { LoadLogEntry } from '../types';

export type LoadLogStatus = 'exito' | 'parcial' | 'error' | string;

export interface OperationalMessage {
  title: string;
  summary: string;
  cause: string;
  action: string;
  category: string;
}

const normalizeText = (value?: string | null): string =>
  String(value || '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase();

export const getLoadLogErrorCount = (log: LoadLogEntry | null): number => {
  if (!log) return 0;
  const explicit = Number(log.error_count);
  if (Number.isFinite(explicit)) return explicit;
  return Array.isArray(log.detalles) ? log.detalles.length : 0;
};

export const getLoadLogProcessedCount = (log: LoadLogEntry | null): number => {
  if (!log) return 0;
  const explicit = Number(log.records_processed);
  return Number.isFinite(explicit) ? explicit : 0;
};

export const getLoadLogStatus = (log: LoadLogEntry | null): LoadLogStatus => {
  if (!log) return 'error';
  const status = String(log.estado || '').trim().toLowerCase();
  if (status === 'parcial') return 'parcial';
  if (status === 'exito' && getLoadLogErrorCount(log) > 0) return 'parcial';
  return status || 'error';
};

export const getRawLoadLogMessage = (log: LoadLogEntry | null): string => {
  const message = String(log?.mensaje || '').trim();
  if (message) return message;
  const processed = getLoadLogProcessedCount(log);
  const errors = getLoadLogErrorCount(log);
  const status = getLoadLogStatus(log);
  if (status === 'exito') return `Carga completada. ${processed} registros procesados.`;
  if (status === 'parcial') return `Carga parcial. ${processed} registros procesados y ${errors} errores.`;
  return 'Sin detalle adicional.';
};

const firstLineError = (log: LoadLogEntry | null): string => {
  if (!Array.isArray(log?.detalles) || log.detalles.length === 0) return '';
  return String(log.detalles[0]?.error || '').trim();
};

export const describeLoadLog = (log: LoadLogEntry | null): OperationalMessage => {
  const rawMessage = getRawLoadLogMessage(log);
  const rawError = firstLineError(log);
  const text = normalizeText(`${rawMessage} ${rawError}`);
  const processed = getLoadLogProcessedCount(log);
  const errors = getLoadLogErrorCount(log);
  const status = getLoadLogStatus(log);

  if (text.includes('archivo nuevo no encontrado') || text.includes('0 pendientes')) {
    const summary = rawMessage.includes('ultimo archivo')
      ? rawMessage
      : 'Archivo nuevo no encontrado. No hay archivos pendientes para importar en la carpeta configurada.';
    return {
      title: 'Archivo nuevo no encontrado.',
      summary,
      cause: 'La conexion fue exitosa, pero no se encontro un archivo nuevo que cumpla el patron, extension o estado pendiente.',
      action: 'Confirme que el locatario subio el archivo correcto y que no este marcado como procesado o error.',
      category: 'Archivo',
    };
  }

  if (
    text.includes('archivo leido con 0 datos')
    || text.includes('archivo vacio')
    || text.includes('sin datos validos')
    || text.includes('no contiene registros')
    || text.includes('solo encabezado')
  ) {
    return {
      title: 'Archivo leido con 0 datos.',
      summary: 'El archivo fue encontrado y leido, pero no contiene registros validos para cargar.',
      cause: 'Puede estar vacio, contener solo encabezados o tener filas que no pasan la validacion inicial.',
      action: 'Solicite al locatario reenviar el archivo con registros de venta o revise la linea donde inicia la data.',
      category: 'Archivo',
    };
  }

  if (
    text.includes('estructura')
    || text.includes('encabezado')
    || text.includes('header')
    || text.includes('separador')
    || text.includes('delimiter')
    || text.includes('no se detectaron columnas')
    || text.includes('mapping')
    || text.includes('mapeo')
  ) {
    return {
      title: 'El archivo no cumple con la estructura requerida.',
      summary: 'La estructura del archivo no coincide con la configuracion del importador.',
      cause: 'Los encabezados, separadores, columnas obligatorias o la linea inicial de data no coinciden con el mapeo.',
      action: 'Revise el mapeo, el separador, la opcion de encabezado y la linea donde inicia la data.',
      category: 'Estructura',
    };
  }

  if (
    text.includes('datos incompletos')
    || text.includes('faltante')
    || text.includes('fecha o total bruto')
    || text.includes('campo obligatorio')
  ) {
    return {
      title: 'Datos incompletos en el registro.',
      summary: 'Uno o mas registros no tienen los campos obligatorios para insertar la venta.',
      cause: 'Falta fecha, total bruto, identificador de factura u otro campo requerido por el mapeo.',
      action: 'Revise las lineas marcadas y corrija los campos obligatorios en el archivo o en el mapeo.',
      category: 'Datos',
    };
  }

  if (
    text.includes('fecha invalida')
    || text.includes('formato de fecha')
    || text.includes('monto invalido')
    || text.includes('decimal')
    || text.includes('campo invalido')
    || text.includes('invalid')
  ) {
    return {
      title: 'Campo invalido.',
      summary: 'Un campo del archivo tiene un formato que el importador no puede interpretar.',
      cause: 'Puede ser una fecha no reconocida, un monto con separador decimal distinto al configurado o un valor no numerico.',
      action: 'Revise el formato de fecha, el separador decimal y el contenido de las lineas reportadas.',
      category: 'Datos',
    };
  }

  if (text.includes('duplicado') || text.includes('duplicate') || text.includes('unique')) {
    return {
      title: 'Documento duplicado.',
      summary: 'La venta ya existe o choca con una restriccion de unicidad.',
      cause: 'El mismo local, fecha y numero de factura ya fueron cargados anteriormente.',
      action: 'Valide si el archivo ya fue importado o si el numero de factura debe corregirse.',
      category: 'Datos',
    };
  }

  if (text.includes('cierre') || text.includes('fecha de corte') || text.includes('periodo cerrado')) {
    return {
      title: 'Periodo cerrado para importacion.',
      summary: 'El registro pertenece a una fecha anterior o igual al cierre configurado para el local.',
      cause: 'El control de cierre de mes evita modificar periodos ya cerrados.',
      action: 'Confirme la fecha de corte del local o cargue solo ventas de periodos abiertos.',
      category: 'Configuracion',
    };
  }

  if (
    text.includes('conexion')
    || text.includes('timed out')
    || text.includes('timeout')
    || text.includes('name or service not known')
    || text.includes('authentication')
    || text.includes('auth')
    || text.includes('permission denied')
    || text.includes('login')
    || text.includes('ftp')
    || text.includes('sftp')
  ) {
    return {
      title: 'No se pudo completar la conexion FTP/SFTP.',
      summary: rawMessage,
      cause: 'El servidor remoto, credenciales, puerto, DNS, ruta o permisos pueden no estar disponibles.',
      action: 'Revise host, puerto, usuario, clave, ruta remota y disponibilidad del servidor del locatario.',
      category: 'Conexion',
    };
  }

  if (
    text.includes('insertar')
    || text.includes('insercion')
    || text.includes('base de datos')
    || text.includes('bd')
    || text.includes('persistencia')
    || text.includes('no se confirmo')
  ) {
    if (status === 'exito' || status === 'parcial') {
      return status === 'parcial'
        ? {
            title: 'Carga parcial.',
            summary: `${processed} registros procesados y ${errors} errores detectados.`,
            cause: 'Parte del archivo fue aceptada, pero algunos registros no cumplieron la validacion o no pudieron insertarse.',
            action: 'Revise las lineas con error, corrija el archivo y reprocese solo lo pendiente si aplica.',
            category: 'Validacion',
          }
        : {
            title: 'Carga completada.',
            summary: rawMessage || `${processed} registros procesados correctamente.`,
            cause: 'El archivo fue validado e insertado sin errores reportados.',
            action: 'No requiere accion.',
            category: 'Exito',
          };
    }

    return {
      title: 'Error al insertar informacion.',
      summary: rawMessage,
      cause: 'El archivo pudo procesarse, pero la base de datos no confirmo la insercion total o parcial.',
      action: 'Revise los errores por linea, duplicados, campos obligatorios y disponibilidad de Supabase.',
      category: 'Base de datos',
    };
  }

  if (status === 'parcial') {
    return {
      title: 'Carga parcial.',
      summary: `${processed} registros procesados y ${errors} errores detectados.`,
      cause: 'Parte del archivo fue aceptada, pero algunos registros no cumplieron la validacion o no pudieron insertarse.',
      action: 'Revise las lineas con error, corrija el archivo y reprocese solo lo pendiente si aplica.',
      category: 'Validacion',
    };
  }

  if (status === 'exito') {
    return {
      title: 'Carga completada.',
      summary: rawMessage || `${processed} registros procesados correctamente.`,
      cause: 'El archivo fue validado e insertado sin errores reportados.',
      action: 'No requiere accion.',
      category: 'Exito',
    };
  }

  return {
    title: 'Fallo de ejecucion.',
    summary: rawMessage,
    cause: 'La carga no pudo completarse y no hay una clasificacion mas especifica disponible.',
    action: 'Revise el detalle tecnico, el archivo origen, la configuracion del importador y los logs del worker.',
    category: 'Ejecucion',
  };
};
