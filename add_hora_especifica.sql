-- Add hora_especifica column to locales table for scheduled imports
ALTER TABLE locales
ADD COLUMN IF NOT EXISTS hora_especifica TIME;

COMMENT ON COLUMN locales.hora_especifica IS 'Hora específica del día para ejecutar la importación automática';
