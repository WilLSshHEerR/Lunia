import React, { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import axios from 'axios';
import { Sparkles, Check } from 'lucide-react';
import { apiUrl } from './api';

export default function ModePicker() {
  const [open, setOpen] = useState(false);
  const [modos, setModos] = useState([]);
  const [modoActual, setModoActual] = useState('normal');
  const [loading, setLoading] = useState(false);
  const ref = useRef(null);

  const cargar = async () => {
    try {
      const res = await axios.get(apiUrl('/modo'));
      setModos(res.data.modos || []);
      setModoActual(res.data.modo_actual || 'normal');
    } catch {
      // silencioso: si falla, el menú simplemente no mostrará opciones
    }
  };

  useEffect(() => { if (open) cargar(); }, [open]);

  useEffect(() => {
    const onClickOutside = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener('mousedown', onClickOutside);
    return () => document.removeEventListener('mousedown', onClickOutside);
  }, []);

  const elegir = async (modoId) => {
    if (modoId === modoActual || loading) return;
    setLoading(true);
    try {
      await axios.post(apiUrl('/modo'), { modo: modoId });
      setModoActual(modoId);
      setOpen(false);
    } catch {
      // deja el menú abierto para reintentar
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((v) => !v)}
        className={`p-1.5 rounded-lg border border-white/10 transition-colors ${open ? 'bg-cyan-500/20' : 'bg-white/5 hover:bg-white/10'}`}
        title="Modos de Lunia"
      >
        <Sparkles size={14} color="#22d3ee" />
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -6, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -6, scale: 0.97 }}
            transition={{ duration: 0.15 }}
            className="absolute right-0 mt-2 w-40 bg-[#0f172a] border border-white/10 rounded-xl p-1.5 z-50 shadow-xl"
          >
            {modos.length === 0 && (
              <p className="text-white/30 text-xs text-center py-2">Cargando...</p>
            )}
            {modos.map(({ id, label }) => (
              <button
                key={id}
                onClick={() => elegir(id)}
                disabled={loading}
                className={`w-full flex items-center justify-between gap-2 px-3 py-2 rounded-lg text-xs text-left transition-colors disabled:opacity-50 ${
                  id === modoActual
                    ? 'bg-cyan-500/20 text-cyan-300'
                    : 'text-white/60 hover:bg-white/10'
                }`}
              >
                {label}
                {id === modoActual && <Check size={12} />}
              </button>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
