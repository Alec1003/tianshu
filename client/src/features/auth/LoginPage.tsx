// Email/password login page.
//
// Uses MUI primitives only so we don't drag in another form library. The
// post-login redirect target comes from RequireAuth's saved `from` location,
// falling back to /scenarios.

import { useState, type FormEvent } from "react";
import { Link as RouterLink, useLocation, useNavigate } from "react-router-dom";
import {
  Alert,
  Box,
  Button,
  Container,
  Link,
  Paper,
  Stack,
  TextField,
  Typography,
} from "@mui/material";

import { ApiError } from "@/api/client";
import { useAuth } from "./AuthContext";

type LocationState = { from?: { pathname?: string } } | null;

export default function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(email.trim(), password);
      const state = location.state as LocationState;
      const target = state?.from?.pathname ?? "/scenarios";
      navigate(target, { replace: true });
    } catch (err) {
      if (err instanceof ApiError) {
        // fastapi-users returns { detail: "LOGIN_BAD_CREDENTIALS" } for bad
        // creds. Map known codes to friendly Chinese copy.
        const detail =
          typeof err.detail === "object" && err.detail !== null
            ? (err.detail as { detail?: string }).detail
            : null;
        if (detail === "LOGIN_BAD_CREDENTIALS") {
          setError("邮箱或密码错误");
        } else if (detail === "LOGIN_USER_NOT_VERIFIED") {
          setError("账户尚未验证");
        } else {
          setError(err.message || "登录失败");
        }
      } else {
        setError("登录失败,请稍后重试");
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Container maxWidth="xs" sx={{ pt: 10 }}>
      <Paper sx={{ p: 4 }}>
        <Stack spacing={2.5} component="form" onSubmit={handleSubmit}>
          <Box>
            <Typography variant="h5" sx={{ fontWeight: 600 }}>
              登录 AICC
            </Typography>
            <Typography variant="body2" color="text.secondary">
              使用邮箱与密码进入指挥平台
            </Typography>
          </Box>

          {error && <Alert severity="error">{error}</Alert>}

          <TextField
            type="email"
            label="邮箱"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            autoComplete="email"
            autoFocus
            fullWidth
          />
          <TextField
            type="password"
            label="密码"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            autoComplete="current-password"
            fullWidth
          />

          <Button
            type="submit"
            variant="contained"
            disabled={submitting}
            fullWidth
          >
            {submitting ? "登录中…" : "登录"}
          </Button>

          <Typography variant="body2" sx={{ textAlign: "center" }}>
            还没有账户?{" "}
            <Link component={RouterLink} to="/register">
              立即注册
            </Link>
          </Typography>
        </Stack>
      </Paper>
    </Container>
  );
}
