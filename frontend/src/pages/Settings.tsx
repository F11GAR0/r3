import { Loader2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { jsonFetch } from "../api";
import { isAdmin, isSuperAdmin, useAuth } from "../auth";

type Sett = {
  redmine_base_url: string | null;
  redmine_insecure_ssl: boolean;
  sprint_lifecycle_days: number;
  redmine_complexity_field_id: number | null;
  has_redmine: boolean;
  has_ai: boolean;
  project_id: number | null;
  ai_key_entries: { provider: string; name: string }[];
  ldap_enabled: boolean;
  ldap_server_uri: string | null;
  ldap_bind_dn: string | null;
  ldap_user_base_dn: string | null;
  ldap_user_filter: string | null;
  has_ldap_bind_password: boolean;
  ldap_effective: boolean;
};

type RoleRow = { id: string; label: string; description: string };

type AdminUser = {
  id: number;
  username: string;
  email: string | null;
  role: string;
  is_ldap: boolean;
  is_active: boolean;
};

type KeyRow = { provider: string; name: string; key: string };

type ProviderInfo = { id: string; label: string };

/**
 * Admin: Redmine (optional TLS verify off), list field id for complexity, AI keys (no delete), provider test.
 */
export default function Settings() {
  const { user } = useAuth();
  const [s, setS] = useState<Sett | null>(null);
  const [url, setUrl] = useState("");
  const [insecure, setInsecure] = useState(false);
  const [apiKey, setApiKey] = useState("");
  const [sprint, setSprint] = useState(14);
  const [cfid, setCfid] = useState<string>("");
  const [proj, setProj] = useState<string>("");
  const [keys, setKeys] = useState<KeyRow[]>([]);
  const [msg, setMsg] = useState("");
  const [providerCatalogue, setProviderCatalogue] = useState<ProviderInfo[]>([]);
  const [testMsg, setTestMsg] = useState<Record<string, string>>({});
  const [ldapEnabled, setLdapEnabled] = useState(false);
  const [ldapUri, setLdapUri] = useState("");
  const [ldapBindDn, setLdapBindDn] = useState("");
  const [ldapBindPassword, setLdapBindPassword] = useState("");
  const [ldapUserBase, setLdapUserBase] = useState("");
  const [ldapFilter, setLdapFilter] = useState("(uid={username})");
  const [ldapTestUser, setLdapTestUser] = useState("");
  const [ldapTestPass, setLdapTestPass] = useState("");
  const [ldapTestMsg, setLdapTestMsg] = useState("");
  const [roleRows, setRoleRows] = useState<RoleRow[]>([]);
  const [adminUsers, setAdminUsers] = useState<AdminUser[]>([]);
  const [userMsg, setUserMsg] = useState("");
  const [ldapSaveMsg, setLdapSaveMsg] = useState("");
  const [ldapSaveErr, setLdapSaveErr] = useState("");
  const [ldapSaving, setLdapSaving] = useState(false);
  const [ldapProvisionLogin, setLdapProvisionLogin] = useState("");
  const [provisionFromLdapLoading, setProvisionFromLdapLoading] = useState(false);
  const [provisionFromLdapMsg, setProvisionFromLdapMsg] = useState("");
  const [provisionFromLdapErr, setProvisionFromLdapErr] = useState("");
  const [bootstrapNew, setBootstrapNew] = useState("");
  const [bootstrapCurrent, setBootstrapCurrent] = useState("");
  const [bootstrapMsg, setBootstrapMsg] = useState("");
  const [bootstrapErr, setBootstrapErr] = useState("");
  const [bootstrapSaving, setBootstrapSaving] = useState(false);

  const canBootstrapPassword =
    isAdmin(user) && (isSuperAdmin(user) || user?.username === "admin");

  const load = useCallback(async () => {
    const j = await jsonFetch<Sett>("/api/settings");
    setS(j);
    setUrl(j.redmine_base_url ?? "");
    setInsecure(!!j.redmine_insecure_ssl);
    setSprint(j.sprint_lifecycle_days);
    setCfid(j.redmine_complexity_field_id != null ? String(j.redmine_complexity_field_id) : "");
    setProj(j.project_id != null ? String(j.project_id) : "");
    setKeys(
      j.ai_key_entries.length > 0
        ? j.ai_key_entries.map((e) => ({ provider: e.provider, name: e.name, key: "" }))
        : [{ provider: "openai", name: "default", key: "" }]
    );
    setLdapEnabled(!!j.ldap_enabled);
    setLdapUri(j.ldap_server_uri ?? "");
    setLdapBindDn(j.ldap_bind_dn ?? "");
    setLdapUserBase(j.ldap_user_base_dn ?? "");
    setLdapFilter(j.ldap_user_filter || "(uid={username})");
    setLdapBindPassword("");
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    void (async () => {
      try {
        const c = await jsonFetch<ProviderInfo[]>("/api/settings/ai-providers");
        setProviderCatalogue(c);
      } catch {
        setProviderCatalogue([
          { id: "openai", label: "OpenAI" },
          { id: "gemini", label: "Google Gemini" },
          { id: "deepseek", label: "DeepSeek" },
        ]);
      }
    })();
  }, []);

  useEffect(() => {
    if (!isAdmin(user)) {
      return;
    }
    void (async () => {
      try {
        const rr = await jsonFetch<RoleRow[]>("/api/settings/roles");
        setRoleRows(rr);
      } catch {
        setRoleRows([]);
      }
      try {
        const uu = await jsonFetch<AdminUser[]>("/api/admin/users");
        setAdminUsers(uu);
      } catch {
        setAdminUsers([]);
      }
    })();
  }, [user]);

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-bold" title="Только роль admin/superadmin">
        Настройки
      </h1>
      {msg && <p className="text-sm text-green-700">{msg}</p>}
      {s && (
        <p className="text-sm text-slate-500">
          Redmine: {s.has_redmine ? "подключён" : "не настроен"} · ИИ:{" "}
          {s.has_ai ? "есть ключи" : "нет ключей"} · LDAP:{" "}
          {s.ldap_effective ? "доступен для входа" : "не настроен"}
        </p>
      )}
      <div
        className="card max-w-2xl space-y-3"
        title="Самоподписанный сертификат: отключает проверку TLS к Redmine"
      >
        <h2 className="font-medium">Redmine</h2>
        <label className="text-sm text-slate-600">Base URL (без конечного /)</label>
        <input
          className="w-full rounded border border-slate-300 px-3 py-2"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
        />
        <label className="text-sm text-slate-600" title="Оставьте пустым, чтобы не обновлять">
          API key (X-Redmine-API-Key)
        </label>
        <input
          className="w-full rounded border border-slate-300 px-3 py-2"
          value={apiKey}
          onChange={(e) => setApiKey(e.target.value)}
          type="password"
        />
        <label
          className="flex items-center gap-2 text-sm text-slate-700"
          title="Включите, если Redmine с HTTPS и самоподписанным сертификатом"
        >
          <input
            type="checkbox"
            checked={insecure}
            onChange={(e) => setInsecure(e.target.checked)}
          />
          Самоподписанный сертификат (не проверять TLS)
        </label>
        <div className="grid gap-2 sm:grid-cols-2">
          <div>
            <label className="text-sm">Sprint Livecycle, дн.</label>
            <input
              type="number"
              min={1}
              className="mt-1 w-full rounded border border-slate-300 px-3 py-2"
              value={sprint}
              onChange={(e) => setSprint(parseInt(e.target.value, 10) || 14)}
            />
          </div>
          <div>
            <label
              className="text-sm"
              title="ID спискового поля в Redmine, значения: s, m, l, xl, 2xl (отображается как метка)"
            >
              ID поля «метка сложности» в Redmine
            </label>
            <input
              type="number"
              min={1}
              className="mt-1 w-full rounded border border-slate-300 px-3 py-2"
              value={cfid}
              onChange={(e) => setCfid(e.target.value)}
              placeholder="например 5"
            />
          </div>
        </div>
        <p className="text-xs text-slate-500">
          Метка сложности в Redmine — это список s, m, l, xl, 2xl в пользовательском поле задачи;
          укажите числовой id поля из «Администрирование → Пользовательские поля».
        </p>
        <div>
          <label className="text-sm" title="Для бэклога PM: id проекта в Redmine">
            ID проекта (для PM Backlog)
          </label>
          <input
            className="mt-1 w-full rounded border border-slate-300 px-3 py-2"
            value={proj}
            onChange={(e) => setProj(e.target.value)}
          />
        </div>
      </div>

      <div className="card max-w-2xl space-y-3">
        <h2 className="font-medium">LDAP</h2>
        <p className="text-xs text-slate-500">
          Если включено и заполнены URI и base DN, вход использует эти настройки. Иначе можно
          задать LDAP через переменные окружения бэкенда (как раньше). Пароль bind: пустое поле при
          сохранении — не менять сохранённый.
        </p>
        {s && (
          <p className="text-xs text-amber-800">
            Сервисный пароль в БД: {s.has_ldap_bind_password ? "задан" : "не задан"}
            {s.ldap_effective ? " · в данный момент вход по LDAP активен" : ""}
          </p>
        )}
        {ldapSaveMsg && <p className="text-sm text-green-700">{ldapSaveMsg}</p>}
        {ldapSaveErr && <p className="text-sm text-red-600">{ldapSaveErr}</p>}
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={ldapEnabled}
            onChange={(e) => setLdapEnabled(e.target.checked)}
          />
          Использовать LDAP из этой формы (не только env)
        </label>
        <div>
          <label className="text-sm text-slate-600">Server URI</label>
          <input
            className="mt-1 w-full rounded border border-slate-300 px-3 py-2 font-mono text-sm"
            value={ldapUri}
            onChange={(e) => setLdapUri(e.target.value)}
            placeholder="ldap://ldap.example.com:389"
          />
        </div>
        <div>
          <label className="text-sm text-slate-600">Bind DN (сервисная учётка для поиска)</label>
          <input
            className="mt-1 w-full rounded border border-slate-300 px-3 py-2 font-mono text-sm"
            value={ldapBindDn}
            onChange={(e) => setLdapBindDn(e.target.value)}
          />
        </div>
        <div>
          <label className="text-sm text-slate-600">Пароль bind</label>
          <input
            type="password"
            className="mt-1 w-full rounded border border-slate-300 px-3 py-2"
            value={ldapBindPassword}
            onChange={(e) => setLdapBindPassword(e.target.value)}
            placeholder="оставьте пустым, чтобы не менять"
          />
        </div>
        <div>
          <label className="text-sm text-slate-600">User base DN</label>
          <input
            className="mt-1 w-full rounded border border-slate-300 px-3 py-2 font-mono text-sm"
            value={ldapUserBase}
            onChange={(e) => setLdapUserBase(e.target.value)}
            placeholder="ou=users,dc=example,dc=com"
          />
        </div>
        <div>
          <label className="text-sm text-slate-600">Фильтр поиска</label>
          <input
            className="mt-1 w-full rounded border border-slate-300 px-3 py-2 font-mono text-sm"
            value={ldapFilter}
            onChange={(e) => setLdapFilter(e.target.value)}
          />
        </div>
        <p className="text-xs text-slate-500">
          Для Active Directory часто:{" "}
          <code className="rounded bg-slate-100 px-1">(sAMAccountName={"{"}username{"}"})</code>
        </p>
        <div>
          <button
            type="button"
            className="btn-primary inline-flex items-center gap-2"
            disabled={ldapSaving}
            onClick={async () => {
              setLdapSaveMsg("");
              setLdapSaveErr("");
              setLdapSaving(true);
              try {
                const body: Record<string, unknown> = {
                  ldap_enabled: ldapEnabled,
                  ldap_server_uri: ldapUri.trim() || null,
                  ldap_bind_dn: ldapBindDn.trim() || null,
                  ldap_user_base_dn: ldapUserBase.trim() || null,
                  ldap_user_filter: ldapFilter.trim() || null,
                };
                if (ldapBindPassword.trim()) {
                  body.ldap_bind_password = ldapBindPassword.trim();
                }
                await jsonFetch<Sett>("/api/settings", {
                  method: "PUT",
                  body: JSON.stringify(body),
                });
                setLdapSaveMsg("Настройки LDAP сохранены.");
                setLdapBindPassword("");
                await load();
              } catch (e) {
                setLdapSaveErr(e instanceof Error ? e.message : "Ошибка");
              } finally {
                setLdapSaving(false);
              }
            }}
          >
            {ldapSaving && <Loader2 className="h-4 w-4 shrink-0 animate-spin" />}
            Сохранить настройки LDAP
          </button>
        </div>
        <div className="rounded border border-slate-200 p-2 space-y-2">
          <p className="text-xs font-medium text-slate-600">Проверка (без сохранения в БД)</p>
          <div className="grid gap-2 sm:grid-cols-2">
            <input
              className="rounded border border-slate-200 px-2 text-sm"
              placeholder="тестовый логин"
              value={ldapTestUser}
              onChange={(e) => setLdapTestUser(e.target.value)}
            />
            <input
              type="password"
              className="rounded border border-slate-200 px-2 text-sm"
              placeholder="тестовый пароль"
              value={ldapTestPass}
              onChange={(e) => setLdapTestPass(e.target.value)}
            />
          </div>
          {ldapTestMsg && <p className="text-xs text-slate-600">{ldapTestMsg}</p>}
          <button
            type="button"
            className="btn-ghost text-sm"
            onClick={async () => {
              setLdapTestMsg("…");
              try {
                const r = await jsonFetch<{ ok: boolean; message: string }>(
                  "/api/settings/ldap/test",
                  {
                    method: "POST",
                    body: JSON.stringify({
                      ldap_server_uri: ldapUri,
                      ldap_bind_dn: ldapBindDn,
                      ldap_bind_password: ldapBindPassword,
                      ldap_user_base_dn: ldapUserBase,
                      ldap_user_filter: ldapFilter,
                      test_username: ldapTestUser.trim() || null,
                      test_password: ldapTestPass || null,
                    }),
                  }
                );
                setLdapTestMsg(`${r.ok ? "OK" : "Ошибка"}: ${r.message}`);
              } catch (e) {
                setLdapTestMsg(e instanceof Error ? e.message : "Ошибка");
              }
            }}
          >
            Проверить bind (+ опционально пользователя)
          </button>
        </div>
      </div>

      {isAdmin(user) && roleRows.length > 0 && (
        <div className="card max-w-2xl space-y-3">
          <h2 className="font-medium">Роли и пользователи</h2>
          <p className="text-sm text-slate-600">
            Старшие роли в порядке привилегий: <strong>superadmin</strong> → <strong>admin</strong>{" "}
            → <strong>product_manager</strong> → <strong>user</strong>. Супер-админ может
            назначать роль superadmin; остальные admin — нет.
          </p>
          <ul className="space-y-1 text-xs text-slate-500">
            {roleRows.map((r) => (
              <li key={r.id}>
                <strong className="text-slate-700">{r.label}</strong> ({r.id}): {r.description}
              </li>
            ))}
          </ul>
          {userMsg && <p className="text-sm text-green-700">{userMsg}</p>}
          {provisionFromLdapMsg && <p className="text-sm text-green-700">{provisionFromLdapMsg}</p>}
          {provisionFromLdapErr && <p className="text-sm text-red-600">{provisionFromLdapErr}</p>}
          <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
            <div className="min-w-0 flex-1">
              <label className="text-xs text-slate-600" htmlFor="ldap-provision-login">
                Логин в LDAP (добавить в список без первого входа)
              </label>
              <input
                id="ldap-provision-login"
                className="mt-1 w-full rounded border border-slate-300 px-3 py-2 font-mono text-sm"
                value={ldapProvisionLogin}
                onChange={(e) => setLdapProvisionLogin(e.target.value)}
                placeholder="uid или sAMAccountName"
                autoComplete="off"
              />
            </div>
            <button
              type="button"
              className="btn-ghost inline-flex shrink-0 items-center gap-2"
              disabled={provisionFromLdapLoading}
              onClick={async () => {
                setProvisionFromLdapMsg("");
                setProvisionFromLdapErr("");
                const u = ldapProvisionLogin.trim();
                if (!u) {
                  setProvisionFromLdapErr("Укажите логин.");
                  return;
                }
                setProvisionFromLdapLoading(true);
                try {
                  await jsonFetch<AdminUser>("/api/admin/users/from-ldap", {
                    method: "POST",
                    body: JSON.stringify({ username: u }),
                  });
                  setProvisionFromLdapMsg("Пользователь добавлен из LDAP; назначьте роль в таблице.");
                  setLdapProvisionLogin("");
                  const uu = await jsonFetch<AdminUser[]>("/api/admin/users");
                  setAdminUsers(uu);
                } catch (e) {
                  setProvisionFromLdapErr(e instanceof Error ? e.message : "Ошибка");
                } finally {
                  setProvisionFromLdapLoading(false);
                }
              }}
            >
              {provisionFromLdapLoading && <Loader2 className="h-4 w-4 shrink-0 animate-spin" />}
              Добавить из LDAP
            </button>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[28rem] text-left text-sm">
              <thead>
                <tr className="border-b text-xs text-slate-500">
                  <th className="py-1 pr-2">Пользователь</th>
                  <th className="py-1 pr-2">Источник</th>
                  <th className="py-1">Роль</th>
                </tr>
              </thead>
              <tbody>
                {adminUsers.map((u) => (
                  <tr key={u.id} className="border-b border-slate-100">
                    <td className="py-1.5 pr-2">
                      <span className="font-mono text-xs">{u.username}</span>
                      {u.email && (
                        <span className="ml-1 text-xs text-slate-400">({u.email})</span>
                      )}
                    </td>
                    <td className="py-1.5 pr-2 text-xs">{u.is_ldap ? "LDAP" : "локально"}</td>
                    <td className="py-1.5">
                      <select
                        className="rounded border border-slate-200 px-2 py-1 text-sm"
                        value={u.role}
                        disabled={!u.is_active}
                        onChange={async (e) => {
                          setUserMsg("");
                          try {
                            await jsonFetch(`/api/admin/users/${u.id}`, {
                              method: "PATCH",
                              body: JSON.stringify({ role: e.target.value }),
                            });
                            setUserMsg("Роль обновлена.");
                            const uu = await jsonFetch<AdminUser[]>("/api/admin/users");
                            setAdminUsers(uu);
                          } catch (err) {
                            setUserMsg(
                              err instanceof Error ? err.message : "Ошибка",
                            );
                          }
                        }}
                      >
                        {roleRows.map((r) => (
                          <option
                            key={r.id}
                            value={r.id}
                            disabled={r.id === "superadmin" && !isSuperAdmin(user)}
                          >
                            {r.label}
                          </option>
                        ))}
                      </select>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {canBootstrapPassword && (
        <div className="card max-w-2xl space-y-3">
          <h2 className="font-medium">Пароль встроенной учётки admin</h2>
          <p className="text-xs text-slate-500">
            Учётная запись с именем <code className="rounded bg-slate-100 px-1">admin</code> из
            первого запуска. Супер-админ может задать новый пароль без старого; сам пользователь
            <code className="rounded bg-slate-100 px-1"> admin</code> — укажите текущий пароль.
          </p>
          {bootstrapMsg && <p className="text-sm text-green-700">{bootstrapMsg}</p>}
          {bootstrapErr && <p className="text-sm text-red-600">{bootstrapErr}</p>}
          {!isSuperAdmin(user) && (
            <div>
              <label className="text-sm text-slate-600">Текущий пароль</label>
              <input
                type="password"
                className="mt-1 w-full rounded border border-slate-300 px-3 py-2"
                value={bootstrapCurrent}
                onChange={(e) => setBootstrapCurrent(e.target.value)}
                autoComplete="current-password"
              />
            </div>
          )}
          <div>
            <label className="text-sm text-slate-600">Новый пароль (от 8 символов)</label>
            <input
              type="password"
              className="mt-1 w-full rounded border border-slate-300 px-3 py-2"
              value={bootstrapNew}
              onChange={(e) => setBootstrapNew(e.target.value)}
              autoComplete="new-password"
            />
          </div>
          <button
            type="button"
            className="btn-primary inline-flex items-center gap-2"
            disabled={bootstrapSaving}
            onClick={async () => {
              setBootstrapMsg("");
              setBootstrapErr("");
              if (bootstrapNew.trim().length < 8) {
                setBootstrapErr("Минимум 8 символов.");
                return;
              }
              if (!isSuperAdmin(user) && !bootstrapCurrent.trim()) {
                setBootstrapErr("Укажите текущий пароль.");
                return;
              }
              setBootstrapSaving(true);
              try {
                const body: Record<string, string> = { new_password: bootstrapNew.trim() };
                if (!isSuperAdmin(user)) {
                  body.current_password = bootstrapCurrent;
                }
                await jsonFetch<{ ok: boolean }>("/api/settings/bootstrap-admin-password", {
                  method: "PUT",
                  body: JSON.stringify(body),
                });
                setBootstrapMsg("Пароль обновлён.");
                setBootstrapNew("");
                setBootstrapCurrent("");
              } catch (e) {
                setBootstrapErr(e instanceof Error ? e.message : "Ошибка");
              } finally {
                setBootstrapSaving(false);
              }
            }}
          >
            {bootstrapSaving && <Loader2 className="h-4 w-4 shrink-0 animate-spin" />}
            Сохранить пароль
          </button>
        </div>
      )}

      <div className="card max-w-2xl space-y-3" title="Проверка без сохранения: используется первый ключ провайдера в базе">
        <h2 className="font-medium">Провайдеры ИИ</h2>
        <ul className="divide-y divide-slate-100 rounded border border-slate-200">
          {providerCatalogue.map((p) => (
            <li key={p.id} className="flex items-center justify-between gap-2 px-3 py-2">
              <span className="text-sm text-slate-800">{p.label}</span>
              <div className="flex items-center gap-2">
                {testMsg[p.id] && (
                  <span
                    className="max-w-[180px] truncate text-xs text-slate-500"
                    title={testMsg[p.id]}
                  >
                    {testMsg[p.id]}
                  </span>
                )}
                <button
                  type="button"
                  className="btn-ghost text-sm"
                  onClick={async () => {
                    setTestMsg((m) => ({ ...m, [p.id]: "…" }));
                    try {
                      const r = await jsonFetch<{ ok: boolean; message: string }>(
                        "/api/settings/ai-providers/test",
                        {
                          method: "POST",
                          body: JSON.stringify({ provider: p.id }),
                        }
                      );
                      setTestMsg((m) => ({
                        ...m,
                        [p.id]: r.ok ? "OK" : r.message,
                      }));
                    } catch (e) {
                      setTestMsg((m) => ({
                        ...m,
                        [p.id]: e instanceof Error ? e.message : "Ошибка",
                      }));
                    }
                  }}
                >
                  Проверить
                </button>
              </div>
            </li>
          ))}
        </ul>
      </div>

      <div
        className="card max-w-2xl space-y-2"
        title="Ключи нельзя удалить через интерфейс, только обновить секрет или добавить ещё"
      >
        <h2 className="font-medium">Сохранённые API-ключи</h2>
        {keys.map((k, i) => (
          <div
            key={`${k.provider}-${k.name}-${i}`}
            className="grid gap-1 rounded border border-slate-200 p-2 sm:grid-cols-3"
          >
            <input
              placeholder="openai|gemini|deepseek"
              className="rounded border border-slate-200 px-2"
              value={k.provider}
              onChange={(e) => {
                const n = [...keys];
                n[i] = { ...k, provider: e.target.value };
                setKeys(n);
              }}
              title="Провайдер (из списка выше)"
            />
            <input
              placeholder="имя слота"
              className="rounded border border-slate-200 px-2"
              value={k.name}
              onChange={(e) => {
                const n = [...keys];
                n[i] = { ...k, name: e.target.value };
                setKeys(n);
              }}
            />
            <input
              placeholder="новый ключ (пусто = не менять)"
              className="rounded border border-slate-200 px-2"
              value={k.key}
              onChange={(e) => {
                const n = [...keys];
                n[i] = { ...k, key: e.target.value };
                setKeys(n);
              }}
              type="password"
            />
          </div>
        ))}
        <button
          type="button"
          className="btn-ghost"
          onClick={() =>
            setKeys((ks) => [
              ...ks,
              { provider: "openai", name: `slot${ks.length + 1}`, key: "" },
            ])
          }
        >
          + Добавить ключ
        </button>
        <p className="text-xs text-slate-500">
          Удаление ключей из системы не поддерживается: можно только добавить слоты или сменить
          секрет (укажите новый ключ в поле). Пустой ключ при сохранении оставляет прежний.
        </p>
        <div>
          <button
            type="button"
            className="btn-primary"
            onClick={async () => {
              setMsg("");
              const body: Record<string, unknown> = {
                redmine_base_url: url || null,
                redmine_insecure_ssl: insecure,
                sprint_lifecycle_days: sprint,
                project_id: proj ? parseInt(proj, 10) : null,
                ai_keys: keys.map((k) => ({ provider: k.provider, name: k.name, key: k.key })),
              };
              if (apiKey.trim()) {
                body.redmine_api_key = apiKey.trim();
              }
              if (cfid.trim()) {
                body.redmine_complexity_field_id = parseInt(cfid, 10);
              } else {
                body.redmine_complexity_field_id = null;
              }
              await jsonFetch<Sett>("/api/settings", { method: "PUT", body: JSON.stringify(body) });
              setMsg("Сохранено.");
              setApiKey("");
              await load();
            }}
          >
            Сохранить
          </button>
        </div>
      </div>
    </div>
  );
}
