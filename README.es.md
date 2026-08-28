<p align="center">
  <img src="branding/paladin.gif" alt="coffee-paladin - la mascota del proyecto" width="220">
</p>
<p align="center"><em>Shield the Process, Sip the Coffee</em></p>

# coffee-paladin

**Un fusible térmico y de energía para Macs con Apple Silicon - de un solo portátil
a una flota entera.** Vigila la temperatura del chip, la batería, los ventiladores y la
fuente de alimentación, y **congela** los trabajos pesados antes de que la máquina se
cocine a sí misma, en lugar de dejarlos correr hasta el apagón.

**Requisitos: Apple Silicon (M1 o más nuevo) y macOS 14+.** Sin `sudo`. Sin extensiones
de kernel. Sin demonios ejecutándose como root. Todo se lee con un proceso de usuario normal.

> Esta es la versión resumida. La documentación completa - con mediciones, los fracasos
> documentados y el porqué de cada decisión - está en el [README en inglés](README.md).

<p align="center">
  <img src="docs/screens/menu_es.webp" alt="coffee-paladin - barra de menús en español" width="360">
</p>

---

## Por qué existe

Un MacBook Pro M4 Pro trabajó toda la noche renderizando vídeo, exactamente para lo que
se compran estas máquinas. Por la mañana: olor a quemado bajo el chasis y un apagón forzado.
Y lo peor: al revisar los registros después **no había nada que revisar** - ni kernel panic,
ni registro de apagado térmico; el log del sistema simplemente terminaba en el instante
en que la máquina murió. No había forma de reconstruir la curva de temperatura.

Además, perder un Mac duele más en 2026 que nunca. Cuando llamamos a los operadores de
leasing en Polonia este julio, el plazo para un MacBook nuevo era de 15+ semanas, con
clientes en cola desde abril; hasta los M1 viejos se agotaban y los precios habían subido.

Este proyecto es la respuesta a ambas cosas: **pararlo antes de que se cocine** y
**conservar las pruebas** si aun así algo sale mal.

---

## Qué hace exactamente

**1. Pausa en lugar de matar.** Cuando el chip se calienta, los procesos pesados reciben
`SIGSTOP`: el proceso se congela donde está, su memoria queda intacta y, al enfriarse,
recibe `SIGCONT` y continúa desde el mismo punto. La parada ocurre entre instrucciones,
así que la pausa en sí no puede corromper los datos del proceso. Y no tiene nada de exótico:
macOS hace esto todo el día por su cuenta (App Nap con las apps en segundo plano, cualquier
depurador al engancharse) y el hardware no sufre desgaste. Medido en un trabajo real:
chip a 89,3 °C → pausa → **60,2 °C diecinueve segundos después** → reanudación.
El cálculo no se enteró.

**2. Encuentra al culpable de verdad.** Una lista de nombres conocidos siempre tiene agujeros:
un binario propio llamado `b3core` llevó la máquina a 90 °C porque no coincidía con nada.
Un caso peor: un script de Python lanzaba cientos de instancias del solver `cadical` que
vivían un segundo cada una - cada hijo demasiado breve para cruzar un umbral, el padre
casi sin CPU propia, y entre todos ocho núcleos al 100 %. Por eso el guard calcula el
**uso de CPU de todo el árbol de procesos**: aquel Python apareció como **595 %** y fue
congelado en el origen, lo que además cortó el nacimiento de nuevos hijos.

<p align="center">
  <img src="docs/screens/load_info.webp" alt="Información de carga: qué calienta y qué consume RAM" width="420">
</p>

**3. Vigila la energía, no solo el calor.** Con batería y por debajo del 10 %, los trabajos
largos se pausan y solo se reanudan al enchufar: un cálculo de treinta días no debería morir
a mitad de camino porque el portátil se quedó sin carga. Además, alarma de ventiladores:
chip por encima de 70 °C con ambos ventiladores a 0 rpm - un ventilador agarrotado es
precisamente una causa habitual de ese olor a quemado.

