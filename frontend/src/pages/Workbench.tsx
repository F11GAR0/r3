import { useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { jsonFetch } from "../api";
import { useAuth } from "../auth";
import { AlertTriangle, ExternalLink, Loader2, Timer, Wand2 } from "lucide-react";

type Issue = {
  id: number;
  subject: string;
  status_name: string;
  project_name: string;
  stagnation_days: number;
  life_days: number;
  criticality: number;
  description: string;
  complexity: string | null;
};

type RelatedMini = { id: number; subject: string; relation_type: string | null };

type IssueContext = {
  issue: Issue;
  subtasks: RelatedMini[];
  related: RelatedMini[];
};

type Suggestion = { subject: string; description: string };

type AppSettings = {
  redmine_base_url: string | null;
  sprint_lifecycle_days: number;
};

/**
 * HSL color from sprint threshold → 600d; band changes every 14d above threshold.
 */
function stalenessStyle(sprintDays: number, stagnationDays: number): { background: string; title: string } {
  const minD = Math.max(1, sprintDays);
  const maxD = 600;
  const d = Math.max(0, stagnationDays);
  const t = d <= minD ? 0 : Math.min(1, (d - minD) / (maxD - minD));
  const hue = Math.round(130 * (1 - t));
  const above = Math.max(0, d - minD);
  const band = Math.floor(above / 14);
  return {
    background: `hsl(${hue} 72% 44%)`,
    title: `Протухание: ${d.toFixed(0)} дн. (от порога +${band}×14д)`,
  };
}

function redmineIssueUrl(base: string | null, id: number): string | null {
  if (!base) {
    return null;
  }
  return `${base.replace(/\/$/, "")}/issues/${id}`;
}

const SUG_SCROLL_PAGE = 12;

function formatDurationSec(ms: number): string {
  if (ms < 1000) {
    return `${Math.round(ms)} мс`;
  }
  return `${(ms / 1000).toFixed(1).replace(".", ",")} с`;
}

/**
 * Split workbench: left = stale list, right = context + AI or manual subtasks.
 */
export default function Workbench() {
  const { user, refresh } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const [issues, setIssues] = useState<Issue[]>([]);
  const [sort, setSort] = useState<"date" | "stale" | "criticality">("stale");
  const [onlyStale, setOnlyStale] = useState(true);
  const [sel, setSel] = useState<Issue | null>(null);
  const [context, setContext] = useState<IssueContext | null>(null);
  const [contextLoading, setContextLoading] = useState(false);
  const [sug, setSug] = useState<Suggestion[]>([]);
  const [rid, setRid] = useState(String(user?.redmine_user_id ?? ""));
  const [err, setErr] = useState("");
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [splitLoading, setSplitLoading] = useState(false);
  const [complexityLoading, setComplexityLoading] = useState(false);
  const [listLoading, setListLoading] = useState(true);
  const [contextRefreshing, setContextRefreshing] = useState(false);
  const [subtaskSubmitting, setSubtaskSubmitting] = useState<number | null>(null);
  const [profileSaving, setProfileSaving] = useState(false);
  const [rmKey, setRmKey] = useState("");
  const [skipApiVerify, setSkipApiVerify] = useState(false);
  const [openById, setOpenById] = useState("");
  const [openByIdLoading, setOpenByIdLoading] = useState(false);
  const [splitLastMs, setSplitLastMs] = useState<number | null>(null);
  const [splitLiveMs, setSplitLiveMs] = useState(0);
  const [sugVisibleCount, setSugVisibleCount] = useState(SUG_SCROLL_PAGE);
  const splitScrollRef = useRef<HTMLDivElement | null>(null);
  const sugLoadMoreRef = useRef<HTMLDivElement | null>(null);
  const loadGen = useRef(0);

  const loadIssueForSplit = useCallback(
    async (
      issueId: number,
      options?: { clearIssueQueryOnSuccess?: boolean }
    ): Promise<boolean> => {
      setOpenByIdLoading(true);
      setErr("");
      try {
        const ctx = await jsonFetch<IssueContext>(`/api/issues/${issueId}/context`);
        setSel(ctx.issue as Issue);
        setSug([]);
        setIssues((prev) =>
          prev.some((x) => x.id === ctx.issue.id) ? prev : [ctx.issue as Issue, ...prev]
        );
        if (options?.clearIssueQueryOnSuccess) {
          setSearchParams(
            (prev) => {
              const next = new URLSearchParams(prev);
              next.delete("issue");
              return next;
            },
            { replace: true }
          );
        }
        return true;
      } catch (e) {
        setErr(e instanceof Error ? e.message : "Не удалось открыть задачу");
        return false;
      } finally {
        setOpenByIdLoading(false);
      }
    },
    [setSearchParams]
  );

  const load = useCallback(async () => {
    const my = ++loadGen.current;
    setListLoading(true);
    setErr("");
    try {
      const [list, sett] = await Promise.all([
        jsonFetch<Issue[]>(`/api/issues?sort=${sort}&only_stale=${onlyStale}`),
        jsonFetch<AppSettings>("/api/settings"),
      ]);
      if (my === loadGen.current) {
        setIssues(list);
        setSettings(sett);
      }
    } catch (e) {
      if (my === loadGen.current) {
        setErr(e instanceof Error ? e.message : "Ошибка");
      }
    } finally {
      if (my === loadGen.current) {
        setListLoading(false);
      }
    }
  }, [onlyStale, sort]);

  useEffect(() => {
    void load();
  }, [load]);

  const selectedId = sel?.id;
  useEffect(() => {
    if (selectedId == null) {
      setContext(null);
      setContextLoading(false);
      return;
    }
    setContext(null);
    setContextLoading(true);
    let cancel = false;
    void (async () => {
      try {
        const ctx = await jsonFetch<IssueContext>(`/api/issues/${selectedId}/context`);
        if (!cancel) {
          setContext(ctx);
        }
      } catch {
        if (!cancel) {
          setContext(null);
        }
      } finally {
        if (!cancel) {
          setContextLoading(false);
        }
      }
    })();
    return () => {
      cancel = true;
    };
  }, [selectedId]);

  useEffect(() => {
    if (!user?.redmine_user_id) {
      return;
    }
    const raw = searchParams.get("issue");
    if (!raw) {
      return;
    }
    const id = parseInt(raw, 10);
    if (Number.isNaN(id) || id < 1) {
      return;
    }
    void loadIssueForSplit(id, { clearIssueQueryOnSuccess: true });
  }, [user?.redmine_user_id, searchParams, loadIssueForSplit]);

  useEffect(() => {
    setSugVisibleCount(sug.length === 0 ? 0 : Math.min(SUG_SCROLL_PAGE, sug.length));
  }, [sug]);

  useEffect(() => {
    const root = splitScrollRef.current;
    const target = sugLoadMoreRef.current;
    if (!root || !target) {
      return;
    }
    if (sugVisibleCount >= sug.length) {
      return;
    }
    const obs = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting) {
          setSugVisibleCount((c) => Math.min(c + SUG_SCROLL_PAGE, sug.length));
        }
      },
      { root, rootMargin: "120px 0px", threshold: 0.01 }
    );
    obs.observe(target);
    return () => obs.disconnect();
  }, [sug, sug.length, sugVisibleCount]);

  if (!user?.redmine_user_id) {
    return (
      <div className="space-y-4">
        <h1 className="text-xl font-bold">Workbench</h1>
        <p className="text-slate-600">Укажите ваш Redmine user id, чтобы увидеть задачи.</p>
        <p className="text-xs text-slate-500 max-w-md">
          Если глобальный API-ключ в настройках не от администратора Redmine, укажите <strong>персональный</strong>{" "}
          ключ (Redmine → Моя учётная запись → API access key) — тогда R3 обращается к Redmine от вашего
          имени, как при входе по LDAP/паролю в Redmine.
        </p>
        {err && <p className="text-sm text-red-600 max-w-md">{err}</p>}
        <div className="card flex max-w-md flex-col gap-2">
          <label className="text-sm text-slate-600">Redmine user id (число)</label>
          <input
            className="rounded border border-slate-300 px-3 py-2"
            value={rid}
            onChange={(e) => setRid(e.target.value)}
            title="ID пользователя в Redmine (см. /users/ в Redmine)"
          />
          <label className="text-sm text-slate-600">Персональный API-ключ Redmine (необязательно)</label>
          <input
            className="rounded border border-slate-300 px-3 py-2 font-mono text-sm"
            type="password"
            autoComplete="off"
            value={rmKey}
            onChange={(e) => setRmKey(e.target.value)}
            placeholder="скопируйте из My account → API access"
          />
          <label className="flex items-start gap-2 text-sm text-slate-700">
            <input
              type="checkbox"
              className="mt-0.5"
              checked={skipApiVerify}
              onChange={(e) => setSkipApiVerify(e.target.checked)}
            />
            <span>
              Сохранить без проверки API — если с сервера R3 к Redmine везде <strong>403</strong> (ip,
              WAF, прокси), а в браузере тот же ключ работает. Id и ключ должны быть верными.
            </span>
          </label>
          <button
            type="button"
            className="btn-primary inline-flex w-fit items-center gap-1"
            disabled={profileSaving}
            onClick={async () => {
              setErr("");
              setProfileSaving(true);
              try {
                const n = parseInt(rid, 10);
                if (!Number.isFinite(n) || n < 1) {
                  setErr("Укажите корректный числовой id (≥ 1).");
                  return;
                }
                const body: Record<string, string | number | boolean> = {
                  redmine_user_id: n,
                };
                if (rmKey.trim()) {
                  body.redmine_api_key = rmKey.trim();
                }
                if (skipApiVerify) {
                  body.skip_redmine_verify = true;
                }
                await jsonFetch("/api/profile", {
                  method: "PATCH",
                  body: JSON.stringify(body),
                });
                setRmKey("");
                await refresh();
              } catch (e) {
                setErr(e instanceof Error ? e.message : "Ошибка");
              } finally {
                setProfileSaving(false);
              }
            }}
          >
            {profileSaving && <Loader2 className="h-4 w-4 shrink-0 animate-spin" />}
            {profileSaving ? "Сохраняем…" : "Сохранить"}
          </button>
        </div>
      </div>
    );
  }

  const baseUrl = settings?.redmine_base_url ?? null;
  const sprint = settings?.sprint_lifecycle_days ?? 14;

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold">Workbench</h1>
      <p className="text-sm text-slate-500">
        Показаны открытые назначенные вам задачи, отфильтрованные по «протуханию»
        (дольше, чем Sprint Livecycle, от последнего обновления). Кружок — наглядная шкала
        от порога спринта до 600 дней, оттенок смещается каждые 14 дней. Проверка TLS к Redmine —
        глобально в «Настройки» (админ).
      </p>
      {err && <p className="text-sm text-red-600">{err}</p>}
      <div className="flex flex-wrap items-end gap-2 rounded-lg border border-slate-200/80 bg-slate-50/50 px-3 py-2">
        <div className="flex min-w-[12rem] flex-1 flex-col gap-0.5">
          <span className="text-xs text-slate-500">Разбивка по номеру в Redmine</span>
          <form
            className="flex flex-wrap items-center gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              const id = parseInt(openById.trim(), 10);
              if (Number.isNaN(id) || id < 1) {
                setErr("Укажите номер задачи (целое положительное число).");
                return;
              }
              setErr("");
              void (async () => {
                const ok = await loadIssueForSplit(id);
                if (ok) {
                  setOpenById("");
                }
              })();
            }}
          >
            <input
              className="w-32 rounded border border-slate-300 bg-white px-2 py-1.5 font-mono text-sm tabular-nums"
              type="text"
              inputMode="numeric"
              placeholder="напр. 4821"
              value={openById}
              disabled={openByIdLoading}
              onChange={(e) => setOpenById(e.target.value.replace(/\D/g, ""))}
            />
            <button
              type="submit"
              className="btn-primary inline-flex items-center gap-1 text-sm"
              disabled={openByIdLoading || !openById.trim()}
            >
              {openByIdLoading ? (
                <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin" />
              ) : null}
              {openByIdLoading ? "Открываем…" : "Открыть разбивку"}
            </button>
          </form>
        </div>
        <p className="max-w-md pb-0.5 text-xs text-slate-500">
          Не нужно искать в списке: откроется панель разбивки, если задача назначена на вас. Ссылка:{" "}
          <code className="rounded bg-slate-100 px-1 text-[0.7rem]">/workbench?issue=</code> и id.
        </p>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm">Сортировка</span>
        <select
          className="rounded border border-slate-300 bg-white px-2 py-1 text-sm"
          value={sort}
          onChange={(e) => setSort(e.target.value as typeof sort)}
        >
          <option value="stale">По протуханию</option>
          <option value="date">По дате</option>
          <option value="criticality">По критичности</option>
        </select>
        <label className="flex items-center gap-1 text-sm">
          <input
            type="checkbox"
            checked={onlyStale}
            onChange={(e) => setOnlyStale(e.target.checked)}
          />
          Только «тянущие» задачи
        </label>
        <button
          type="button"
          className="btn-ghost inline-flex items-center gap-1"
          disabled={listLoading}
          onClick={() => void load()}
        >
          {listLoading && <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin opacity-80" />}
          {listLoading ? "Список…" : "Обновить"}
        </button>
      </div>
      <div className="grid min-h-0 grid-cols-1 gap-4 lg:grid-cols-[minmax(0,19rem)_minmax(0,1fr)] lg:items-stretch xl:grid-cols-[22rem_minmax(0,1fr)]">
        <div
          className="card flex min-h-0 min-w-0 max-h-[min(88vh,920px)] flex-col overflow-hidden p-0"
        >
          <h2 className="flex shrink-0 items-center justify-between gap-2 border-b border-slate-100 px-4 py-2 text-sm font-medium text-slate-700">
            <span>Мои открытые ({issues.length})</span>
            {listLoading && (
              <span className="inline-flex items-center gap-1 text-xs font-normal text-slate-500">
                <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin" />
                загрузка…
              </span>
            )}
          </h2>
          <ul className="min-h-0 flex-1 overflow-y-auto">
            {issues.map((i) => {
              const st = stalenessStyle(sprint, i.stagnation_days);
              return (
                <li key={i.id}>
                  <button
                    type="button"
                    className={`flex w-full items-start gap-2 border-b border-slate-100 px-4 py-2 text-left hover:bg-slate-50 ${
                      sel?.id === i.id ? "bg-brand-50" : ""
                    }`}
                    title={i.subject}
                    onClick={() => {
                      setSel(i);
                      setSug([]);
                    }}
                  >
                    <span
                      className="mt-1.5 h-3 w-3 shrink-0 rounded-full border border-white/30 shadow"
                      style={{ background: st.background }}
                      title={st.title}
                    />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 text-sm">
                        {i.criticality >= 4 && <AlertTriangle className="h-4 w-4 text-amber-600" />}
                        {redmineIssueUrl(baseUrl, i.id) ? (
                          <a
                            href={redmineIssueUrl(baseUrl, i.id)!}
                            target="_blank"
                            rel="noreferrer"
                            className="font-mono text-xs text-brand-700 hover:underline"
                            onClick={(e) => e.stopPropagation()}
                          >
                            #{i.id}
                            <ExternalLink className="ml-0.5 inline h-3 w-3 opacity-60" />
                          </a>
                        ) : (
                          <span className="font-mono text-xs text-slate-400">#{i.id}</span>
                        )}
                        <span className="line-clamp-1 font-medium text-slate-800">{i.subject}</span>
                      </div>
                      <div className="text-xs text-slate-500">
                        {i.project_name} · {i.stagnation_days} дн. без движения
                        {i.complexity ? ` · ${i.complexity}` : ""}
                      </div>
                    </div>
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
        <div
          className="card flex min-h-0 min-w-0 max-h-[min(88vh,920px)] flex-col overflow-hidden p-0"
        >
          <h2 className="shrink-0 border-b border-slate-100 px-3 py-2 text-sm font-medium text-slate-700">
            Разбивка
          </h2>
          <div
            ref={splitScrollRef}
            className="min-h-0 flex-1 space-y-3 overflow-y-auto px-3 py-3"
          >
            {sel ? (
              <>
                {contextLoading && (
                  <div className="flex items-center gap-2 rounded-lg border border-slate-200 bg-slate-50/80 px-3 py-3 text-sm text-slate-600">
                    <Loader2 className="h-4 w-4 shrink-0 animate-spin text-brand-600" />
                    <span>Загружаем подзадачи и связи из Redmine…</span>
                  </div>
                )}
                {!contextLoading && context && context.issue.id === sel.id && (
                  <div className="relative rounded-lg border border-slate-200 bg-slate-50/60 p-3 text-sm">
                    {contextRefreshing && (
                      <div
                        className="absolute inset-0 z-10 flex items-center justify-center gap-2 rounded-lg border border-slate-200/80 bg-slate-50/90 text-xs text-slate-600"
                        aria-live="polite"
                      >
                        <Loader2 className="h-4 w-4 shrink-0 animate-spin text-brand-600" />
                        Обновляем подзадачи и связи…
                      </div>
                    )}
                    <p className="text-xs font-medium text-slate-600">Связи в Redmine</p>
                    {context.subtasks.length > 0 && (
                      <ul className="mt-1 space-y-0.5">
                        <li className="text-xs text-slate-500">Подзадачи</li>
                        {context.subtasks.map((c) => (
                          <li key={c.id}>
                            {redmineIssueUrl(baseUrl, c.id) ? (
                              <a
                                href={redmineIssueUrl(baseUrl, c.id)!}
                                className="text-brand-700 hover:underline"
                                target="_blank"
                                rel="noreferrer"
                              >
                                #{c.id} {c.subject}
                              </a>
                            ) : (
                              <span>
                                #{c.id} {c.subject}
                              </span>
                            )}
                          </li>
                        ))}
                      </ul>
                    )}
                    {context.related.length > 0 && (
                      <ul className="mt-2 space-y-0.5">
                        <li className="text-xs text-slate-500">Связанные задачи</li>
                        {context.related.map((c) => (
                          <li key={`${c.id}-${c.relation_type}`}>
                            <span className="text-xs text-slate-400">[{c.relation_type}] </span>
                            {redmineIssueUrl(baseUrl, c.id) ? (
                              <a
                                href={redmineIssueUrl(baseUrl, c.id)!}
                                className="text-brand-700 hover:underline"
                                target="_blank"
                                rel="noreferrer"
                              >
                                #{c.id} {c.subject}
                              </a>
                            ) : (
                              <span>
                                #{c.id} {c.subject}
                              </span>
                            )}
                          </li>
                        ))}
                      </ul>
                    )}
                    {context.subtasks.length === 0 && context.related.length === 0 && (
                      <p className="text-xs text-slate-500">Нет дочерних и связанных (в Redmine).</p>
                    )}
                  </div>
                )}

                <p className="text-sm text-slate-800">{sel.subject}</p>
                <p className="line-clamp-6 text-xs text-slate-500 whitespace-pre-wrap">
                  {sel.description || "— нет описания —"}
                </p>
                <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
                  <button
                    type="button"
                    className="btn-primary inline-flex items-center gap-1"
                    disabled={splitLoading}
                    onClick={async () => {
                      setErr("");
                      setSplitLastMs(null);
                      setSplitLiveMs(0);
                      setSplitLoading(true);
                      const t0 = performance.now();
                      const tick = setInterval(() => {
                        setSplitLiveMs(performance.now() - t0);
                      }, 100);
                      try {
                        const s = await jsonFetch<Suggestion[]>(
                          `/api/issues/${sel.id}/suggest-split`,
                          { method: "POST", body: JSON.stringify({ extra_prompt: "" }) }
                        );
                        setSug(s);
                        setSplitLastMs(performance.now() - t0);
                      } catch (e) {
                        setErr(e instanceof Error ? e.message : "Ошибка");
                        setSplitLastMs(performance.now() - t0);
                      } finally {
                        clearInterval(tick);
                        setSplitLoading(false);
                        setSplitLiveMs(0);
                      }
                    }}
                  >
                    {splitLoading ? (
                      <Loader2 className="h-4 w-4 shrink-0 animate-spin" />
                    ) : (
                      <Wand2 className="h-4 w-4" />
                    )}
                    {splitLoading ? "Запрос к ИИ…" : "Предложить (ИИ)"}
                  </button>
                  {splitLoading && (
                    <span
                      className="inline-flex items-center gap-1.5 text-sm text-slate-600 tabular-nums"
                      aria-live="polite"
                    >
                      <Timer className="h-3.5 w-3.5 shrink-0 text-slate-400" />
                      {formatDurationSec(splitLiveMs)}
                    </span>
                  )}
                  {!splitLoading && splitLastMs != null && (
                    <span className="inline-flex items-center gap-1.5 text-sm text-slate-500 tabular-nums">
                      <Timer className="h-3.5 w-3.5 shrink-0 text-slate-400" />
                      {formatDurationSec(splitLastMs)}
                    </span>
                  )}
                  {redmineIssueUrl(baseUrl, sel.id) && (
                    <a
                      href={redmineIssueUrl(baseUrl, sel.id)!}
                      target="_blank"
                      className="btn-ghost inline-flex items-center gap-1"
                      rel="noreferrer"
                    >
                      Открыть в Redmine <ExternalLink className="h-4 w-4" />
                    </a>
                  )}
                  <button
                    type="button"
                    className="btn-ghost inline-flex items-center gap-1"
                    disabled={complexityLoading}
                    onClick={async () => {
                      setErr("");
                      setComplexityLoading(true);
                      try {
                        const c = await jsonFetch<{ value: string }>(
                          `/api/issues/${sel.id}/suggest-complexity`,
                          { method: "POST", body: JSON.stringify({}) }
                        );
                        await jsonFetch(
                          `/api/issues/${sel.id}/complexity?value=${encodeURIComponent(
                            c.value
                          )}`,
                          { method: "PUT" }
                        );
                        await load();
                      } catch (e) {
                        setErr(e instanceof Error ? e.message : "Ошибка");
                      } finally {
                        setComplexityLoading(false);
                      }
                    }}
                  >
                    {complexityLoading && (
                      <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin opacity-80" />
                    )}
                    {complexityLoading ? "Сложность…" : "Сложность (ИИ) →"}
                  </button>
                </div>
                {sug.length > 0 && (
                  <p className="text-xs text-slate-500">
                    Показано {Math.min(sugVisibleCount, sug.length)} из {sug.length} предложений
                    {sug.length > SUG_SCROLL_PAGE
                      ? " — пролистайте вниз, чтобы подгрузить ещё"
                      : ""}
                  </p>
                )}
                <ul className="space-y-2">
                  {sug.slice(0, sugVisibleCount).map((s, j) => (
                    <li key={j} className="rounded-lg border border-slate-200 p-3 text-sm">
                      <div className="font-medium">{s.subject}</div>
                      <div className="mt-1 whitespace-pre-wrap break-words text-slate-600">
                        {s.description}
                      </div>
                      <button
                        type="button"
                        className="btn-ghost mt-2 inline-flex items-center gap-1"
                        disabled={subtaskSubmitting !== null}
                        onClick={async () => {
                          setErr("");
                          setSubtaskSubmitting(j);
                          try {
                            await jsonFetch<Issue>(`/api/issues/${sel.id}/subtasks`, {
                              method: "POST",
                              body: JSON.stringify({
                                subject: s.subject,
                                description: s.description,
                              }),
                            });
                            setContextRefreshing(true);
                            await load();
                            const ctx = await jsonFetch<IssueContext>(
                              `/api/issues/${sel.id}/context`
                            );
                            if (ctx.issue.id === sel.id) {
                              setContext(ctx);
                            }
                          } catch (e) {
                            setErr(e instanceof Error ? e.message : "Ошибка");
                          } finally {
                            setSubtaskSubmitting(null);
                            setContextRefreshing(false);
                          }
                        }}
                      >
                        {subtaskSubmitting === j && (
                          <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin" />
                        )}
                        {subtaskSubmitting === j
                          ? "Создаём…"
                          : "Создать подзадачу в Redmine"}
                      </button>
                    </li>
                  ))}
                </ul>
                {sug.length > 0 && sugVisibleCount < sug.length && (
                  <div
                    ref={sugLoadMoreRef}
                    className="py-1 text-center text-xs text-slate-400"
                    aria-hidden
                  >
                    …
                  </div>
                )}
              </>
            ) : (
              <p className="text-sm text-slate-500">Выберите задачу слева.</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
