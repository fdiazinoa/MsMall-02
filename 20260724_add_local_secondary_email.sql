ALTER TABLE locales
ADD COLUMN IF NOT EXISTS email_secundario VARCHAR(255);

COMMENT ON COLUMN locales.email_secundario IS 'Correo adicional del local para recibir notificaciones operativas y auditorías de días faltantes.';
