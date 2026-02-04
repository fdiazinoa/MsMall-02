-- Add concurrency control columns to 'locales' table

DO $$ 
BEGIN 
    -- Add processing_status if it doesn't exist
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'locales' AND column_name = 'processing_status') THEN
        ALTER TABLE locales ADD COLUMN processing_status VARCHAR(20) DEFAULT 'IDLE';
        ALTER TABLE locales ADD CONSTRAINT check_processing_status CHECK (processing_status IN ('IDLE', 'BUSY'));
    END IF;

    -- Add processing_started_at if it doesn't exist
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'locales' AND column_name = 'processing_started_at') THEN
        ALTER TABLE locales ADD COLUMN processing_started_at TIMESTAMP WITH TIME ZONE;
    END IF;
END $$;
