import React from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "./AuthContext";

export default function ProtectedRoute({ children, allow = ["admin", "staff"] }) {
  const { user, loading } = useAuth();
  const loc = useLocation();

  if (loading) return null; // o spinner global

  if (!user) {
    return <Navigate to="/login" replace state={{ from: loc.pathname }} />;
  }
  if (allow.length && !allow.includes(user.role)) {
    return <Navigate to="/" replace />;
  }
  return children;
}
