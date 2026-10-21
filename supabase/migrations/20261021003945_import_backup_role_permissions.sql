-- Preserve existing backup access, then manage it independently of sales reports.
INSERT INTO public.app_role_permissions (role_id, module_key, can_view, can_create, can_update, can_delete)
SELECT role_id, 'import_backup', can_view, false, false, false
FROM public.app_role_permissions
WHERE module_key = 'sales_reports'
ON CONFLICT (role_id, module_key) DO NOTHING;
