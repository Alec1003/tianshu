// Registration page. After success the AuthContext auto-logs the user in
// and we redirect to /scenarios.

import { useState, type FormEvent } from "react";
import { Link as RouterLink, useNavigate } from "react-router-dom";
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

export default function RegisterPage() {
  const { register } = useAuth();
  const navigate = useNavigate();

  const [email, setEmail] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [password2, setPassword2] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    if (password.length < 8) {
      setError("密码至少 8 位");
      return;
    }
    if (password !== password2) {
      setError("两次输入的密码不一致");
      return;
    }
    setSubmitting(true);
    try {
      await register(email.trim(), password, displayName.trim());
      navigate("/scenarios", { replace: true });
    } catch (err) {
      if (err instanceof ApiError) {
        const detail =
          typeof err.detail === "object" && err.detail !== null
            ? (err.detail as { detail?: string | { code?: string } }).detail
            : null;
        const code =
          typeof detail === "string"
            ? detail
            : (detail as { code?: string } | null)?.code ?? null;
        if (code === "REGISTER_USER_ALREADY_EXISTS") {
          setError("该邮箱已注册");
        } else if (code === "REGISTER_INVALID_PASSWORD") {
          setError("密码不符合要求(至少 8 位)");
        } else {
          setError(err.message || "注册失败");
        }
      } else {
        setError("注册失败,请稍后重试");
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Container maxWidth="xs" sx={{ pt: 8 }}>
      <Paper sx={{ p: 4 }}>
        <Stack spacing={2.5} component="form" onSubmit={handleSubmit}>
          <Box>
            <Typography variant="h5" sx={{ fontWeight: 600 }}>
              注册 AICC
            </Typography>
            <Typography variant="body2" color="text.secondary">
              创建账户后即可保存自己的想定
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
            label="昵称(可选)"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            inputProps={{ maxLength: 80 }}
            fullWidth
          />
          <TextField
            type="password"
            label="密码 (>= 8 位)"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            autoComplete="new-password"
            fullWidth
          />
          <TextField
            type="password"
            label="再次输入密码"
            value={password2}
            onChange={(e) => setPassword2(e.target.value)}
            required
            autoComplete="new-password"
            fullWidth
          />

          <Button
            type="submit"
            variant="contained"
            disabled={submitting}
            fullWidth
          >
            {submitting ? "注册中…" : "注册并登录"}
          </Button>

          <Typography variant="body2" sx={{ textAlign: "center" }}>
            已有账户?{" "}
            <Link component={RouterLink} to="/login">
              返回登录
            </Link>
          </Typography>
        </Stack>
      </Paper>
    </Container>
  );
}
