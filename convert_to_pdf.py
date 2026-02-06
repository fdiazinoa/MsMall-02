import subprocess
import sys
import os

html_file = "presentacion_msmall.html"
pdf_file = "MSMALL_Funcionalidades.pdf"

# Try using Chrome/Chromium headless
try:
    # Try Google Chrome
    chrome_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    
    # Get absolute path
    abs_html = os.path.abspath(html_file)
    abs_pdf = os.path.abspath(pdf_file)
    
    result = subprocess.run([
        chrome_path,
        "--headless",
        "--disable-gpu",
        f"--print-to-pdf={abs_pdf}",
        f"file://{abs_html}"
    ], capture_output=True, text=True)
    
    if os.path.exists(pdf_file):
        print(f"✅ PDF generado exitosamente: {abs_pdf}")
    else:
        print(f"❌ Error al generar PDF")
        print(f"stdout: {result.stdout}")
        print(f"stderr: {result.stderr}")
        sys.exit(1)
        
except Exception as e:
    print(f"❌ Error: {e}")
    sys.exit(1)
