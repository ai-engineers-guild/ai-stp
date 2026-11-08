import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { prepareLocale } from "./i18n";
import { preparePreferences } from "./preferences";
import { cmdPreferencesRead, cmdPreferencesWrite } from "./transport";
import "./index.css";

void preparePreferences({ cmdPreferencesRead, cmdPreferencesWrite })
  .then(prepareLocale)
  .then(() => {
    const root = document.getElementById("root");
    if (!root) throw new Error("The desktop root element is missing.");
    createRoot(root).render(
      <StrictMode>
        <App />
      </StrictMode>,
    );
  });
