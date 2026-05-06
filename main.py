import os
import subprocess
import google.generativeai as genai
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from pyngrok import ngrok

# Configuración inicial
load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# Configuración de Ngrok para acceso remoto
NGROK_TOKEN = os.getenv("NGROK_AUTHTOKEN")
public_url = ""

if NGROK_TOKEN:
    ngrok.set_auth_token(NGROK_TOKEN)
    # Abrir un túnel HTTP en el puerto 8000
    public_url = ngrok.connect(8000).public_url
    print(f"\n[NGROK] Lunia es accesible remotamente en: {public_url}\n")

# Definición del System Prompt interno
SYSTEM_PROMPT = """Eres Lunia, una asistente personal inteligente y eficiente. 
Tu objetivo es ayudar al usuario con tareas de Windows y responder preguntas de forma clara y amable. 
Si se ejecuta una acción de sistema, simplemente intégralo en tu respuesta."""

app = FastAPI()

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # En producción deberías restringir esto
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

model = genai.GenerativeModel('gemini-3-flash-preview')

# Esquema de validación con Pydantic
class AskRequest(BaseModel):
    text: str

def ejecutar_accion(user_input: str) -> str:
    """Ejecuta comandos de Windows basados en el input del usuario."""
    user_input = user_input.lower()
    log_msg = ""
    
    print(f"[LOG] Analizando comando: {user_input}")
    
    try:
        # Abrir Visual Studio Code
        if any(word in user_input for word in ["visual", "code", "programar"]):
            print("[LOG] Abriendo el editor Antigravity...")
            # Usamos la ruta detectada del editor actual
            ruta_editor = r"C:\Users\diana\AppData\Local\Programs\Antigravity\Antigravity.exe"
            subprocess.Popen(f'"{ruta_editor}"', shell=True)
            log_msg = "[Acción: Abriendo Antigravity (VS Code)] "
            
        # Abrir Navegador Chrome
        elif any(word in user_input for word in ["navegador", "chrome"]):
            print("[LOG] Ejecutando: start chrome")
            subprocess.Popen("start chrome", shell=True)
            log_msg = "[Acción: Abriendo Chrome] "
            
    except Exception as e:
        error_msg = f"[Error al ejecutar acción: {str(e)}]"
        print(f"[LOG] {error_msg}")
        return error_msg

    return log_msg

@app.get("/")
async def root():
    return {"status": "Lunia Online"}

@app.post("/ask")
async def ask(request: AskRequest):
    try:
        # 1. Intentar ejecutar acción basada en el texto
        resultado_accion = ejecutar_accion(request.text)
        
        # 2. Obtener respuesta de Gemini
        print(f"[LOG] Consultando a Gemini: {request.text}")
        response = model.generate_content(f"{SYSTEM_PROMPT}\nUsuario: {request.text}")
        
        # 3. Concatenar y retornar
        respuesta_final = f"{resultado_accion}{response.text}"
        
        print("[LOG] Respuesta generada con éxito")
        return {"lunia_says": respuesta_final}
        
    except Exception as e:
        print(f"[LOG] ERROR en /ask: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error interno en el servidor de Lunia: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)