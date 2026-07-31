-- Prevent a sale from being assigned to a mall different from its local.
-- Existing inconsistencies are repaired separately under an approved,
-- narrowly-scoped production procedure.

create or replace function public.enforce_venta_local_mall_identity()
returns trigger
language plpgsql
set search_path = public
as $$
declare
  expected_mall_id uuid;
begin
  if new.local_id is null then
    raise exception using
      errcode = '23502',
      message = 'ventas.local_id is required to validate mall identity';
  end if;

  select l.mall_id
    into expected_mall_id
  from public.locales l
  where l.id = new.local_id;

  if expected_mall_id is null then
    raise exception using
      errcode = '23503',
      message = 'ventas.local_id must reference a local with mall_id';
  end if;

  if new.mall_id is distinct from expected_mall_id then
    raise exception using
      errcode = '23514',
      message = 'ventas.mall_id must match the mall_id of ventas.local_id';
  end if;

  return new;
end;
$$;

drop trigger if exists trg_enforce_venta_local_mall_identity on public.ventas;

create trigger trg_enforce_venta_local_mall_identity
before insert or update of local_id, mall_id on public.ventas
for each row
execute function public.enforce_venta_local_mall_identity();
