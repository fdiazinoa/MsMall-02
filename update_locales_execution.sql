-- Actualiza la tabla locales para soportar la configuración de ejecución de importaciones
ALTER TABLE locales
ADD COLUMN tipo_ejecucion VARCHAR(20) DEFAULT 'MANUAL', -- 'MANUAL', 'AUTOMATICO'
ADD COLUMN frecuencia_cron VARCHAR(100), -- 'Cada hora', o formato cron
ADD COLUMN accion_post_procesado VARCHAR(50) DEFAULT 'NINGUNA', -- 'NINGUNA', 'RENOMBRAR_PROCESADO', 'ELIMINAR'
ADD COLUMN prefijo_backup VARCHAR(50) DEFAULT 'PR_',
-- Campos de conexión (migrados desde localStorage)
ADD COLUMN sftp_host VARCHAR(255),
ADD COLUMN sftp_port INTEGER DEFAULT 22,
ADD COLUMN sftp_user VARCHAR(100),
ADD COLUMN sftp_pass TEXT,
ADD COLUMN sftp_path TEXT DEFAULT '.',
ADD COLUMN sftp_protocol VARCHAR(10) DEFAULT 'SFTP',
ADD COLUMN file_type VARCHAR(10) DEFAULT 'CSV',
-- Configuración de Mapeo
ADD COLUMN mapping_config JSONB DEFAULT '{}',
ADD COLUMN constants_config JSONB DEFAULT '{}';

COMMENT ON COLUMN locales.tipo_ejecucion IS 'Modo de procesado: interactivo manual o lote automático';
COMMENT ON COLUMN locales.accion_post_procesado IS 'Acción a realizar en el servidor remoto tras éxito';
