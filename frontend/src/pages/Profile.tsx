import { useCallback, useEffect, useState } from "react";
import { jsonFetch } from "../api";
import { useAuth } from "../auth";

type Me = { ai_prompts: Record<string, string> };

/**
 * Per-user AI system prompt overrides (merged with R3 defaults on the server).
 */
export default function Profile() {
  const { user, refresh } = useAuth();
  const [split, setSplit] = useState("");
  const [comp, setComp] = useState("");
  const [wiz, setWiz] = useState("");
  const [msg, setMsg] = useState("");

  const load = useCallback(async () => {
    if (!user) {
      return;
    }
    const me = await jsonFetch<Me>("/api/auth/me");
    const p = me.ai_prompts || {};
    setSplit(p.split_system ?? "");
    setComp(p.complexity_system ?? "");
    setWiz(p.wizard_system ?? "");
  }, [user]);

  useEffect(() => {
    void load();
  }, [load]);

  if (!user) {
    return null;
  }

  return (
    <div className="max-w-3xl space-y-4">
      <h1 className="text-xl font-bold">Профиль и промпты ИИ</h1>
      <p className="text-sm text-slate-600">
        Системные инструкции для разбивки, оценки сложности и Task Wizard. Пустое поле — встроенный
        текст по умолчанию. Настройки Redmine (проект, версия, исполнитель) при создании подзадачи
        копируются с родительской задачи.
      </p>
      {msg && <p className="text-sm text-green-700">{msg}</p>}
      <div className="card space-y-4">
        <label className="block space-y-1">
          <span className="text-sm font-medium text-slate-700">Разбивка (system)</span>
          <textarea
            className="min-h-[100px] w-full rounded border border-slate-300 px-3 py-2 font-mono text-xs"
            value={split}
            onChange={(e) => setSplit(e.target.value)}
            spellCheck={false}
          />
        </label>
        <label className="block space-y-1">
          <span className="text-sm font-medium text-slate-700">Сложность s–2xl (system)</span>
          <textarea
            className="min-h-[80px] w-full rounded border border-slate-300 px-3 py-2 font-mono text-xs"
            value={comp}
            onChange={(e) => setComp(e.target.value)}
            spellCheck={false}
          />
        </label>
        <label className="block space-y-1">
          <span className="text-sm font-medium text-slate-700">Task Wizard (system)</span>
          <textarea
            className="min-h-[100px] w-full rounded border border-slate-300 px-3 py-2 font-mono text-xs"
            value={wiz}
            onChange={(e) => setWiz(e.target.value)}
            spellCheck={false}
          />
        </label>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            className="btn-primary"
            onClick={async () => {
              setMsg("");
              try {
                await jsonFetch("/api/profile", {
                  method: "PATCH",
                  body: JSON.stringify({
                    ai_prompts: {
                      split_system: split,
                      complexity_system: comp,
                      wizard_system: wiz,
                    },
                  }),
                });
                await refresh();
                setMsg("Сохранено.");
              } catch (e) {
                setMsg(e instanceof Error ? e.message : "Ошибка");
              }
            }}
          >
            Сохранить промпты
          </button>
        </div>
      </div>
    </div>
  );
}
