import { useState } from "react";
import type { HealthInfo, LanguageCode } from "../api";
import {
  getAppAccessToken,
  getOpenRouterKey,
  setAppAccessToken,
  setOpenRouterKey,
} from "../credentials";

type Props = {
  health: HealthInfo | null;
  language: LanguageCode;
  onSaved: () => void;
};

export function AccessGate({ health, language, onSaved }: Props) {
  const fr = language === "fr";
  const [openrouter, setOpenrouter] = useState(getOpenRouterKey);
  const [appToken, setAppToken] = useState(getAppAccessToken);
  const needsApp = Boolean(health?.app_access_required);

  return (
    <div className="card max-w-lg mx-auto space-y-4">
      <h2 className="text-lg font-semibold">{fr ? "Clé personnelle" : "Your own key"}</h2>
      <p className="text-sm text-muted">
        {fr
          ? "Facultatif sur la démo. Une clé personnelle utilise les crédits de votre compte OpenRouter et reste dans cet onglet."
          : "Optional on the demo. Your own key uses your OpenRouter credits and stays in this tab."}
      </p>
      {needsApp && (
        <label className="block space-y-1">
          <span className="text-sm font-medium">{fr ? "Jeton d’accès" : "App access token"}</span>
          <input
            className="input w-full"
            type="password"
            autoComplete="off"
            value={appToken}
            onChange={(e) => setAppToken(e.target.value)}
            placeholder="Set APP_ACCESS_TOKEN on the server"
          />
        </label>
      )}
      <label className="block space-y-1">
        <span className="text-sm font-medium">{fr ? "Clé OpenRouter" : "OpenRouter API key"}</span>
        <input
          className="input w-full"
          type="password"
          autoComplete="off"
          value={openrouter}
          onChange={(e) => setOpenrouter(e.target.value)}
          placeholder="sk-or-v1-… from openrouter.ai/keys"
        />
      </label>
      <button
        type="button"
        className="btn"
        onClick={() => {
          setOpenRouterKey(openrouter);
          setAppAccessToken(appToken);
          onSaved();
        }}
      >
        {fr ? "Enregistrer" : "Save"}
      </button>
    </div>
  );
}
