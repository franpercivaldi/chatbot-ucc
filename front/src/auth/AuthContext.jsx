import React, { createContext, useContext, useEffect, useState } from "react";
import { setToken, getToken } from "@/lib/api";

// Roles ejemplo: "admin", "staff", "viewer"
const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null); // {name, role, token}
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // restaurar sesión si hay token guardado (opcionalmente validar contra /auth/me)
    const token = getToken();
    if (token) {
      // Para V1 simple: asumimos rol "admin" si hay token.
      setUser({ name: "usuario", role: "admin", token });
    }
    setLoading(false);
  }, []);

  const login = async ({ username, password }) => {
    // V1: mock local; V2: llamar /auth/login en el back y recibir {token, role}
    // const resp = await apiPost("/auth/login", { username, password });
    // setToken(resp.token); setUser({ name: username, role: resp.role, token: resp.token });

    // MOCK login local (mientras el back no está):
    if (!username || !password) throw new Error("Credenciales requeridas");
    const fakeToken = btoa(`${username}:${Date.now()}`);
    const role = username === "admin" ? "admin" : "staff";
    setToken(fakeToken);
    setUser({ name: username, role, token: fakeToken });
  };

  const logout = () => {
    setToken("");
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
