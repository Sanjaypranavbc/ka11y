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
  secondaryButtonClass,
} from "@/components/auth/AuthShell";
import { PasswordField } from "@/components/auth/PasswordField";
import {
  AUTH_PROVIDER_LABEL,
  AuthApiError,
  DEFAULT_AUTH_CONFIG,
  fetchAuthConfig,
  loginUrl,
  passwordLogin,
  type AuthConfig,
} from "@/lib/auth";

/**
 * Sign-in page.
 *
 * Primary path: e-mail + password, posted to the Python API through the
 * /api/v1/auth/* rewrite; the API checks the allow-list and the password and
 * sets the httpOnly session cookie. Secondary path (when the server has an
 * OIDC provider configured): "Continue with Google", the redirect flow.
 * Which paths are offered comes from GET /api/v1/auth/config.
 */
function LoginForm() {
  const { t } = useLanguage();
  const router = useRouter();
  const searchParams = useSearchParams();

  const [config, setConfig] = useState<AuthConfig>(DEFAULT_AUTH_CONFIG);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [keepSignedIn, setKeepSignedIn] = useState(false);
  const [busy, setBusy] = useState<"password" | "oidc" | null>(null);
  const [errorCode, setErrorCode] = useState<string | null>(searchParams.get("error"));

  const next = searchParams.get("next") ?? undefined;
  const errors = t.login.errors as Record<string, string>;
  const errorMessage = errorCode ? errors[errorCode] ?? t.login.errors.generic : null;

  useEffect(() => {
    let cancelled = false;
    fetchAuthConfig().then((cfg) => {
      if (!cancelled) setConfig(cfg);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  async function handlePasswordSubmit(e: React.FormEvent) {
    e.preventDefault();
    setErrorCode(null);
    setBusy("password");
    try {
      const { next: target } = await passwordLogin({
        email: email.trim(),
        password,
        remember: keepSignedIn,
        next,
      });
      router.replace(target);
    } catch (err) {
      setErrorCode(err instanceof AuthApiError ? err.code : "generic");
      setBusy(null);
    }
  }

  function handleOidc() {
    setBusy("oidc");
    window.location.assign(loginUrl({ remember: keepSignedIn, next }));
  }

  const registerHref = next ? `/register?next=${encodeURIComponent(next)}` : "/register";

  return (
    <>
      <h1 className="text-center text-[28px] font-bold text-gray-900 sm:text-[32px]">
        {t.login.signIn}
      </h1>
      <p className="mt-2 text-center text-[15px] leading-6 text-gray-500">{t.login.subtitle}</p>

      {errorMessage && (
        <p
          role="alert"
          className="mt-6 rounded-[10px] border border-red-200 bg-red-50 px-4 py-3 text-[14px] leading-5 text-red-800"
        >
          {errorMessage}
        </p>
      )}

      {config.password_login && (
        <form onSubmit={handlePasswordSubmit} className="mt-8 flex flex-col gap-5" noValidate>
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
              disabled={busy !== null}
              className={inputClass}
            />
          </div>

          <PasswordField
            id="password"
            label={t.login.password}
            value={password}
            onChange={setPassword}
            autoComplete="current-password"
            showLabel={t.login.showPassword}
            hideLabel={t.login.hidePassword}
            disabled={busy !== null}
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
            disabled={busy !== null || !email || !password}
            className={primaryButtonClass}
          >
            <ChevronRight size={18} aria-hidden="true" />
            <span>{busy === "password" ? t.login.signingIn : t.login.signInButton}</span>
          </button>
        </form>
      )}

      {config.oidc && (
        <div className={config.password_login ? "mt-6" : "mt-8"}>
          {config.password_login && (
            <div className="mb-6 flex items-center gap-3 text-[13px] uppercase tracking-wide text-gray-500">
              <span className="h-px flex-1 bg-gray-200" aria-hidden="true" />
              <span>{t.login.or}</span>
              <span className="h-px flex-1 bg-gray-200" aria-hidden="true" />
            </div>
          )}
          <button
            type="button"
            onClick={handleOidc}
            disabled={busy !== null}
            className={config.password_login ? secondaryButtonClass : primaryButtonClass}
          >
            <span>
              {busy === "oidc" ? t.login.redirecting : t.login.continueWith(AUTH_PROVIDER_LABEL)}
            </span>
          </button>
          {!config.password_login && (
            <label className="mt-5 flex items-center gap-2 text-[14px] text-gray-700 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={keepSignedIn}
                onChange={(e) => setKeepSignedIn(e.target.checked)}
                className="h-4 w-4 rounded border-gray-300 text-[#005A54] accent-[#005A54] focus:ring-[#005A54]"
              />
              <span>{t.login.keepMeSignedIn}</span>
            </label>
          )}
        </div>
      )}

      {config.registration && (
        <p className="mt-6 text-center text-[14px] leading-5 text-gray-700">
          {t.login.noAccount}{" "}
          <Link href={registerHref} className={linkClass}>
            {t.login.createAccount}
          </Link>
        </p>
      )}

      <p className="mt-6 text-center text-[13px] leading-5 text-gray-500">{t.login.accessNote}</p>
    </>
  );
}

export default function LoginPage() {
  return (
    <AuthShell>
      {/* useSearchParams() needs a Suspense boundary for static rendering */}
      <Suspense fallback={null}>
        <LoginForm />
      </Suspense>
    </AuthShell>
  );
}
