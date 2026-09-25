-- These functions use schema-qualified relations. Pin an empty search_path so
-- future unqualified objects cannot be resolved from a caller-controlled schema.

ALTER FUNCTION public.audit_sales_dates(uuid, uuid[], date, date)
    SET search_path = '';

ALTER FUNCTION public.audit_sales_summary(uuid, date, date, uuid)
    SET search_path = '';

ALTER FUNCTION public.audit_annual_status(uuid, uuid[], date, date)
    SET search_path = '';
