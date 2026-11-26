import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";
import {
  clearHistory, fetchAgents, fetchHealth, fetchSession, googleSignInUrl, logout, streamRun,
  type AccountSession, type AgentEvent, type ChatMessage, type HealthInfo, type LanguageCode,
  type RunError, type RunResult,
} from "./api";
import { getOpenRouterKey, hasRunCredentials } from "./credentials";
import { AccessGate } from "./components/AccessGate";
import type { AgentStatus, FlowProps } from "./components/AgentFlow";
import { CitedMarkdown } from "./components/CitedMarkdown";

import { EventLog } from "./components/EventLog";
import { RunMetricsPanel } from "./components/RunMetricsPanel";
import { SourcesBibliography } from "./components/SourcesBibliography";

const AgentFlow = lazy(() => import("./components/AgentFlow").then((mod) => ({ default: mod.AgentFlow })));
const EvalDashboard = lazy(() => import("./components/EvalDashboard").then((mod) => ({ default: mod.EvalDashboard })));

type RunMode = "query" | "brief" | "compare";
type View = RunMode | "examples" | "history";
type Example = "finals" | "brief";
const REPO = "https://github.com/svensundell/nba_moa_agents";
const CI = `${REPO}/actions/workflows/ci.yml`;
const COPY = {
  fr: {
    views: { query: "Copilot", brief: "Brief multi-agent", compare: "Comparaison", examples: "Exemples et qualité", history: "Mon historique" },
    headline: "La NBA, sources à l’appui.",
    summary: "J’ai créé un assistant NBA qui interroge ESPN, balldontlie et Reddit via MCP. Un graphe LangGraph orchestre le brief multi-agent. Chaque exécution expose les appels d’outils et les mesures.",
    live: "Essayer la question en direct",
    recorded: "Voir l’exemple enregistré",
    game: "Finales NBA 2025 · Match 7",
    finalScore: "Score final · 22 juin 2025",
    placeholder: "Votre question sur la NBA",
    question: "Qui a gagné le match 7 des Finales NBA du 22 juin 2025 et sur quel score ? Consulte uniquement le tableau des scores ESPN.",
    guest: "Accès invité, sans clé ni inscription. Évitez les données personnelles dans les questions, qui peuvent être envoyées aux fournisseurs.",
    signed: "Session Google active. Vos nouvelles exécutions et vos briefs sont privés.",
    quota: "essais gratuits restants aujourd’hui, partagés entre visiteurs. Nouveau quota à 00 h UTC.",
    ask: "Envoyer", run: "Lancer le brief", compare: "Lancer la comparaison", reset: "Nouvelle discussion",
    connecting: "Connexion aux agents…", working: "Les agents recherchent et synthétisent les informations…",
    waiting: "La démo peut mettre un moment à démarrer.",
    briefIntro: "Cinq spécialistes examinent les matchs, les statistiques, les nouvelles, les blessures et les réactions avant la synthèse.",
    compareIntro: "Voyez comment le brief LangGraph et le Copilot traitent le même sujet, puis comparez leurs sources et leurs coûts estimés.",
    optionalKey: "Clé OpenRouter", retry: "Vérifier la connexion", source: "Ouvrir la source", traces: "Appels d’outils et trace", raw: "Journal technique",
    tools: "Appels d’outils", noTools: "Aucun appel d’outil terminé.", failure: "Échec ou donnée indisponible",
    answer: "Réponse", copilot: "Vous pouvez poursuivre avec une question de suivi.",
    exampleTitle: "Exécutions enregistrées", exampleIntro: "Ces exemples proviennent d’appels sur la démo Azure. Les durées, appels et jetons sont relevés pendant l’exécution. Les coûts sont calculés à partir des tarifs des modèles.",
    exampleFinals: "Finales 2025 · Copilot", exampleBrief: "Finales 2025 · Brief multi-agent (EN)",
    liveFallback: "Le score en direct n’a pas pu être vérifié. Voici une réponse enregistrée.",
    captured: "Exécution enregistrée le", exampleError: "L’exemple est momentanément indisponible.", loading: "Chargement…",
    quality: "Limite observée dans ce brief",
    qualityNote: "Le résumé dit « triple-double », alors que sa propre ligne indique 29 points, 12 passes et 5 rebonds. Reddit a aussi refusé un appel. Un lien permet de vérifier la statistique.",
    boxScore: "Feuille de match officielle NBA", tests: "Tests automatisés", testing: "Méthode de test", llmops: "Calcul des métriques", architecture: "Architecture",
    historyIntro: "Connectez-vous pour retrouver vos futures réponses, leurs traces et leurs métriques sur cet appareil ou un autre. Les essais invités restent dans l’onglet et ne sont pas repris dans l’historique.",
    historyOff: "La connexion Google attend l’activation du client OAuth de la démo.",
    signIn: "Se connecter avec Google", signOut: "Se déconnecter", erase: "Effacer mon historique",
    eraseConfirm: "Supprimer toutes les exécutions et tous les briefs enregistrés pour ce compte ?",
    accountError: "L’action sur le compte a échoué. Réessayez.", erased: "Historique effacé.",
    errors: {
      quota: "Le quota partagé est épuisé. Il revient à 00 h UTC. Vous pouvez ouvrir un exemple enregistré ou utiliser votre clé OpenRouter.",
      access: "La clé ou le jeton d’accès doit être vérifié. Les exemples enregistrés restent disponibles.",
      invalid: "Vérifiez la question et réessayez.",
      timeout: "Le délai de réponse est dépassé. Réessayez avec une question plus courte ou ouvrez un exemple enregistré.",
      connection: "La connexion s’est interrompue. Réessayez ou ouvrez un exemple enregistré.",
      generation: "Les agents n’ont pas pu terminer la réponse. Réessayez ou ouvrez un exemple enregistré.",
    },
  },
  en: {
    views: { query: "Copilot", brief: "Multi-agent brief", compare: "Compare", examples: "Examples & quality", history: "My history" },
    headline: "NBA answers you can verify.",
    summary: "I built an NBA assistant that queries ESPN, balldontlie and Reddit through MCP. A LangGraph workflow runs the multi-agent brief. Every run shows its tool calls and metrics.",
    live: "Try the live question", recorded: "View the recorded example",
    game: "2025 NBA Finals · Game 7", finalScore: "Final score · June 22, 2025",
    placeholder: "Your NBA question",
    question: "Who won Game 7 of the NBA Finals on June 22, 2025, and what was the final score? Use only the ESPN scoreboard.",
    guest: "Guest access needs no key or sign-in. Keep personal information out of questions, which may be sent to data and model providers.",
    signed: "Google session active. Your new runs and briefs are private.",
    quota: "free runs remaining today, shared across visitors. Resets at 00:00 UTC.",
    ask: "Send", run: "Run the brief", compare: "Run the comparison", reset: "New conversation",
    connecting: "Connecting to the agents…", working: "The agents are looking up and synthesizing the data…",
    waiting: "The demo can take a moment to start.",
    briefIntro: "Five specialists check scores, stats, news, injuries and fan reactions before the editor writes the brief.",
    compareIntro: "See how the LangGraph brief and Copilot handle the same topic, then compare their sources and estimated costs.",
    optionalKey: "OpenRouter key", retry: "Check connection", source: "Open source", traces: "Tool calls and trace", raw: "Technical log",
    tools: "Tool calls", noTools: "No tool calls have finished.", failure: "Failed or unavailable",
    answer: "Answer", copilot: "You can ask a follow-up question.",
    exampleTitle: "Recorded runs", exampleIntro: "These examples come from real runs on the Azure demo. Runtime, calls and tokens are recorded during each run. Costs are calculated from model prices.",
    exampleFinals: "2025 Finals · Copilot", exampleBrief: "2025 Finals · Multi-agent brief (EN)",
    liveFallback: "The live score could not be verified. Here is a recorded answer.",
    captured: "Recorded on", exampleError: "This example is temporarily unavailable.", loading: "Loading…",
    quality: "Limitation observed in this brief",
    qualityNote: "The summary calls this a triple-double, while its own stat line lists 29 points, 12 assists and 5 rebounds. Reddit also rejected a tool call. Check the official box score to verify the stat.",
    boxScore: "Official NBA box score", tests: "Automated checks", testing: "Testing method", llmops: "How metrics are calculated", architecture: "Architecture",
    historyIntro: "Sign in to revisit future answers, traces and metrics on this device or another. Guest runs stay in this tab and are excluded from your history.",
    historyOff: "Google sign-in awaits activation of the demo’s OAuth client.",
    signIn: "Sign in with Google", signOut: "Sign out", erase: "Clear my history",
    eraseConfirm: "Delete every saved run and brief for this account?",
    accountError: "The account action failed. Try again.", erased: "History cleared.",
    errors: {
      quota: "The shared quota is used up. It resets at 00:00 UTC. Open a recorded example or use your OpenRouter key.",
      access: "Check the key or access token. Recorded examples are still available.",
      invalid: "Check the question and try again.",
      timeout: "The run timed out. Try a shorter question or open a recorded example.",
      connection: "The connection was interrupted. Try again or open a recorded example.",
      generation: "The agents could not finish the answer. Try again or open a recorded example.",
    },
  },
} as const;

