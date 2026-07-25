-- Permite guardar conexiones API como credenciales reutilizables para importacion webservice.

alter table public.remote_connections
  drop constraint if exists remote_connections_protocolo_check;

alter table public.remote_connections
  add constraint remote_connections_protocolo_check
  check (protocolo in ('FTP', 'SFTP', 'API'));
