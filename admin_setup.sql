-- 1. Create system_audit_logs table
CREATE TABLE IF NOT EXISTS system_audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ DEFAULT now(),
    usuario_id UUID REFERENCES auth.users(id),
    mall_id UUID REFERENCES malls(id),
    accion TEXT NOT NULL,
    detalle TEXT,
    metadata JSONB
);

-- Habilitar RLS
ALTER TABLE system_audit_logs ENABLE ROW LEVEL SECURITY;

-- Política opcional: Solo admins pueden ver logs
CREATE POLICY "Admins can view audit logs" 
ON system_audit_logs FOR SELECT 
TO authenticated 
USING (
  EXISTS (
    SELECT 1 FROM usuarios_malls 
    WHERE usuario_id = auth.uid() 
    AND mall_id = system_audit_logs.mall_id 
    AND rol IN ('ADMIN', 'TIC')
  )
);

-- 2. Asegurar que las políticas de ventas permitan DELETE a los roles autorizados
-- Nota: Usualmente ventas tiene RLS. Necesitamos una política específica para DELETE.
CREATE POLICY "Admins and TIC can delete sales" 
ON ventas FOR DELETE 
TO authenticated 
USING (
  EXISTS (
    SELECT 1 FROM usuarios_malls 
    WHERE usuario_id = auth.uid() 
    AND mall_id = ventas.mall_id 
    AND rol IN ('ADMIN', 'TIC')
  )
);
