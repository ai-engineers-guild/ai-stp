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
    createRoot(document.getElementById("root")!).render(
      <StrictMode>
        <App />
      </StrictMode>,
    );
  });
