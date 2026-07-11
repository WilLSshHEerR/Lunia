import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import axios from 'axios';
import { X, Trash2, Plus, Volume2, Users, LayoutGrid } from 'lucide-react';
import { apiUrl } from './api';

const TABS = [
  { id: 'contactos', label: 'Contactos', icon: Users },
  { id: 'voz', label: 'Voz', icon: Volume2 },
  { id: 'apps', label: 'Apps', icon: LayoutGrid },
];

export default function SettingsPanel({ onClose }) {
  const [tab, setTab] = useState('contactos');

  return (
    <motion.div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm px-4"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      onClick={onClose}
    >
      <motion.div
        className="relative w-full max-w-md bg-[#0f172a] border border-white/10 rounded-2xl p-6 max-h-[85vh] overflow-y-auto"
        initial={{ opacity: 0, y: 20, scale: 0.97 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: 20, scale: 0.97 }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-5">
          <p className="text-cyan-400/70 text-[10px] font-bold tracking-[0.3em] uppercase">Ajustes</p>
          <button
            onClick={onClose}
            className="p-1.5 bg-white/5 hover:bg-white/10 rounded-lg border border-white/10 transition-colors"
          >
            <X size={14} color="#64748b" />
          </button>
        </div>

        <div className="flex gap-2 mb-5">
          {TABS.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => setTab(id)}
              className={`flex-1 flex items-center justify-center gap-1.5 py-2 rounded-xl border text-xs transition-colors ${
                tab === id
                  ? 'bg-cyan-500/20 border-cyan-400/40 text-cyan-300'
                  : 'bg-white/5 border-white/10 text-white/40 hover:bg-white/10'
              }`}
            >
              <Icon size={13} />
              {label}
            </button>
          ))}
        </div>

        {tab === 'contactos' && <ContactosTab />}
        {tab === 'voz' && <VozTab />}
        {tab === 'apps' && <AppsTab />}
      </motion.div>
    </motion.div>
  );
}

