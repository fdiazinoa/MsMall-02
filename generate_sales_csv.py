import csv
import random
from datetime import date, timedelta
import os

# Configuration
START_DATE = date(2023, 1, 1)
END_DATE = date.today()
OUTPUT_FILE = "ventas_generadas.csv"
STORE_CODES = ["L001", "L002", "L003"] # Assuming these exist or user will map them. Using L001 primarily.

def generate_csv():
    print(f"Generando ventas desde {START_DATE} hasta {END_DATE}...")
    
    with open(OUTPUT_FILE, mode='w', newline='') as file:
        writer = csv.writer(file)
        # Header
        writer.writerow(["factura_numero", "fecha_venta", "local_codigo", "total_bruto", "total_impuestos", "total_neto", "comprobante", "hora_transaccion"])
        
        current_date = START_DATE
        invoice_counter = 10000
        
        while current_date <= END_DATE:
            # Generate 0 to 5 sales per day per store
            for store in STORE_CODES:
                num_sales = random.randint(0, 5)
                
                for _ in range(num_sales):
                    invoice_id = str(invoice_counter)
                    
                    # Random amount between 20.00 and 500.00
                    neto = round(random.uniform(20.00, 500.00), 2)
                    tax_rate = 0.10 # 10% tax based on example
                    impuestos = round(neto * tax_rate, 2)
                    bruto = round(neto + impuestos, 2)
                    
                    hora = f"{random.randint(10, 21):02}:{random.randint(0, 59):02}:{random.randint(0, 59):02}"
                    comprobante = f"BE-{invoice_id}"

                    writer.writerow([
                        invoice_id,
                        current_date.isoformat(),
                        store,
                        f"{bruto:.2f}",
                        f"{impuestos:.2f}",
                        f"{neto:.2f}",
                        comprobante,
                        hora
                    ])
                    
                    invoice_counter += 1
            
            current_date += timedelta(days=1)
            
    print(f"Archivo generado exitosamente: {os.path.abspath(OUTPUT_FILE)}")

if __name__ == "__main__":
    generate_csv()
