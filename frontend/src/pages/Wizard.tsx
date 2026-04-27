import { useCallback, useEffect, useState } from "react";
import { jsonFetch } from "../api";
import { useAuth } from "../auth";
import { ChevronLeft, ChevronRight, Loader2, Sparkles } from "lucide-react";

type Issue = {
  id: number;
  subject: string;
  description: string;
  stagnation_days: number;
  status_id: number;
  status_name: string;
  project_name: string;
  priority_name?: string;
  spent_hours: number;
};

type Queue = Issue[];

type Hint = Record<string, unknown>;

type StatusOpt = { id: number; name: string };

/**
 * Renders model JSON in readable Russian lines (wizard AI schema).
 */
function WizardHintView({ hint }: { hint: Hint }) {
  if (typeof hint.summary === "string" && Object.keys(hint).length === 1) {
    return <p className="text-sm text-amber-950">{hint.summary}</p>;
  }
  const line = (label: string, v: string | null | undefined) =>
    v != null && v !== "" ? (
      <p>
        <span className="font-medium text-amber-900">{label}:</span> {v}
      </p>
    ) : null;
  return (
    <div className="space-y-1.5 text-sm text-amber-950">
      {line("Кратко", typeof hint.summary === "string" ? hint.summary : null)}
      {typeof hint.close === "boolean" && (
        <p>
          <span className="font-medium text-amber-900">Закрыть задачу:</span>{" "}
          {hint.close ? "да" : "нет"}
        </p>
      )}
      {typeof hint.split === "boolean" && (
        <p>
          <span className="font-medium text-amber-900">Разбить на подзадачи:</span>{" "}
          {hint.split ? "да" : "нет"}
        </p>
      )}
      {hint.time_hours != null && (
        <p>
          <span className="font-medium text-amber-900">Предлагаемые часы:</span>{" "}
          {String(hint.time_hours)}
        </p>
      )}
      {line(
        "Статус (идея)",
        typeof hint.new_status_suggestion === "string" ? hint.new_status_suggestion : null
      )}
      {line("Комментарий", typeof hint.comment === "string" ? hint.comment : null)}
    </div>
  );
}

/**
 * Tinder-style wizard: centered card, full issue text, AI hint, status from workflow, notes.
 */
