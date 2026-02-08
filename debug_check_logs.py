import requests
import json

url = "http://localhost:8000/api/v1/remote/execute-manual"
payload = {
    "config_id": "dummy-id", 
    "filename": "test.json",
    "config": {
        "nombre": "Test",
        "protocolo": "SFTP",
        "host": "test",
        "puerto": 22,
        "usuario": "test",
        "password": "test",
        "ruta_remota": "/tmp/test.json"
    }
}

try:
    print(f"Sending request to {url}...")
    res = requests.post(url, json=payload)
    print(f"Status: {res.status_code}")
    print(f"Response: {res.text}")
except Exception as e:
    print(f"Error: {e}")
    for entry in data:
        print("-" * 50)
        print(f"ID: {entry.get('id')}")
        print(f"Fecha: {entry.get('fecha_hora')}")
        print(f"Archivo: {entry.get('archivo')}")
        print(f"Estado: {entry.get('estado')}")
        print(f"Mensaje: {entry.get('mensaje')}")
        
        detalles = entry.get('detalles')
        if detalles:
            print("Detalles de error:")
            if isinstance(detalles, str):
                try:
                    detalles = json.loads(detalles)
                except:
                    print(detalles)
            
            if isinstance(detalles, list):
                for d in detalles:
                    print(f"  - {d}")
            else:
                print(f"  {detalles}")
        print("-" * 50)

except Exception as e:
    print(f"Error querying Supabase: {e}")
