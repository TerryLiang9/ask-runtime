import Link from "next/link";

import UserMenu from "../../components/user-menu";
import { fetchWorkspaces } from "../../lib/api";
import { requireCurrentUser } from "../../lib/auth";

export default async function WorkspacesPage() {
  const { user, cookieHeader } = await requireCurrentUser();
  const workspaces = await fetchWorkspaces({ cookieHeader });

  return (
    <main className="shell detail-shell">
      <UserMenu user={user} />
      <div className="panel-header">
        <h1>Workspace 路由</h1>
        <Link href="/">返回控制台</Link>
      </div>
      <div className="grid">
        {workspaces.map((workspace) => (
          <section className="panel" key={workspace.id}>
            <h2>{workspace.name}</h2>
            <p className="subtitle">{workspace.description}</p>
            <ul>
              <li>ID: {workspace.id}</li>
              <li>Organization: {workspace.organization_id}</li>
              <li>Knowledge Scope: private + shared</li>
            </ul>
          </section>
        ))}
      </div>
    </main>
  );
}