export default function Wizard() {
  const { user, refresh } = useAuth();
  const [q, setQ] = useState<Queue>([]);
  const [ix, setIx] = useState(0);
  const [rid, setRid] = useState(String(user?.redmine_user_id ?? ""));
  const [rmKey, setRmKey] = useState("");
  const [hint, setHint] = useState<Hint | null>(null);
  const [err, setErr] = useState("");
  const [linkSaving, setLinkSaving] = useState(false);
  const [skipApiVerify, setSkipApiVerify] = useState(false);
  const [aiLoading, setAiLoading] = useState(false);
  const [card, setCard] = useState<Issue | null>(null);
  const [cardLoading, setCardLoading] = useState(false);
  const [statuses, setStatuses] = useState<StatusOpt[]>([]);
  const [statusLoading, setStatusLoading] = useState(false);
  const [statusPick, setStatusPick] = useState("");
  const [note, setNote] = useState("");

  const load = useCallback(async () => {
    setErr("");
    try {
      const list = await jsonFetch<Queue>("/api/wizard/queue");
      setQ(list);
      setIx(0);
      setHint(null);
      setNote("");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Ошибка");
    }
  }, []);

  useEffect(() => {
    if (user?.redmine_user_id) {
      void load();
    }
  }, [load, user?.redmine_user_id]);

  const cur = q[ix] ?? null;
  const curId = cur?.id;

  useEffect(() => {
    setHint(null);
    setAiLoading(false);
    setNote("");
    setStatusPick("");
    if (curId == null) {
      setCard(null);
      setStatuses([]);
      return;
    }
    let cancel = false;
    setCardLoading(true);
    setStatusLoading(true);
    void (async () => {
      try {
        const [c, st] = await Promise.all([
          jsonFetch<Issue>(`/api/wizard/${curId}/card`),
          jsonFetch<StatusOpt[]>(`/api/wizard/${curId}/status-options`),
        ]);
        if (!cancel) {
          setCard(c);
          setStatuses(st.filter((s) => s.id !== c.status_id));
        }
      } catch (e) {
        if (!cancel) {
          setErr(e instanceof Error ? e.message : "Ошибка загрузки карточки");
          setCard(null);
          setStatuses([]);
        }
      } finally {
        if (!cancel) {
          setCardLoading(false);
          setStatusLoading(false);
        }
      }
    })();
    return () => {
      cancel = true;
    };
  }, [curId]);

  const goNext = () => {
    setIx((i) => {
      const max = Math.max(0, q.length - 1);
      return Math.min(i + 1, max);
    });
  };

  const goPrev = () => setIx((i) => Math.max(0, i - 1));

  if (!user?.redmine_user_id) {
    return (
      <div className="space-y-4">
        <h1 className="text-xl font-bold">Task Wizard</h1>
        <p className="text-slate-600">Сначала привяжите Redmine user id (как в Workbench).</p>
        <p className="text-xs text-slate-500 max-w-md">
          При необходимости укажите персональный API-ключ из Redmine (Моя учётная запись → API access),
          если сервисный ключ в настройках R3 не видит пользователей.
        </p>
        {err && <p className="text-sm text-red-600 max-w-md">{err}</p>}
        <div className="card flex max-w-md flex-col gap-2">
          <label className="text-sm text-slate-600">Redmine user id</label>
          <input
            className="rounded border border-slate-300 px-3 py-2"
            value={rid}
            onChange={(e) => setRid(e.target.value)}
          />
          <label className="text-sm text-slate-600">Персональный API-ключ (необязательно)</label>
          <input
            className="rounded border border-slate-300 px-3 py-2 font-mono text-sm"
            type="password"
            autoComplete="off"
            value={rmKey}
            onChange={(e) => setRmKey(e.target.value)}
          />
          <label className="flex items-start gap-2 text-sm text-slate-700">
            <input
              type="checkbox"
              className="mt-0.5"
              checked={skipApiVerify}
              onChange={(e) => setSkipApiVerify(e.target.checked)}
            />
            <span>
              Сохранить без проверки API, если с сервера R3 к Redmine везде 403, а ключ в браузере
              рабочий.
            </span>
          </label>
          <button
            type="button"
            className="btn-primary inline-flex w-fit items-center gap-1"
            disabled={linkSaving}
            onClick={async () => {
              setErr("");
              setLinkSaving(true);
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
                void refresh();
              } catch (e) {
                setErr(e instanceof Error ? e.message : "Ошибка");
              } finally {
                setLinkSaving(false);
              }
            }}
          >
            {linkSaving && <Loader2 className="h-4 w-4 shrink-0 animate-spin" />}
            Сохранить
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-[calc(100vh-7rem)] flex-col items-center px-3">
      <div className="w-full max-w-lg flex-1 space-y-4">
        <h1
          className="text-center text-xl font-bold"
          title="Карта задачи, быстрые действия, подсказка ИИ"
        >
          Task Wizard
        </h1>
        {err && <p className="text-center text-sm text-red-600">{err}</p>}

        <div
          className="card space-y-4 border border-slate-200/80 shadow-md"
          title="Листайте кнопками, выполняйте действия. ИИ по кнопке — опционален"
        >
          {cur && card && card.id === cur.id && !cardLoading ? (
            <>
              <div className="text-center text-xs text-slate-500">
                {ix + 1} / {q.length}
              </div>
              <h2 className="text-center text-lg font-semibold">
                #{cur.id} — {cur.subject}
              </h2>
              <p className="text-center text-sm text-slate-500">
                {card.project_name} · {card.status_name}
                {card.priority_name ? ` · ${card.priority_name}` : ""} · {card.spent_hours} ч. списано
              </p>
              <p className="text-center text-sm text-slate-500" title="Дней с последнего обновления">
                Протухание: {card.stagnation_days} дн.
              </p>
              <div
                className="max-h-40 overflow-y-auto rounded-md border border-slate-200 bg-slate-50/80 p-3 text-xs text-slate-800 whitespace-pre-wrap"
                title="Описание задачи из Redmine"
              >
                {card.description?.trim() ? card.description : "— нет описания —"}
              </div>

              {aiLoading && (
                <div
                  className="flex items-center justify-center gap-2 rounded-lg bg-amber-50/80 py-3 text-sm text-amber-900"
                >
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Запрашиваем подсказку ИИ…
                </div>
              )}

              {!aiLoading && hint && (
                <div
                  className="rounded-lg bg-amber-50 p-3 text-amber-950"
                  title="Ответ по схеме Task Wizard"
                >
                  <WizardHintView hint={hint} />
                </div>
              )}

              <div className="flex flex-wrap justify-center gap-2">
                <button
                  type="button"
                  className="btn-primary inline-flex items-center gap-1"
                  disabled={aiLoading}
                  onClick={async () => {
                    setErr("");
                    setAiLoading(true);
                    setHint(null);
                    try {
                      const h = await jsonFetch<Hint>(`/api/wizard/${cur.id}/ai-hint`, {
                        method: "POST",
                        body: JSON.stringify({ use_ai: true }),
                      });
                      setHint(h);
                    } catch (e) {
                      setErr(e instanceof Error ? e.message : "Ошибка");
                    } finally {
                      setAiLoading(false);
                    }
                  }}
                  title="Ключи в настройках; промпты в Профиле"
                >
                  {aiLoading ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Sparkles className="h-4 w-4" />
                  )}{" "}
                  Подсказка ИИ
                </button>
              </div>

              <div className="space-y-2 border-t border-slate-100 pt-3">
                <label className="block text-xs font-medium text-slate-600">Сменить статус</label>
                {statusLoading ? (
                  <p className="text-xs text-slate-500">Загрузка статусов…</p>
                ) : (
                  <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
                    <select
                      className="flex-1 rounded border border-slate-300 bg-white px-2 py-2 text-sm"
                      value={statusPick}
                      onChange={(e) => setStatusPick(e.target.value)}
                      title="Допустимые переходы по workflow (Redmine 5+)"
                    >
                      <option value="">— выберите статус —</option>
                      {statuses.map((s) => (
                        <option key={s.id} value={String(s.id)}>
                          {s.name}
                        </option>
                      ))}
                    </select>
                    <button
                      type="button"
                      className="btn-ghost text-sm"
                      disabled={!statusPick}
                      onClick={async () => {
                        if (!statusPick) {
                          return;
                        }
                        setErr("");
                        try {
                          await jsonFetch(`/api/wizard/${cur.id}/action`, {
                            method: "POST",
                            body: JSON.stringify({
                              action: "status",
                              status_id: parseInt(statusPick, 10),
                              note: note.trim() || null,
                            }),
                          });
                          goNext();
                        } catch (e) {
                          setErr(e instanceof Error ? e.message : "Ошибка");
                        }
                      }}
                    >
                      Применить
                    </button>
                  </div>
                )}
              </div>

              <div className="grid grid-cols-2 gap-2 text-sm">
                <button
                  type="button"
                  className="btn-ghost"
                  onClick={async () => {
                    setErr("");
                    try {
                      await jsonFetch(`/api/wizard/${cur.id}/action`, {
                        method: "POST",
                        body: JSON.stringify({ action: "keep" }),
                      });
                      goNext();
                    } catch (e) {
                      setErr(e instanceof Error ? e.message : "Ошибка");
                    }
                  }}
                  title="Ничего не менять, следующая"
                >
                  Пропустить
                </button>
                <button
                  type="button"
                  className="btn-ghost"
                  onClick={async () => {
                    setErr("");
                    const h = window.prompt("Часов (число, например 1.5)", "1");
                    if (h) {
                      try {
                        await jsonFetch(`/api/wizard/${cur.id}/action`, {
                          method: "POST",
                          body: JSON.stringify({
                            action: "time",
                            hours: parseFloat(h),
                            note: note.trim() || "R3 wizard",
                          }),
                        });
                        goNext();
                      } catch (e) {
                        setErr(e instanceof Error ? e.message : "Ошибка");
                      }
                    }
                  }}
                  title="Добавит time entry; комментарий — из поля примечания"
                >
                  Трудозатраты
                </button>
              </div>

              <div className="flex justify-between border-t border-slate-100 pt-2">
                <button type="button" className="btn-ghost" onClick={goPrev} title="Предыдущая">
                  <ChevronLeft className="h-5 w-5" />
                </button>
                <button
                  type="button"
                  className="btn-ghost"
                  onClick={() => goNext()}
                  title="Следующая"
                >
                  <ChevronRight className="h-5 w-5" />
                </button>
              </div>
            </>
          ) : cur && cardLoading ? (
            <div className="flex items-center justify-center gap-2 py-12 text-slate-500">
              <Loader2 className="h-5 w-5 animate-spin" />
              Загрузка карточки…
            </div>
          ) : cur && !card ? (
            <p className="text-center text-sm text-amber-800">
              Не удалось загрузить карточку задачи. Попробуйте «Обновить очередь».
            </p>
          ) : !cur ? (
            <p className="text-center text-slate-500">
              Очередь пуста — нет «протухших» открытых задач.
            </p>
          ) : null}

          {cur && (
            <div className="mt-3 space-y-2 border-t border-slate-200 pt-3">
              <label className="block w-full text-left text-xs text-slate-600">
                Примечание к журналу Redmine
                <textarea
                  className="mt-1 w-full rounded border border-slate-300 px-2 py-2 text-sm"
                  rows={3}
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  placeholder="Смена статуса, трудозатраты, отдельная кнопка — всё пишет в журнал"
                />
              </label>
              {!cardLoading && card?.id === cur.id && (
                <button
                  type="button"
                  className="btn-ghost w-full text-sm"
                  disabled={!note.trim()}
                  onClick={async () => {
                    setErr("");
                    try {
                      await jsonFetch(`/api/wizard/${cur.id}/action`, {
                        method: "POST",
                        body: JSON.stringify({ action: "comment", note: note.trim() }),
                      });
                      setNote("");
                      goNext();
                    } catch (e) {
                      setErr(e instanceof Error ? e.message : "Ошибка");
                    }
                  }}
                >
                  Только примечание
                </button>
              )}
            </div>
          )}

          <button type="button" className="btn-primary w-full" onClick={() => void load()}>
            Обновить очередь
          </button>
        </div>
      </div>
    </div>
  );
}
