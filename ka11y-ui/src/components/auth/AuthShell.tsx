"use client";

import Image from "next/image";
import type { ReactNode } from "react";
import { Logo } from "@/components/ui/Logo";
import { LanguageToggle } from "@/components/dashboard/LanguageToggle";
import { useLanguage } from "@/components/dashboard/LanguageContext";
import { POST_LOGIN_PATH } from "@/lib/auth";

/**
 * Split layout shared by /login and /register: hero image + logo on the left,
 * a white card (the form) on the right. Purely presentational.
 */
export function AuthShell({ children }: { children: ReactNode }) {
  const { t } = useLanguage();
  return (
    <div className="relative flex min-h-screen w-full flex-col md:flex-row bg-[#F7F8FA]">
      <div className="absolute top-4 right-4 z-20 md:top-6 md:right-6">
        <LanguageToggle />
      </div>

      <div className="relative hidden md:block md:w-1/2 min-h-screen overflow-hidden">
        <Image
          src="/login-hero.jpg"
          alt=""
          fill
          priority
          className="object-cover object-center"
        />
        <div className="absolute top-8 left-8 z-10 sm:top-10 sm:left-10">
          <Logo variant="color" href={POST_LOGIN_PATH} prefetch={false} label={t.nav.homeLink} />
        </div>
      </div>

      <main className="flex min-h-screen w-full md:w-1/2 flex-col items-center justify-center px-4 py-12 sm:px-8 lg:px-16">
        <div className="mb-8 md:hidden">
          <Logo variant="color" href={POST_LOGIN_PATH} prefetch={false} label={t.nav.homeLink} />
        </div>
        <div className="w-full max-w-[460px] rounded-[16px] bg-white p-8 sm:p-12 shadow-[0px_4px_24px_rgba(0,0,0,0.04)]">
          {children}
        </div>
      </main>
    </div>
  );
}

/** Shared control styles so both forms look identical. */
export const inputClass =
  "h-12 w-full rounded-[8px] border border-gray-300 bg-white px-4 text-[16px] leading-6 text-gray-900 placeholder:text-gray-400 focus:border-[#005A54] focus:outline-none focus:ring-2 focus:ring-[#005A54]/30 disabled:bg-gray-50";
export const labelClass = "mb-1.5 block text-[14px] font-medium text-gray-800";
export const primaryButtonClass =
  "flex w-full items-center justify-center gap-2 rounded-full bg-[#005A54] px-6 py-3.5 text-[16px] font-medium text-white hover:bg-[#004843] active:bg-[#003834] disabled:opacity-60 transition-colors shadow-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#005A54]";
export const secondaryButtonClass =
  "flex w-full items-center justify-center gap-2 rounded-full border border-gray-300 bg-white px-6 py-3.5 text-[16px] font-medium text-gray-900 hover:bg-gray-50 disabled:opacity-60 transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#005A54]";
export const linkClass =
  "font-medium text-[#005A54] underline underline-offset-2 hover:text-[#004843] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#005A54] rounded-sm";