**4. Mantiene el Mac despierto - pero con fusible.** Temporizador (de 15 minutos a 12 horas),
indefinidamente, mientras se ejecuta una app concreta, mientras hay descargas: el juego
completo al estilo Amphetamine. La diferencia es el **fusible**: todos esos modos mantienen
el bloqueo de suspensión **solo mientras la máquina está fría**. En cuanto el guard empieza
a pausar por calor, el bloqueo se libera - dormir es la forma más rápida de enfriarse, y un
«no duermas» incondicional dentro de una mochila es exactamente como se cocinan los MacBook.

<p align="center">
  <img src="docs/screens/keep_awake.webp" alt="Modos de mantener despierto con fusible térmico" width="420">
</p>

**5. Se calibra a la máquina donde aterriza - y conoce sus límites.** En el primer arranque
mide qué Mac es (si tiene ventiladores, cuántos núcleos, qué chip) y elige umbrales acordes;
las máquinas sin ventilador reciben umbrales más bajos y una pausa máxima más larga,
y los umbrales puestos a mano nunca se sobrescriben. Y con historia acumulada, `heat --profile` lee las mediciones de esta máquina concreta
y dice dónde están sus límites reales: la temperatura en reposo, la meseta bajo carga
sostenida, la temperatura a la que arrancan los ventiladores, y si macOS tuvo que frenar
la CPU alguna vez. Si los umbrales no encajan con la máquina, lo dice e imprime los que
encajarían - pero **nunca escribe nada por su cuenta**, y los consejos llevan barandillas:
el umbral de terminación nunca sube, el de reanudación nunca cae dentro de la banda de
reposo, y con pocos datos no hay consejo.

**6. Sabe poner los trabajos pesados en cola (opcional).** Con `admission_control`
activado, los trabajos lanzados con `safe-run` declaran cuántos núcleos van a ocupar
(`--cores 6`) y el guard los admite o los encola según el margen térmico: chip frío,
todos los núcleos de rendimiento; templado, la mitad; caliente, nada nuevo. La cola
sobrevive a un reinicio del demonio y `--after NOMBRE` encadena trabajos sin bucles
de `pgrep` hechos a mano. El árbitro solo retrasa arranques: nunca pausa ni mata nada,
y ante cualquier error interno deja pasar a todos. Desactivado por defecto.

**7. Guarda pruebas (la caja negra).** El demonio escribe un pulso en cada ciclo y una
marca aparte al apagarse limpiamente. Tras reiniciar, compara ambas cosas con la hora de
arranque del sistema: un pulso interrumpido antes del arranque, sin marca de apagado
limpio, significa que la máquina se apagó sin previo aviso. El evento se registra
**junto con las últimas ocho mediciones anteriores a la caída**. `thermal-report` lo
convierte todo en un documento que un servicio técnico aceptará: hardware y número de
serie, salud de la batería, apagones en seco con las lecturas que los precedieron,
cada intervención del guard y el histórico completo de temperaturas.

<p align="center">
  <img src="docs/screens/guard_log.webp" alt="El registro con una alarma real de fallo de refrigeración" width="620">
</p>

---

## En qué se diferencia de Caffeine / Amphetamine / Stats

| | Caffeine | Amphetamine | Stats / iStat | coffee-paladin |
|---|---|---|---|---|
| Muestra la temperatura | no | no | **sí** | **sí** |
| Mantiene el sistema despierto | vía pantalla | sí | no | **sí** |
| Deja que la pantalla duerma y se bloquee | no | según config. | - | **siempre** |
| Suelta el bloqueo cuando el Mac se calienta | no | no | - | **sí, fusible térmico** |
| Pausa los trabajos que recalientan el Mac | no | no | no | **sí** |
| Registra una caja negra antes del apagón | no | no | no | **sí** |
| Código abierto | no | no | parcial | **MIT** |

