"use client";

import { useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ChevronRight } from "lucide-react";
import { Logo } from "@/components/ui/Logo";
import { useLanguage } from "@/components/dashboard/LanguageContext";
import { LanguageToggle } from "@/components/dashboard/LanguageToggle";

export default function LoginPage() {
  const router = useRouter();
  const { t } = useLanguage();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [keepSignedIn, setKeepSignedIn] = useState(false);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    // Navigate to dashboard upon sign in
    router.push("/dashboard");
  }

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

      {/* Right side: Login Form Section */}
      <div className="flex min-h-screen w-full md:w-1/2 flex-col items-center justify-center px-4 py-12 sm:px-8 lg:px-16">
        {/* Mobile Logo */}
        <div className="mb-8 md:hidden">
          <Logo variant="color" />
        </div>

        {/* Sign In Card */}
        <div className="w-full max-w-[460px] rounded-[16px] bg-white p-8 sm:p-12 shadow-[0px_4px_24px_rgba(0,0,0,0.04)]">
          <h1 className="text-center text-[28px] font-bold text-gray-900 sm:text-[32px]">
            {t.login.signIn}
          </h1>
          <p className="mt-2 text-center text-[15px] leading-6 text-gray-500">
            {t.login.subtitle}
          </p>

          <form onSubmit={handleSubmit} className="mt-8 flex flex-col gap-5">
            {/* Email input */}
            <div>
              <label className="block text-[14px] font-medium text-gray-700 mb-1.5">
                {t.login.emailLabel}
              </label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder={t.login.emailPlaceholder}
                required
                className="w-full rounded-[10px] border border-gray-300 bg-white px-4 py-3 text-[15px] text-gray-900 placeholder:text-gray-400 focus:border-[#005A54] focus:outline-none focus:ring-1 focus:ring-[#005A54] transition-all"
              />
            </div>

            {/* Password input */}
            <div>
              <label className="block text-[14px] font-medium text-gray-700 mb-1.5">
                {t.login.passwordLabel}
              </label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder={t.login.passwordPlaceholder}
                required
                className="w-full rounded-[10px] border border-gray-300 bg-white px-4 py-3 text-[15px] text-gray-900 placeholder:text-gray-400 focus:border-[#005A54] focus:outline-none focus:ring-1 focus:ring-[#005A54] transition-all"
              />
            </div>

            {/* Keep me signed in & Forgot password */}
            <div className="flex items-center justify-between text-[14px] pt-1">
              <label className="flex items-center gap-2 text-gray-700 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={keepSignedIn}
                  onChange={(e) => setKeepSignedIn(e.target.checked)}
                  className="h-4 w-4 rounded border-gray-300 text-[#005A54] accent-[#005A54] focus:ring-[#005A54]"
                />
                <span>{t.login.keepMeSignedIn}</span>
              </label>
              <Link
                href="#"
                className="font-medium text-[#005A54] hover:underline"
              >
                {t.login.forgotPassword}
              </Link>
            </div>

            {/* Sign in button */}
            <button
              type="submit"
              className="mt-3 flex w-full items-center justify-center gap-2 rounded-full bg-[#005A54] px-6 py-3.5 text-[16px] font-medium text-white hover:bg-[#004843] active:bg-[#003834] transition-colors shadow-sm"
            >
              <ChevronRight size={18} aria-hidden="true" />
              <span>{t.login.signIn}</span>
            </button>
          </form>
        </div>

        {/* Footer sign up prompt */}
        <div className="mt-8 text-center text-[15px] text-gray-600">
          <span>{t.login.signUpText} </span>
          <Link
            href="#"
            className="font-semibold text-[#005A54] hover:underline ml-1"
          >
            {t.login.signUpLink}
          </Link>
        </div>
      </div>
    </div>
  );
}
