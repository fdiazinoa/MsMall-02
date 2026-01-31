-- SQL for Supabase: Update locales table for financial analysis
-- Run this in the Supabase SQL Editor

ALTER TABLE locales 
ADD COLUMN IF NOT EXISTS renta_fija NUMERIC DEFAULT 0,
ADD COLUMN IF NOT EXISTS breakpoint_venta NUMERIC DEFAULT 0,
ADD COLUMN IF NOT EXISTS porcentaje_variable NUMERIC DEFAULT 0;

-- Optional: Seed some data for Adidas as an example
UPDATE locales 
SET renta_fija = 4500, 
    breakpoint_venta = 50000, 
    porcentaje_variable = 0.08
WHERE nombre ILIKE '%Adidas%';
