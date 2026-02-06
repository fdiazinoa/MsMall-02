
import json
import io
import csv
from datetime import datetime
from typing import Dict, Any

# Mocking enough of main.py logic to test process_file_content
def mock_process_file_content(content: str, filename: str, config: Dict[str, Any]):
    mapping = config.get("mapping", {})
    constants = config.get("constants", {})
    tipo_archivo = config.get("tipo_archivo", "CSV").upper()
    
    records_to_insert = []
    errors = []
    
    try:
        raw_rows = []
        if tipo_archivo == "JSON":
            data = json.loads(content)
            if isinstance(data, list):
                raw_rows = data
            elif isinstance(data, dict):
                for k, v in data.items():
                    if isinstance(v, list) and len(v) > 0 and isinstance(v[0], dict):
                        raw_rows = v
                        break
                if not raw_rows:
                    raw_rows = [data]
        else:
            f = io.StringIO(content)
            reader = csv.DictReader(f)
            raw_rows = list(reader)

        for i, row in enumerate(raw_rows):
            record = {}
            for sys_field, header in mapping.items():
                if header in row:
                    record[sys_field] = row[header]
            for k, v in constants.items():
                record[k] = v
            
            # Normalization logic from main.py
            raw_date = str(record.get('fecha_venta', '')).strip()
            parsed_date = None
            for fmt in ['%d/%m/%Y', '%Y-%m-%d', '%m/%d/%Y', '%d-%m-%Y', '%Y/%m/%d']:
                try:
                    parsed_date = datetime.strptime(raw_date, fmt)
                    break
                except ValueError:
                    continue
            
            if parsed_date:
                record['fecha_venta'] = parsed_date.strftime('%Y-%m-%d')
            
            for num_field in ['total_bruto', 'total_impuestos', 'total_neto']:
                val = record.get(num_field, 0.0)
                if val is None: val = 0.0
                try:
                    record[num_field] = float(str(val).replace(',', '').strip())
                except:
                    record[num_field] = 0.0
            
            records_to_insert.append(record)
            
    except Exception as e:
        print(f"Error: {e}")
        return 0, [str(e)]
    return records_to_insert, errors

# Test Case
json_content = json.dumps([
    {"invoice": "101", "date": "06/02/2026", "sales": "1,250.50", "store": "S001"},
    {"invoice": "102", "date": "2026-02-07", "sales": 800.00, "store": "S001"}
])

config = {
    "tipo_archivo": "JSON",
    "mapping": {
        "factura_numero": "invoice",
        "fecha_venta": "date",
        "total_bruto": "sales",
        "local_codigo": "store"
    },
    "constants": {"mall_id": "MALL-01"}
}

records, errs = mock_process_file_content(json_content, "test.json", config)
print("Processed Records:")
for r in records:
    print(r)
if errs:
    print("Errors:", errs)

# Assertions
assert records[0]['fecha_venta'] == '2026-02-06'
assert records[0]['total_bruto'] == 1250.5
assert records[1]['fecha_venta'] == '2026-02-07'
assert records[1]['total_bruto'] == 800.0
print("\nValidation PASSED!")
