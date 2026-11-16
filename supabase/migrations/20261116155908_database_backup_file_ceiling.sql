-- Permit larger full bases (Agora exceeds 2 GB). Existing limits/defaults stay unchanged.
alter table public.import_backup_policy
    drop constraint import_backup_policy_max_file_mb_check;
alter table public.import_backup_policy
    add constraint import_backup_policy_max_file_mb_check check (max_file_mb between 1 and 5000);
