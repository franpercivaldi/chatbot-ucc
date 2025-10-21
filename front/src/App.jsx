import React from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider } from "@/auth/AuthContext";
import ProtectedRoute from "@/auth/ProtectedRoute";

import Chat from "@/Chat";
import Login from "@/pages/Login";
import Dashboard from "@/pages/Dashboard";

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/" element={<Chat />} />
        <Route path="/login" element={<Login />} />
        <Route
          path="/admin"
          element={
            <ProtectedRoute allow={["admin", "staff"]}>
              <Dashboard />
            </ProtectedRoute>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AuthProvider>
  );
}