En una frase: Stats e iStat Menus son un **panel de instrumentos** - te dicen cuánto calienta.
Caffeine y Amphetamine son un **interruptor** - impiden que la máquina duerma.
coffee-paladin es un **fusible**: actúa por su cuenta.

---

## Flotas: todos los Macs en una tabla

Cada vez más empresas ejecutan IA local en Macs: Mac mini o Mac Studio con mucha RAM,
modelos on-premise, datos que no salen de la red. Esas máquinas trabajan 24/7, igual que
las granjas de render, los estudios de postproducción y los pools de CI. Cada máquina
escribe una instantánea en una carpeta compartida (iCloud, SMB, NFS - da igual) y en el
menú aparece una tabla: quién está caliente, quién ya está pausando trabajos y quién ha
dejado de reportar (la marca STALE aparece a los cinco minutos de silencio).

<p align="center">
  <img src="docs/screens/fleet.webp" alt="Flota Apple: dos Macs, uno sin reportar" width="620">
</p>

---

## Tu agente de IA puede hablar con él

Los agentes de programación son hoy una fuente normal de carga en un portátil y, en la
práctica, la peor: un agente no oye el ventilador ni nota que la máquina se está calentando.
Por eso el proyecto incluye un **skill para agentes de IA**; `install.sh` lo coloca en
`~/.claude/skills/coffee-paladin/` para Claude Code, y también en `~/.agents/skills/`
(OpenClaw y todo lo que lee la disposición AgentSkills) y `~/.grok/skills/`, pero solo
donde ese árbol ya existe: no plantamos configuración para una herramienta que no tienes.
Es el mismo archivo Markdown en todas partes.

Le enseña cuatro cosas: mirar antes de empezar leyendo `~/.coffee-paladin/status.json`
(el campo `level` lo decide todo: `0` adelante, `1` no paralelices, `2` no empieces nada
nuevo, `3` para y avisa a la persona); lanzar lo pesado con `safe-run`; **nunca** hacer
`SIGCONT` a un proceso que el guard congeló; y no generar calor de entrada - ninguna tarea
en segundo plano sin tiempo límite y limpieza, ninguna búsqueda recursiva en carpetas
sincronizadas con iCloud. Esta última regla salió de un incidente real: un `grep` que gastó
13 segundos de CPU en 1 h 42 min mantuvo un Mac sin ventilador a 90 °C, porque obligaba a
`fileproviderd` y `cloudd` a materializar archivos desde la nube.

**Statusline en Claude Code.** El instalador puede escribir el estado térmico
justo bajo la sesión del agente, en dos líneas: la verdad de la máquina arriba
y la sesión de IA abajo.

```
🛡  🌡 55°  🌀 2.4k  🧠 50%  💾 94%  ☕
🤖 Fable 5  5h 86% ↺14:30  7d 41% ↺Thu  ctx 62%  my-project
```

La segunda línea lleva el modelo, **los límites de tu cuenta** (los mismos
porcentajes de 5 horas y 7 días que muestra la pantalla `/usage`, directos del
JSON de sesión que Claude Code entrega a las statuslines; cuentas de
suscripción, los campos aparecen tras la primera respuesta de la sesión), más
el uso de contexto y el directorio. Los porcentajes se ponen amarillos en 75 y
rojos en 90. Si el JSON no trae límites, no se muestra ninguno: la línea nunca
se inventa un número. Esa misma instantánea filtrada se guarda en
`~/.coffee-paladin/claude_usage_cache.json`, de donde la lee la barra de menús,
así que la respuesta a «cuánto Claude me queda» está en la barra y no detrás de
un comando con barra. En un terminal estrecho es la línea de IA la que cede
primero, elemento a elemento desde la derecha, y desaparece entera antes de
soltar un solo dato térmico.

