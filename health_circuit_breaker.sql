-- Health Check & Circuit Breaker Migration

-- 1. Create system_health table for Heartbeat
CREATE TABLE IF NOT EXISTS system_health (
    key VARCHAR(50) PRIMARY KEY,
    value TEXT,
    last_update TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Initialize Heartbeat key if not exists
INSERT INTO system_health (key, value, last_update)
VALUES ('CRON_LAST_RUN', 'INITIAL', CURRENT_TIMESTAMP)
ON CONFLICT (key) DO NOTHING;

-- 2. Add consecutive_failures to locales for Circuit Breaker
DO $$ 
BEGIN 
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'locales' AND column_name = 'consecutive_failures') THEN
        ALTER TABLE locales ADD COLUMN consecutive_failures INTEGER DEFAULT 0;
    END IF;
END $$;
