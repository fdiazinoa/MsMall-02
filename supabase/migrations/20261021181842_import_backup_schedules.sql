-- Private artifacts, accessible only through the quota-protected backend.
insert into storage.buckets(id,name,public,file_size_limit,allowed_mime_types)
values('import-backups','import-backups',false,50000000,array['text/csv'])
on conflict(id) do update set public=false,file_size_limit=excluded.file_size_limit,allowed_mime_types=excluded.allowed_mime_types;
-- Existing permissive object policies must not make this dedicated bucket readable.
create policy import_backup_objects_backend_only on storage.objects as restrictive
for all to anon,authenticated using(bucket_id <> 'import-backups') with check(bucket_id <> 'import-backups');

create table public.import_backup_schedules (
 id uuid primary key default gen_random_uuid(),
 owner_id uuid not null references auth.users(id) on delete cascade,
 mall_id uuid not null references public.malls(id) on delete cascade,
 frequency text not null check(frequency in ('weekly','fortnightly','monthly')),
 run_hour integer not null default 2 check(run_hour between 0 and 23),
 folder text not null default 'importaciones' check(folder ~ '^[a-zA-Z0-9_-]+(/[a-zA-Z0-9_-]+)*$' and length(folder)<=80),
 local_ids uuid[],
 retention_days integer not null default 30 check(retention_days between 7 and 90),
 enabled boolean not null default false,
 next_run_at timestamptz not null,
 updated_at timestamptz not null default now(),
 unique(owner_id,mall_id),
 check(local_ids is null or cardinality(local_ids)>0)
);
create index import_backup_schedules_due on public.import_backup_schedules(next_run_at) where enabled;
create table public.import_backup_artifacts (
 id uuid primary key,
 schedule_id uuid references public.import_backup_schedules(id) on delete set null,
 owner_id uuid references auth.users(id) on delete set null,
 mall_id uuid references public.malls(id) on delete set null,
 scheduled_at timestamptz not null,
 start_date date not null,
 end_date date not null check(end_date>=start_date),
 status text not null default 'pending' check(status in ('pending','completed','failed','expired')),
 object_path text not null unique,
 filename text not null,
 bytes bigint not null default 0 check(bytes between 0 and 50000000),
 records integer not null default 0 check(records>=0),
 error text,
 created_at timestamptz not null default now(),
 expires_at timestamptz not null,
 unique(schedule_id,scheduled_at)
);
create index import_backup_artifacts_owner on public.import_backup_artifacts(owner_id,mall_id,created_at desc);
create index import_backup_artifacts_expiry on public.import_backup_artifacts(expires_at) where status <> 'expired';
alter table public.import_backup_schedules enable row level security;
alter table public.import_backup_artifacts enable row level security;
revoke all on public.import_backup_schedules,public.import_backup_artifacts from public,anon,authenticated;
grant all on public.import_backup_schedules,public.import_backup_artifacts to service_role;

-- Claim and advance one slot in the same transaction. Two workers cannot export
-- the same slot. A changed configuration invalidates a stale candidate.
create function public.claim_import_backup_schedule(
 p_id uuid,p_expected timestamptz,p_version timestamptz,p_next timestamptz,
 p_run_id uuid,p_start date,p_end date
) returns jsonb language plpgsql security invoker set search_path='' as $$
declare s public.import_backup_schedules%rowtype; r public.import_backup_artifacts%rowtype;
begin
 if p_next <= now() or p_end < p_start then raise exception 'Invalid backup slot'; end if;
 update public.import_backup_schedules set next_run_at=p_next
 where id=p_id and enabled and next_run_at=p_expected and updated_at=p_version and next_run_at<=now()
 returning * into s;
 if not found then return null; end if;
 insert into public.import_backup_artifacts(id,schedule_id,owner_id,mall_id,scheduled_at,start_date,end_date,object_path,filename,expires_at)
 values(p_run_id,s.id,s.owner_id,s.mall_id,p_expected,p_start,p_end,
 s.mall_id::text||'/'||s.owner_id::text||'/'||s.folder||'/'||p_run_id::text||'.csv',
 'backup_'||p_start::text||'_'||p_end::text||'.csv',now()+make_interval(days=>s.retention_days)) returning * into r;
 return jsonb_build_object('schedule',to_jsonb(s),'artifact',to_jsonb(r));
end $$;
revoke all on function public.claim_import_backup_schedule(uuid,timestamptz,timestamptz,timestamptz,uuid,date,date) from public,anon,authenticated;
grant execute on function public.claim_import_backup_schedule(uuid,timestamptz,timestamptz,timestamptz,uuid,date,date) to service_role;

insert into public.app_role_permissions(role_id,module_key,can_view,can_create,can_update,can_delete)
select id,'backup_schedules',key='admin',key='admin',key='admin',key='admin' from public.app_roles
on conflict(role_id,module_key) do nothing;
