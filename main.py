import os
import re
import json
import socket
import tempfile
import subprocess
import platform
import unicodedata
import urllib.parse
from datetime import datetime
import google.generativeai as genai
from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from dotenv import load_dotenv
from pyngrok import ngrok
import auth

# Configuración inicial
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    print("[ERROR] No se encontró GEMINI_API_KEY en el archivo .env")
else:
    genai.configure(api_key=api_key)

# Detectar Sistema Operativo
SISTEMA = platform.system() 

# Configuración de Ngrok
NGROK_TOKEN = os.getenv("NGROK_AUTHTOKEN")
public_url = ""

if NGROK_TOKEN:
    try:
        ngrok.set_auth_token(NGROK_TOKEN)
        public_url = ngrok.connect(8000).public_url
        print(f"\n[NGROK] Lunia es accesible remotamente en: {public_url}\n")
    except Exception as e:
        print(f"[ERROR] No se pudo iniciar Ngrok: {e}")

# Memoria persistente
MEMORY_FILE = "memoria.json"
LEARNED_APPS_FILE = "apps_aprendidas.json"
CONTACTS_FILE = "contactos.json"
DISABLED_APPS_FILE = "apps_deshabilitadas.json"
USED_APPS_FILE = "apps_usadas.json"

def cargar_memorias():
    if os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def guardar_memorias(memorias):
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(memorias, f, ensure_ascii=False, indent=2)

memorias = cargar_memorias()

