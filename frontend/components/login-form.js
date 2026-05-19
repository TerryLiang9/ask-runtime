"use client";

import { useState } from "react";

import { loginWithPassword } from "../lib/api";

export default function LoginForm() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");
    setIsSubmitting(true);
    try {
      await loginWithPassword({ username, password });
      window.location.assign("/");
    } catch (requestError) {
      setError(requestError.message === "invalid_credentials" ? "账号或密码不正确。" : "登录失败，请稍后重试。");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <form className="login-form" onSubmit={handleSubmit}>
      <label>
        <span>账号</span>
        <input
          autoComplete="username"
          name="username"
          onChange={(event) => setUsername(event.target.value)}
          required
          type="text"
          value={username}
        />
      </label>
      <label>
        <span>密码</span>
        <input
          autoComplete="current-password"
          name="password"
          onChange={(event) => setPassword(event.target.value)}
          required
          type="password"
          value={password}
        />
      </label>
      {error ? <p className="form-error">{error}</p> : null}
      <button className="action-button login-submit" disabled={isSubmitting} type="submit">
        {isSubmitting ? "登录中" : "进入控制台"}
      </button>
    </form>
  );
}
