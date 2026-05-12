import React, { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import axios from 'axios';
import { Mic, MicOff, Settings, Palette, Send, MessageSquare } from 'lucide-react';

const API_URL = "http://localhost:8000/ask";

function App() {
  const [isListening, setIsListening] = useState(false);
  const [isActiveListening, setIsActiveListening] = useState(true);
  const [status, setStatus] = useState("Lunia en espera (Di 'Lunia')...");
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [lastResponse, setLastResponse] = useState("");
  const [chatInput, setChatInput] = useState("");
  const [messages, setMessages] = useState([]);

  const recognitionRef = useRef(null);
  const wakeWordRecognitionRef = useRef(null);
  const chatEndRef = useRef(null);

  useEffect(() => {
    if (!('webkitSpeechRecognition' in window || 'SpeechRecognition' in window)) return;

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

    // Reconocimiento para comandos manuales (el que ya existía)
    const recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.lang = 'es-ES';

    recognition.onstart = () => {
      setIsListening(true);
      setStatus("Escuchando comando...");
    };

    recognition.onresult = async (event) => {
      const text = event.results[0][0].transcript;
      setIsListening(false);
      setStatus(`Procesando: "${text}"`);
      await sendToLunia(text);
    };

    recognition.onerror = () => {
      setIsListening(false);
      setStatus("No te escuché bien...");
    };

    recognition.onend = () => {
      setIsListening(false);
      // Al terminar el manual, volvemos a activar el de palabra clave si está habilitado
      if (isActiveListening) startWakeWordDetection();
    };

    recognitionRef.current = recognition;

    // Reconocimiento de Palabra Clave (Lunia)
    const wakeWordRecognition = new SpeechRecognition();
    wakeWordRecognition.continuous = true;
    wakeWordRecognition.interimResults = true;
    wakeWordRecognition.lang = 'es-ES';

    wakeWordRecognition.onresult = async (event) => {
      for (let i = event.resultIndex; i < event.results.length; ++i) {
        if (event.results[i].isFinal) {
          const transcript = event.results[i][0].transcript.toLowerCase();
          console.log("Voz detectada:", transcript);

          if (transcript.includes("lunia")) {
            // Detener el de palabra clave momentáneamente para procesar
            wakeWordRecognition.stop();

            // Extraer el comando después de "Lunia"
            const parts = transcript.split("lunia");
            const command = parts[parts.length - 1].trim();

            if (command) {
              setStatus(`Lunia detectado: "${command}"`);
              await sendToLunia(command);
            } else {
              setStatus("¿Dime? Te escucho...");
              // Si solo dijo "Lunia", activamos el reconocimiento normal de un solo tiro
              startListening();
            }
          }
        }
      }
    };

    wakeWordRecognition.onend = () => {
      // Reiniciar automáticamente si sigue en modo activo y no estamos en escucha manual o hablando
      if (isActiveListening && !isListening && !isSpeaking) {
        try { wakeWordRecognition.start(); } catch (e) { }
      }
    };

    wakeWordRecognitionRef.current = wakeWordRecognition;

    if (isActiveListening) {
      startWakeWordDetection();
    }

    return () => {
      if (wakeWordRecognitionRef.current) wakeWordRecognitionRef.current.stop();
      if (recognitionRef.current) recognitionRef.current.stop();
    };
  }, [isActiveListening]);

  const startWakeWordDetection = () => {
    if (wakeWordRecognitionRef.current && !isListening) {
      try {
        wakeWordRecognitionRef.current.start();
        setStatus("Escucha activa: Di 'Lunia'...");
      } catch (e) {
        // Ya estaba corriendo
      }
    }
  };

  const toggleActiveListening = () => {
    if (isActiveListening) {
      if (wakeWordRecognitionRef.current) wakeWordRecognitionRef.current.stop();
      setIsActiveListening(false);
      setStatus("Escucha activa desactivada");
    } else {
      setIsActiveListening(true);
      // El useEffect se encargará de iniciarlo
    }
  };

  const startListening = () => {
    if (wakeWordRecognitionRef.current) wakeWordRecognitionRef.current.stop();
    if (recognitionRef.current) {
      try {
        recognitionRef.current.start();
      } catch (e) { }
    }
  };

  const [voiceIndex, setVoiceIndex] = useState(0);

  const speak = (text) => {
    if ('speechSynthesis' in window) {
      window.speechSynthesis.cancel();

      const cleanText = text.replace(/\[Acción:.*?\]/g, "");
      const utterance = new SpeechSynthesisUtterance(cleanText);

      const loadVoices = () => {
        const voices = window.speechSynthesis.getVoices().filter(v => v.lang.startsWith('es'));

        if (voices.length > 0) {
          // Prioridad absoluta a Marisol
          const marisol = voices.find(v => v.name.includes('Marisol'));
          const selectedVoice = marisol || voices[voiceIndex % voices.length];

          utterance.voice = selectedVoice;
          setStatus(`Lunia responde (Voz: ${selectedVoice.name})`);
        }

        utterance.lang = 'es-ES';
        utterance.rate = 1.0;
        utterance.pitch = 1.0;

        utterance.onstart = () => setIsSpeaking(true);
        utterance.onend = () => {
          setIsSpeaking(false);
          if (isActiveListening) startWakeWordDetection();
        };

        window.speechSynthesis.speak(utterance);
      };

      if (window.speechSynthesis.getVoices().length !== 0) {
        loadVoices();
      } else {
        window.speechSynthesis.onvoiceschanged = loadVoices;
      }

    }
  };

  const cycleVoice = () => {
    const voices = window.speechSynthesis.getVoices().filter(v => v.lang.startsWith('es'));
    if (voices.length > 0) {
      const nextIndex = (voiceIndex + 1) % voices.length;
      setVoiceIndex(nextIndex);
      const nextVoice = voices[nextIndex];
      setStatus(`Voz cambiada a: ${nextVoice.name}`);

      // Probar la voz inmediatamente
      const testUtterance = new SpeechSynthesisUtterance("Hola, esta es mi nueva voz.");
      testUtterance.voice = nextVoice;
      window.speechSynthesis.speak(testUtterance);
    }
  };

  const sendToLunia = async (text) => {
    if (!text.trim()) return;
    setMessages(prev => [...prev, { from: 'user', text }]);
    try {
      const response = await axios.post(API_URL, { text });
      const luniaSays = response.data.lunia_says;
      setLastResponse(luniaSays);
      setStatus("Lunia responde");
      setMessages(prev => [...prev, { from: 'lunia', text: luniaSays }]);
      speak(luniaSays);
    } catch (error) {
      setStatus("Error de conexión");
      setMessages(prev => [...prev, { from: 'lunia', text: "No pude conectarme al servidor." }]);
    }
    setTimeout(() => chatEndRef.current?.scrollIntoView({ behavior: 'smooth' }), 100);
  };

  const handleChatSubmit = (e) => {
    e.preventDefault();
    if (chatInput.trim()) {
      setStatus("Procesando...");
      sendToLunia(chatInput);
      setChatInput("");
    }
  };

  return (
    <div className="min-h-screen bg-[#020617] bg-gradient-to-br from-[#0f172a] to-[#020617] flex overflow-hidden font-sans text-white">

      {/* SECCIÓN IZQUIERDA: EL ROSTRO (Se mantiene igual de Premium) */}
      <div className="w-full md:w-1/2 flex flex-col items-center justify-center md:border-r border-white/5 relative bg-black/20">
        <motion.div
          className="flex flex-col items-center gap-10 md:gap-16"
          initial={{ opacity: 0, x: -50 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.8 }}
        >
          {/* Ojos */}
          <div className="flex gap-8 md:gap-10">
            <div className="flex flex-col items-center gap-2 md:gap-6">
              <motion.div
                className="w-9 h-5 md:w-14 md:h-6 border-t-[3px] border-x-[2px] border-cyan-400 rounded-t-full"
                style={{ filter: 'drop-shadow(0 -3px 8px #22d3ee)' }}
                animate={{ y: isSpeaking ? [0, -3, 0] : 0 }}
                transition={{ repeat: Infinity, duration: 0.5 }}
              />
              <motion.div
                className="w-7 h-24 md:w-10 md:h-36 bg-cyan-400 rounded-full"
                style={{ boxShadow: '0 0 35px #22d3ee, 0 0 60px rgba(34,211,238,0.3)' }}
                animate={{ scaleY: isListening ? [1, 1.1, 1] : [1, 0.08, 1] }}
                transition={{ repeat: Infinity, duration: isListening ? 0.6 : 5, delay: isListening ? 0 : 3 }}
              />
            </div>
            <div className="flex flex-col items-center gap-2 md:gap-6">
              <motion.div
                className="w-9 h-5 md:w-14 md:h-6 border-t-[3px] border-x-[2px] border-cyan-400 rounded-t-full"
                style={{ filter: 'drop-shadow(0 -3px 8px #22d3ee)' }}
                animate={{ y: isSpeaking ? [0, -3, 0] : 0 }}
                transition={{ repeat: Infinity, duration: 0.5, delay: 0.05 }}
              />
              <motion.div
                className="w-7 h-24 md:w-10 md:h-36 bg-cyan-400 rounded-full"
                style={{ boxShadow: '0 0 35px #22d3ee, 0 0 60px rgba(34,211,238,0.3)' }}
                animate={{ scaleY: isListening ? [1, 1.1, 1] : [1, 0.08, 1] }}
                transition={{ repeat: Infinity, duration: isListening ? 0.6 : 5, delay: isListening ? 0.1 : 3 }}
              />
            </div>
          </div>

          {/* Boca */}
          <motion.div
            className="w-44 h-8 md:w-64 md:h-10 border-b-[4px] md:border-b-[5px] border-cyan-400 rounded-b-full"
            style={{ filter: 'drop-shadow(0 8px 14px #22d3ee)' }}
            animate={isSpeaking ? {
              scaleY: [1, 2.2, 0.5, 1.8, 0.3, 1.5, 0.8, 1],
              scaleX: [1, 1.08, 0.96, 1.05, 0.98, 1.03, 1],
            } : { scaleY: 1, scaleX: 1 }}
            transition={{ repeat: isSpeaking ? Infinity : 0, duration: 0.45, ease: "easeInOut" }}
          />
        </motion.div>
      </div>

      {/* SECCIÓN DERECHA */}
      <div className="hidden md:flex w-1/2 flex-col h-screen p-6 relative z-10">

        {/* HEADER */}
        <div className="flex justify-between items-center py-3 border-b border-white/5 mb-6">
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 bg-cyan-400 rounded-full animate-pulse shadow-[0_0_8px_#22d3ee]" />
            <span className="text-cyan-400/70 text-[10px] font-bold tracking-[0.3em] uppercase">Lunia</span>
          </div>
          <div className="flex gap-2">
            <button
              onClick={toggleActiveListening}
              className={`p-1.5 rounded-lg border border-white/10 transition-colors ${isActiveListening ? 'bg-cyan-500/20' : 'bg-white/5 hover:bg-white/10'}`}
              title={isActiveListening ? "Desactivar escucha activa" : "Activar escucha activa"}
            >
              <Mic size={14} color={isActiveListening ? "#22d3ee" : "#64748b"} className={isActiveListening ? "animate-pulse" : ""} />
            </button>
            <button className="p-1.5 bg-white/5 hover:bg-white/10 rounded-lg border border-white/10 transition-colors">
              <Settings color="#22d3ee" size={14} />
            </button>
          </div>
        </div>

        {/* ESTADO */}
        <AnimatePresence mode="wait">
          <motion.p
            key={status}
            initial={{ opacity: 0, y: -6 }}
            animate={{ opacity: 0.4, y: 0 }}
            exit={{ opacity: 0, y: 6 }}
            className="text-cyan-400 text-[10px] uppercase tracking-[0.5em] font-bold mb-4"
          >
            {status}
          </motion.p>
        </AnimatePresence>

        {/* ZONA SUPERIOR — espacio para futuras secciones */}
        <div className="flex-1 border border-white/5 rounded-2xl mb-4" />

        {/* ZONA INFERIOR — CHAT */}
        <div className="h-[45%] flex flex-col border-t border-white/5 pt-4">

          {/* Historial de mensajes */}
          <div className="flex-1 overflow-y-auto flex flex-col gap-2 pr-1 mb-3">
            <AnimatePresence>
              {messages.map((msg, i) => (
                <motion.div
                  key={i}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  className={`flex ${msg.from === 'user' ? 'justify-end' : 'justify-start'}`}
                >
                  <div className={`max-w-[80%] px-4 py-2.5 rounded-2xl text-sm leading-relaxed ${
                    msg.from === 'user'
                      ? 'bg-cyan-500/20 border border-cyan-400/30 text-cyan-100'
                      : 'bg-white/5 border border-white/10 text-white/80 italic'
                  }`}>
                    {msg.text}
                  </div>
                </motion.div>
              ))}
            </AnimatePresence>
            <div ref={chatEndRef} />
          </div>

          {/* Input */}
          <form
            onSubmit={handleChatSubmit}
            className="bg-white/5 border border-white/10 rounded-2xl flex items-center gap-2 px-4 py-2"
          >
            <input
              type="text"
              value={chatInput}
              onChange={(e) => setChatInput(e.target.value)}
              placeholder="Escribe a Lunia..."
              className="flex-1 bg-transparent outline-none py-2 text-sm placeholder:text-white/20"
            />
            <motion.button
              whileTap={{ scale: 0.9 }}
              type="submit"
              className="p-2 bg-cyan-500 text-black rounded-xl hover:bg-cyan-400 transition-colors"
            >
              <Send size={14} />
            </motion.button>
            <motion.button
              whileTap={{ scale: 0.9 }}
              type="button"
              onClick={startListening}
              className={`p-2 rounded-xl border transition-colors ${isListening ? 'bg-red-500/20 border-red-500' : 'bg-white/5 border-white/10 hover:bg-white/10'}`}
            >
              {isListening ? <MicOff size={14} color="#ef4444" /> : <Mic size={14} color="#22d3ee" />}
            </motion.button>
          </form>

        </div>
      </div>

      {/* Partículas de Fondo Estéticas */}
      <div className="absolute inset-0 z-0 pointer-events-none opacity-10">
        {[...Array(15)].map((_, i) => (
          <motion.div
            key={i}
            className="absolute bg-cyan-400 rounded-full"
            style={{ width: 2, height: 2, left: `${Math.random() * 100}%`, top: `${Math.random() * 100}%` }}
            animate={{ y: [0, -100], opacity: [0, 1, 0] }}
            transition={{ duration: Math.random() * 10 + 5, repeat: Infinity }}
          />
        ))}
      </div>

    </div>
  );
}

export default App;
