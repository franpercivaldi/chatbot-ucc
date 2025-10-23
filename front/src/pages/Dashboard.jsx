import React, { useEffect, useMemo, useState } from "react";
import { apiGet } from "@/lib/api";
import { useAuth } from "@/auth/AuthContext";

function Pill({ children, tone = "indigo" }) {
  const tones = {
    indigo: "bg-indigo-50 text-indigo-700 ring-indigo-200",
    sky: "bg-sky-50 text-sky-700 ring-sky-200",
    slate: "bg-slate-100 text-slate-700 ring-slate-200",
  };
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium ring-1 ${tones[tone]}`}>
      {children}
    </span>
  );
}

function Card({ title, children, right }) {
  return (
    <section className="rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div className="flex items-center justify-between px-4 py-3 border-b border-slate-100">
        <h2 className="text-sm font-semibold text-slate-700">{title}</h2>
        {right}
      </div>
      <div className="p-4">{children}</div>
    </section>
  );
}

function SkeletonRows({ rows = 5, cols = 4 }) {
  return (
    <tbody className="divide-y divide-slate-100">
      {Array.from({ length: rows }).map((_, i) => (
        <tr key={i} className="animate-pulse">
          {Array.from({ length: cols }).map((__, j) => (
            <td key={j} className="py-3">
              <div className="h-3 w-28 rounded bg-slate-100" />
            </td>
          ))}
        </tr>
      ))}
    </tbody>
  );
}

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

  const successRate = useMemo(() => {
    if (!daily.length) return null;
    const ok = daily.reduce((acc, d) => acc + (d.success || 0), 0);
    const total = daily.reduce((acc, d) => acc + (d.total || 0), 0);
    return total ? Math.round((ok / total) * 100) : null;
  }, [daily]);

  return (
    <div className="min-h-screen w-screen bg-slate-50">
      {/* Header sticky */}
      <header className="sticky top-0 z-10 backdrop-blur bg-slate-50/75 w-full">
        <div className="w-full px-4 py-4">
          <div className="flex items-center gap-3">
            <h1 className="text-3xl md:text-4xl font-extrabold tracking-tight text-sky-600">Dashboard</h1>
            <Pill tone="sky">{botId.replace("-", " ")}</Pill>
            {successRate !== null && (
              <Pill tone="slate">Éxito {successRate}%</Pill>
            )}
          </div>
          <div className="flex items-center gap-3">
            <Pill>{user?.name} ({user?.role})</Pill>
            <button
              className="rounded-xl bg-slate-900 text-white px-3 py-1.5 text-sm shadow hover:bg-slate-800"
              onClick={logout}
            >
              Salir
            </button>
          </div>
        </div>
        <div className="container mx-auto px-4 pb-3">
          <div className="inline-flex items-center gap-2">
            <label className="text-xs text-slate-500">Bot:</label>
            <select
              className="rounded-md border border-slate-300 bg-white px-2 py-1 text-slate-500"
              value={botId}
              onChange={(e) => setBotId(e.target.value)}
            >
              <option value="public-admisiones">public-admisiones</option>
              <option value="interna-secretarias">interna-secretarias</option>
            </select>
          </div>
        </div>
      </header>

      <main className="w-full p-4 space-y-6">
        {/* Top carreras */}
        <Card title="Top carreras (90 días)">
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm text-slate-800">
              <thead className="bg-slate-50 text-slate-500">
                <tr>
                  <th className="py-2 pr-4 font-medium text-left">Carrera</th>
                  <th className="py-2 pr-4 font-medium text-left">Periodo</th>
                  <th className="py-2 pr-4 font-medium text-left">Consultas</th>
                  <th className="py-2 pr-0 font-medium text-left">Con aranceles</th>
                </tr>
              </thead>

              {loading ? (
                <SkeletonRows rows={5} cols={4} />
              ) : (
                <tbody className="divide-y divide-slate-100">
                  {topCarreras.map((r, i) => (
                    <tr key={i} className="hover:bg-slate-50/60">
                      <td className="py-2 pr-4">{r.carrera}</td>
                      <td className="py-2 pr-4">{r.periodo || "-"}</td>
                      <td className="py-2 pr-4 tabular-nums">{r.consultas}</td>
                      <td className="py-2 pr-0 tabular-nums">{r.con_aranceles}</td>
                    </tr>
                  ))}
                  {!topCarreras.length && (
                    <tr>
                      <td colSpan={4} className="text-slate-500 py-6 text-center">Sin datos</td>
                    </tr>
                  )}
                </tbody>
              )}
            </table>
          </div>
        </Card>

        {/* Dominios usados */}
        <Card title="Dominios usados (90 días)">
          {loading ? (
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
              {Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className="h-8 rounded-lg bg-slate-100 animate-pulse" />
              ))}
            </div>
          ) : dominios.length ? (
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
              {dominios.map((d, i) => (
                <div key={i} className="flex items-center justify-between rounded-lg border border-slate-200 px-3 py-2">
                  <span className="text-slate-700">{d.domain}</span>
                  <span className="text-slate-900 font-semibold tabular-nums">{d.usos}</span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-slate-500">Sin datos</p>
          )}
        </Card>

        {/* Unanswered */}
        <Card title="Consultas sin respuesta (30 días)" right={
          <span className="text-xs text-slate-500">{errors.length} casos</span>
        }>
          {loading ? (
            <div className="space-y-3">
              {Array.from({ length: 3 }).map((_, i) => (
                <div key={i} className="h-16 rounded-lg bg-slate-100 animate-pulse" />
              ))}
            </div>
          ) : errors.length ? (
            <div className="space-y-2">
              {errors.map((e, i) => (
                <div key={i} className="border border-slate-200 rounded-lg p-3">
                  <div className="text-[11px] text-slate-500">
                    {e.ts ? new Date(e.ts * 1000).toLocaleString() : ""}
                  </div>
                  <div className="text-sm font-medium text-slate-800">{e.user_query}</div>
                  {e.answer_short && (
                    <div className="text-xs text-slate-500">{e.answer_short}</div>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-slate-500">Sin pendientes 🎉</p>
          )}
        </Card>
      </main>
    </div>
  );
}
