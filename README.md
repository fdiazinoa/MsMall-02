
# MSMALL - Documentación de API de Consumo

Esta plataforma permite a los locales de los centros comerciales automatizar el envío de sus ventas para auditoría.

## Endpoint de Ingesta
`POST /api/v1/ingesta`

### Cabeceras (Headers)
| Header | Valor | Descripción |
|--------|-------|-------------|
| `X-API-Key` | `tu-api-key-secreta` | Clave de autenticación proporcionada por la administración del mall. |
| `Content-Type` | `multipart/form-data` | El archivo debe enviarse como un formulario binario. |

### Cuerpo de la Petición (Body)
- `file`: Archivo `.csv` con las ventas del día.

### Ejemplo de consumo con cURL
```bash
curl -X POST "http://localhost:8000/api/v1/ingesta" \
     -H "X-API-Key: demo-key-123" \
     -F "file=@ventas_hoy.csv"
```

### Formato de CSV Requerido
El archivo debe contener al menos las siguientes columnas:
`factura_numero, fecha_venta, local_codigo, total_bruto, total_impuestos, total_neto`

### Respuestas
- **201 Created**: El archivo fue procesado con éxito.
- **403 Forbidden**: API Key inválida.
- **422 Unprocessable Entity**: El CSV no tiene el formato correcto.
