-- RBAC configurable para MsMall.
-- Mantiene Administrador, IT, Auditor y Visualizador como perfiles de fábrica.

CREATE TABLE IF NOT EXISTS public.app_roles (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    key text NOT NULL UNIQUE CHECK (key ~ '^[a-z][a-z0-9_]{1,63}$'),
    nombre text NOT NULL,
    descripcion text,
    is_factory boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.app_role_permissions (
    role_id uuid NOT NULL REFERENCES public.app_roles(id) ON DELETE CASCADE,
    module_key text NOT NULL CHECK (module_key ~ '^[a-z][a-z0-9_]{1,63}$'),
    can_view boolean NOT NULL DEFAULT false,
    can_create boolean NOT NULL DEFAULT false,
    can_update boolean NOT NULL DEFAULT false,
    can_delete boolean NOT NULL DEFAULT false,
    PRIMARY KEY (role_id, module_key),
    CONSTRAINT app_role_permissions_requires_view
      CHECK (NOT (can_create OR can_update OR can_delete) OR can_view)
);

CREATE TABLE IF NOT EXISTS public.profile_role_assignments (
    user_id uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    role_id uuid NOT NULL REFERENCES public.app_roles(id) ON DELETE RESTRICT,
    assigned_at timestamptz NOT NULL DEFAULT now(),
    assigned_by uuid REFERENCES auth.users(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_app_role_permissions_role_id
    ON public.app_role_permissions(role_id);

ALTER TABLE public.app_roles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.app_role_permissions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.profile_role_assignments ENABLE ROW LEVEL SECURITY;

-- El frontend no accede directamente a estas tablas: la API valida permisos
-- y usa la service role. No se crean políticas públicas deliberadamente.

INSERT INTO public.app_roles (key, nombre, descripcion, is_factory)
VALUES
  ('admin', 'Administrador', 'Gestión completa del sistema.', true),
  ('it', 'IT', 'Operación técnica, cargas y mantenimiento.', true),
  ('auditor', 'Auditor', 'Consulta y análisis operativo.', true),
  ('visualizador', 'Visualizador', 'Consulta de indicadores y reportes sin cambios operativos.', true)
ON CONFLICT (key) DO UPDATE
SET nombre = EXCLUDED.nombre,
    descripcion = EXCLUDED.descripcion,
    is_factory = true,
    updated_at = now();

WITH factory_permissions(role_key, module_key, can_view, can_create, can_update, can_delete) AS (
  VALUES
    ('admin', 'dashboard', true, true, true, true),
    ('admin', 'sales_reports', true, true, true, true),
    ('admin', 'stores', true, true, true, true),
    ('admin', 'imports', true, true, true, true),
    ('admin', 'monitor', true, true, true, true),
    ('admin', 'financial', true, true, true, true),
    ('admin', 'cube', true, true, true, true),
    ('admin', 'comparisons', true, true, true, true),
    ('admin', 'malls', true, true, true, true),
    ('admin', 'users', true, true, true, true),
    ('admin', 'roles', true, true, true, true),
    ('it', 'dashboard', true, false, false, false),
    ('it', 'sales_reports', true, true, false, false),
    ('it', 'stores', true, true, true, false),
    ('it', 'imports', true, true, true, false),
    ('it', 'monitor', true, true, true, false),
    ('it', 'financial', true, false, false, false),
    ('it', 'cube', true, false, false, false),
    ('it', 'comparisons', true, false, false, false),
    ('auditor', 'dashboard', true, false, false, false),
    ('auditor', 'sales_reports', true, false, false, false),
    ('auditor', 'monitor', true, false, false, false),
    ('auditor', 'financial', true, false, false, false),
    ('auditor', 'cube', true, false, false, false),
    ('auditor', 'comparisons', true, false, false, false),
    ('visualizador', 'dashboard', true, false, false, false),
    ('visualizador', 'sales_reports', true, false, false, false),
    ('visualizador', 'financial', true, false, false, false),
    ('visualizador', 'cube', true, false, false, false),
    ('visualizador', 'comparisons', true, false, false, false)
)
INSERT INTO public.app_role_permissions (role_id, module_key, can_view, can_create, can_update, can_delete)
SELECT r.id, p.module_key, p.can_view, p.can_create, p.can_update, p.can_delete
FROM factory_permissions p
JOIN public.app_roles r ON r.key = p.role_key
ON CONFLICT (role_id, module_key) DO UPDATE
SET can_view = EXCLUDED.can_view,
    can_create = EXCLUDED.can_create,
    can_update = EXCLUDED.can_update,
    can_delete = EXCLUDED.can_delete;

-- Asignación inicial: cada usuario conserva su rol actual con una plantilla equivalente.
INSERT INTO public.profile_role_assignments (user_id, role_id)
SELECT p.id, r.id
FROM public.profiles p
JOIN public.app_roles r ON r.key = CASE
  WHEN lower(coalesce(p.role::text, p.rol::text, 'auditor')) IN ('admin', 'superadmin', 'super_admin', 'administrador') THEN 'admin'
  WHEN lower(coalesce(p.role::text, p.rol::text, 'auditor')) IN ('it', 'tic') THEN 'it'
  ELSE 'auditor'
END
ON CONFLICT (user_id) DO NOTHING;
