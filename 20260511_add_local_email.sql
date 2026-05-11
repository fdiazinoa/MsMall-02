ALTER TABLE locales
ADD COLUMN IF NOT EXISTS email VARCHAR(255);

COMMENT ON COLUMN locales.email IS 'Correo de contacto del local para notificaciones operativas y auditoria de dias faltantes.';