El escudo se convierte en un ojo en modo observación y en un `OFF` rojo y
ruidoso cuando la instantánea del demonio caduca - exactamente la avería en la
que el guardián está desconectado y nadie lo nota. Tu statusline existente
nunca se toca (`--replace` es una elección consciente) y el desinstalador borra
solo su propia entrada.

**Cuánto llevas consumido hoy.** Si existe el `ccusage` externo, el submenú
*Actividad de agentes* añade una línea con el consumo del día en todas las CLI
de agentes que conoce: `322M tokens · ~$312`. Los tokens van primero a
propósito: con una suscripción, la cifra en dólares no es dinero que nadie
gastó, sino lo que ese mismo trabajo habría costado por API, así que lleva `~`
delante y `"ccusage_cost": false` la quita del todo. El presupuesto real de una
suscripción son los porcentajes de la ventana de 5 horas y de la semana, que
están en la línea de arriba. Llamamos al binario ajeno y guardamos su respuesta
10 minutos en caché, en vez de meter código ajeno en el repositorio; sin
`ccusage` esa línea sencillamente no aparece y todo lo demás sigue igual.
Al desplegarla, el día se reparte **por agente** y **por modelo** - se ve qué
CLI y qué modelo gastaron los tokens de verdad - y debajo aparece el **bloque
activo de cinco horas** con su ritmo: `47M tokens · 283k/min · quedan 94 min`.
Ese bloque lo cuenta ccusage a partir de archivos locales y está etiquetado así
a propósito: no es el límite oficial de 5 horas de tu cuenta, que tiene su
propia línea directa de Claude Code. Y hay una línea que ningún panel de
consumo puede dar, porque necesita las dos mitades a la vez: si la previsión
del propio guardián dice que el chip forzará una pausa antes de que acabe el
bloque, lo dice sin rodeos.

**Actividad de agentes.** El demonio escribe `agent_activity.json`: qué
sesiones de IA corren en este Mac y qué árbol de procesos arrancó cada una,
con el contexto térmico. El menú tiene un submenú con iconos por tipo de
proceso, y un marcador ✨ luce en la barra mientras viva alguna sesión: la
mera presencia del marcador responde a «¿está trabajando una IA ahora?».
La barra además se volvió más silenciosa: fijos solo el chip y la RAM; el
resto (ventiladores, batería desde 40 °C, marcador IA, pausa) aparece solo
cuando trae noticia, con histéresis de 60 s.

**Una puerta para todos los hosts de agentes.** `coffee-paladin hook-gate`
implementa el contrato pre-exec que comparten, con diferencias de dialecto,
Claude Code, Codex CLI, Gemini CLI, Grok Build y Antigravity. Lee el JSON de
la llamada a herramienta en la grafía que hable cada host (`tool_input` en
snake_case, el `toolInput` en camelCase de Grok, el
`toolCall.args.CommandLine` de Antigravity) y responde como ese host escucha:
salida 2 con el motivo en stderr, más un `{"decision": "deny"}` explícito por
stdout para los dos hosts que solo se fían de eso (Grok deja pasar ante
cualquier otra respuesta; Antigravity no tiene contrato de códigos de salida).
Una herramienta pesada lanzada a pelo - `ffmpeg`, un solver, `ollama run` -
recibe un rechazo con la línea `safe-run` exacta a usar. La puerta comprueba
disciplina de proceso, no temperatura; responde en milisegundos y ante
cualquier imprevisto deja pasar, porque una puerta rota jamás debe secuestrar
una sesión de trabajo. `PALADIN_HOOK=off` la desactiva para un comando
deliberado y `hook_heavy_patterns` en config.json sustituye la lista interna.

El cableado es **voluntario host por host**, un adaptador para cada uno, todos
con los mismos modales que el cableado de Claude: la entrada propia se añade
bajo un bloqueo de archivo, las ajenas no se tocan, cada escritura deja copia
con marca de tiempo y el desconectado quita exactamente la nuestra.

