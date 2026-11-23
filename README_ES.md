# CodeHatch: controla tu juego de Roblox desde Discord

🌐 **English:** [README_EN.md](README_EN.md) · **Polski:** [README_PL.md](README_PL.md) · **Español:** README_ES.md

CodeHatch es un bot de Discord para creadores de juegos de Roblox: controlas tu juego directamente desde Discord. Los códigos promocionales, huevos, eventos con multiplicadores, regalos, anuncios en pantalla y bans llegan al juego en unos segundos, sin publicarlo. Habla inglés, polaco y español. **No necesitas saber programar.**

**Tu juego no necesita el bot encendido.** Los códigos, huevos, eventos y regalos que ya enviaste están guardados en el juego y siguen funcionando cuando el bot está apagado. El ⚙️ Manager del juego también los crea y borra sin el bot; el bot solo hace falta para Discord, así que tenerlo en línea 24/7 es una comodidad, no una obligación.

## 👉 Empieza aquí: `DOCS.html`

En la carpeta del bot hay un archivo llamado **`DOCS.html`**. Haz doble clic y se abrirá en tu navegador toda la documentación:

- **misiones paso a paso**, p. ej. *Bot en línea desde cero* o *Tu primer código en el juego*, con barra de progreso e insignias,
- un buscador (escribe p. ej. «token» o «clave API»),
- tres idiomas: español, inglés y polaco,
- los mismos textos que `/tutorial` y `/setup-guide` en el bot.

La página funciona sin internet y guarda tu progreso en el navegador por sí sola. El bot la actualiza en cada arranque, así que tras una actualización las instrucciones siempre están al día. ¿El bot está en un servidor sin navegador? Copia `DOCS.html` a tu ordenador y ábrelo allí.

## 🛠️ Instalación: del zip a tu primer código en el juego

### Qué necesitas

- Un ordenador con Windows 10/11, Linux o macOS (o un servicio de hosting para bots).
- **Python 3.12, 3.13 o 3.14** (el bot está probado en 3.14) de **python.org**, no de Microsoft Store.
- Un servidor de Discord donde seas administrador.
- Un juego de Roblox que puedas editar en Roblox Studio **y** para el que puedas crear una clave API de Open Cloud: tu propio juego, o un juego de grupo donde tu rol permita gestionar claves API.
- Conexión a internet.

### ¿Cuánto se tarda?

**Instalar el bot: unos 10–15 minutos. Configurarlo todo: cerca de una hora** (solo una vez; tener el bot en línea 24/7 es aparte, mira *Bot 24/7* en `DOCS.html`). Pasas por tres webs (python.org, el Discord Developer Portal y el Roblox Creator Hub) y por Roblox Studio. Tómatelo con calma y pruébalo todo antes de publicar en un juego que ya tiene jugadores. Las actualizaciones posteriores llevan unos minutos (mira *Una versión nueva* más abajo).

**Usa UNA sola copia del bot por juego.** Dos copias conectadas al mismo juego harían cada cambio dos veces.

### Paso a paso

1. **Descomprime.** Clic derecho en `CodeHatch-1.0.0.zip` → **Extraer todo…** → elige una carpeta que se quede fija, p. ej. `C:\Bots`. Abre dentro la carpeta `CodeHatch-1.0.0`: verás, entre otros, `start.bat`, `main.py` y `DOCS.html`. Esa es la carpeta de tu bot.
   - No ejecutes nada desde la vista previa del zip.
   - No guardes la carpeta del bot en OneDrive ni en Dropbox (a menudo el Escritorio y Documentos se sincronizan): bloquean sus archivos.
   *Detalles: `DOCS.html` → Qué necesitas y Python.*
2. **Python** (una vez por ordenador). **python.org** → **Downloads** → **Windows** → en Python 3.14 pulsa **Windows installer (64-bit)** → ejecuta el archivo. En la primera pantalla marca **“Add python.exe to PATH”** → **Install Now**.
   *Detalles: `DOCS.html` → Qué necesitas y Python.*