function ContactosTab() {
  const [contactos, setContactos] = useState({});
  const [nombre, setNombre] = useState('');
  const [numero, setNumero] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const cargar = async () => {
    try {
      const res = await axios.get(apiUrl('/contactos'));
      setContactos(res.data.contactos || {});
    } catch {
      setError('No se pudieron cargar los contactos');
    }
  };

  useEffect(() => { cargar(); }, []);

  const agregar = async (e) => {
    e.preventDefault();
    setError('');
    if (!nombre.trim() || !numero.trim()) return;
    setLoading(true);
    try {
      await axios.post(apiUrl('/contactos'), { nombre, numero });
      setNombre('');
      setNumero('');
      await cargar();
    } catch (err) {
      setError(err.response?.data?.detail || 'No se pudo guardar el contacto');
    } finally {
      setLoading(false);
    }
  };

  const borrar = async (n) => {
    try {
      await axios.delete(apiUrl(`/contactos/${encodeURIComponent(n)}`));
      await cargar();
    } catch {
      setError('No se pudo borrar el contacto');
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <form onSubmit={agregar} className="flex flex-col gap-2">
        <input
          value={nombre}
          onChange={(e) => setNombre(e.target.value)}
          placeholder="Nombre (ej. Fer)"
          className="bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-sm outline-none focus:border-cyan-400/50 transition-colors placeholder:text-white/20"
        />
        <input
          value={numero}
          onChange={(e) => setNumero(e.target.value)}
          placeholder="Número con código de país (ej. +521234567890)"
          className="bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-sm outline-none focus:border-cyan-400/50 transition-colors placeholder:text-white/20"
        />
        {error && <p className="text-red-400 text-xs">{error}</p>}
        <button
          type="submit"
          disabled={loading}
          className="flex items-center justify-center gap-1.5 bg-cyan-500 hover:bg-cyan-400 text-black font-bold rounded-xl py-2 text-sm transition-colors disabled:opacity-50"
        >
          <Plus size={14} /> {loading ? 'Guardando...' : 'Agregar contacto'}
        </button>
      </form>

      <div className="flex flex-col gap-2 max-h-48 overflow-y-auto">
        {Object.entries(contactos).length === 0 && (
          <p className="text-white/30 text-xs text-center py-2">Sin contactos guardados</p>
        )}
        {Object.entries(contactos).map(([n, num]) => (
          <div key={n} className="flex items-center justify-between bg-white/5 border border-white/10 rounded-xl px-3 py-2">
            <div>
              <p className="text-sm capitalize">{n}</p>
              <p className="text-white/40 text-xs">{num}</p>
            </div>
            <button onClick={() => borrar(n)} className="p-1.5 hover:bg-red-500/20 rounded-lg transition-colors">
              <Trash2 size={13} color="#64748b" />
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}

function VozTab() {
  const [voces, setVoces] = useState([]);
  const [seleccionada, setSeleccionada] = useState(localStorage.getItem('lunia_voice_name') || '');

  useEffect(() => {
    const cargarVoces = () => {
      const disponibles = window.speechSynthesis.getVoices().filter((v) => v.lang.startsWith('es'));
      setVoces(disponibles);
    };
    cargarVoces();
    window.speechSynthesis.onvoiceschanged = cargarVoces;
  }, []);

  const elegir = (nombreVoz) => {
    setSeleccionada(nombreVoz);
    localStorage.setItem('lunia_voice_name', nombreVoz);
    const voice = voces.find((v) => v.name === nombreVoz);
    if (voice) {
      const utterance = new SpeechSynthesisUtterance('Hola, esta es mi voz.');
      utterance.voice = voice;
      window.speechSynthesis.speak(utterance);
    }
  };

  return (
    <div className="flex flex-col gap-2 max-h-72 overflow-y-auto">
      {voces.length === 0 && <p className="text-white/30 text-xs text-center py-2">Cargando voces...</p>}
      {voces.map((v) => (
        <button
          key={v.name}
          onClick={() => elegir(v.name)}
          className={`flex items-center justify-between px-3 py-2 rounded-xl border text-left text-sm transition-colors ${
            seleccionada === v.name
              ? 'bg-cyan-500/20 border-cyan-400/40 text-cyan-300'
              : 'bg-white/5 border-white/10 text-white/70 hover:bg-white/10'
          }`}
        >
          {v.name}
          {seleccionada === v.name && <span className="text-cyan-400 text-xs">Activa</span>}
        </button>
      ))}
    </div>
  );
}

function AppsTab() {
  const [apps, setApps] = useState([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);

  const cargar = async () => {
    try {
      const res = await axios.get(apiUrl('/apps'));
      setApps(res.data.apps || []);
    } catch {
      setError('No se pudieron cargar las apps');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { cargar(); }, []);

  const alternar = async (nombre, habilitada) => {
    setError('');
    setApps((prev) => prev.map((a) => (a.nombre === nombre ? { ...a, habilitada } : a)));
    try {
      await axios.post(apiUrl('/apps/toggle'), { nombre, habilitada });
    } catch {
      setError('No se pudo actualizar la app');
      setApps((prev) => prev.map((a) => (a.nombre === nombre ? { ...a, habilitada: !habilitada } : a)));
    }
  };

  return (
    <div className="flex flex-col gap-3">
      <p className="text-white/40 text-xs">Controla a qué aplicaciones puede acceder Lunia.</p>
      {error && <p className="text-red-400 text-xs">{error}</p>}
      <div className="flex flex-col gap-2 max-h-72 overflow-y-auto">
        {loading && <p className="text-white/30 text-xs text-center py-2">Cargando apps...</p>}
        {!loading && apps.length === 0 && (
          <p className="text-white/30 text-xs text-center py-2">No hay apps registradas todavía</p>
        )}
        {apps.map(({ nombre, habilitada }) => (
          <div key={nombre} className="flex items-center justify-between bg-white/5 border border-white/10 rounded-xl px-3 py-2">
            <p className="text-sm">{nombre}</p>
            <button
              onClick={() => alternar(nombre, !habilitada)}
              className={`relative w-10 h-5 rounded-full transition-colors ${habilitada ? 'bg-cyan-500' : 'bg-white/10'}`}
              title={habilitada ? 'Deshabilitar' : 'Habilitar'}
            >
              <span
                className={`absolute top-0.5 w-4 h-4 bg-white rounded-full transition-transform ${habilitada ? 'translate-x-[22px]' : 'translate-x-0.5'}`}
              />
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