```bash
python3 ~/.coffee-paladin/settings_wire.py hook          # Claude Code
python3 ~/.coffee-paladin/codex_hooks_wire.py hook       # Codex CLI (confirma la confianza en la primera ejecución)
python3 ~/.coffee-paladin/gemini_hooks_wire.py hook      # Gemini CLI
python3 ~/.coffee-paladin/grok_hooks_wire.py hook        # Grok Build
python3 ~/.coffee-paladin/antigravity_hooks_wire.py hook # Antigravity
```

(`unhook` deshace cada uno; `uninstall.sh` los recorre todos.) Grok además lee
por defecto los hooks de `~/.claude/settings.json`, así que una puerta cableada
en Claude ya lo cubre. El campo de tiempo límite de Gemini va en milisegundos
donde los demás usan segundos: el adaptador lo sabe.

**¿Trabajas con un enjambre de agentes? Ya estás cubierto.** Los orquestadores
que lanzan sus workers como sesiones CLI normales (equipos de
oh-my-claudecode, claude-squad, workmux, paneles de dmux) heredan la puerta
gratis: cada worker es un proceso `claude`, `codex`, `gemini` o `grok`, lee los
mismos ajustes de usuario y choca con el mismo PreToolUse. No hay nada que
configurar del lado del orquestador. Lo que ningún orquestador ve todavía es la
máquina misma: cuánto calienta y cuántos trabajos pesados aguanta. Justo esa es
la capa que sostiene el guardián: un `status.json` que cualquier planificador
puede leer antes de escalar.

**Terminales.** La misma línea térmica sirve fuera de las sesiones de agente:
en `integrations/terminals/` hay un fragmento `status-right` para tmux, un
manejador `update-status` para WezTerm y un componente de barra de estado para
iTerm2, cada uno del tamaño de un copiar y pegar y con las instrucciones
dentro del archivo.

**Latido de progreso.** `safe-run` entrega a cada tarea una ruta en
`$PALADIN_PROGRESS`; la tarea toca el archivo tras cada unidad de trabajo y,
declarado su ritmo (`--progress-interval 300`), el guardián dirá con honradez
«¿parada?» cuando calle el triple de lo prometido - siempre con palabras,
nunca con señales.

---

## Instalación

**Con Homebrew (lo más simple):**

```bash
brew install pawelkwaczynski/tap/coffee-paladin
bash "$(brew --prefix)/share/coffee-paladin/install.sh"
```

Hacen falta las dos líneas: `brew install` solo deja los archivos, y la segunda compila
la app de la barra de menús y arranca el demonio.

Si este Mac se configuró con el Asistente de Migración desde uno Intel, en `/usr/local`
puede vivir también el Homebrew de Intel, y un `brew` a secas puede apuntar a él - y ese
no conoce este tap. En ese caso usa rutas completas: `/opt/homebrew/bin/brew install ...`.
Más detalles en el [FAQ](FAQ.md).

**Desde el código fuente:**

```bash
git clone https://github.com/pawelkwaczynski/coffee-paladin.git
cd coffee-paladin
bash install.sh
```

Los dos caminos dan la misma versión.

El script compila las partes en Swift en la propia máquina y registra **dos** LaunchAgents:
el demonio y, por separado, la app de la barra de menús - esta última se puede desactivar
sin tocar la red de seguridad. **Empieza en modo de solo observación**: mide y avisa,
pero no toca nada. Cuando compruebes que ve cosas razonables, actívala con un clic en el
menú (*Activar protección*) o desmarcando *Ajustes → Solo observación (dry run)*.
Se puede volver atrás cuando quieras, sin reiniciar nada.

Para desinstalar: la opción **«Desinstalar»** está en el propio menú (con una casilla
«borrar también los datos» y una segunda ventana de aviso), o `bash uninstall.sh`.
El histórico de mediciones y la caja negra se conservan por defecto - todavía pueden
hacer falta para la garantía; `--purge` los borra también.

