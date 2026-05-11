CREATE TABLE IF NOT EXISTS public.email_notification_settings (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  mall_id uuid NOT NULL REFERENCES public.malls(id) ON DELETE CASCADE,
  notification_type text NOT NULL DEFAULT 'missing_days_audit',
  enabled boolean NOT NULL DEFAULT false,
  weekdays smallint[] NOT NULL DEFAULT '{}',
  send_time time NOT NULL DEFAULT '08:00',
  lookback_days integer NOT NULL DEFAULT 7 CHECK (lookback_days BETWEEN 1 AND 90),
  send_only_with_gaps boolean NOT NULL DEFAULT true,
  cc_emails text[] NOT NULL DEFAULT '{}',
  created_by uuid NULL,
  updated_by uuid NULL,
  created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  updated_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  UNIQUE (mall_id, notification_type)
);

COMMENT ON TABLE public.email_notification_settings IS 'Configuracion recurrente de notificaciones por email.';
COMMENT ON COLUMN public.email_notification_settings.weekdays IS 'Dias de envio: 0=lunes, 6=domingo.';
COMMENT ON COLUMN public.email_notification_settings.lookback_days IS 'Cantidad de dias hacia atras que se auditan en cada envio.';
