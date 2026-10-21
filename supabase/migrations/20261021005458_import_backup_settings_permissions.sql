-- Only administrators retain global settings access by default.
-- Existing explicit grants/revocations are never overwritten on reapplication.
INSERT INTO public.app_role_permissions (role_id, module_key, can_view, can_create, can_update, can_delete)
SELECT id, 'backup_settings', key = 'admin', false, key = 'admin', false
FROM public.app_roles
ON CONFLICT (role_id, module_key) DO NOTHING;
