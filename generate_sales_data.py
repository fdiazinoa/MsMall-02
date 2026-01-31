import csv
import random
from datetime import date, timedelta

start_date = date(2023, 1, 1)
end_date = date(2026, 1, 27)
stores = ['L001', 'L002', 'L003']

filename = 'ventas_generadas.csv'

with open(filename, 'w', newline='') as csvfile:
    writer = csv.writer(csvfile)
    # Header not explicitly requested but good practice, user example didn't have it but previous code expects it?
    # Actually api.ts checks "if (lines.length === 0)" and "for (let i = 1; i < lines.length; i++)", so it EXPECTS a header.
    # The user example:
    # 12345,2024-01-26,L001,100.00,10.00,90.00
    # The user didn't explicitly say "no header", and my code skips the first row. So I MUST add a header.
    writer.writerow(['factura_numero', 'fecha_venta', 'local_codigo', 'total_bruto', 'total_impuestos', 'total_neto'])

    current_date = start_date
    invoice_counter = 10000

    while current_date <= end_date:
        # Generate random number of sales per store per day (e.g., 2-5 sales)
        for store in stores:
            daily_sales_count = random.randint(2, 5)
            
            for _ in range(daily_sales_count):
                invoice_id = str(invoice_counter)
                invoice_counter += 1
                
                # Random amount between 20.00 and 500.00
                gross = round(random.uniform(20.00, 500.00), 2)
                
                # Tax ~19% (standard in many places, or user example 100 -> 10 tax? 
                # User example: 100.00, 10.00, 90.00. That's 10% tax included in gross? Or 100 gross, 10 tax, 90 net?
                # Wait, 90 + 10 = 100. So Net + Tax = Gross.
                # Example 2: 50.00, 5.00, 45.00.  45 + 5 = 50.
                # So Tax is 10% of Gross, or roughly 11.11% of Net.
                # Let's stick to the math: Net = Gross - Tax. Tax = Gross * 0.10.
                
                tax = round(gross * 0.10, 2)
                net = round(gross - tax, 2)
                
                # Adjust for rounding errors to ensure Net + Tax = Gross exactly
                if net + tax != gross:
                    net = round(gross - tax, 2)

                writer.writerow([
                    invoice_id,
                    current_date.isoformat(),
                    store,
                    f"{gross:.2f}",
                    f"{tax:.2f}",
                    f"{net:.2f}"
                ])
        
        current_date += timedelta(days=1)

print(f"Archivo {filename} generado exitosamente.")
