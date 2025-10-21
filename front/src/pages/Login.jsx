import React, { useState } from "react";
import { useAuth } from "@/auth/AuthContext";
import { useLocation, useNavigate } from "react-router-dom";

export default function Login() {
  const { login } = useAuth();
  const nav = useNavigate();
  const loc = useLocation();
  const [username, setU] = useState("");
  const [password, setP] = useState("");
  const [err, setErr] = useState("");

  const from = loc.state?.from || "/admin";

  const submit = async (e) => {
    e.preventDefault();
    setErr("");
    try {
      await login({ username, password });
      nav(from, { replace: true });
    } catch (e) {
      setErr("Credenciales inválidas");
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50">
      <form onSubmit={submit} className="w-full max-w-sm bg-white p-6 rounded-xl shadow">
        <h1 className="text-xl font-semibold mb-4">Ingreso</h1>
        <label className="block text-sm mb-1">Usuario</label>
        <input
          className="w-full rounded-md border p-2 mb-3"
          value={username}
          onChange={(e) => setU(e.target.value)}
          placeholder="usuario"
        />
        <label className="block text-sm mb-1">Contraseña</label>
        <input
          type="password"
          className="w-full rounded-md border p-2 mb-3"
          value={password}
          onChange={(e) => setP(e.target.value)}
          placeholder="••••••••"
        />
        {err && <p className="text-red-600 text-sm mb-2">{err}</p>}
        <button
          type="submit"
          className="w-full rounded-md bg-indigo-600 text-white py-2 hover:bg-indigo-700"
        >
          Entrar
        </button>
        <p className="text-xs text-slate-500 mt-3">
          *En V1 este login es local (mock). En V2 se conectará al backend.
        </p>
      </form>
    </div>
  );
}
