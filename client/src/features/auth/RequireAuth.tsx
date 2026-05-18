// Gate route subtrees behind a logged-in user.

import { Navigate, useLocation } from "react-router-dom";
import { Box, CircularProgress } from "@mui/material";
import type { ReactNode } from "react";

import { useAuth } from "./AuthContext";

export default function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <Box
        sx={{
          height: "100vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <CircularProgress />
      </Box>
    );
  }

  if (!user) {
    // Preserve the path the user wanted so we can bounce them back post-login.
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  return <>{children}</>;
}
