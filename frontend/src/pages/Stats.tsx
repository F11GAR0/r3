import { useState } from "react";
import { jsonFetch } from "../api";
import { useAuth } from "../auth";
import { BarChart3 } from "lucide-react";

type Summary = {
  userId: number;
  username: string;
  splitsInPeriod: number;
  redmineSpentHours: number;
  workingDaysInRange: number;
  velocityHintHoursPerWorkingDay: number;
  sprintLifecycleDays: number;
};

/**
 * PM statistics: time range, optional user, velocity hint.
 */
export default function Stats() {
  const { user } = useAuth();
  const [from, setFrom] = useState("2026-01-01");
  const [to, setTo] = useState("2026-12-31");
  const [uid, setUid] = useState<string>("");
  const [d, setD] = useState<Summary | null>(null);
  const [err, setErr] = useState("");

  return (
    <div className="space-y-4">
      <h1
        className="flex items-center gap-2 text-xl font-bold"
        title="Продакт и админ: можно выбрать user id"
      >
        <BarChart3 className="h-6 w-6" /> Статистика
      </h1>
      <p className="text-sm text-slate-500" title="Суббота/воскресенье: только рабочие дни в расчёте">
        Суббота и воскресенье не входят в количество рабочих дней в периоде. Velocity-оценка
        = часы / рабочие дни.
      </p>
      <div className="card flex max-w-2xl flex-wrap gap-3">
        <label className="text-sm">
          С
          <input
            type="date"
            className="ml-1 rounded border border-slate-200 px-2"
            value={from}
            onChange={(e) => setFrom(e.target.value)}
          />
        </label>
        <label className="text-sm">
          По
          <input
            type="date"
            className="ml-1 rounded border border-slate-200 px-2"
            value={to}
            onChange={(e) => setTo(e.target.value)}
          />
        </label>
        {["superadmin", "admin", "product_manager"].includes(user?.role ?? "") && (
          <label className="text-sm" title="Внутренний id пользователя R3">
            User id
            <input
              className="ml-1 w-20 rounded border border-slate-200 px-2"
              value={uid}
              onChange={(e) => setUid(e.target.value)}
              placeholder={String(user?.id ?? "")}
            />
          </label>
        )}
        <button
          type="button"
          className="btn-primary"
          onClick={async () => {
            setErr("");
            try {
              const qs = new URLSearchParams({
                from_date: from,
                to_date: to,
              });
              if (uid) {
                qs.set("target_user_id", uid);
              }
              const s = await jsonFetch<Summary>(`/api/stats/summary?${qs.toString()}`);
              setD(s);
            } catch (e) {
              setErr(e instanceof Error ? e.message : "Ошибка");
            }
          }}
        >
          Показать
        </button>
      </div>
      {err && <p className="text-sm text-red-600">{err}</p>}
      {d && (
        <div className="card grid max-w-2xl gap-2 sm:grid-cols-2">
          <div>
            <div className="text-xs text-slate-500">Пользователь</div>
            <div className="font-medium">
              {d.username} (id {d.userId})
            </div>
          </div>
          <div>
            <div className="text-xs text-slate-500" title="События разбивки/мастера в R3">События (splits) в БД R3</div>
            <div className="font-medium">{d.splitsInPeriod}</div>
          </div>
          <div>
            <div className="text-xs text-slate-500">Redmine, списанные часы (по API)</div>
            <div className="font-medium">{d.redmineSpentHours.toFixed(1)}</div>
          </div>
          <div>
            <div className="text-xs text-slate-500">Рабочих дней в диапазоне</div>
            <div className="font-medium">{d.workingDaysInRange}</div>
          </div>
          <div className="sm:col-span-2">
            <div className="text-xs text-slate-500" title="Грубая оценка">Ч/рабочий день (подсказка)</div>
            <div className="text-lg font-semibold text-brand-700">
              {d.velocityHintHoursPerWorkingDay.toFixed(2)}
            </div>
            <p className="text-xs text-slate-500">Sprint Livecycle: {d.sprintLifecycleDays} дн.</p>
          </div>
        </div>
      )}
    </div>
  );
}
