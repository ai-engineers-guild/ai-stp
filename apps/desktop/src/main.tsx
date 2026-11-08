import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { prepareLocale } from "./i18n";
import "./index.css";

void prepareLocale().then(() => {
  createRoot(document.getElementById("root")!).render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
});
