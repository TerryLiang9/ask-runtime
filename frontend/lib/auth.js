import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { fetchCurrentUser } from "./api";

export async function getServerAuthContext() {
  const cookieStore = await cookies();
  if (cookieStore.get("emata_demo_signed_out")?.value === "1") {
    return { user: null, cookieHeader: cookieStore.toString() };
  }
  const cookieHeader = cookieStore.toString();
  try {
    const user = await fetchCurrentUser({ cookieHeader });
    return { user, cookieHeader };
  } catch (_error) {
    return { user: null, cookieHeader };
  }
}

export async function requireCurrentUser() {
  const context = await getServerAuthContext();
  if (!context.user) {
    redirect("/login");
  }
  return context;
}
