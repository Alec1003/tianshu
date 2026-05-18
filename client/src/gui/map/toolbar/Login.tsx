import { useAuth0 } from "@auth0/auth0-react";
import { Chip } from "@mui/material";
import React from "react";

const LoginButton = () => {
  const { loginWithRedirect } = useAuth0();

  return (
    <Chip
      variant="outlined"
      onClick={() => loginWithRedirect()}
      label="登录"
      sx={{
        marginRight: "1em",
        color: "#f8fafc",
        borderColor: "rgba(148, 163, 184, 0.45)",
        backgroundColor: "rgba(15, 23, 42, 0.35)",
        "& .MuiChip-label": {
          color: "inherit",
        },
      }}
    />
  );
};

export default LoginButton;
