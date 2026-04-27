import { useEffect, useState } from "react";
import { useAuth } from "../auth";
import { jsonFetch } from "../api";
import { useNavigate } from "react-router-dom";

/**
 * Simple login form (local and LDAP, depending on server config).
 */
export default function Login() {
  const { login } = useAuth();
  const nav = useNavigate();
  const [u, setU] = useState("admin");
  const [p, setP] = useState("changeme");
  const [err, setErr] = useState("");
  const [ldapOn, setLdapOn] = useState<boolean | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        const s = await jsonFetch<{ enabled: boolean }>("/api/auth/ldap-status");
        setLdapOn(s.enabled);
      } catch {
        setLdapOn(false);
      }
    })();
  }, []);

  return (
    <div className="mx-auto flex min-h-screen max-w-sm flex-col justify-center gap-4 px-4">
      <h1 className="text-2xl font-bold text-slate-800">Вход в R3</h1>
      <p className="text-sm text-slate-500" title="По умолчанию после развёртывания: admin / changeme">
        {ldapOn
          ? "Настроен вход по LDAP (или локально: та же форма). Локальный admin создаётся при первом старте."
          : "Сейчас только локальные учётные записи; LDAP можно включить в «Настройки» или через env бэкенда."}
      </p>
      {err && <p className="text-sm text-red-600">{err}</p>}
      <label className="text-sm text-slate-600">
        Имя пользователя
        <input
          className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2"
          value={u}
          onChange={(e) => setU(e.target.value)}
        />
      </label>
      <label className="text-sm text-slate-600">
        Пароль
        <input
          type="password"
          className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2"
          value={p}
          onChange={(e) => setP(e.target.value)}
        />
      </label>
      <button
        type="button"
        className="btn-primary"
        onClick={async () => {
          setErr("");
          try {
            await login(u, p);
            void nav("/");
          } catch (e) {
            setErr(e instanceof Error ? e.message : "Ошибка");
          }
        }}
      >
        Войти
      </button>
    </div>
  );
}
