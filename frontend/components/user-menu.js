"use client";

import { useState } from "react";

import { logoutCurrentUser } from "../lib/api";

export default function UserMenu({ user }) {
  const [isLoggingOut, setIsLoggingOut] = useState(false);

  async function handleLogout() {
    setIsLoggingOut(true);
    try {
      await logoutCurrentUser();
    } finally {
      window.location.assign("/login");
    }
  }

  return (
    <div className="user-menu">
      <div>
        <span>当前用户</span>
        <strong>{user?.display_name || user?.username || "未知用户"}</strong>
      </div>
      <button className="ghost-link compact" disabled={isLoggingOut} onClick={handleLogout} type="button">
        {isLoggingOut ? "退出中" : "退出"}
      </button>
    </div>
  );
}
