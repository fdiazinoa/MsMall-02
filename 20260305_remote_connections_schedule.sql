-- Adds per-destination execution schedule to reusable remote connections.
-- This keeps schedule attached to the connection template (FTP/SFTP) itself.

alter table if exists public.remote_connections
  add column if not exists schedule_frequency text not null default 'manual';

alter table if exists public.remote_connections
  add column if not exists schedule_time time null;

alter table if exists public.remote_connections
  drop constraint if exists remote_connections_schedule_frequency_chk;

alter table if exists public.remote_connections
  add constraint remote_connections_schedule_frequency_chk
  check (schedule_frequency in ('manual', 'cada_hora', 'cada_2_horas', 'hora_especifica'));