3. **Cuenta del bot.** **discord.com/developers/applications** → **New Application** → nombre → **Create**. Pestaña **Bot**: activa **Server Members Intent** (los otros dos intents no hacen falta) → **Save Changes** → **Reset Token** → **Copy**.
   - El token es la contraseña del bot: nunca se lo envíes a nadie.
   - Se muestra solo una vez. ¿Lo perdiste? Pulsa otra vez **Reset Token** (Discord puede pedir **Yes, do it!** y tu contraseña o código 2FA).
   - Hacer el bot privado es para más tarde, no hace falta para empezar: `DOCS.html` → La cuenta del bot en Discord → *Bot privado*.
   *Detalles: `DOCS.html` → La cuenta del bot en Discord.*
4. **Primer arranque.** Haz doble clic en `start.bat` (Linux/macOS: `bash start.sh`).
   - ¿Windows muestra «Windows protegió su PC»? Pulsa **Más información** → **Ejecutar de todas formas**.
   - El Bloc de notas abre el archivo `.env` (se crea a partir de `.env.example`): cambia `your_bot_token_here` por tu token, sin espacios ni comillas (`DISCORD_TOKEN=MTI3NDk…`) → guarda → cierra el Bloc de notas.
   - ¿Cerraste el Bloc de notas sin el token? `start.bat` te lo dice y vuelve a abrir el Bloc de notas: pega, guarda y haz doble clic otra vez en `start.bat`.
   - El bot instala sus librerías (durante unos minutos la ventana puede parecer congelada) y luego muestra `📦 CodeHatch 1.0.0` y `✅ Synced … commands`. **Deja abierta esta ventana negra**: si la cierras, el bot se apaga. Hacer clic en ella no detiene el bot.
   - `⚠️ "Public Bot" is ON…` en la ventana es un recordatorio normal en el primer arranque, no un error.
   - ¿Abriste `start.bat` dos veces? La segunda ventana se detiene sola con «already running». Es normal.
   - Deja `ROBLOX_API_KEY` vacío: la clave la pegas en Discord en el paso 7.
   - En Linux/macOS no hay Bloc de notas: el script crea `.env` y se detiene, así que ábrelo con `nano .env`, pega el token y vuelve a ejecutar `bash start.sh`.
   *Detalles: `DOCS.html` → Primer arranque, Problemas al empezar.*
5. **Invita al bot.** Developer Portal → tu aplicación → **OAuth2** → **URL Generator** → scopes **bot** y **applications.commands**. La lista de permisos aparece cuando marcas **bot**: marca **View Channels**, **Send Messages**, **Embed Links**, **Read Message History** (es todo lo que necesita; no marques **Administrator**) → abre el enlace del final → elige tu servidor → **Authorize**. El bot aparece en la lista de miembros.
   *Detalles: `DOCS.html` → Invita al bot a tu servidor.*
6. **En Discord.** Escribe `/tutorial`: el bot muestra ✅ o ⚠️ en cada paso. El bot empieza en inglés; para cambiarlo: `/setup` → **🌐 Language / Język / Idioma**.
   - ¿No ves `/tutorial`? Espera unos minutos, pulsa **Ctrl+R** en Discord y comprueba que la ventana negra está abierta.
   - Los paneles se cierran solos tras 5 minutos sin clics (el tutorial, tras 14). Vuelve a escribir el comando: no se pierde nada.
   *Detalles: `/tutorial` → El bot en tu servidor: permisos, Idioma del bot.*
7. **Conecta el juego.** Mientras creas la clave, ten abierto `/tutorial` → *Conectar tu juego de Roblox*: ahí está cada clic.
   - `/setup-roblox` → **🎮 Juego de Roblox** → pega el enlace de tu juego, p. ej. `https://www.roblox.com/games/123456789/Nombre` (la dirección de la página de tu juego en el navegador; el juego debe haberse publicado al menos una vez).
   - **create.roblox.com** → menú de la izquierda **All tools** → **API Keys** → **Create API Key**. Dale solo estos permisos: **universe-datastores** `objects:create`, `objects:read`, `objects:update`, `control:create`; **messaging-service** `universe-messaging-service:publish`. Para bans y la clasificación, también **user-restrictions** `read`/`write` y **ordered-data-store** `entry:read`. Deja desactivada la restricción de IP y sin fecha de caducidad.
   - Tras elegir cada sistema de permisos pulsa **Add Experience** y elige **tu** juego; si no, la clave no funcionará.
   - **Save & Generate Key** → **Copy**. La clave se muestra solo una vez: ¿la perdiste? Crea una nueva.
   - `/setup-roblox` → **🔑 Conexión con el juego** → **Pegar clave API** → **Activar / desactivar** (debe estar activado) → **Probar y sincronizar**. Verás ✅ o qué corregir.
   *Detalles: `/tutorial` → Conectar tu juego de Roblox.*
