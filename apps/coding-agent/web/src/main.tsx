import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { applyStoredTheme } from "./hooks/useTheme";
import "./styles.css";

// Before the first paint, not in an effect: an effect runs after the browser has already painted,
// which shows every dark-mode user a white frame on load. This is synchronous on purpose.
applyStoredTheme();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
