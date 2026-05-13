import os
import re
import json
import tempfile
import subprocess
import platform
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

GENERATION_CONFIG = genai.GenerationConfig(
    max_output_tokens=350,
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
Solo incluye estos tags cuando el usuario haya pedido la acción concreta."""
    if memorias:
        hechos = "\n".join(f"- {m}" for m in memorias)
        base += f"\n\nRecuerdas sobre tu dueño:\n{hechos}"
    return base

app = FastAPI()

ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    # Capacitor mobile origins
    "capacitor://localhost",
    "ionic://localhost",
    "http://localhost",
    "https://localhost",
    # IP local de la Mac en la red WiFi
    "http://10.10.100.222:8000",
]
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

class AskRequest(BaseModel):
    text: str

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
ARTICULOS = ["el ", "la ", "los ", "las ", "un ", "una ", "unos ", "unas "]
SEPARADORES = [" y ", ", y ", ", ", " también ", " además ", " y también "]

def limpiar_nombre(nombre: str) -> str:
    nombre = nombre.strip()
    for art in ARTICULOS:
        if nombre.startswith(art):
            nombre = nombre[len(art):].strip()
    return nombre

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

def ejecutar_accion(user_input: str) -> str:
    texto = user_input.lower().strip()

    try:
        if not any(t in texto for t in TRIGGER_WORDS):
            return ""

        # Extraer todo lo que viene después del trigger
        resto = texto
        for word in sorted(TRIGGER_WORDS, key=len, reverse=True):
            if word in texto:
                partes = texto.split(word, 1)
                if len(partes) > 1:
                    resto = partes[1].strip()
                    break

        # Separar múltiples apps por conjunciones y comas
        segmentos = [resto]
        for sep in SEPARADORES:
            nuevos = []
            for seg in segmentos:
                nuevos.extend(seg.split(sep))
            segmentos = nuevos

        abiertas = []
        for segmento in segmentos:
            nombre = limpiar_nombre(segmento)
            if not nombre:
                continue
            app_final = resolver_app(nombre)
            if app_final and abrir_app(app_final, nombre):
                abiertas.append(app_final)
            else:
                # Buscar automáticamente en /Applications
                encontrada = buscar_en_aplicaciones(nombre)
                if encontrada and abrir_app(encontrada, encontrada):
                    print(f"[APRENDIZAJE] Nueva app aprendida: '{nombre}' → '{encontrada}'")
                    apps_aprendidas[nombre] = encontrada
                    guardar_apps_aprendidas(apps_aprendidas)
                    abiertas.append(encontrada)

        if abiertas:
            lista = ", ".join(abiertas)
            return f"[Acción: Abriendo {lista}] "

    except Exception as e:
        print(f"[ERROR ACCION] {e}")

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

def ejecutar_applescript(script: str):
    if SISTEMA != "Darwin":
        print("[EXEC] AppleScript solo disponible en macOS.")
        return
    with tempfile.NamedTemporaryFile(mode="w", suffix=".applescript", delete=False, encoding="utf-8") as f:
        f.write(script)
        tmp_path = f.name
    try:
        subprocess.Popen(["osascript", tmp_path])
    except Exception as e:
        print(f"[EXEC] Error osascript: {e}")

def ejecutar_powershell(script: str):
    if SISTEMA != "Windows":
        print("[EXEC] PowerShell solo disponible en Windows.")
        return
    try:
        subprocess.Popen(["powershell", "-Command", script])
    except Exception as e:
        print(f"[EXEC] Error PowerShell: {e}")

def enviar_whatsapp(contacto: str, mensaje: str):
    print(f"[WHATSAPP] Enviando a {contacto}: {mensaje}")
    if SISTEMA == "Darwin":
        keyword = contacto.strip().split()[0]
        script = f'''
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
        keystroke "{keyword}"
        delay 3.5
        key code 36
        delay 2.5
        key code 53
        delay 0.8
        keystroke "{mensaje}"
        delay 0.5
        key code 36
    end tell
end tell
'''
        ejecutar_applescript(script)
    elif SISTEMA == "Windows":
        keyword = contacto.strip().split()[0]
        script = f'''
Add-Type -AssemblyName System.Windows.Forms
Start-Process "whatsapp:"
Start-Sleep -Seconds 2
[System.Windows.Forms.SendKeys]::SendWait("^f")
Start-Sleep -Milliseconds 800
[System.Windows.Forms.SendKeys]::SendWait("{keyword}")
Start-Sleep -Seconds 3
[System.Windows.Forms.SendKeys]::SendWait("{{ENTER}}")
Start-Sleep -Seconds 2
[System.Windows.Forms.SendKeys]::SendWait("{mensaje}")
Start-Sleep -Milliseconds 500
[System.Windows.Forms.SendKeys]::SendWait("{{ENTER}}")
'''
        ejecutar_powershell(script)
    else:
        # Linux: abrir WhatsApp Web como fallback
        import urllib.parse
        mensaje_encoded = urllib.parse.quote(mensaje)
        subprocess.Popen(["xdg-open", f"https://web.whatsapp.com/send?text={mensaje_encoded}"])
        print("[WHATSAPP] En Linux se abre WhatsApp Web. Selecciona el contacto manualmente.")

def procesar_tags_especiales(texto: str):
    """Procesa tags como [WHATSAPP: contacto='...' mensaje='...']"""
    patron_wa = r'\[WHATSAPP:\s*contacto=["\'](.+?)["\']\s+mensaje=["\'](.+?)["\']\s*\]'
    matches = re.findall(patron_wa, texto, re.DOTALL)
    for contacto, mensaje in matches:
        enviar_whatsapp(contacto.strip(), mensaje.strip())
    texto = re.sub(patron_wa, "", texto, flags=re.DOTALL).strip()
    return texto

def ejecutar_exec_tags(texto_respuesta: str):
    patron_completo = r'\[EXEC:\s*(.*?)\]'
    patron_incompleto = r'\[EXEC:.*$'

    comandos = re.findall(patron_completo, texto_respuesta, re.DOTALL)
    ejecutados = []
    for cmd in comandos:
        cmd = cmd.strip()
        print(f"[EXEC] Ejecutando: {cmd}")
        try:
            es_applescript = "tell application" in cmd or "tell app" in cmd
            es_powershell = "Start-Process" in cmd or "Add-Type" in cmd or "SendKeys" in cmd
            if es_applescript and SISTEMA == "Darwin":
                ejecutar_applescript(cmd)
            elif es_powershell and SISTEMA == "Windows":
                ejecutar_powershell(cmd)
            else:
                subprocess.Popen(cmd, shell=True)
            ejecutados.append(cmd[:80])
        except Exception as e:
            print(f"[EXEC] Error: {e}")

    texto = re.sub(patron_completo, "", texto_respuesta, flags=re.DOTALL)
    texto = re.sub(patron_incompleto, "", texto, flags=re.MULTILINE)
    return texto.strip(), comandos

@app.post("/ask")
async def ask(request: AskRequest, _: bool = Depends(require_auth)):
    try:
        import asyncio
        resultado_accion = ejecutar_accion(request.text)
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

@app.get("/memoria")
async def ver_memoria(_: bool = Depends(require_auth)):
    return {"memorias": memorias}

@app.delete("/memoria")
async def borrar_memoria(_: bool = Depends(require_auth)):
    global memorias
    memorias = []
    guardar_memorias(memorias)
    return {"status": "Memoria borrada"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)