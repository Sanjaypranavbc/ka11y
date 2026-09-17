"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { ChevronRight } from "lucide-react";
import { useLanguage } from "@/components/dashboard/LanguageContext";
import {
  AuthShell,
  inputClass,
  labelClass,
  linkClass,
  primaryButtonClass,
} from "@/components/auth/AuthShell";
import { PasswordField } from "@/components/auth/PasswordField";
import {
  AuthApiError,
  DEFAULT_AUTH_CONFIG,
  fetchAuthConfig,
  registerAccount,
  type AuthConfig,
} from "@/lib/auth";

/**
 * Self-service account creation for allow-listed e-mail addresses. The API
 * rejects anything not on KA11Y_ALLOWED_EMAILS / _DOMAINS and any address
 * that already has an account; on success the session cookie is set and the
 * user lands on the dashboard.
 */
function RegisterForm() {
  const { t } = useLanguage();
  const router = useRouter();
  const searchParams = useSearchParams();

  const [config, setConfig] = useState<AuthConfig>(DEFAULT_AUTH_CONFIG);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [keepSignedIn, setKeepSignedIn] = useState(false);
  const [busy, setBusy] = useState(false);
  const [errorCode, setErrorCode] = useState<string | null>(null);

  const next = searchParams.get("next") ?? undefined;
  const errors = t.login.errors as Record<string, string>;
  const errorMessage = errorCode ? errors[errorCode] ?? t.login.errors.generic : null;
  const mismatch = confirm.length > 0 && confirm !== password;

  useEffect(() => {
    let cancelled = false;
    fetchAuthConfig().then((cfg) => {
      if (!cancelled) setConfig(cfg);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (password !== confirm) {
      setErrorCode("password_mismatch");
      return;
    }
    setErrorCode(null);
    setBusy(true);
    try {
      const { next: target } = await registerAccount({
        email: email.trim(),
        password,
        name: name.trim(),
        remember: keepSignedIn,
        next,
      });
      router.replace(target);
    } catch (err) {
      setErrorCode(err instanceof AuthApiError ? err.code : "generic");
      setBusy(false);
    }
  }

  const loginHref = next ? `/login?next=${encodeURIComponent(next)}` : "/login";

  return (
    <>
      <h1 className="text-center text-[28px] font-bold text-gray-900 sm:text-[32px]">
        {t.login.register.title}
      </h1>
      <p className="mt-2 text-center text-[15px] leading-6 text-gray-500">
        {t.login.register.subtitle}
      </p>

      {(errorMessage || !config.registration) && (
        <p
          role="alert"
          className="mt-6 rounded-[10px] border border-red-200 bg-red-50 px-4 py-3 text-[14px] leading-5 text-red-800"
        >
          {errorMessage ?? t.login.errors.register_disabled}
        </p>
      )}

      <form onSubmit={handleSubmit} className="mt-8 flex flex-col gap-5" noValidate>
        <div>
          <label htmlFor="name" className={labelClass}>
            {t.login.register.name}
          </label>
          <input
            id="name"
            name="name"
            type="text"
            autoComplete="name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            disabled={busy || !config.registration}
            className={inputClass}
          />
        </div>

        <div>
          <label htmlFor="email" className={labelClass}>
            {t.login.email}
          </label>
          <input
            id="email"
            name="email"
            type="email"
            inputMode="email"
            autoComplete="username"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            disabled={busy || !config.registration}
            className={inputClass}
          />
        </div>

        <PasswordField
          id="new-password"
          label={t.login.password}
          value={password}
          onChange={setPassword}
          autoComplete="new-password"
          showLabel={t.login.showPassword}
          hideLabel={t.login.hidePassword}
          hint={t.login.register.passwordHint}
          disabled={busy || !config.registration}
        />

        <PasswordField
          id="confirm-password"
          label={t.login.register.confirmPassword}
          value={confirm}
          onChange={setConfirm}
          autoComplete="new-password"
          showLabel={t.login.showPassword}
          hideLabel={t.login.hidePassword}
          error={mismatch ? t.login.errors.password_mismatch : undefined}
          disabled={busy || !config.registration}
        />

        <label className="flex items-center gap-2 text-[14px] text-gray-700 cursor-pointer select-none">
          <input
            type="checkbox"
            checked={keepSignedIn}
            onChange={(e) => setKeepSignedIn(e.target.checked)}
            className="h-4 w-4 rounded border-gray-300 text-[#005A54] accent-[#005A54] focus:ring-[#005A54]"
          />
          <span>{t.login.keepMeSignedIn}</span>
        </label>

        <button
          type="submit"
          disabled={busy || !config.registration || !email || !password || !confirm || mismatch}
          className={primaryButtonClass}
        >
          <ChevronRight size={18} aria-hidden="true" />
          <span>{busy ? t.login.register.submitting : t.login.register.submit}</span>
        </button>
      </form>

      <p className="mt-6 text-center text-[14px] leading-5 text-gray-700">
        {t.login.haveAccount}{" "}
        <Link href={loginHref} className={linkClass}>
          {t.login.backToSignIn}
        </Link>
      </p>

      <p className="mt-6 text-center text-[13px] leading-5 text-gray-500">{t.login.accessNote}</p>
    </>
  );
}

export default function RegisterPage() {
  return (
    <AuthShell>
      <Suspense fallback={null}>
        <RegisterForm />
      </Suspense>
    </AuthShell>
  );
}
