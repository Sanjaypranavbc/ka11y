"use client";

import { LanguageToggle } from "@/components/dashboard/LanguageToggle";
import { PageHeader } from "@/components/dashboard/PageHeader";
import { useAuditData } from "@/components/dashboard/AuditDataContext";
import { useLanguage } from "@/components/dashboard/LanguageContext";
import { ImageVisualisationTab } from "@/components/dashboard/ImageVisualisationTab";

export default function ImageVisualisationPage() {
  const { auditData } = useAuditData();
  const { t } = useLanguage();

  const report = auditData?.contrast_report ?? auditData?.image_audit_report ?? null;

  return (
    <>
      <PageHeader
        title="A11Y"
        target={auditData?.url ?? "https://samplesite.com/"}
        actions={<LanguageToggle />}
      />

      <main className="flex flex-1 flex-col gap-6 min-w-0 px-4 py-6 sm:px-8 sm:py-8 lg:px-16 lg:py-10">
        <h1 className="text-[20px] font-semibold text-brand-gray">
          {t.nav.imageVisualisation}
        </h1>

        {!auditData ? (
          <div className="flex min-h-[50vh] items-center justify-center rounded-2xl bg-gray-10">
            <p className="text-[16px] leading-6 text-gray-60">
              {t.passes.emptyState}
            </p>
          </div>
        ) : (
          <ImageVisualisationTab report={report} />
        )}
      </main>
    </>
  );
}
