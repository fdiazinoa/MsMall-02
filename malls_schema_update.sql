-- Add timezone column to malls table
ALTER TABLE malls ADD COLUMN IF NOT EXISTS timezone TEXT DEFAULT 'America/Santo_Domingo';

-- Update existing malls (optional, but good for defaults)
UPDATE malls SET timezone = 'America/Santo_Domingo' WHERE timezone IS NULL;