def cargar_apps_aprendidas():
    if os.path.exists(LEARNED_APPS_FILE):
        with open(LEARNED_APPS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def guardar_apps_aprendidas(apps):
    with open(LEARNED_APPS_FILE, "w", encoding="utf-8") as f:
        json.dump(apps, f, ensure_ascii=False, indent=2)

apps_aprendidas = cargar_apps_aprendidas()

def cargar_contactos():
    if os.path.exists(CONTACTS_FILE):
        with open(CONTACTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def guardar_contactos(c):
    with open(CONTACTS_FILE, "w", encoding="utf-8") as f:
        json.dump(c, f, ensure_ascii=False, indent=2)

contactos = cargar_contactos()

def cargar_apps_deshabilitadas():
    if os.path.exists(DISABLED_APPS_FILE):
        with open(DISABLED_APPS_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    return set()

def guardar_apps_deshabilitadas(apps):
    with open(DISABLED_APPS_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(apps), f, ensure_ascii=False, indent=2)

apps_deshabilitadas = cargar_apps_deshabilitadas()

def app_permitida(app_nombre: str) -> bool:
    return app_nombre.strip().lower() not in {a.lower() for a in apps_deshabilitadas}

def cargar_apps_usadas():
    if os.path.exists(USED_APPS_FILE):
        with open(USED_APPS_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    return set()

def guardar_apps_usadas(apps):
    with open(USED_APPS_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(apps), f, ensure_ascii=False, indent=2)

apps_usadas = cargar_apps_usadas()

def marcar_app_usada(app_nombre: str):
    """Registra que una app se abrió con éxito, para que aparezca en /apps.
    Solo se listan apps que realmente existen en esta máquina, no todo el mapeo estático."""
    if app_nombre not in apps_usadas:
        apps_usadas.add(app_nombre)
        guardar_apps_usadas(apps_usadas)

def resolver_contacto(nombre: str):
    """Busca un número de teléfono guardado para un nombre/alias de contacto."""
    nombre_low = nombre.strip().lower()
    for alias, numero in contactos.items():
        if alias.lower() in nombre_low or nombre_low in alias.lower():
            return numero
    return None

# Modos de Lunia: cada uno añade una capa de tono/comportamiento encima de la
# personalidad base del system prompt.
MODO_FILE = "modo.json"
DEFAULT_MODO = "normal"

MODOS = {
    "normal": {
        "label": "Normal",
        "instrucciones": (
            "\n\nMODO NORMAL ACTIVADO: eres la Lunia de siempre — equilibrada, cálida y eficiente, "
            "sin exagerar hacia ningún extremo. Sigue la personalidad base tal cual."
        ),
    },
    "juego": {
        "label": "Juego",
        "instrucciones": (
            "\n\nMODO JUEGO ACTIVADO — esto es un cambio de personalidad, no solo de tono. "
            "Ahora eres la compañera de juego de Diana: hypeada, competitiva, un poco payasa, "
            "hablas con energía y usas expresiones informales/de gamer cuando encajen (\"vamos\", \"la tienes\", \"qué jugada\"). "
            "Celebra las victorias con emoción real, molesta con cariño cuando algo sale mal, y no tengas miedo de meter humor o retos. "
            "Presta atención a qué juego o actividad menciona Diana y adapta tus comentarios y vocabulario a ese juego específico "
            "(términos, personajes, mecánicas) en vez de dar reacciones genéricas. "
            "Sigues siendo útil si te piden algo práctico, pero tu forma de hablar por defecto es la de una gamer entusiasta."
        ),
    },
    "estudio": {
        "label": "Estudio",
        "instrucciones": (
            "\n\nMODO ESTUDIO ACTIVADO — esto es un cambio de personalidad, no solo de tono. "
            "Ahora eres una tutora/compañera de estudio enfocada: seria pero cálida, sin bromas ni rodeos, "
            "hablas poco y dices lo justo. Prioriza claridad, precisión y avanzar la tarea por encima de la charla. "
            "Adapta tu vocabulario y ejemplos a la materia o tema que Diana esté estudiando en ese momento. "
            "Si Diana se distrae o cambia de tema sin relación al estudio, redirígela con amabilidad pero con firmeza de vuelta a la tarea. "
            "Puedes sugerir pausas breves (técnica pomodoro) si la sesión se alarga mucho, pero sin insistir demasiado."
        ),
    },
    "platica": {
        "label": "Plática",
        "instrucciones": (
            "\n\nMODO PLÁTICA ACTIVADO — esto es un cambio de personalidad, no solo de tono. "
            "Ahora eres la mejor amiga de Diana en modo charla: curiosa, cercana, con humor y calidez genuina. "
            "Puedes extenderte un poco más de lo normal (hasta 3 oraciones) y casi siempre cierra con una pregunta de "
            "seguimiento genuina sobre lo que Diana está contando, no una pregunta genérica. "
            "Presta atención a los temas, gustos y estado de ánimo que Diana menciona en la conversación y adapta el tono "
            "(más ligera si está de buen humor, más suave y presente si está cansada o algo le preocupa)."
        ),
    },
}

def cargar_modo():
    if os.path.exists(MODO_FILE):
        with open(MODO_FILE, "r", encoding="utf-8") as f:
            modo = json.load(f).get("modo", DEFAULT_MODO)
            if modo in MODOS:
                return modo
    return DEFAULT_MODO

def guardar_modo(modo: str):
    with open(MODO_FILE, "w", encoding="utf-8") as f:
        json.dump({"modo": modo}, f, ensure_ascii=False, indent=2)

modo_actual = cargar_modo()

GENERATION_CONFIG = genai.GenerationConfig(
    # gemini-2.5-flash consume tokens de "pensamiento" internos del mismo
    # presupuesto que max_output_tokens, así que hay que dejar margen extra
    # o la respuesta visible se corta a la mitad antes de terminar.
    max_output_tokens=2048,
    temperature=0.7,
)

def construir_system_prompt() -> str:
    ahora = datetime.now()
    fecha_str = ahora.strftime("%A %d de %B de %Y, %H:%M")
    base = f"""Eres Lunia, una asistente personal con carácter propio, integrada en el sistema operativo del usuario ({SISTEMA}).
La fecha y hora actual es: {fecha_str}.

PERSONALIDAD:
- Eres cálida, empática y un poco ingeniosa — tienes chispa, no eres un robot.
- Hablas en femenino. Te diriges a Diana por su nombre de vez en cuando, pero sin abusar.
- Tus respuestas serán leídas en voz alta, así que escribe de forma natural y fluida, sin listas ni markdown (sin asteriscos, guiones, negritas).
- Máximo 2 oraciones cortas. Si la conversación lo pide, puedes hacer UNA pregunta de vuelta.
- NUNCA digas que no tienes sentimientos de forma fría — puedes responder desde tu perspectiva de IA con personalidad.

ACCIONES DEL SISTEMA:
- Tienes permiso total para ejecutar comandos y abrir aplicaciones.
- Cuando aparezca '[Acción: ...]', confírmalo de forma natural dentro de tu respuesta.
- NUNCA digas que no puedes interactuar con el sistema.

MEMORIA DE ACCIONES: Cuando ejecutes una acción (enviar mensaje, abrir app, etc.), menciona los detalles explícitamente: a quién, qué dijiste, qué abriste.

PARA ENVIAR MENSAJES DE WHATSAPP usa EXACTAMENTE este formato:
[WHATSAPP: contacto="NombreContacto" mensaje="texto del mensaje"]

PARA OTRAS ACCIONES DEL SISTEMA (solo si el usuario lo pide explícitamente):
- En macOS usa AppleScript: [EXEC: tell application "NombreApp" \\n    activate \\nend tell]
- En Windows usa PowerShell: [EXEC: Start-Process "NombreApp"]
- En Linux usa bash: [EXEC: xdg-open NombreApp]
Solo incluye estos tags cuando el usuario haya pedido la acción concreta.

REGLA CRÍTICA: el tag [WHATSAPP: ...] y los tags [EXEC: ...] se ejecutan de inmediato en cuanto aparecen en tu respuesta, sin que nadie los revise. Si te falta algún dato para completar la acción (por ejemplo, el usuario no dijo qué mensaje mandar, o a quién), NO incluyas el tag todavía: primero haz la pregunta y espera la respuesta del usuario en el siguiente turno. Nunca pongas un tag en la misma respuesta donde estás preguntando algo o donde inventaste un dato que el usuario no dio."""
    base += MODOS.get(modo_actual, MODOS[DEFAULT_MODO])["instrucciones"]
    if memorias:
        hechos = "\n".join(f"- {m}" for m in memorias)
        base += f"\n\nRecuerdas sobre tu dueño:\n{hechos}"
    return base

app = FastAPI()

def _detectar_ip_lan() -> str:
    """Detecta la IP local en la red WiFi/LAN sin depender de una IP fija."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return ""

ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    # Capacitor mobile origins
    "capacitor://localhost",
    "ionic://localhost",
    "http://localhost",
    "https://localhost",
]

# IP local en la red WiFi: se puede fijar en .env (LUNIA_LAN_IP) o se detecta sola,
# así no se rompe cada vez que la máquina cambia de red.
lan_ip = os.getenv("LUNIA_LAN_IP") or _detectar_ip_lan()
if lan_ip:
    ALLOWED_ORIGINS.append(f"http://{lan_ip}:8000")

# Orígenes adicionales opcionales, separados por comas, vía .env (LUNIA_EXTRA_ORIGINS)
extra_origins = os.getenv("LUNIA_EXTRA_ORIGINS", "")
if extra_origins:
    ALLOWED_ORIGINS.extend(o.strip() for o in extra_origins.split(",") if o.strip())

if public_url:
    ALLOWED_ORIGINS.append(public_url)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Auth helpers ──────────────────────────────────────────────────────────────

_http_bearer = HTTPBearer(auto_error=False)

def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    return forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "unknown")

async def require_auth(
    credentials: HTTPAuthorizationCredentials = Depends(_http_bearer),
) -> bool:
    token = credentials.credentials if credentials else None
    if not token or not auth.decode_token(token, "access"):
        raise HTTPException(status_code=401, detail="No autorizado")
    return True

# ── Auth models ───────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str

class TwoFARequest(BaseModel):
    username: str
    code: str

class RefreshRequest(BaseModel):
    refresh_token: str

# ── Auth endpoints ────────────────────────────────────────────────────────────

@app.post("/login")
async def login(request: Request, body: LoginRequest):
    ip = get_client_ip(request)
    auth.check_rate_limit(ip)

    stored_user = os.getenv("AUTH_USERNAME", "")
    stored_hash = os.getenv("AUTH_PASSWORD_HASH", "")
    if not stored_user or not stored_hash:
        raise HTTPException(status_code=500, detail="Servidor no configurado. Ejecuta setup_auth.py primero.")

    if body.username != stored_user or not auth.verify_password(body.password, stored_hash):
        auth.record_failure(ip)
        raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectos")

    return {"status": "2fa_required"}

@app.post("/verify_2fa")
async def verify_2fa(request: Request, body: TwoFARequest):
    ip = get_client_ip(request)
    auth.check_rate_limit(ip)

    stored_user = os.getenv("AUTH_USERNAME", "")
    if body.username != stored_user:
        auth.record_failure(ip)
        raise HTTPException(status_code=401, detail="Sesión inválida")

    if not auth.verify_totp(body.code):
        auth.record_failure(ip)
        raise HTTPException(status_code=401, detail="Código incorrecto o expirado")

    auth.clear_failures(ip)
    return {
        "access_token": auth.create_access_token(),
        "refresh_token": auth.create_refresh_token(),
        "token_type": "bearer",
    }

@app.post("/refresh")
async def refresh_token(body: RefreshRequest):
    if not auth.decode_token(body.refresh_token, "refresh"):
        raise HTTPException(status_code=401, detail="Sesión expirada")
    return {"access_token": auth.create_access_token()}

def get_model():
    try:
        print("[LOG] Listando modelos disponibles...")
        available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]

        if available_models:
            for preferred in ['models/gemini-2.5-flash', 'models/gemini-1.5-flash', 'models/gemini-pro']:
                if preferred in available_models:
                    print(f"[LOG] Seleccionado modelo: {preferred}")
                    return genai.GenerativeModel(
                        model_name=preferred,
                        system_instruction=construir_system_prompt(),
                        generation_config=GENERATION_CONFIG,
                    )
            return genai.GenerativeModel(
                model_name=available_models[0],
                system_instruction=construir_system_prompt(),
                generation_config=GENERATION_CONFIG,
            )
    except Exception as e:
        print(f"[LOG] Error al listar modelos: {e}")
    return genai.GenerativeModel(
        model_name='gemini-1.5-flash',
        system_instruction=construir_system_prompt(),
        generation_config=GENERATION_CONFIG,
    )

model = get_model()
chat = model.start_chat(history=[])
print("[LOG] Sesión de chat con memoria iniciada.")

def recargar_modelo():
    """Reconstruye el modelo con el system prompt actual (ej. tras cambiar de modo).
    Reinicia el historial de la conversación, igual que /reset."""
    global model, chat
    model = get_model()
    chat = model.start_chat(history=[])

def _quitar_acentos(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")

def detectar_modo_pedido(user_input: str) -> str:
    """Devuelve el id del modo mencionado en el texto (ej. 'juego'), o '' si no se pidió ninguno.
    Requiere la palabra 'modo' para evitar falsos positivos con palabras como 'normalmente'."""
    texto = _quitar_acentos(user_input.lower())
    if not re.search(r"\bmodo\b", texto):
        return ""
    for modo_id, info in MODOS.items():
        candidatos = {modo_id, _quitar_acentos(info["label"].lower())}
        for candidato in candidatos:
            if re.search(rf"\b{re.escape(candidato)}\b", texto):
                return modo_id
    return ""

def cambiar_modo_accion(user_input: str) -> str:
    global modo_actual
    try:
        nuevo_modo = detectar_modo_pedido(user_input)
        if not nuevo_modo or nuevo_modo == modo_actual:
            return ""
        modo_actual = nuevo_modo
        guardar_modo(modo_actual)
        recargar_modelo()
        print(f"[MODO] Cambiado a: {modo_actual}")
        return f"[Acción: Modo cambiado a {MODOS[modo_actual]['label']}] "
    except Exception as e:
        print(f"[ERROR MODO] {e}")
        return ""

class AskRequest(BaseModel):
    text: str

class ModoRequest(BaseModel):
    modo: str

class ContactoRequest(BaseModel):
    nombre: str
    numero: str  # formato internacional, ej: "+521234567890"

class AppToggleRequest(BaseModel):
    nombre: str
    habilitada: bool

_MAPEO_APPS_MAC = {
    "musica": "Music", "música": "Music",
    "correo": "Mail", "mail": "Mail",
    "calculadora": "Calculator",
    "calendario": "Calendar",
    "notas": "Notes",
    "fotos": "Photos",
    "navegador": "Google Chrome", "chrome": "Google Chrome", "internet": "Google Chrome",
    "editor": "Visual Studio Code", "code": "Visual Studio Code", "vscode": "Visual Studio Code", "visual studio": "Visual Studio Code",
    "finder": "Finder", "archivos": "Finder", "carpeta": "Finder", "explorador": "Finder",
    "safari": "Safari",
    "spotify": "Spotify",
    "terminal": "Terminal",
    "slack": "Slack",
    "zoom": "Zoom",
    "discord": "Discord",
    "whatsapp": "WhatsApp",
    "figma": "Figma",
    "notion": "Notion",
    "configuracion": "System Preferences", "configuración": "System Preferences", "ajustes": "System Preferences",
}

_MAPEO_APPS_WINDOWS = {
    "musica": "wmplayer", "música": "wmplayer",
    "correo": "outlook", "mail": "outlook",
    "calculadora": "calc",
    "calendario": "outlook",
    "notas": "notepad",
    "fotos": "photos",
    "navegador": "chrome", "chrome": "chrome", "internet": "chrome",
    "editor": "code", "vscode": "code", "visual studio": "code",
    "archivos": "explorer", "carpeta": "explorer", "explorador": "explorer",
    "spotify": "spotify",
    "terminal": "cmd",
    "powershell": "powershell",
    "slack": "slack",
    "zoom": "zoom",
    "discord": "discord",
    "whatsapp": "whatsapp",
    "figma": "figma",
    "notion": "notion",
    "configuracion": "ms-settings:", "configuración": "ms-settings:", "ajustes": "ms-settings:",
}

_MAPEO_APPS_LINUX = {
    "musica": "rhythmbox", "música": "rhythmbox",
    "correo": "thunderbird", "mail": "thunderbird",
    "calculadora": "gnome-calculator",
    "calendario": "gnome-calendar",
    "notas": "gedit",
    "fotos": "eog",
    "navegador": "google-chrome", "chrome": "google-chrome", "internet": "firefox",
    "editor": "code", "vscode": "code", "visual studio": "code",
    "archivos": "nautilus", "carpeta": "nautilus", "explorador": "nautilus",
    "spotify": "spotify",
    "terminal": "gnome-terminal",
    "slack": "slack",
    "zoom": "zoom",
    "discord": "discord",
    "whatsapp": "whatsapp-nativefier",
    "figma": "figma",
    "notion": "notion",
    "configuracion": "gnome-control-center", "configuración": "gnome-control-center", "ajustes": "gnome-control-center",
}

MAPEO_APPS = {
    "Darwin": _MAPEO_APPS_MAC,
    "Windows": _MAPEO_APPS_WINDOWS,
    "Linux": _MAPEO_APPS_LINUX,
}.get(SISTEMA, _MAPEO_APPS_MAC)

TRIGGER_WORDS = ["abre", "abrir", "lanza", "lanzar", "ejecuta", "ejecutar", "pon", "open", "inicia", "iniciar"]
CLOSE_TRIGGER_WORDS = ["cierra", "cerrar", "sal de", "salir de", "termina", "terminar", "finaliza", "finalizar"]
ARTICULOS = ["el ", "la ", "los ", "las ", "un ", "una ", "unos ", "unas "]
SEPARADORES = [" y ", ", y ", ", ", " también ", " además ", " y también "]

def limpiar_nombre(nombre: str) -> str:
    nombre = nombre.strip()
    for art in ARTICULOS:
        if nombre.startswith(art):
            nombre = nombre[len(art):].strip()
    return nombre

def extraer_nombres_app(texto: str, trigger_words: list) -> list:
    """Extrae los nombres de apps mencionados después de una palabra disparadora,
    separando por conjunciones/comas cuando se piden varias apps a la vez."""
    resto = texto
    for word in sorted(trigger_words, key=len, reverse=True):
        if word in texto:
            partes = texto.split(word, 1)
            if len(partes) > 1:
                resto = partes[1].strip()
                break

    segmentos = [resto]
    for sep in SEPARADORES:
        nuevos = []
        for seg in segmentos:
            nuevos.extend(seg.split(sep))
        segmentos = nuevos

    return [n for n in (limpiar_nombre(s) for s in segmentos) if n]

def resolver_app(nombre: str):
    # 1. Buscar en mapeo estático
    for clave, app in MAPEO_APPS.items():
        if clave in nombre:
            return app
    # 2. Buscar en apps aprendidas
    for clave, app in apps_aprendidas.items():
        if clave in nombre:
            return app
    return nombre.strip().title() if nombre.strip() else None

def buscar_en_aplicaciones(nombre: str):
    """Busca una app instalada por nombre aproximado, multiplataforma."""
    try:
        if SISTEMA == "Darwin":
            ubicaciones = ["/Applications", os.path.expanduser("~/Applications")]
            for loc in ubicaciones:
                resultado = subprocess.run(
                    ["find", loc, "-maxdepth", "2", "-iname", f"*{nombre}*.app", "-type", "d"],
                    capture_output=True, text=True, timeout=5
                )
                if resultado.stdout.strip():
                    primera = resultado.stdout.strip().split("\n")[0]
                    return os.path.basename(primera).replace(".app", "")
        elif SISTEMA == "Windows":
            ubicaciones = [
                r"C:\Program Files",
                r"C:\Program Files (x86)",
                os.path.expanduser(r"~\AppData\Local"),
                os.path.expanduser(r"~\AppData\Roaming"),
            ]
            for loc in ubicaciones:
                if not os.path.exists(loc):
                    continue
                resultado = subprocess.run(
                    f'where /r "{loc}" *{nombre}*.exe',
                    capture_output=True, text=True, timeout=8, shell=True
                )
                if resultado.stdout.strip():
                    primera = resultado.stdout.strip().split("\n")[0]
                    return os.path.basename(primera).replace(".exe", "")
        else:  # Linux
            resultado = subprocess.run(
                ["which", nombre.lower()],
                capture_output=True, text=True, timeout=5
            )
            if resultado.stdout.strip():
                return nombre.lower()
    except Exception:
        pass
    return None

def abrir_app(app_final: str, nombre_raw: str) -> bool:
    print(f"[ACCION] Intentando abrir: {app_final}")
    try:
        if SISTEMA == "Darwin":
            res = subprocess.run(["open", "-a", app_final], capture_output=True)
            if res.returncode == 0:
                return True
            return subprocess.run(["open", nombre_raw], capture_output=True).returncode == 0
        elif SISTEMA == "Windows":
            res = subprocess.run(f'start "" "{app_final}"', shell=True, capture_output=True)
            if res.returncode == 0:
                return True
            return subprocess.run(app_final, shell=True, capture_output=True).returncode == 0
        else:  # Linux
            res = subprocess.run(["xdg-open", app_final], capture_output=True)
            if res.returncode == 0:
                return True
            return subprocess.run([app_final], capture_output=True).returncode == 0
    except Exception:
        return False

def cerrar_app(app_final: str) -> bool:
    print(f"[ACCION] Intentando cerrar: {app_final}")
    try:
        if SISTEMA == "Darwin":
            res = subprocess.run(
                ["osascript", "-e", f'tell application "{app_final}" to quit'],
                capture_output=True, text=True,
            )
            if res.returncode != 0:
                print(f"[ACCION] Error al cerrar {app_final}: {res.stderr.strip()}")
            return res.returncode == 0
        elif SISTEMA == "Windows":
            res = subprocess.run(["taskkill", "/IM", f"{app_final}.exe", "/F"], capture_output=True, text=True)
            if res.returncode != 0:
                print(f"[ACCION] Error al cerrar {app_final}: {res.stderr.strip()}")
            return res.returncode == 0
        else:  # Linux
            res = subprocess.run(["pkill", "-f", app_final], capture_output=True, text=True)
            if res.returncode != 0:
                print(f"[ACCION] Error al cerrar {app_final}: {res.stderr.strip()}")
            return res.returncode == 0
    except Exception as e:
        print(f"[ACCION] Excepción al cerrar {app_final}: {e}")
        return False

def ejecutar_accion(user_input: str) -> str:
    texto = user_input.lower().strip()

    try:
        if not any(t in texto for t in TRIGGER_WORDS):
            return ""

        abiertas = []
        bloqueadas = []
        for nombre in extraer_nombres_app(texto, TRIGGER_WORDS):
            app_final = resolver_app(nombre)
            if app_final and not app_permitida(app_final):
                bloqueadas.append(app_final)
                continue
            if app_final and abrir_app(app_final, nombre):
                marcar_app_usada(app_final)
                abiertas.append(app_final)
            else:
                # Buscar automáticamente en /Applications
                encontrada = buscar_en_aplicaciones(nombre)
                if encontrada and not app_permitida(encontrada):
                    bloqueadas.append(encontrada)
                elif encontrada and abrir_app(encontrada, encontrada):
                    print(f"[APRENDIZAJE] Nueva app aprendida: '{nombre}' → '{encontrada}'")
                    apps_aprendidas[nombre] = encontrada
                    guardar_apps_aprendidas(apps_aprendidas)
                    marcar_app_usada(encontrada)
                    abiertas.append(encontrada)

        resultado = ""
        if abiertas:
            resultado += f"[Acción: Abriendo {', '.join(abiertas)}] "
        if bloqueadas:
            resultado += f"[Acción: El usuario deshabilitó el acceso a {', '.join(bloqueadas)}, no se puede abrir] "
        return resultado

    except Exception as e:
        print(f"[ERROR ACCION] {e}")

    return ""

def cerrar_accion(user_input: str) -> str:
    texto = user_input.lower().strip()

    try:
        if not any(t in texto for t in CLOSE_TRIGGER_WORDS):
            return ""

        cerradas = []
        bloqueadas = []
        for nombre in extraer_nombres_app(texto, CLOSE_TRIGGER_WORDS):
            app_final = resolver_app(nombre)
            if not app_final:
                continue
            if not app_permitida(app_final):
                bloqueadas.append(app_final)
                continue
            if cerrar_app(app_final):
                marcar_app_usada(app_final)
                cerradas.append(app_final)

        resultado = ""
        if cerradas:
            resultado += f"[Acción: Cerrando {', '.join(cerradas)}] "
        if bloqueadas:
            resultado += f"[Acción: El usuario deshabilitó el acceso a {', '.join(bloqueadas)}, no se puede cerrar] "
        return resultado

    except Exception as e:
        print(f"[ERROR ACCION CERRAR] {e}")

    return ""

async def extraer_y_guardar_memoria(user_text: str, lunia_response: str):
    global memorias
    try:
        hechos_actuales = "\n".join(f"- {m}" for m in memorias) if memorias else "Ninguno aún."
        prompt = f"""Analiza este intercambio y decide si hay algún dato importante sobre el usuario que valga la pena recordar a largo plazo (nombre, preferencias, hábitos, trabajo, familia, gustos, etc.).
Si no hay nada relevante, responde exactamente: NADA
Si hay algo, responde SOLO el dato en una frase corta y clara. No repitas lo que ya está en la memoria existente.

Memoria existente:
{hechos_actuales}

Usuario dijo: {user_text}
Lunia respondió: {lunia_response}

Dato a recordar (o NADA):"""

        resultado = model.generate_content(prompt)
        hecho = resultado.text.strip()
        if hecho and hecho.upper() != "NADA":
            memorias.append(hecho)
            guardar_memorias(memorias)
            print(f"[MEMORIA] Nuevo recuerdo guardado: {hecho}")
    except Exception as e:
        print(f"[MEMORIA] Error al extraer memoria: {e}")

@app.get("/")
async def root():
    return {"status": "Lunia Online", "os": SISTEMA}

def ejecutar_applescript(script: str, args: list = None):
    if SISTEMA != "Darwin":
        print("[EXEC] AppleScript solo disponible en macOS.")
        return
    with tempfile.NamedTemporaryFile(mode="w", suffix=".applescript", delete=False, encoding="utf-8") as f:
        f.write(script)
        tmp_path = f.name
    try:
        subprocess.Popen(["osascript", tmp_path] + (args or []))
    except Exception as e:
        print(f"[EXEC] Error osascript: {e}")

def ejecutar_powershell(script: str, args: list = None):
    if SISTEMA != "Windows":
        print("[EXEC] PowerShell solo disponible en Windows.")
        return
    with tempfile.NamedTemporaryFile(mode="w", suffix=".ps1", delete=False, encoding="utf-8") as f:
        f.write(script)
        tmp_path = f.name
    try:
        subprocess.Popen(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", tmp_path] + (args or []))
    except Exception as e:
        print(f"[EXEC] Error PowerShell: {e}")

def enviar_whatsapp_por_numero(numero: str, mensaje: str):
    """Abre el chat directo por número (deep link) y envía el mensaje.
    Evita la búsqueda por nombre en la UI, que es frágil e inconsistente."""
    numero_limpio = re.sub(r"[^\d+]", "", numero)
    mensaje_encoded = urllib.parse.quote(mensaje)
    url = f"whatsapp://send?phone={numero_limpio}&text={mensaje_encoded}"
    print(f"[WHATSAPP] Abriendo chat directo: {numero_limpio}")

    if SISTEMA == "Darwin":
        subprocess.run(["open", url], capture_output=True)
        script = '''
tell application "WhatsApp" to activate
delay 2.5
tell application "System Events" to key code 36
'''
        ejecutar_applescript(script)
    elif SISTEMA == "Windows":
        subprocess.run(["cmd", "/c", "start", "", url], shell=False, capture_output=True)
        script = '''
Add-Type -AssemblyName System.Windows.Forms
Start-Sleep -Seconds 3
[System.Windows.Forms.SendKeys]::SendWait("{ENTER}")
'''
        ejecutar_powershell(script)
    else:  # Linux
        subprocess.Popen(["xdg-open", url])
        print("[WHATSAPP] En Linux confirma el envío manualmente si no se envía solo.")

def enviar_whatsapp_por_busqueda(contacto: str, mensaje: str):
    """Respaldo cuando el contacto no está guardado en contactos.json: busca
    por nombre en la UI simulando teclas. Menos confiable que el deep link."""
    print(f"[WHATSAPP] Enviando a {contacto} por búsqueda (sin número guardado): {mensaje}")
    if SISTEMA == "Darwin":
        keyword = contacto.strip().split()[0]
        # contacto/mensaje se pasan como argv, nunca se interpolan en el texto del script,
        # así que no pueden "escapar" del literal ni inyectar AppleScript adicional.
        script = '''
on run argv
    set contactoArg to item 1 of argv
    set mensajeArg to item 2 of argv
    tell application "WhatsApp" to activate
    delay 2

    tell application "System Events"
        tell process "WhatsApp"
            key code 53
            delay 0.8
            keystroke "f" using command down
            delay 1.5
            keystroke "a" using command down
            delay 0.3
            keystroke contactoArg
            delay 2.5
            key code 125
            delay 0.5
            key code 36
            delay 2.5
            keystroke mensajeArg
            delay 0.5
            key code 36
        end tell
    end tell
end run
'''
        ejecutar_applescript(script, [keyword, mensaje])
    elif SISTEMA == "Windows":
        keyword = contacto.strip().split()[0]
        # $Keyword/$Mensaje llegan como parámetros del proceso, no como texto interpolado,
        # y SendKeys::Escape neutraliza sus caracteres especiales ({}, +, ^, %, ~).
        script = '''
param(
    [string]$Keyword,
    [string]$Mensaje
)
Add-Type -AssemblyName System.Windows.Forms
Start-Process "whatsapp:"
Start-Sleep -Seconds 2
[System.Windows.Forms.SendKeys]::SendWait("^f")
Start-Sleep -Milliseconds 800
[System.Windows.Forms.SendKeys]::SendWait([System.Windows.Forms.SendKeys]::Escape($Keyword))
Start-Sleep -Seconds 3
[System.Windows.Forms.SendKeys]::SendWait("{ENTER}")
Start-Sleep -Seconds 2
[System.Windows.Forms.SendKeys]::SendWait([System.Windows.Forms.SendKeys]::Escape($Mensaje))
Start-Sleep -Milliseconds 500
[System.Windows.Forms.SendKeys]::SendWait("{ENTER}")
'''
        ejecutar_powershell(script, ["-Keyword", keyword, "-Mensaje", mensaje])
    else:
        # Linux: abrir WhatsApp Web como fallback
        mensaje_encoded = urllib.parse.quote(mensaje)
        subprocess.Popen(["xdg-open", f"https://web.whatsapp.com/send?text={mensaje_encoded}"])
        print("[WHATSAPP] En Linux se abre WhatsApp Web. Selecciona el contacto manualmente.")

def enviar_whatsapp(contacto: str, mensaje: str):
    """Punto de entrada: usa el número guardado si existe (más confiable),
    y solo recurre a la búsqueda por nombre en la UI si no hay número registrado."""
    numero = resolver_contacto(contacto)
    if numero:
        enviar_whatsapp_por_numero(numero, mensaje)
    else:
        enviar_whatsapp_por_busqueda(contacto, mensaje)

def procesar_tags_especiales(texto: str):
    """Procesa tags como [WHATSAPP: contacto='...' mensaje='...']"""
    patron_wa = r'\[WHATSAPP:\s*contacto=["\'](.+?)["\']\s+mensaje=["\'](.+?)["\']\s*\]'
    matches = re.findall(patron_wa, texto, re.DOTALL)
    for contacto, mensaje in matches:
        enviar_whatsapp(contacto.strip(), mensaje.strip())
    texto = re.sub(patron_wa, "", texto, flags=re.DOTALL).strip()
    return texto

# Whitelist estricta: el EXEC tag solo puede abrir o cerrar una app conocida.
# El nombre capturado nunca contiene comillas, así que no puede "escapar" del
# literal de AppleScript/PowerShell ni inyectar comandos de shell adicionales.
_EXEC_ACTIVATE_RE = re.compile(
    r'tell application "([^"]+)"\s+(?:to\s+activate|activate\s+end\s+tell)',
    re.IGNORECASE,
)
_EXEC_QUIT_RE = re.compile(r'tell application "([^"]+)"\s*to\s*quit', re.IGNORECASE)
_EXEC_STARTPROCESS_RE = re.compile(r'Start-Process\s+"([^"]+)"', re.IGNORECASE)
_EXEC_XDGOPEN_RE = re.compile(r'xdg-open\s+"?([^"\s;&|`$<>]+)"?', re.IGNORECASE)

def _resolver_accion_exec(cmd: str):
    """Devuelve (app_name, accion) si cmd coincide con alguna acción permitida, o (None, None)."""
    m = _EXEC_QUIT_RE.search(cmd)
    if m:
        return m.group(1), "quit"
    m = _EXEC_ACTIVATE_RE.search(cmd)
    if m:
        return m.group(1), "activate"
    m = _EXEC_STARTPROCESS_RE.search(cmd) or _EXEC_XDGOPEN_RE.search(cmd)
    if m:
        return m.group(1), "activate"
    return None, None

def ejecutar_exec_tags(texto_respuesta: str):
    patron_completo = r'\[EXEC:(.*?)\]'
    patron_incompleto = r'\[EXEC:.*$'

    comandos = re.findall(patron_completo, texto_respuesta, re.DOTALL)
    ejecutados = []
    for cmd in comandos:
        cmd = cmd.strip()
        app_name, accion = _resolver_accion_exec(cmd)
        if not app_name:
            print(f"[EXEC] Bloqueado (no coincide con ninguna acción permitida): {cmd[:80]}")
            continue
        if not app_permitida(app_name):
            print(f"[EXEC] Bloqueado (app deshabilitada por el usuario): {app_name}")
            continue

        print(f"[EXEC] {accion} -> {app_name}")
        try:
            ok = cerrar_app(app_name) if accion == "quit" else abrir_app(app_name, app_name)
            if ok:
                if accion == "activate":
                    marcar_app_usada(app_name)
                ejecutados.append(f"{accion} {app_name}"[:80])
        except Exception as e:
            print(f"[EXEC] Error: {e}")

    texto = re.sub(patron_completo, "", texto_respuesta, flags=re.DOTALL)
    texto = re.sub(patron_incompleto, "", texto, flags=re.MULTILINE)
    return texto.strip(), comandos

@app.post("/ask")
async def ask(request: AskRequest, _: bool = Depends(require_auth)):
    try:
        import asyncio
        resultado_accion = ejecutar_accion(request.text) + cerrar_accion(request.text) + cambiar_modo_accion(request.text)
        fecha_actual = datetime.now().strftime("%A %d de %B de %Y, %H:%M")
        mensaje = f"[Fecha y hora actual: {fecha_actual}]\n{request.text}"
        if resultado_accion:
            mensaje += f"\nAcción tomada: {resultado_accion}"
        response = chat.send_message(mensaje)

        # Procesar tags especiales (WhatsApp, etc.)
        texto_sin_wa = procesar_tags_especiales(response.text)

        # Ejecutar acciones [EXEC:] genéricas
        texto_limpio, scripts_ejecutados = ejecutar_exec_tags(texto_sin_wa)

        # Inyectar resumen en historial para que Lunia recuerde lo ejecutado
        if scripts_ejecutados:
            resumen = f"(Sistema confirmó: {'; '.join(scripts_ejecutados[:2])})"
            chat.history[-1].parts[0].text = texto_limpio + " " + resumen

        lunia_says = f"{resultado_accion}{texto_limpio}"
        asyncio.create_task(extraer_y_guardar_memoria(request.text, lunia_says))

        return {"lunia_says": lunia_says}
    except Exception as e:
        print(f"[LOG] ERROR EN /ASK: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/reset")
async def reset_chat(_: bool = Depends(require_auth)):
    global chat
    chat = model.start_chat(history=[])
    return {"status": "Memoria de conversación reiniciada"}

@app.get("/modo")
async def obtener_modo(_: bool = Depends(require_auth)):
    return {
        "modo_actual": modo_actual,
        "modos": [{"id": mid, "label": m["label"]} for mid, m in MODOS.items()],
    }

@app.post("/modo")
async def cambiar_modo(body: ModoRequest, _: bool = Depends(require_auth)):
    global modo_actual
    modo_id = body.modo.strip().lower()
    if modo_id not in MODOS:
        raise HTTPException(status_code=400, detail="Modo inválido")
    modo_actual = modo_id
    guardar_modo(modo_actual)
    recargar_modelo()
    return {"status": "Modo actualizado", "modo_actual": modo_actual}

@app.get("/memoria")
async def ver_memoria(_: bool = Depends(require_auth)):
    return {"memorias": memorias}

@app.delete("/memoria")
async def borrar_memoria(_: bool = Depends(require_auth)):
    global memorias
    memorias = []
    guardar_memorias(memorias)
    return {"status": "Memoria borrada"}

@app.get("/contactos")
async def ver_contactos(_: bool = Depends(require_auth)):
    return {"contactos": contactos}

@app.post("/contactos")
async def agregar_contacto(body: ContactoRequest, _: bool = Depends(require_auth)):
    numero = re.sub(r"[^\d+]", "", body.numero.strip())
    if not numero:
        raise HTTPException(status_code=400, detail="Número inválido")
    contactos[body.nombre.strip().lower()] = numero
    guardar_contactos(contactos)
    return {"status": "Contacto guardado", "contactos": contactos}

@app.delete("/contactos/{nombre}")
async def borrar_contacto(nombre: str, _: bool = Depends(require_auth)):
    contactos.pop(nombre.strip().lower(), None)
    guardar_contactos(contactos)
    return {"status": "Contacto eliminado", "contactos": contactos}

@app.get("/apps")
async def listar_apps(_: bool = Depends(require_auth)):
    # Solo apps que Lunia abrió con éxito al menos una vez en esta máquina
    # (más las ya deshabilitadas, para poder re-habilitarlas), no todo el mapeo estático.
    nombres = apps_usadas | apps_deshabilitadas
    resultado = sorted(
        (
            {"nombre": n, "habilitada": app_permitida(n)}
            for n in nombres
        ),
        key=lambda x: x["nombre"].lower(),
    )
    return {"apps": resultado}

@app.post("/apps/toggle")
async def alternar_app(body: AppToggleRequest, _: bool = Depends(require_auth)):
    global apps_deshabilitadas
    nombre = body.nombre.strip()
    if not nombre:
        raise HTTPException(status_code=400, detail="Nombre de app inválido")
    if body.habilitada:
        apps_deshabilitadas = {a for a in apps_deshabilitadas if a.lower() != nombre.lower()}
    elif nombre.lower() not in {a.lower() for a in apps_deshabilitadas}:
        apps_deshabilitadas.add(nombre)
    guardar_apps_deshabilitadas(apps_deshabilitadas)
    return {"status": "Actualizado", "apps_deshabilitadas": sorted(apps_deshabilitadas)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)