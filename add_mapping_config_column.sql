-- Migration to add JSONB column for column mapping configuration
ALTER TABLE locales 
ADD COLUMN IF NOT EXISTS configuracion_mapeo JSONB DEFAULT '{}'::jsonb;

COMMENT ON COLUMN locales.configuracion_mapeo IS 'Almacena el mapeo de columnas del archivo CSV a campos del sistema para importación automática.';
