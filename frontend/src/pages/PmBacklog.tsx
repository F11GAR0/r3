import { useCallback, useEffect, useState } from "react";
import { jsonFetch } from "../api";
import { AlertTriangle } from "lucide-react";

type Issue = {
  id: number;
  subject: string;
  project_name: string;
  stagnation_days: number;
  criticality: number;
  status_name: string;
};

/**
 * Product manager view: project-wide open issues (stale optional).
 */
export default function PmBacklog() {
  const [issues, setIssues] = useState<Issue[]>([]);
  const [sort, setSort] = useState<"date" | "stale" | "criticality">("stale");
  const [onlyStale, setOnlyStale] = useState(true);
  const [err, setErr] = useState("");

  const load = useCallback(async () => {
    setErr("");
    try {
      const list = await jsonFetch<Issue[]>(
        `/api/pm/backlog?sort=${sort}&only_stale=${onlyStale}`
      );
      setIssues(list);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Ошибка");
    }
  }, [onlyStale, sort]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold" title="Требуется project id в настройках и роль product_manager+">
        Бэклог проекта (PM)
      </h1>
      {err && <p className="text-sm text-red-600">{err}</p>}
      <div className="flex flex-wrap items-center gap-2">
        <select
          className="rounded border border-slate-300 px-2 py-1 text-sm"
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
          Только «тянущие»
        </label>
        <button type="button" className="btn-ghost" onClick={() => void load()}>
          Обновить
        </button>
      </div>
      <ul className="card divide-y divide-slate-100 p-0">
        {issues.map((i) => (
          <li key={i.id} className="px-4 py-2">
            <div className="flex items-center gap-2 text-sm">
              {i.criticality >= 4 && <AlertTriangle className="h-4 w-4 text-amber-600" />}
              <span className="font-mono text-xs text-slate-400">#{i.id}</span>
              <span className="font-medium text-slate-800">{i.subject}</span>
            </div>
            <div className="text-xs text-slate-500">
              {i.project_name} · {i.status_name} · {i.stagnation_days} дн. без движения
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
