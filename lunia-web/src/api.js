// En desarrollo web: VITE_API_BASE está vacío → usa el proxy de Vite (/api/*)
// En mobile (Capacitor): VITE_API_BASE apunta al ngrok o IP local del servidor
const BASE = import.meta.env.VITE_API_BASE || '';

export function apiUrl(path) {
  return BASE ? `${BASE}${path}` : `/api${path}`;
}
