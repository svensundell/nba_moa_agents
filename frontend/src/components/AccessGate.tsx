import { useState } from "react";
import type { HealthInfo } from "../api";
import {
  getAppAccessToken,
  getOpenRouterKey,
  setAppAccessToken,
  setOpenRouterKey,
} from "../credentials";

type Props = {
  health: HealthInfo | null;
  onSaved: () => void;
};

export function AccessGate({ health, onSaved }: Props) {
  const [openrouter, setOpenrouter] = useState(getOpenRouterKey);
  const [appToken, setAppToken] = useState(getAppAccessToken);
  const needsApp = Boolean(health?.app_access_required);

  return (
    <div className="card max-w-lg mx-auto space-y-4">
      <h2 className="text-lg font-semibold text-ink">Access</h2>
      <p className="text-sm text-muted">
        LLM runs use your own OpenRouter key (BYOK). Billing stays on your OpenRouter account.
      </p>
      {needsApp && (
        <label className="block space-y-1">
          <span className="text-sm font-medium">App access token</span>
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
          <span className="text-sm font-medium">OpenRouter API key</span>
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
        className="btn-primary w-full"
        onClick={() => {
          setOpenRouterKey(openrouter);
          setAppAccessToken(appToken);
          onSaved();
        }}
      >
        Save and continue
      </button>
    </div>
  );
}
