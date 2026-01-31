
-- Add ultima_ejecucion column to locales table for tracking worker activity
ALTER TABLE locales
ADD COLUMN IF NOT EXISTS ultima_ejecucion TIMESTAMP WITH TIME ZONE;

COMMENT ON COLUMN locales.ultima_ejecucion IS 'Fecha y hora de la última ejecución exitosa del worker de importación';