## Uso

```bash
heat                            # un comando: cuánto calienta y qué lo está calentando
heat --profile                  # el perfil térmico de ESTE Mac, leído de su propia historia
safe-run --hours 8 -- ffmpeg …  # la forma correcta de lanzar un trabajo pesado
thermal-report --days 14        # informe para el servicio técnico (--pdf lo hace PDF)
fleet --setup                   # configurar la carpeta compartida de la flota
heat --paladin                  # huevo de pascua ☕︎
```

`safe-run` tiene banderas pensadas para colas nocturnas: `--wait-cool` (en una máquina
caliente, esperar a que se enfríe y arrancar entonces, en vez de salir con un código de
error), `--grace N` (segundos entre `SIGTERM` y `SIGKILL`, para que un solver o un
codificador pueda escribir su estado), y al salir limpia todo su grupo de procesos:
un hijo huérfano ya no puede sobrevivir a su supervisor y quemar la máquina durante
horas sin límite de tiempo.

**La barra de menús y el «notch».** La fila completa de lecturas no cabe junto al notch
de un MacBook Pro, y en ese caso macOS directamente no dibuja el elemento - sin avisar.
Por eso una instalación nueva mantiene fijos solo el chip y la RAM (el resto
es condicional, aparece cuando trae noticia); en el menú
hay tres preajustes («Solo el icono», «Icono y temperatura del chip», «Mostrar todo») y los mismos
preajustes funcionan desde el terminal, para cuando el icono no se ve y no hay menú que abrir:

```bash
coffee-paladin bar icon-only   # solo el termómetro, cabe en cualquier sitio
coffee-paladin bar chip        # el icono y un número
coffee-paladin bar full        # todo
coffee-paladin panel           # abrir una ventana sin pasar por la barra
```

Una actualización conserva la disposición que ya habías elegido.

La barra de menús, las notificaciones y todas las herramientas hablan **cinco idiomas**:
inglés (por defecto), polaco, ruso, chino y español. Los botones para cambiarlo están
directamente en el menú principal.

## Limitaciones conocidas

- La pausa es visible para la **E/S sensible al tiempo**: el otro extremo de una conexión,
  los watchdogs y los servidores de licencias pueden notarla. La alternativa es peor de
  todos modos: el calor sin gestionar hace que macOS limite todo y, en el extremo,
  que la máquina se apague en seco.
- La temperatura del chip llega vía `macmon` (IOReport, sin sudo). Sin él el guard funciona,
  pero se apoya solo en la temperatura de la batería y el estado térmico del sistema,
  y reacciona varios minutos más tarde.
- Solo **Apple Silicon** y **macOS 14 o más nuevo**. En los Macs Intel la ruta a los
  sensores es distinta (SMC en vez de IOReport) y todavía no está implementada.
- No sustituye a una reparación de la refrigeración. Si el ventilador está muerto, el guard
  solo pausará tus trabajos más a menudo - y lo dejará por escrito.

---

## Licencia y autoría

MIT. Haz lo que quieras con esto. Si te salva la máquina, con eso basta.

Autor: Paweł Kwaczyński / FOCUS FRAME, 2026. Las versiones 1.0 a 3.2.7 se desarrollaron
dentro de **AIrON**, el club de investigación estudiantil de informática de la AHE en Łódź;
desde 3.3.0 el proyecto se desarrolla y mantiene de forma independiente del club.
El código Swift lo escribió **Claude (Anthropic)** en Claude Code, con **Codex (OpenAI,
GPT-5.5)** como revisor adversarial y dos modelos locales en paralelo:
Devstral 24B sobre MLX y qwen3:4b sobre Ollama.

**Ilustración.** El paladín, la mascota, es un **diseño propio del autor** y se usa como
imagen oficial del proyecto; los detalles están en [`branding/CREDITS.md`](branding/CREDITS.md).
