-- Migration: Recipes, Kits & Inventory Transformation
-- Date: 2026-02-05

-- 1. Create Items Table (if not exists) as the base for Products and Ingredients
-- Note: Assuming 'items' is the table name based on user prompt. 
-- In a real integration, this might need to sync with 'products' in CLIC-POS, 
-- but for the scope of this backend module, we define the structure here.

CREATE TYPE tipo_item_enum AS ENUM ('MATERIA_PRIMA', 'PRODUCTO_TERMINADO', 'RECETA', 'KIT');

CREATE TABLE IF NOT EXISTS items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    nombre VARCHAR(255) NOT NULL,
    sku VARCHAR(100) UNIQUE,
    tipo_item tipo_item_enum DEFAULT 'PRODUCTO_TERMINADO',
    es_inventariable BOOLEAN DEFAULT TRUE,
    costo_unitario NUMERIC(15, 4) DEFAULT 0, -- Costo manual para materias primas
    costo_teorico NUMERIC(15, 4) DEFAULT 0, -- Costo calculado para recetas
    precio_venta NUMERIC(15, 2) DEFAULT 0,
    unidad_medida VARCHAR(20) DEFAULT 'un',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 2. Create Recipe Details (Recetas Detalles) - The Bill of Materials (BOM)
CREATE TABLE IF NOT EXISTS recetas_detalles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    parent_item_id UUID NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    child_item_id UUID NOT NULL REFERENCES items(id) ON DELETE RESTRICT, -- Prevents deleting an ingredient used in a recipe
    cantidad_bruta NUMERIC(15, 4) NOT NULL, -- Gross quantity needed
    unidad_medida VARCHAR(20) NOT NULL, -- Unit used in the recipe (e.g., 'g')
    factor_merma NUMERIC(5, 4) DEFAULT 0, -- Waste factor (0.10 = 10%)
    es_opcional BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT uq_receta_parent_child UNIQUE (parent_item_id, child_item_id)
);

-- Index for fast lookup of a product's ingredients
CREATE INDEX idx_recetas_parent ON recetas_detalles(parent_item_id);
-- Index to find which recipes use a specific ingredient (Impact Analysis)
CREATE INDEX idx_recetas_child ON recetas_detalles(child_item_id);

-- 3. Trigger to update updated_at on items
CREATE OR REPLACE FUNCTION update_items_timestamp()
RETURNS TRIGGER AS $$
BEGIN
   NEW.updated_at = NOW();
   RETURN NEW;
END;
$$ language 'plpgsql';

DROP TRIGGER IF EXISTS tr_items_updated ON items;
CREATE TRIGGER tr_items_updated
    BEFORE UPDATE ON items
    FOR EACH ROW
    EXECUTE PROCEDURE update_items_timestamp();
