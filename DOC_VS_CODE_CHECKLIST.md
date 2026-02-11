# MsMall-02 - Checklist Doc vs Código

Estado de validación realizado sobre el repositorio local.

## 1. Stack y Runtime
- [x] Frontend React + TypeScript + Vite presente.
- [x] Recharts y Lucide presentes.
- [x] Backend FastAPI presente.
- [x] Pandas, Paramiko y TheFuzz presentes.
- [x] Integración con Supabase/PostgreSQL presente.
- [ ] React 19: no coincide (código usa 18.3.1).
- [ ] Python 3.10+: no coincide (runtime fija 3.9).

## 1.1 Despliegue Operativo (Confirmado)
- [x] Frontend desplegado en Vercel.
- [x] Cron/Worker ejecutados en Railway.

## 2. Arquitectura y Estructura
- [x] Arquitectura monolítica modular observada.
- [x] `main.py` como entrypoint de API.
- [x] `worker_importacion.py` presente y operativo.
- [x] Carpeta `routers/` presente.
- [ ] `routers/analytics_routes.py` no existe.
- [ ] `routers/insights_routes.py` no existe.
- [ ] `run.sh` no existe (sí existe `start_worker.sh`).

## 3. Módulos Funcionales
- [x] BI/KPIs y dashboard financiero presentes.
- [x] Insights y heatmap presentes.
- [x] Importación SFTP/FTP presente.
- [x] Mapeo dinámico CSV/JSON presente.
- [x] Auditoría de brechas de ventas presente.
- [x] Multi-mall y asignación de malls por usuario presentes.

## 4. Seguridad y Gobierno de Datos
- [x] Uso de token Bearer con Supabase Auth en endpoints críticos.
- [x] Evidencia de scripts SQL para RLS y RBAC.
- [x] Logs de carga (`logs_carga`) presentes.
- [ ] Claim de keepalive SSH no está claramente implementado en worker.
- [ ] Claim de reintentos automáticos no está claramente implementado.
- [~] Circuit breaker: existe, pero con implementación parcial/optimista.

## 5. Hallazgo Crítico Corregido
- [x] Se eliminó bypass de autorización en purge de ventas:
  - Antes: permitía acceso con `return True` en modo bypass.
  - Ahora: exige rol `ADMIN` o `TIC` en `usuarios_malls`, y falla cerrado ante error.

## 6. Recomendaciones de Alineación
- Actualizar documentación técnica para reflejar versiones reales (React 18.3.1, Python 3.9 runtime).
- Definir una única fuente de verdad para versión del producto/API (MVP vs `FastAPI version`).
- Mover endpoints de analytics/insights a routers dedicados si esa es la arquitectura objetivo.
- Implementar keepalive/retry explícitos en worker si esos claims deben mantenerse.
