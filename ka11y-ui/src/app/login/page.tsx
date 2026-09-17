"use client";

import { Suspense, useState } from "react";
import Image from "next/image";
import { useSearchParams } from "next/navigation";
import { ChevronRight } from "lucide-react";
import { Logo } from "@/components/ui/Logo";
import { useLanguage } from "@/components/dashboard/LanguageContext";
import { LanguageToggle } from "@/components/dashboard/LanguageToggle";
import { AUTH_PROVIDER_LABEL, loginUrl } from "@/lib/auth";

// Sign-in is OAuth 2.0 / OpenID Connect only (no local passwords). The button
// sends the browser to the Python API's /auth/login, which redirects to the
// identity provider and back; the API sets the session cookie on the way in.
function LoginForm() {
  const { t } = useLanguage();
  const searchParams = useSearchParams();
  const [keepSignedIn, setKeepSignedIn] = useState(false);
  const [redirecting, setRedirecting] = useState(false);

  const errorCode = searchParams.get("error");
  const errorMessage = errorCode
    ? (t.login.errors as Record<string, string>)[errorCode] ?? t.login.errors.generic
    : null;
  const next = searchParams.get("next") ?? undefined;

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setRedirecting(true);
    window.location.assign(loginUrl({ remember: keepSignedIn, next }));
  }

  return (
    <div className="w-full max-w-[460px] rounded-[16px] bg-white p-8 sm:p-12 shadow-[0px_4px_24px_rgba(0,0,0,0.04)]">
      <h1 className="text-center text-[28px] font-bold text-gray-900 sm:text-[32px]">
        {t.login.signIn}
      </h1>
      <p className="mt-2 text-center text-[15px] leading-6 text-gray-500">
        {t.login.subtitle}
      </p>

      {errorMessage && (
        <p
          role="alert"
          className="mt-6 rounded-[10px] border border-red-200 bg-red-50 px-4 py-3 text-[14px] leading-5 text-red-800"
        >
          {errorMessage}
        </p>
      )}

      <form onSubmit={handleSubmit} className="mt-8 flex flex-col gap-5">
        <button
          type="submit"
          disabled={redirecting}
          className="flex w-full items-center justify-center gap-2 rounded-full bg-[#005A54] px-6 py-3.5 text-[16px] font-medium text-white hover:bg-[#004843] active:bg-[#003834] disabled:opacity-60 transition-colors shadow-sm"
        >
          <ChevronRight size={18} aria-hidden="true" />
          <span>
            {redirecting ? t.login.redirecting : t.login.continueWith(AUTH_PROVIDER_LABEL)}
          </span>
        </button>

        <label className="flex items-center gap-2 text-[14px] text-gray-700 cursor-pointer select-none">
          <input
            type="checkbox"
            checked={keepSignedIn}
            onChange={(e) => setKeepSignedIn(e.target.checked)}
            className="h-4 w-4 rounded border-gray-300 text-[#005A54] accent-[#005A54] focus:ring-[#005A54]"
          />
          <span>{t.login.keepMeSignedIn}</span>
        </label>
      </form>

      <p className="mt-6 text-center text-[13px] leading-5 text-gray-500">
        {t.login.accessNote}
      </p>
    </div>
  );
}

export default function LoginPage() {
  return (
    <div className="relative flex min-h-screen w-full flex-col md:flex-row bg-[#F7F8FA]">
      {/* Language Toggle in top corner */}
      <div className="absolute top-4 right-4 z-20 md:top-6 md:right-6">
        <LanguageToggle />
      </div>

      {/* Left side: Hero Image Section */}
      <div className="relative hidden md:block md:w-1/2 min-h-screen overflow-hidden">
        <Image
          src="/login-hero.jpg"
          alt="Accessibility audits"
          fill
          priority
          className="object-cover object-center"
        />
        {/* Logo overlay on top-left of image */}
        <div className="absolute top-8 left-8 z-10 sm:top-10 sm:left-10">
          <Logo variant="color" />
        </div>
      </div>

      {/* Right side: Sign-in card */}
      <div className="flex min-h-screen w-full md:w-1/2 flex-col items-center justify-center px-4 py-12 sm:px-8 lg:px-16">
        {/* Mobile Logo */}
        <div className="mb-8 md:hidden">
          <Logo variant="color" />
        </div>

        {/* useSearchParams() needs a Suspense boundary for static rendering */}
        <Suspense fallback={null}>
          <LoginForm />
        </Suspense>
      </div>
    </div>
  );
}
