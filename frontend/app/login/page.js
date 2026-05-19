import { redirect } from "next/navigation";

import LoginForm from "../../components/login-form";
import { getServerAuthContext } from "../../lib/auth";

export default async function LoginPage() {
  const { user } = await getServerAuthContext();
  if (user) {
    redirect("/");
  }

  return (
    <main className="login-shell">
      <section className="login-panel">
        <div className="login-copy">
          <p className="eyebrow">EMATA TEAM ACCESS</p>
          <h1>登录企业 Ask Runtime</h1>
          <p className="subtitle">
            团队试用环境只允许管理员预置账号访问。登录后可进入 Ask、Knowledge 和 Workspace 控制台。
          </p>
        </div>
        <LoginForm />
      </section>
      <aside className="login-signal" aria-label="Runtime capability preview">
        <div className="signal-grid">
          <span />
          <span />
          <span />
        </div>
        <div className="signal-list">
          <strong>Protected Runtime</strong>
          <p>Session Cookie / Workspace RBAC / Controlled Tool Use</p>
        </div>
      </aside>
    </main>
  );
}
