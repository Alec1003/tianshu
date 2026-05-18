import {
  Menu as MuiMenu,
  MenuProps as MuiMenuProps,
  Popover as MuiPopover,
  PopoverProps as MuiPopoverProps,
} from "@mui/material";

const darkMenuPaperSx = {
  backgroundColor: "#111827",
  color: "#f8fafc",
  border: "1px solid rgba(148, 163, 184, 0.22)",
  boxShadow: "0 16px 40px rgba(15, 23, 42, 0.45)",
  "& .MuiList-root": {
    paddingTop: 0.5,
    paddingBottom: 0.5,
  },
  "& .MuiMenuItem-root": {
    color: "inherit",
  },
  "& .MuiTypography-root": {
    color: "inherit",
  },
  "& .MuiListSubheader-root": {
    backgroundColor: "#111827",
    color: "#cbd5e1",
  },
  "& .MuiDivider-root": {
    borderColor: "rgba(148, 163, 184, 0.22)",
  },
};

export function Menu(props: MuiMenuProps) {
  return (
    <MuiMenu
      {...props}
      PaperProps={{
        ...props.PaperProps,
        sx: darkMenuPaperSx,
      }}
    />
  );
}

export function Popover(props: MuiPopoverProps) {
  return <MuiPopover {...props} />;
}
