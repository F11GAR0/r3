import { Link, NavLink, Outlet } from "react-router-dom";
import { useAuth, isPM, isAdmin } from "../auth";
import { Layers2 } from "lucide-react";

/**
 * App shell: logo, navigation, and outlet for child routes.
 */
export default function Layout() {
  const { user, logout } = useAuth();
  const nav = "rounded-md px-3 py-2 text-sm text-slate-600 hover:bg-slate-100";
  const active = "bg-white shadow-sm text-slate-900";
  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-200 bg-slate-100/80 backdrop-blur">
        <div className="mx-auto flex w-full max-w-[88rem] items-center justify-between gap-4 px-4 py-3">
          <Link to="/" className="flex items-center gap-2 font-semibold text-brand-800">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand-600 text-sm font-bold text-white">
              R3
            </div>
            <span>R3</span>
          </Link>
          <nav className="hidden flex-1 items-center justify-center gap-1 sm:flex">
            <NavLink
              to="/"
              className={({ isActive }) => (isActive ? `${nav} ${active}` : nav)}
              title="Старт и скачивание сертификата"
            >
              Главная
            </NavLink>
            <NavLink
              to="/profile"
              className={({ isActive }) => (isActive ? `${nav} ${active}` : nav)}
              title="Промпты ИИ"
            >
              Профиль
            </NavLink>
            <NavLink
              to="/workbench"
              className={({ isActive }) => (isActive ? `${nav} ${active}` : nav)}
              title="Список «протухших» и разбивка"
            >
              <span className="inline-flex items-center gap-1">
                <Layers2 className="h-4 w-4" /> Workbench
              </span>
            </NavLink>
            <NavLink
              to="/wizard"
              className={({ isActive }) => (isActive ? `${nav} ${active}` : nav)}
              title="Task Wizard: быстрые действия"
            >
              Task Wizard
            </NavLink>
            {isPM(user) && (
              <>
                <NavLink
                  to="/backlog"
                  className={({ isActive }) => (isActive ? `${nav} ${active}` : nav)}
                  title="Весь бэклог проекта"
                >
                  PM Backlog
                </NavLink>
                <NavLink
                  to="/stats"
                  className={({ isActive }) => (isActive ? `${nav} ${active}` : nav)}
                  title="Статистика и velocity"
                >
                  Статистика
                </NavLink>
              </>
            )}
            {isAdmin(user) && (
              <NavLink
                to="/settings"
                className={({ isActive }) => (isActive ? `${nav} ${active}` : nav)}
                title="Redmine и AI"
              >
                Настройки
              </NavLink>
            )}
          </nav>
          <div className="flex items-center gap-2 text-sm text-slate-600">
            <span title="Текущий пользователь">{user?.username}</span>
            <button type="button" className="btn-ghost" onClick={() => logout()}>
              Выйти
            </button>
          </div>
        </div>
      </header>
      <main className="mx-auto w-full max-w-[88rem] px-4 py-6">
        <Outlet />
      </main>
    </div>
  );
}