8. **El archivo para Studio.** De la carpeta `scripts` solo necesitas `DiscordCodes.rbxmx` (`DiscordSettings` es opcional; `DiscordCatalog` y `DiscordCodesWindow` son extras opcionales que se explican más adelante).
   - Abre la versión más reciente de tu juego en Roblox Studio (**File** → **Open from Roblox**).
   - En la ventana **Explorer** haz clic derecho en **ServerScriptService** → **Insert** → **Import Roblox Model** → `scripts/DiscordCodes.rbxmx` de la carpeta del bot.
   - ¿No aparece (Studio nuevo)? Crea tu propia pestaña: **+** tras las pestañas → **Add tools** → `model` → marca **Model** → púlsalo y elige el archivo.
   - **DiscordCodes** tiene que quedar dentro de **ServerScriptService**. ¿Quedó en otro sitio? Arrástralo allí.
   - Opcional: `DiscordSettings.rbxmx` a su lado (no dentro).
   - **File** → **Experience Settings** (Studio antiguo: **Home** → **Game Settings**) → **Security** → activa **Enable Studio Access to API Services** → **Save**.
   *Detalles: `/tutorial` → El archivo para Roblox Studio.*
9. **Prueba en Studio.** Pulsa **Play**. La ventana **Output** (¿no la ves? menú **Window** → **Output**) muestra `[DiscordCodes] File version …`, y ves el botón morado **Codes** y el botón **⚙️ Manager** (arriba a la derecha; solo lo ves tú, como dueño del juego).
   *Detalles: `/tutorial` → El archivo para Roblox Studio; `DOCS.html` → El juego desde Discord: detalles.*
10. **Publica.** Solo cuando la prueba haya funcionado: **File** → **Publish to Roblox**. Publish envía a los jugadores todo el juego abierto en Studio, no solo el archivo del bot. Después entra al juego **publicado** (no con **Play** en Studio), espera un minuto y `/setup-roblox` mostrará ✅ junto al archivo de Studio (un panel abierto antes: pulsa **Actualizar**). Hasta entonces es normal ver ⚠️ *está en Studio, pero el juego publicado aún no la usa*.
    *Detalles: `/tutorial` → El archivo para Roblox Studio.*
11. **Tu primer código.**
    - Primero elige los nombres: `/setup-roblox` → **🔍 Qué tiene tu juego** → elige de las listas tu moneda (p. ej. Coins) y tus objetos. Vienen de tu juego, así que el bot solo sugiere nombres que existen.
    - `/setup-roblox` → **📜 Códigos promocionales** (o `/code-add`), p. ej. el código `TEST1` que da 10 Coins (código: letras, dígitos, `_` y `-`, hasta 30 caracteres).
    - Entra al juego → **Codes** → escribe `TEST1` → recibes la recompensa. El juego recibe los códigos nuevos en más o menos un minuto.
    - Un mensaje rojo en la ventana de códigos significa que no se pudo dar la recompensa y el código **no** se gastó (salvo un error en tu propio `OnReward`: entonces el código se gasta, mira `DOCS.html`). La ventana **Output** dice por qué.
    - **Comprueba que se queda:** sal del juego publicado y vuelve a entrar. ¿Siguen ahí los 10 Coins? Las recompensas funcionan solas. ¿Desaparecieron, o el juego usa ProfileStore o algo parecido? El programador del juego añade `Core.OnReward` (códigos y regalos), `Core.OnSpend` (precios de huevos) y `Live.OnHatch` (mascotas): `DOCS.html` → *Recompensas: para el programador del juego*.
    *Detalles: `/tutorial` → Qué tiene tu juego, Códigos promocionales; `DOCS.html` → Recompensas: para el programador del juego.*

**¿Algo salió mal?** `/setup` → **🩺 Diagnóstico**, `/setup-roblox` → **🧪 Comprobar todo** y `DOCS.html` → *Problemas al empezar*.

## 🧭 Tres comandos que debes recordar

