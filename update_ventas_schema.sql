-- Add Comprobante and Hora_Transaccion columns to ventas table

ALTER TABLE ventas 
ADD COLUMN IF NOT EXISTS comprobante TEXT,
ADD COLUMN IF NOT EXISTS hora_transaccion TIME;

COMMENT ON COLUMN ventas.comprobante IS 'Número o código del comprobante de venta';
COMMENT ON COLUMN ventas.hora_transaccion IS 'Hora exacta de la transacción';
