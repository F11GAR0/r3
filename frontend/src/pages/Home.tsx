import { Download, Shield } from "lucide-react";

/**
 * Home: TLS CA download, links to the rest of the app.
 */
export default function Home() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-800">Добро пожаловать в R3</h1>
        <p className="mt-1 text-slate-600">
          Помогает с Agile: «протухшие» задачи в Redmine, разбивка, Task Wizard, сложность
          s–2xl, учёт трудозатрат в Redmine, опциональные подсказки ИИ.
        </p>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <a
          href="/api/tls/root-ca"
          className="card group flex items-start gap-3 hover:border-brand-300"
          title="Скачайте и установите в доверенные корневые CA для HTTPS в docker-compose"
        >
          <div className="rounded-lg bg-amber-50 p-2 text-amber-800">
            <Download className="h-5 w-5" />
          </div>
          <div>
            <h2 className="font-semibold text-slate-800">Корневой сертификат (TLS)</h2>
            <p className="text-sm text-slate-500">
              Если открываете R3 по HTTPS с самоподписанной цепочкой, скачайте CA и доверьте
              в ОС. При работе по HTTP кнопка вернёт 404 — это нормально.
            </p>
            <span className="mt-2 inline-block text-sm font-medium text-brand-600 group-hover:underline">
              Скачать r3-rootCA.pem
            </span>
          </div>
        </a>
        <div
          className="card flex items-start gap-3"
          title="Первичный суперпользователь: admin / changeme"
        >
          <div className="rounded-lg bg-slate-100 p-2 text-slate-600">
            <Shield className="h-5 w-5" />
          </div>
          <div>
            <h2 className="font-semibold text-slate-800">Админ и Redmine</h2>
            <p className="text-sm text-slate-500">
              В разделе «Настройки» (роль администратора) укажите URL и API-ключ Redmine, при
              самоподписанном HTTPS — глобальный флаг «не проверять TLS», лимит «Sprint Livecycle» в
              днях и, при необходимости, ключи ИИ. Привяжите свой
              <span className="font-medium"> redmine user id</span> в разделе профиля (пока
              вручную в UI профиля).
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
