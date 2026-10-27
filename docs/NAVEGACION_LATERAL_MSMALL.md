# Navegación lateral MsMall

Base: `origin/main` (`8abdb0a`). Rama: `feature/navigation-contextual`.

## Estructura y alcance

- `components/navigation.ts`: catálogo único de los 22 destinos AppTab existentes, grupos y visibilidad. Sidebar y selector móvil del encabezado lo consumen. No se cambian identificadores, URLs, Dashboard, sesión ni selección de mall.
- `components/RetailNavigation.tsx`: barra permanente de 64 px y panel fijo de 320 px superpuesto, búsquedas global y del grupo, favoritos, últimos ocho accesos, fijado en escritorio, teclado, foco y drawer móvil.
- `components/navigation.css`: identidad MsMall, fondo oscuro, acento turquesa, estados activos y foco, animación con respeto a reduced-motion. El panel no participa del layout. Sus capas quedan por debajo de los modales existentes.
- `components/Sidebar.tsx`: conserva el cambio de contraseña y delega la navegación; `Header.tsx` conserva encabezado y selector móvil, eliminando su catálogo duplicado.
- Pruebas actualizadas: `tests/import_backup_navigation.test.cjs`, `tests/test_frontend_sensitive_ops_smoke.py`, `tests/test_mall_comparison_frontend.py`; pruebas nuevas en `tests/navigation.test.cjs`.

## Comportamiento

La estrella añade o quita favoritos. Recientes y favoritos siempre se filtran contra las opciones permitidas, también tras cambios de permisos. Buscar no consulta datos del negocio: busca nombres de opciones autorizadas y tolera acentos.

Fijar conserva el panel después de elegir un destino en escritorio/tablet. No reserva espacio adicional. El botón de cierre, Escape y clic fuera lo cierran incluso fijado. En móvil nunca se aplica el fijado: hay fondo oscurecido, foco inicial en búsqueda, ciclo de Tab dentro del drawer y área de trabajo inert mientras está abierto. Las flechas arriba/abajo y Home/End recorren los iconos; todos los controles aceptan Tab, Enter/Espacio y tienen nombres accesibles.

Se guardan grupo, panel abierto, fijado, favoritos, recientes y última vista en `localStorage`, bajo una clave versionada por usuario y mall. Solo se restaura un destino autorizado; si el almacenamiento está bloqueado o corrupto el menú funciona sin persistencia. No se guardan credenciales ni datos de ventas. El estado global del área de trabajo no se remonta al abrir/cerrar el panel. Como antes, cambiar AppTab puede desmontar la vista anterior; no se añade un sistema de pestañas ni se altera esa política.

## Permisos y limitaciones previas

AuthProvider sigue siendo la fuente de permisos y roles. Se conservan las excepciones existentes por rol para reportes, administración e importación; los permisos explícitos de backups siguen siendo independientes del rol admin. Las opciones antes incondicionales de indicadores/finanzas/cubo se ocultan cuando faltan sus permisos ya existentes (`dashboard`, `financial`, `cube`), para cumplir la visibilidad requerida. No se cambian permisos de servidor ni reglas de negocio.

Esta revisión no contiene módulos, destinos, permisos o licencias de Recursos Humanos ni Nómina. No se crean entradas ficticias ni se combinan ambos conceptos. Para incorporarlos hacen falta sus implementaciones y contratos de acceso independientes.

La licencia Big Data se comprueba dentro del módulo, no en AuthProvider. Se conserva esa comprobación. El menú no introduce una segunda fuente de licencias ni una consulta de licencias paralela. El selector móvil anterior duplicaba Operations Center y aplicaba visibilidad distinta del lateral; ahora consume el catálogo común.

## Validación

- 41 pruebas Node correctas: todas las suites `tests/*.test.cjs` y `tests/*.test.mjs`, incluyendo acceso limitado, admin con permisos revocados, búsquedas y preferencias corruptas.
- Navegador Chrome con harness local del componente real y AuthProvider simulado: 1440×900, 820×1000 y 390×844. Medición de x/ancho del workspace antes/después: idéntica. Probados búsqueda global/local, favoritos, recientes, recarga, fijado, clic exterior, Escape, ciclo de foco móvil, conservación del formulario y filtrado de rol limitado. Los 22 callbacks entregan el AppTab esperado. Sin errores de ejecución del navegador.
- Esta prueba verifica navegación con perfiles simulados, no autenticaciones reales de producción ni la lógica interna de los 22 módulos.
- `npm run build`: correcto; advertencia previa de tamaño del bundle.
- ESLint sobre los cuatro TS/TSX modificados: correcto usando instalación temporal de ESLint y parser TypeScript con reglas de sintaxis (no-debugger, no-duplicate-case, no-unreachable, no-constant-condition). El repositorio no incluye configuración ni script ESLint; no se añade una política de lint global en esta tarea.
- `npx tsc --noEmit`: falla con los mismos diagnósticos que la base; comparación de logs sin diferencias. Errores previos en api.ts, ImportManager, SalesCube, SecurityTokenAdmin, SmartInsights, StoreImportTool y dependencias/tipos Bun de railway-functions. Ninguno en archivos de esta tarea.
- `python3 -m pytest tests -q --disable-warnings`: 651 correctas, 20 omitidas y 24 fallidas. Ejecutado también en una copia limpia de origin/main: mismos resultados y mismos nombres de pruebas fallidas, sin regresiones. Fallos ajenos de importadores, tokens y roles, entre otros; no se corrigen aquí.
- Invocación pytest desde la raíz: colección interrumpida por `test_mapping_endpoint.py`, que requiere localhost:8000. No se inicia un backend de producción para satisfacer esa prueba.
- `git diff --check`: correcto. No se ejecutan backups, restauraciones, migraciones ni cambios en Railway/Supabase.
