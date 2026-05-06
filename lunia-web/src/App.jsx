import React, { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import axios from 'axios';
import { Mic, MicOff, Settings, Palette, MessageSquare } from 'lucide-react';

const API_URL = "http://localhost:8000/ask";

function App() {
  const [isListening, setIsListening] = useState(false);
  const [status, setStatus] = useState("Lunia en espera...");
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [lastResponse, setLastResponse] = useState("");
  
  const recognitionRef = useRef(null);

  useEffect(() => {
    if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
      const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
      const recognition = new SpeechRecognition();
      recognition.continuous = false;
      recognition.interimResults = false;
      recognition.lang = 'es-ES';

      recognition.onstart = () => {
        setIsListening(true);
        setStatus("Escuchando...");
      };

      recognition.onresult = async (event) => {
        const text = event.results[0][0].transcript;
        setIsListening(false);
        setStatus(`Procesando...`);
        await sendToLunia(text);
      };

      recognition.onerror = () => {
        setIsListening(false);
        setStatus("No te escuché bien...");
      };

      recognition.onend = () => setIsListening(false);
      recognitionRef.current = recognition;
    }
  }, []);

  const startListening = () => {
    if (recognitionRef.current) {
      recognitionRef.current.start();
    }
  };

  const speak = (text) => {
    if ('speechSynthesis' in window) {
      const cleanText = text.replace(/\[Acción:.*?\]/g, "");
      const utterance = new SpeechSynthesisUtterance(cleanText);
      utterance.lang = 'es-ES';
      utterance.rate = 1.1;
      utterance.pitch = 1.2;
      utterance.onstart = () => setIsSpeaking(true);
      utterance.onend = () => setIsSpeaking(false);
      window.speechSynthesis.speak(utterance);
    }
  };

  const sendToLunia = async (text) => {
    try {
      const response = await axios.post(API_URL, { text });
      const luniaSays = response.data.lunia_says;
      setLastResponse(luniaSays);
      setStatus("Lunia responde");
      speak(luniaSays);
    } catch (error) {
      setStatus("Error de conexión");
    }
  };

  return (
    <div className="min-h-screen bg-[#020617] bg-gradient-to-br from-[#0f172a] to-[#020617] flex overflow-hidden font-sans">
      
      {/* SECCIÓN IZQUIERDA: EL ROSTRO */}
      <div className="w-1/2 flex flex-col items-center justify-center border-r border-white/5 relative bg-black/20">
        <motion.div 
          className="flex flex-col items-center gap-14"
          initial={{ opacity: 0, x: -50 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.8 }}
        >
          {/* Cejas Arqueadas */}
          <div className="flex gap-28">
            <motion.div 
              className="w-24 h-10 border-t-4 border-cyan-400 rounded-[50%]"
              style={{ filter: 'drop-shadow(0 -5px 10px #22d3ee)' }}
              animate={{ y: isSpeaking ? [0, -8, 0] : 0 }}
              transition={{ repeat: Infinity, duration: 2 }}
            />
            <motion.div 
              className="w-24 h-10 border-t-4 border-cyan-400 rounded-[50%]"
              style={{ filter: 'drop-shadow(0 -5px 10px #22d3ee)' }}
              animate={{ y: isSpeaking ? [0, -8, 0] : 0 }}
              transition={{ repeat: Infinity, duration: 2, delay: 0.1 }}
            />
          </div>

          {/* Ojos */}
          <div className="flex gap-24">
            <motion.div 
              className="w-14 h-32 bg-cyan-400 rounded-[2.5rem]"
              style={{ boxShadow: '0 0 40px #22d3ee' }}
              animate={{ scaleY: isListening ? [1, 1.1, 1] : [1, 0.1, 1] }}
              transition={{ repeat: Infinity, duration: isListening ? 0.6 : 5, delay: isListening ? 0 : 3 }}
            />
            <motion.div 
              className="w-14 h-32 bg-cyan-400 rounded-[2.5rem]"
              style={{ boxShadow: '0 0 40px #22d3ee' }}
              animate={{ scaleY: isListening ? [1, 1.1, 1] : [1, 0.1, 1] }}
              transition={{ repeat: Infinity, duration: isListening ? 0.6 : 5, delay: isListening ? 0.1 : 3 }}
            />
          </div>

          {/* Boca (Sonrisa) */}
          <motion.div 
            className="w-44 h-16 border-b-8 border-x-4 border-cyan-400 rounded-b-[3.5rem]"
            style={{ filter: 'drop-shadow(0 10px 15px #22d3ee)', backgroundColor: 'rgba(34, 211, 238, 0.05)' }}
            animate={{ scale: isSpeaking ? [1, 1.05, 1] : 1, y: isSpeaking ? [0, 5, 0] : 0 }}
            transition={{ repeat: Infinity, duration: 0.4 }}
          />
        </motion.div>
      </div>

      {/* SECCIÓN DERECHA: INTERACCIÓN Y AJUSTES */}
      <div className="w-1/2 flex flex-col p-12 relative z-10">
        
        {/* Cabecera de personalización (futura) */}
        <div className="flex justify-end gap-4 mb-20">
          <button className="p-3 bg-white/5 hover:bg-white/10 rounded-2xl border border-white/10 transition-colors">
            <Palette color="#22d3ee" size={24} />
          </button>
          <button className="p-3 bg-white/5 hover:bg-white/10 rounded-2xl border border-white/10 transition-colors">
            <Settings color="#22d3ee" size={24} />
          </button>
        </div>

        {/* Zona de Diálogo */}
        <div className="flex-1 flex flex-col justify-center items-start gap-8">
          <motion.div 
            className="bg-cyan-500/5 backdrop-blur-3xl border border-cyan-500/20 p-10 rounded-[3rem] w-full shadow-2xl"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
          >
            <h2 className="text-cyan-500/50 uppercase tracking-[0.4em] text-xs mb-4 font-bold">Estado del Sistema</h2>
            <p className="text-cyan-300 text-3xl font-light tracking-wide leading-relaxed">
              {status}
            </p>
          </motion.div>

          {/* Respuesta rápida (opcional) */}
          <AnimatePresence>
            {lastResponse && (
              <motion.div 
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                className="text-white/60 text-lg italic pl-6 border-l-2 border-cyan-500/30"
              >
                "{lastResponse.slice(0, 100)}..."
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {/* Botón de Acción Principal */}
        <div className="mt-auto flex justify-center py-6">
          <motion.button
            whileHover={{ scale: 1.1, boxShadow: '0 0 40px rgba(34,211,238,0.3)' }}
            whileTap={{ scale: 0.9 }}
            onClick={startListening}
            className={`flex items-center gap-4 px-12 py-6 rounded-full border-2 transition-all ${
              isListening ? 'bg-red-500/20 border-red-500' : 'bg-cyan-500/10 border-cyan-400/50'
            }`}
          >
            {isListening ? (
              <>
                <MicOff color="#ef4444" size={32} />
                <span className="text-red-500 font-bold uppercase tracking-widest">Detener</span>
              </>
            ) : (
              <>
                <Mic color="#22d3ee" size={32} />
                <span className="text-cyan-400 font-bold uppercase tracking-widest">Escuchar</span>
              </>
            )}
          </motion.button>
        </div>
      </div>

      {/* Partículas de Fondo */}
      <div className="absolute inset-0 z-0 pointer-events-none opacity-5">
        {[...Array(20)].map((_, i) => (
          <motion.div
            key={i}
            className="absolute bg-cyan-400 rounded-full"
            style={{ width: 4, height: 4, left: `${Math.random() * 100}%`, top: `${Math.random() * 100}%` }}
            animate={{ y: [0, -100], opacity: [0, 1, 0] }}
            transition={{ duration: Math.random() * 10 + 5, repeat: Infinity }}
          />
        ))}
      </div>

    </div>
  );
}

export default App;
