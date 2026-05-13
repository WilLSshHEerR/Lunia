import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import axios from 'axios';
import { apiUrl } from './api';

export default function LoginPage({ onLogin }) {
  const [step, setStep] = useState('credentials'); // 'credentials' | '2fa'
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [code, setCode] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleCredentials = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await axios.post(apiUrl('/login'), { username, password });
      setStep('2fa');
    } catch (err) {
      const msg = err.response?.data?.detail || 'Error de conexión';
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  const handle2FA = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const res = await axios.post(apiUrl('/verify_2fa'), { username, code });
      const { access_token, refresh_token } = res.data;
      sessionStorage.setItem('lunia_refresh', refresh_token);
      onLogin(access_token);
    } catch (err) {
      const msg = err.response?.data?.detail || 'Código incorrecto';
      setError(msg);
      setCode('');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-[#0f172a] to-[#020617] flex items-center justify-center font-sans text-white">

      {/* Fondo de partículas */}
      <div className="absolute inset-0 pointer-events-none opacity-10">
        {[...Array(12)].map((_, i) => (
          <motion.div
            key={i}
            className="absolute bg-cyan-400 rounded-full"
            style={{ width: 2, height: 2, left: `${Math.random() * 100}%`, top: `${Math.random() * 100}%` }}
            animate={{ y: [0, -80], opacity: [0, 1, 0] }}
            transition={{ duration: Math.random() * 8 + 4, repeat: Infinity, delay: Math.random() * 4 }}
          />
        ))}
      </div>

      <motion.div
        className="relative z-10 w-full max-w-sm px-6"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6 }}
      >
        {/* Logo / cara simplificada */}
        <div className="flex flex-col items-center mb-10">
          <div className="flex gap-5 mb-5">
            {[0, 0.08].map((delay, i) => (
              <motion.div
                key={i}
                className="w-3 h-16 bg-cyan-400 rounded-full"
                style={{ boxShadow: '0 0 20px #22d3ee' }}
                animate={{ scaleY: [1, 0.1, 1] }}
                transition={{ repeat: Infinity, duration: 4, delay: 2 + delay }}
              />
            ))}
          </div>
          <motion.div
            className="w-24 h-4 border-b-[3px] border-cyan-400 rounded-b-full"
            style={{ filter: 'drop-shadow(0 6px 10px #22d3ee)' }}
          />
          <p className="mt-5 text-cyan-400/60 text-[10px] tracking-[0.4em] uppercase font-bold">Lunia</p>
        </div>

        {/* Card */}
        <div className="bg-white/5 border border-white/10 rounded-2xl p-6 backdrop-blur-sm">

          <AnimatePresence mode="wait">

            {step === 'credentials' && (
              <motion.form
                key="credentials"
                onSubmit={handleCredentials}
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: 20 }}
                className="flex flex-col gap-4"
              >
                <p className="text-white/40 text-xs uppercase tracking-widest mb-1">Acceso</p>

                <input
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="Usuario"
                  autoComplete="username"
                  required
                  className="bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-sm outline-none focus:border-cyan-400/50 transition-colors placeholder:text-white/20"
                />
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Contraseña"
                  autoComplete="current-password"
                  required
                  className="bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-sm outline-none focus:border-cyan-400/50 transition-colors placeholder:text-white/20"
                />

                {error && (
                  <motion.p
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    className="text-red-400 text-xs text-center"
                  >
                    {error}
                  </motion.p>
                )}

                <motion.button
                  whileTap={{ scale: 0.97 }}
                  type="submit"
                  disabled={loading}
                  className="mt-1 bg-cyan-500 hover:bg-cyan-400 text-black font-bold rounded-xl py-3 text-sm transition-colors disabled:opacity-50"
                >
                  {loading ? 'Verificando...' : 'Entrar'}
                </motion.button>
              </motion.form>
            )}

            {step === '2fa' && (
              <motion.form
                key="2fa"
                onSubmit={handle2FA}
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -20 }}
                className="flex flex-col gap-4"
              >
                <p className="text-white/40 text-xs uppercase tracking-widest mb-1">Verificación</p>
                <p className="text-white/60 text-sm">
                  Abre Google Authenticator e ingresa el código de 6 dígitos.
                </p>

                <input
                  type="text"
                  value={code}
                  onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                  placeholder="000000"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  maxLength={6}
                  required
                  autoFocus
                  className="bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-sm outline-none focus:border-cyan-400/50 transition-colors placeholder:text-white/20 text-center tracking-[0.5em] text-lg"
                />

                {error && (
                  <motion.p
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    className="text-red-400 text-xs text-center"
                  >
                    {error}
                  </motion.p>
                )}

                <motion.button
                  whileTap={{ scale: 0.97 }}
                  type="submit"
                  disabled={loading || code.length < 6}
                  className="mt-1 bg-cyan-500 hover:bg-cyan-400 text-black font-bold rounded-xl py-3 text-sm transition-colors disabled:opacity-50"
                >
                  {loading ? 'Verificando...' : 'Confirmar'}
                </motion.button>

                <button
                  type="button"
                  onClick={() => { setStep('credentials'); setError(''); setCode(''); }}
                  className="text-white/30 hover:text-white/50 text-xs transition-colors"
                >
                  ← Volver
                </button>
              </motion.form>
            )}

          </AnimatePresence>
        </div>
      </motion.div>
    </div>
  );
}
