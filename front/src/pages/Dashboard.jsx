import React, { useEffect, useState } from "react";
import { apiGet } from "@/lib/api";
import { useAuth } from "@/auth/AuthContext";

export default function Dashboard() {
  const { user, logout } = useAuth();
  const [botId, setBotId] = useState("public-admisiones");
  const [loading, setLoading] = useState(false);
  const [topCarreras, setTopCarreras] = useState([]);
  const [dominios, setDominios] = useState([]);
  const [daily, setDaily] = useState([]);
  const [errors, setErrors] = useState([]);

  const fetchAll = async () => {
    try {
      setLoading(true);
      const [c, d, dl, ua] = await Promise.all([
        apiGet(`/admin/metrics/top-carreras?bot_id=${encodeURIComponent(botId)}&days=90&limit=10`),
        apiGet(`/admin/metrics/dominios?bot_id=${encodeURIComponent(botId)}&days=90`),
        apiGet(`/admin/metrics/daily?bot_id=${encodeURIComponent(botId)}&days=30`),
        apiGet(`/admin/metrics/unanswered?bot_id=${encodeURIComponent(botId)}&days=30&limit=20`),
      ]);
      setTopCarreras(c.items || []);
      setDominios(d.items || []);
      setDaily(dl.items || []);
      setErrors(ua.items || []);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchAll(); /* eslint-disable-next-line */ }, [botId]);

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="flex items-center justify-between p-4 bg-white border-b">
        <div className="flex items-center gap-3">
          <h1 className="text-lg font-semibold">Dashboard</h1>
          <select
            className="rounded-md border p-1"
            value={botId}
            onChange={(e) => setBotId(e.target.value)}
          >
            <option value="public-admisiones">public-admisiones</option>
            <option value="interna-secretarias">interna-secretarias</option>
          </select>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-sm text-slate-600">{user?.name} ({user?.role})</span>
          <button className="text-sm text-indigo-600" onClick={logout}>Salir</button>
        </div>
      </header>

      <main className="max-w-5xl mx-auto p-4 space-y-6">
        {loading && <p className="text-sm text-slate-500">Cargando…</p>}

        <section className="bg-white rounded-xl border p-4">
          <h2 className="font-medium mb-2">Top carreras (90 días)</h2>
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="text-left text-slate-500">
                  <th className="py-2 pr-4">Carrera</th>
                  <th className="py-2 pr-4">Periodo</th>
                  <th className="py-2 pr-4">Consultas</th>
                  <th className="py-2 pr-4">Con aranceles</th>
                </tr>
              </thead>
              <tbody>
                {topCarreras.map((r, i) => (
                  <tr key={i} className="border-t">
                    <td className="py-2 pr-4">{r.carrera}</td>
                    <td className="py-2 pr-4">{r.periodo || "-"}</td>
                    <td className="py-2 pr-4">{r.consultas}</td>
                    <td className="py-2 pr-4">{r.con_aranceles}</td>
                  </tr>
                ))}
                {!topCarreras.length && (
                  <tr><td colSpan={4} className="text-slate-500 py-6">Sin datos</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </section>

        <section className="bg-white rounded-xl border p-4">
          <h2 className="font-medium mb-2">Dominios usados (90 días)</h2>
          <ul className="text-sm list-disc pl-6">
            {dominios.map((d, i) => (
              <li key={i}>{d.domain}: <span className="font-medium">{d.usos}</span></li>
            ))}
            {!dominios.length && <li className="text-slate-500">Sin datos</li>}
          </ul>
        </section>

        <section className="bg-white rounded-xl border p-4">
          <h2 className="font-medium mb-2">Consultas sin respuesta (30 días)</h2>
          <div className="space-y-2">
            {errors.map((e, i) => (
              <div key={i} className="border rounded-lg p-3">
                <div className="text-xs text-slate-500">{new Date(e.ts*1000).toLocaleString?.() || ""}</div>
                <div className="text-sm font-medium">{e.user_query}</div>
                <div className="text-xs text-slate-500">{e.answer_short}</div>
              </div>
            ))}
            {!errors.length && <p className="text-slate-500 text-sm">Sin pendientes 🎉</p>}
          </div>
        </section>
      </main>
    </div>
  );
}