type Copy = (typeof COPY)[LanguageCode];

function currentView(): { view: View; example: Example } {
  const params = new URLSearchParams(location.search);
  const view = params.get("view");
  if (view === "brief" || view === "compare" || view === "history") return { view, example: "finals" };
  if (params.has("example")) return { view: "examples", example: params.get("example") === "brief" ? "brief" : "finals" };
  return { view: "query", example: "finals" };
}

export default function App() {
  const [locationState, setLocationState] = useState(currentView);
  const { view, example } = locationState;
  const [language, setLanguage] = useState<LanguageCode>(() => {
    const requested = new URLSearchParams(location.search).get("lang");
    if (requested === "en" || requested === "fr") return requested;
    return localStorage.getItem("nba-language") === "en" ? "en" : "fr";
  });
  const t = COPY[language];
  const [health, setHealth] = useState<HealthInfo | null>(null);
  const [account, setAccount] = useState<AccountSession | null>(null);
  const [accountError, setAccountError] = useState(new URLSearchParams(location.search).get("account") === "error");
  const [accountBusy, setAccountBusy] = useState(false);
  const [historyGeneration, setHistoryGeneration] = useState(0);
  const [historyCleared, setHistoryCleared] = useState(false);
  const [showKeys, setShowKeys] = useState(false);
  const composer = useRef<HTMLInputElement>(null);
  const workspace = useRef<HTMLElement>(null);
  const [query, setQuery] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [results, setResults] = useState<Partial<Record<RunMode, RunResult>>>({});
  const [statuses, setStatuses] = useState<Record<string, AgentStatus>>({});
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [models, setModels] = useState<Record<string, string>>({});
  const [active, setActive] = useState<{ mode: RunMode; since: number } | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [fallback, setFallback] = useState(false);
  const [error, setError] = useState<RunError | null>(null);
  const [citation, setCitation] = useState<number | null>(null);
  const [recorded, setRecorded] = useState<RunResult | null>(null);
  const [exampleError, setExampleError] = useState(false);

  const result = view === "examples" || view === "history" ? null : results[view] ?? null;
  const quotaEmpty = health?.demo_runs_remaining === 0 && !getOpenRouterKey();
  const ready = Boolean(health?.mcp_initialised && health.database_ok && hasRunCredentials(health) && !quotaEmpty);
  const recordedPath = view === "examples" && example === "brief" ? "/examples/brief-en.json" : `/examples/finals-${language}.json`;

  function refreshHealth() { void fetchHealth().then(setHealth).catch(() => setHealth(null)); }

  useEffect(() => {
    refreshHealth();
    void fetchSession().then(setAccount).catch(() => setAccount(null));
    void fetchAgents().then((agents) => setModels(Object.fromEntries(agents.map((a) => [a.agent, a.provider_model])))).catch(() => {});
    const onPop = () => {
      setLocationState(currentView());
      setCitation(null);
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  useEffect(() => {
    if (health?.mcp_initialised && health.database_ok) return;
    const interval = window.setInterval(refreshHealth, 5000);
    return () => window.clearInterval(interval);
  }, [health?.mcp_initialised, health?.database_ok]);

  useEffect(() => {
    localStorage.setItem("nba-language", language);
    document.documentElement.lang = language;
  }, [language]);

  useEffect(() => {
    if (!active) return;
    const interval = window.setInterval(() => setElapsed(Math.floor((Date.now() - active.since) / 1000)), 1000);
    return () => window.clearInterval(interval);
  }, [active]);

  useEffect(() => {
    if (view !== "examples" && (view !== "query" || !fallback)) return;
    const controller = new AbortController();
    setRecorded(null);
    setExampleError(false);
    void fetch(recordedPath, { signal: controller.signal }).then(async (response) => {
      if (!response.ok) throw new Error("Example unavailable");
      setRecorded(await response.json() as RunResult);
    }).catch(() => { if (!controller.signal.aborted) setExampleError(true); });
    return () => controller.abort();
  }, [view, recordedPath, fallback]);

  function move(next: View, sample: Example = "finals", scroll = false) {
    const search = next === "examples" ? `?example=${sample}` : next === "query" ? "/" : `?view=${next}`;
    if (next !== view || sample !== example) window.history.pushState(null, "", search);
    setLocationState({ view: next, example: sample });
    setCitation(null);
    if (!active) setError(null);
    if (scroll) requestAnimationFrame(() => workspace.current?.scrollIntoView({ block: "start" }));
  }

  function reset() {
    setFallback(false);
    setMessages([]);
    setQuery("");
    setResults({});
    setEvents([]);
    setStatuses({});
    setError(null);
    setCitation(null);
  }

  async function accountAction(action: "logout" | "erase") {
    if (action === "erase" && !window.confirm(t.eraseConfirm)) return;
    setAccountBusy(true);
    setAccountError(false);
    try {
      if (action === "logout") {
        await logout();
        setAccount((prev) => prev && { ...prev, signed_in: false });
        setHistoryCleared(false);
        move("query");
      } else {
        await clearHistory();
        setHistoryGeneration((value) => value + 1);
        setHistoryCleared(true);
      }
      reset();
    } catch {
      setAccountError(true);
    } finally {
      setAccountBusy(false);
    }
  }

  function start(mode: RunMode, input = query, newConversation = false) {
    if (active || accountBusy) return;
    const question = input.trim();
    if (mode === "query" && !question) { composer.current?.focus(); return; }
    if (!ready) {
      setError(quotaEmpty ? "quota" : health?.mcp_initialised && !hasRunCredentials(health) ? "access" : "connection");
      if (!quotaEmpty) refreshHealth();
      return;
    }
    setError(null);
    setFallback(false);
    setCitation(null);
    setResults((prev) => ({ ...prev, [mode]: undefined }));
    setStatuses({});
    setEvents([]);
    setElapsed(0);
    setActive({ mode, since: Date.now() });
    const nextMessages: ChatMessage[] = mode === "query" ? [...(newConversation ? [] : messages), { role: "user", content: question }] : [];
    if (mode === "query") {
      setMessages(nextMessages);
      setQuery("");
    }
    streamRun({
      mode, language, query: mode === "compare" ? question : "",
      messages: nextMessages.slice(-9).map((message) => ({ ...message, content: message.content.slice(0, 2000) })),
      onFrame(frame) {
        if (frame.kind === "event") {
          const event = frame.event;
          setEvents((prev) => [...prev, event]);
          if (event.type === "start" || event.type === "done" || event.type === "error") {
            const status = event.type === "start" ? "running" : event.type;
            setStatuses((prev) => ({ ...prev, [event.agent]: status }));
          }
        } else if (frame.kind === "node_done") {
          const node = frame.node;
          setStatuses((prev) => ({ ...prev, [node]: "done" }));
        } else if (frame.kind === "result") {
          const response = frame.result;
          setResults((prev) => ({ ...prev, [mode]: response }));
          if (mode === "query") {
            const canVerify = response.source_citations?.length > 0;
            setFallback(newConversation && !canVerify);
            setMessages([...nextMessages, { role: "assistant", content: response.final_brief }]);
          }
          setActive(null);
          refreshHealth();
        } else if (frame.kind === "error") {
          if (mode === "query") {
            setMessages(messages);
            setQuery(question);
          }
          setError(frame.code ?? "generation");
          setFallback(newConversation);
          setActive(null);
          refreshHealth();
        }
      },
    });
  }

  const traceEvents = useMemo(() => result?.events ?? (active?.mode === view ? events : []), [active, events, result, view]);
  const currentRunning = active?.mode === view;
  const runOptions = view !== "examples" && view !== "history";
  const recordedDate = recorded ? new Date(recorded.started_at).toLocaleDateString(language, { dateStyle: "long" }) : null;

  return (
    <>
      <header className="site-nav">
        <div className="page-width flex flex-wrap items-center justify-between gap-3">
          <a className="wordmark" href="/">NBA<span> / </span>AGENTS</a>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
            <a className="header-link" href={REPO}>GitHub ↗</a>
            <button className="header-link" type="button" onClick={() => move("history", "finals", true)}>{t.views.history}</button>
            <div className="language-switch" aria-label="Language / Langue">
              {(["fr", "en"] as const).map((lang) => (
                <button type="button" key={lang} onClick={() => setLanguage(lang)} aria-pressed={language === lang}>{lang.toUpperCase()}</button>
              ))}
            </div>
          </div>
        </div>
      </header>
      <main className="page-width pb-10">
        <section className="court-hero">
          <div className="hero-copy">
            <h1>{t.headline}</h1>
            <p>{t.summary}</p>
            <div className="hero-actions">
              <button className="btn" disabled={Boolean(active)} onClick={() => {
                move("query", "finals", true);
                start("query", t.question, true);
              }}>{t.live}</button>
              <a className="hero-link" href="/?example=finals" onClick={(event) => {
                if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
                event.preventDefault();
                move("examples", "finals", true);
              }}>{t.recorded} <span aria-hidden="true">↗</span></a>
            </div>
          </div>
          <div className="hero-score">
            <p>{t.game}</p>
            <div className="score-numbers">
              <div><span>OKC</span><strong>103</strong></div>
              <span aria-hidden="true">–</span>
              <div><span>IND</span><strong>91</strong></div>
            </div>
            <p>{t.finalScore}</p>
          </div>
        </section>

        <section className="workspace space-y-4" ref={workspace} aria-label={t.views[view]}>
          <nav className="mode-nav" aria-label={language === "fr" ? "Modes de la démo" : "Demo modes"}>
            {(["query", "brief", "compare", "examples"] as const).map((item) => (
              <button type="button" key={item} aria-current={view === item ? "page" : undefined} onClick={() => move(item)}>{t.views[item]}</button>
            ))}
          </nav>
          {accountError && <p className="notice-error" role="alert">{t.accountError}</p>}
          {runOptions && (
            <>
              <section className="card space-y-3">
                <h2 className="section-title">{t.views[view]}</h2>
                {view !== "query" && <p className="text-muted">{view === "brief" ? t.briefIntro : t.compareIntro}</p>}
                <form className="flex flex-col sm:flex-row items-stretch gap-2" onSubmit={(event) => { event.preventDefault(); start(view); }}>
                  {view === "query" && <input ref={composer} className="input" aria-label={t.placeholder} placeholder={t.placeholder}
                    maxLength={500} value={query} onChange={(event) => setQuery(event.target.value)} disabled={Boolean(active)} />}
                  <button className="btn shrink-0" type="submit" disabled={Boolean(active)}>
                    {view === "query" ? t.ask : view === "brief" ? t.run : t.compare}
                  </button>
                  {view === "query" && messages.length > 0 && <button className="btn-secondary shrink-0" type="button" onClick={reset} disabled={Boolean(active)}>{t.reset}</button>}
                </form>
                <p className="text-sm text-muted">{account?.signed_in ? t.signed : t.guest}</p>
                <div className="flex flex-wrap items-baseline gap-x-4 gap-y-2 text-sm">
                  {health?.demo_runs_remaining != null && <p className="text-muted"><strong>{health.demo_runs_remaining} / {health.demo_daily_runs}</strong> {t.quota}</p>}
                  {health && <button className="text-link" type="button" onClick={() => setShowKeys((value) => !value)} aria-expanded={showKeys}>{t.optionalKey}</button>}
                  {!health?.mcp_initialised && <button className="text-link" type="button" onClick={refreshHealth}>{t.retry}</button>}
                </div>
                {!health && <p className="text-sm text-muted" role="status">{t.waiting}</p>}
              </section>
              {(showKeys || (health?.app_access_required && !hasRunCredentials(health))) && (
                <AccessGate health={health} language={language} onSaved={() => { setShowKeys(false); refreshHealth(); }} />
              )}
              {error && <div className="notice-error" role="alert">{t.errors[error]} <button className="text-link" onClick={() => move("examples")}>{t.recorded}</button></div>}
              {view === "query" && messages.length > 0 && <section className="space-y-3" aria-label={t.answer}>
                {messages.map((message, index) => (
                  <article key={index} className={message.role === "user" ? "user-message" : "card answer"}>
                    {message.role === "user" ? message.content : <CitedMarkdown content={message.content}
                      onCitationClick={index === messages.length - 1 && result?.source_citations.length ? setCitation : undefined} />}
                  </article>
                ))}
              </section>}
              {currentRunning && <div className="run-progress" role="status">
                <span className="progress-dot" aria-hidden="true" />
                {elapsed === 0 ? t.connecting : t.working} <span className="font-mono">{elapsed} s</span>
              </div>}
              {view === "query" && fallback && <section className="space-y-3" aria-label={t.recorded}>
                <p className="quality-note" role="status">{t.liveFallback}</p>
                {recorded && <>
                  <ResultContent result={recorded} t={t} onCitation={setCitation} />
                  <SourcesBibliography citations={recorded.source_citations} language={language} activeId={citation} />
                </>}
                {!recorded && <button type="button" className="text-link" onClick={() => move("examples")}>{t.recorded}</button>}
              </section>}
              {result && view !== "query" && <ResultContent result={result} t={t} onCitation={setCitation} />}
              {result && <SourcesBibliography citations={result.source_citations} language={language} activeId={citation} />}
              {(currentRunning || traceEvents.length > 0) && <Trace events={traceEvents} metrics={result?.metrics} t={t} language={language} open={currentRunning || citation != null} />}
              {result?.metrics && <RunMetricsPanel metrics={result.metrics} language={language} />}
              {(view === "brief" || view === "compare") && (
                <AgentGraph
                  title={language === "fr" ? "Graphe des agents" : "Agent graph"}
                  loadingText={t.loading}
                  statuses={statuses}
                  models={models}
                />
              )}
            </>
          )}
          {view === "examples" && (
            <>
              <section className="card space-y-3">
                <h2 className="section-title">{t.exampleTitle}</h2>
                <p className="text-muted">{t.exampleIntro}</p>
                <div className="flex flex-wrap gap-2">
                  <button className={example === "finals" ? "btn" : "btn-secondary"} aria-pressed={example === "finals"} onClick={() => move("examples", "finals")}>{t.exampleFinals}</button>
                  <button className={example === "brief" ? "btn" : "btn-secondary"} aria-pressed={example === "brief"} onClick={() => move("examples", "brief")}>{t.exampleBrief}</button>
                </div>
              </section>
              {exampleError && <p className="notice-error" role="alert">{t.exampleError}</p>}
              {!recorded && !exampleError && <p role="status">{t.loading}</p>}
              {recorded && <>
                <p className="text-sm text-muted">{t.captured} {recordedDate}{recorded.query && ` · ${recorded.query}`}</p>
                {example === "brief" && <aside className="quality-note">
                  <strong>{t.quality}</strong><p>{t.qualityNote} <a className="text-link" href="https://www.nba.com/game/ind-vs-okc-0042400407/box-score">{t.boxScore} ↗</a></p>
                </aside>}
                <ResultContent result={recorded} t={t} onCitation={setCitation} />
                <SourcesBibliography citations={recorded.source_citations} language={language} activeId={citation} />
                <Trace events={recorded.events} metrics={recorded.metrics} t={t} language={language} open />
                {recorded.metrics && <RunMetricsPanel metrics={recorded.metrics} language={language} />}
              </>}
            </>
          )}
          {view === "history" && (
            <>
              <section className="card space-y-3">
                <h2 className="section-title">{t.views.history}</h2>
                <p className="text-muted">{account?.signed_in ? t.signed : t.historyIntro}</p>
                {account?.signed_in ? <div className="flex flex-wrap gap-2">
                  <button className="btn-secondary" disabled={Boolean(active || accountBusy)} onClick={() => void accountAction("logout")}>{t.signOut}</button>
                  <button className="btn-secondary" disabled={Boolean(active || accountBusy)} onClick={() => void accountAction("erase")}>{t.erase}</button>
                </div> : account?.google_sign_in ? <a className="btn" href={googleSignInUrl()}>{t.signIn}</a>
                  : <p className="text-sm text-muted">{account ? t.historyOff : t.loading}</p>}
                {historyCleared && <p role="status">{t.erased}</p>}
              </section>
              {account?.signed_in && <Suspense fallback={<p>{t.loading}</p>}><EvalDashboard key={historyGeneration} language={language} /></Suspense>}
            </>
          )}
        </section>
        <footer className="project-links">
          <a href={CI}>{t.tests} ↗</a>
          <a href={`${REPO}/blob/main/docs/testing.md`}>{t.testing} ↗</a>
          <a href={`${REPO}/blob/main/docs/llmops.md`}>{t.llmops} ↗</a>
          <a href={`${REPO}/blob/main/docs/architecture.md`}>{t.architecture} ↗</a>
        </footer>
      </main>
    </>
  );
}

function AgentGraph({ title, loadingText, ...flow }: FlowProps & { title: string; loadingText: string }) {
  const [open, setOpen] = useState(false);

  return (
    <details className="card" onToggle={(event) => setOpen(event.currentTarget.open)}>
      <summary className="section-title">{title}</summary>
      {open && (
        <Suspense fallback={<p>{loadingText}</p>}>
          <AgentFlow {...flow} />
        </Suspense>
      )}
    </details>
  );
}

function ResultContent({ result, t, onCitation }: { result: RunResult; t: Copy; onCitation: (id: number) => void }) {
  return (
    <div className={result.mode === "compare" ? "grid gap-4 lg:grid-cols-2" : ""}>
      <article className="card answer">
        <h2 className="section-title mb-3">{result.mode === "query" ? t.answer : t.views.brief}</h2>
        <CitedMarkdown content={result.final_brief} onCitationClick={result.source_citations.length ? onCitation : undefined} />
      </article>
      {result.single_llm_answer && <article className="card answer">
        <h2 className="section-title mb-3">{t.views.query}</h2>
        <CitedMarkdown content={result.single_llm_answer} onCitationClick={result.source_citations.length ? onCitation : undefined} />
      </article>}
    </div>
  );
}

function Trace({ events, metrics, t, language, open }: {
  events: AgentEvent[];
  metrics?: RunResult["metrics"];
  t: Copy;
  language: LanguageCode;
  open: boolean;
}) {
  const toolEvents = events.filter((event) => event.type === "tool");
  const failures = metrics?.tool_calls.filter((call) => !call.success) ?? [];
  return (
    <details className="card trace" open={open || undefined}>
      <summary className="section-title">{t.traces} · {metrics?.tool_call_count ?? toolEvents.length}</summary>
      <ul className="trace-rows">
        {toolEvents.map((event, i) => (
          <li key={i}>
            <span className="font-mono">{event.citation_id ? `[${event.citation_id}] ` : ""}{event.tool ?? event.agent}</span>
            {event.provider && <span className="pill">{event.provider}</span>}
            {event.source_url?.startsWith("https://") && <a className="text-link" href={event.source_url} target="_blank" rel="noreferrer">{t.source} ↗</a>}
            <p>{event.content}</p>
          </li>
        ))}
        {failures.map((call, i) => <li key={i}><span className="font-mono">{call.tool}</span> · {t.failure}</li>)}
      </ul>
      {!toolEvents.length && !failures.length && <p className="text-sm text-muted">{t.noTools}</p>}
      {events.length > 0 && <details className="mt-4">
        <summary className="text-sm font-semibold">{t.raw}</summary>
        <EventLog events={events} language={language} />
      </details>}
    </details>
  );
}
