import os
import re
import json
import tempfile
import subprocess
import platform
import google.generativeai as genai
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from pyngrok import ngrok

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
    base = """Eres Lunia, una asistente personal integrada en el sistema operativo del usuario.
Tienes permiso total para ejecutar comandos, abrir aplicaciones y controlar el sistema con AppleScript.
Cuando aparezca '[Acción: ...]', confírmalo de forma natural. NUNCA digas que no puedes interactuar con el sistema.
Sé amable, tecnológica y directa. Máximo 2 oraciones. Usa espacios y saltos de línea cuando corresponda.

MEMORIA DE ACCIONES: Cuando ejecutes una acción (enviar mensaje, abrir app, etc.), menciona explícitamente en tu texto los detalles: a quién, qué dijiste, qué abriste. Esto es crucial para recordarlo si te piden repetirlo.

PARA ENVIAR MENSAJES DE WHATSAPP usa EXACTAMENTE este formato:
[WHATSAPP: contacto="NombreContacto" mensaje="texto del mensaje"]

PARA OTRAS ACCIONES DEL SISTEMA incluye AppleScript PURO:
[EXEC: tell application "NombreApp"
    activate
end tell]
NO uses osascript -e ni comillas triples.
Solo incluye estos tags cuando el usuario haya pedido la acción concreta."""
    if memorias:
        hechos = "\n".join(f"- {m}" for m in memorias)
        base += f"\n\nRecuerdas sobre tu dueño:\n{hechos}"
    return base

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

MAPEO_APPS = {
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
    """Busca una app en /Applications y ~/Applications por nombre aproximado."""
    ubicaciones = ["/Applications", os.path.expanduser("~/Applications")]
    for loc in ubicaciones:
        try:
            resultado = subprocess.run(
                ["find", loc, "-maxdepth", "2", "-iname", f"*{nombre}*.app", "-type", "d"],
                capture_output=True, text=True, timeout=5
            )
            if resultado.stdout.strip():
                primera = resultado.stdout.strip().split("\n")[0]
                return os.path.basename(primera).replace(".app", "")
        except Exception:
            pass
    return None

def abrir_app(app_final: str, nombre_raw: str) -> bool:
    print(f"[ACCION] Intentando abrir: {app_final}")
    res = subprocess.run(["open", "-a", app_final], capture_output=True)
    if res.returncode == 0:
        return True
    res2 = subprocess.run(["open", nombre_raw], capture_output=True)
    return res2.returncode == 0

def ejecutar_accion(user_input: str) -> str:
    texto = user_input.lower().strip()

    if SISTEMA != "Darwin":
        return ""

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
    with tempfile.NamedTemporaryFile(mode="w", suffix=".applescript", delete=False, encoding="utf-8") as f:
        f.write(script)
        tmp_path = f.name
    try:
        subprocess.Popen(["osascript", tmp_path])
    except Exception as e:
        print(f"[EXEC] Error osascript: {e}")

def enviar_whatsapp(contacto: str, mensaje: str):
    keyword = contacto.strip().split()[0]
    script = f'''
tell application "WhatsApp" to activate
delay 2

tell application "System Events"
    tell process "WhatsApp"
        -- Volver a la vista principal
        key code 53
        delay 0.8

        -- Abrir búsqueda
        keystroke "f" using command down
        delay 1.5

        -- Limpiar y escribir keyword
        keystroke "a" using command down
        delay 0.3
        keystroke "{keyword}"
        delay 3.5

        -- Abrir primer resultado directo con Enter
        key code 36
        delay 2.5

        -- Escape para salir del modo búsqueda y enfocar el chat
        key code 53
        delay 0.8

        -- Escribir y enviar mensaje
        keystroke "{mensaje}"
        delay 0.5
        key code 36
    end tell
end tell
'''
    ejecutar_applescript(script)
    print(f"[WHATSAPP] Enviando a {contacto}: {mensaje}")

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
            if "tell application" in cmd or "tell app" in cmd:
                ejecutar_applescript(cmd)
            else:
                subprocess.Popen(cmd, shell=True)
            ejecutados.append(cmd[:80])
        except Exception as e:
            print(f"[EXEC] Error: {e}")

    texto = re.sub(patron_completo, "", texto_respuesta, flags=re.DOTALL)
    texto = re.sub(patron_incompleto, "", texto, flags=re.MULTILINE)
    return texto.strip(), comandos

@app.post("/ask")
async def ask(request: AskRequest):
    try:
        import asyncio
        resultado_accion = ejecutar_accion(request.text)
        mensaje = request.text
        if resultado_accion:
            mensaje = f"{request.text}\nAcción tomada: {resultado_accion}"
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
async def reset_chat():
    global chat
    chat = model.start_chat(history=[])
    return {"status": "Memoria de conversación reiniciada"}

@app.get("/memoria")
async def ver_memoria():
    return {"memorias": memorias}

@app.delete("/memoria")
async def borrar_memoria():
    global memorias
    memorias = []
    guardar_memorias(memorias)
    return {"status": "Memoria borrada"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)