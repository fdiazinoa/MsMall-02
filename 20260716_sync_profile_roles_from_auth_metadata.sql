-- Reconcile role changes that reached Auth metadata but failed in profiles because
-- the legacy app_role enum stores the IT role as "tic".
with desired_roles as (
  select
    u.id,
    case lower(coalesce(u.raw_user_meta_data->>'rol', u.raw_user_meta_data->>'role', ''))
      when 'admin' then 'admin'::public.app_role
      when 'superadmin' then 'admin'::public.app_role
      when 'super_admin' then 'admin'::public.app_role
      when 'administrador' then 'admin'::public.app_role
      when 'it' then 'tic'::public.app_role
      when 'tic' then 'tic'::public.app_role
      when 'auditor' then 'auditor'::public.app_role
      else null
    end as role
  from auth.users u
)
update public.profiles p
set
  role = desired_roles.role,
  updated_at = now()
from desired_roles
where p.id = desired_roles.id
  and desired_roles.role is not null
  and p.role is distinct from desired_roles.role;
