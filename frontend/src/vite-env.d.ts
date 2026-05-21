/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Production API root, e.g. https://nbamoaagents-production.up.railway.app/api */
  readonly VITE_API_BASE?: string;
  /** Optional WS override; defaults to wss:// variant of VITE_API_BASE */
  readonly VITE_WS_API_BASE?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
