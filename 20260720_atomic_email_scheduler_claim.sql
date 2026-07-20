-- Prevent duplicate scheduled emails when multiple API/worker instances poll at once.
ALTER TABLE public.system_health
  ALTER COLUMN key TYPE text;

CREATE OR REPLACE FUNCTION public.claim_system_health_slot(
  p_key text,
  p_slot text
)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  claimed boolean;
BEGIN
  INSERT INTO public.system_health (key, value, last_update)
  VALUES (p_key, p_slot, timezone('utc', now()))
  ON CONFLICT (key) DO UPDATE
  SET value = EXCLUDED.value,
      last_update = EXCLUDED.last_update
  WHERE public.system_health.value IS DISTINCT FROM EXCLUDED.value
  RETURNING true INTO claimed;

  RETURN COALESCE(claimed, false);
END;
$$;

REVOKE ALL ON FUNCTION public.claim_system_health_slot(text, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.claim_system_health_slot(text, text) FROM anon, authenticated;
GRANT EXECUTE ON FUNCTION public.claim_system_health_slot(text, text) TO service_role;

COMMENT ON FUNCTION public.claim_system_health_slot(text, text)
IS 'Atomically reserves a scheduler slot. Only the first caller for a key/slot receives true.';