| Comando | Para qué sirve |
|---|---|
| `/tutorial` | El tutorial dentro del bot: lo que ya funciona (✅) y lo que falta (⚠️) |
| `/setup` | Discord: idioma, el canal de reportes de errores, el canal de registro, diagnóstico |
| `/setup-roblox` | Tu juego: conexión, el archivo de Roblox Studio, nombres del juego, códigos promocionales, huevos, eventos y más |

## 🌟 Qué puede hacer el bot

- 📜 Códigos promocionales que funcionan en el juego unos segundos después de crearlos (`/setup-roblox` → 📜 Códigos promocionales o `/code-add`)
- 🥚 Huevos con mascotas y ⚡ eventos con multiplicadores: los creas en Discord y funcionan en el juego en segundos, sin publicar el juego
- 🎁 Regalos para un jugador, 📢 anuncios en pantalla, 🔨 bans con ficha del jugador y 🏆 clasificación (el bot lee la clasificación que tu juego ya tiene)
- 🕹️ Un panel de control en el canal de tu equipo: los administradores y los roles que elijan manejan el juego con botones, y el canal de registro apunta quién cambió qué
- 📒 El catálogo del juego: el bot conoce los nombres exactos de tu juego y rechaza las erratas
- ⚙️ Un panel Manager dentro del juego que solo ves tú (el dueño del juego): revisas códigos y huevos, creas códigos, eventos, huevos, regalos, anuncios y bans dentro del juego (también con el bot apagado), cambias ajustes en directo, pruebas un código y ves lo que verán los jugadores
- 👥 Para los jugadores: `/codes`, `/eggs`, `/events` y `/leaderboard`

Descripción completa: `DOCS.html` → *Qué puede hacer el bot*.

## 🛡️ ¿Es seguro?

Recibes el código fuente completo. El bot no tiene telemetría y solo se conecta a Discord y a Roblox; sus reportes de errores van solo a tu propio canal de Discord. El token del bot y la clave API se quedan en el archivo `.env` de tu ordenador. El script del juego no tiene `require(id)` ni hace peticiones a internet. El bot solo necesita cuatro permisos de Discord y una clave API limitada a tu juego. Detalles: `DOCS.html` → *¿Es seguro?*.

## 🆘 ¿Algo no funciona?

- `/setup` → **🩺 Diagnóstico** (Discord) y `/setup-roblox` → **🧪 Comprobar todo** (juego) te dicen qué corregir.
- `/setup-guide`: respuestas a dudas frecuentes.
- En `DOCS.html` escribe el problema en el buscador o abre *Problemas al empezar*.

## 🔄 Una versión nueva

Tu versión aparece en la ventana del bot (`📦 CodeHatch 1.0.0`) y al final de `/help`. Descarga la versión nueva desde el canal #buyers del servidor de Discord CodeHatch HQ (recibes el rol 💎 Buyer al comprar) y lee en `CHANGELOG.md` todas las entradas entre tu versión y la nueva. Cierra el bot, copia los archivos nuevos encima de la carpeta antigua del bot, pero **conserva** `.env`, `config.json` y la carpeta `data` (nunca los sobrescribas), y vuelve a arrancar el bot con `start.bat` / `start.sh`. Si después `/setup-roblox` muestra ⚠️ junto al archivo DiscordCodes, reemplaza también ese archivo en Studio. Paso a paso: `DOCS.html` → *Actualizaciones del bot*.

## 📁 Qué hay en la carpeta

| Archivo / carpeta | Qué es |
|---|---|
| `DOCS.html` | La documentación: ábrela en tu navegador |
| `start.bat` / `start.sh` | Arrancar el bot (Windows / Linux y macOS) |
| `.env` | El token del bot y la clave de Roblox (se crea a partir de `.env.example` en el primer arranque, no viene en el zip). **Nunca se lo envíes a nadie** |
| `config.json`, `data/` | Tus ajustes y la base de datos. El bot los crea en el primer arranque (no vienen en el zip). No los sobrescribas al actualizar |
| `CHANGELOG.md` | Qué cambió en cada versión |
| `LICENSE.md` | Qué puedes y qué no puedes hacer con el código (licencia, en inglés) |
| `scripts/` | Archivos para insertar en Roblox Studio (fuentes en `scripts/DiscordCodes/`) |
| `cogs/`, `utils/`, `main.py` | El código fuente del bot: mapa en `DOCS.html` → *Para programadores: el código fuente* |
| `locales/` | Textos del bot y de la documentación (ES, EN, PL) |
