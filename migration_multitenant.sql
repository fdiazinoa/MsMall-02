-- FASE 1: Migración a Multi-Tenant (Single DB)

-- 1. Agregar columna mall_id a ventas (Nullable inicialmente)
ALTER TABLE ventas ADD COLUMN IF NOT EXISTS mall_id UUID REFERENCES malls(id);

-- 2. Backfill: Llenar mall_id basado en la relación con locales
UPDATE ventas v
SET mall_id = l.mall_id
FROM locales l
WHERE v.local_id = l.id
AND v.mall_id IS NULL;

-- 3. Hacer la columna obligatoria (Despues del backfill)
ALTER TABLE ventas ALTER COLUMN mall_id SET NOT NULL;

-- 4. Crear índice optimizado para consultas por tenant
CREATE INDEX IF NOT EXISTS idx_ventas_mall_fecha ON ventas(mall_id, fecha);

-- 5. Gestión de Usuarios Multi-Mall (Tabla Intermedia)
CREATE TABLE IF NOT EXISTS usuarios_malls (
    usuario_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    mall_id UUID REFERENCES malls(id) ON DELETE CASCADE,
    rol TEXT DEFAULT 'user', -- 'admin', 'manager', 'viewer'
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    PRIMARY KEY (usuario_id, mall_id)
);

-- Indice para búsquedas rápidas de permisos
CREATE INDEX IF NOT EXISTS idx_usuarios_malls_user ON usuarios_malls(usuario_id);

-- 6. RLS (Row Level Security)
ALTER TABLE ventas ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Tenant Isolation Policy" ON ventas;

CREATE POLICY "Tenant Isolation Policy" ON ventas
    FOR SELECT
    USING (
        mall_id IN (
            SELECT mall_id FROM usuarios_malls 
            WHERE usuario_id = auth.uid()
        )
        OR 
        (auth.jwt() ->> 'role') = 'service_role'
    );

-- 7. SEED DATA (Crucial para que la nueva lógica no bloquee el acceso)
-- Asignar el primer Mall encontrado a todos los usuarios existentes como Admin
INSERT INTO usuarios_malls (usuario_id, mall_id, rol)
SELECT u.id, m.id, 'admin'
FROM auth.users u, (SELECT id FROM malls LIMIT 1) m
ON CONFLICT (usuario_id, mall_id) DO NOTHING;
