"use client";

import { PageHeader } from "@/components/dashboard/PageHeader";
import { useLanguage } from "@/components/dashboard/LanguageContext";
import { Text } from "@/components/ui/Typography";

export function ComingSoon({ title }: { title: string }) {
  const { t } = useLanguage();
  return (
    <>
      <PageHeader title={title} />
      <main className="px-4 py-6 sm:px-8 sm:py-8">
        <div className="flex min-h-[50vh] items-center justify-center rounded-2xl bg-surface">
          <Text variant={2} className="text-gray-60">
            {t.comingSoon.message(title)}
          </Text>
        </div>
      </main>
    </>
  );
}
