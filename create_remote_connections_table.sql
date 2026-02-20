-- Tabla de conexiones remotas reutilizables por mall
create table if not exists public.remote_connections (
  id uuid primary key default gen_random_uuid(),
  mall_id uuid not null references public.malls(id) on delete cascade,
  nombre text not null,
  protocolo text not null check (protocolo in ('FTP', 'SFTP')),
  host text not null,
  puerto integer not null default 22,
  usuario text not null,
  password text not null,
  ruta_base text,
  created_at timestamptz not null default now()
);

create index if not exists idx_remote_connections_mall_id
  on public.remote_connections(mall_id);

create unique index if not exists uq_remote_connections_mall_nombre
  on public.remote_connections(mall_id, nombre);
