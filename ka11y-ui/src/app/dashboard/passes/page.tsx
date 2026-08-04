"use client";

import { useMemo, useState, useRef, useEffect } from "react";
import { ChevronDown, X, ExternalLink } from "lucide-react";
import { LanguageToggle } from "@/components/dashboard/LanguageToggle";
import { DownloadCsvButton } from "@/components/dashboard/DownloadActions";
import { PageHeader } from "@/components/dashboard/PageHeader";
import { ElementImage } from "@/components/dashboard/ElementImage";
import { PageFilterDropdown } from "@/components/dashboard/PageFilterDropdown";
import { useAuditData } from "@/components/dashboard/AuditDataContext";
import { useLanguage } from "@/components/dashboard/LanguageContext";
import { toPassesRows, getScannedPages, type WcagLevel } from "@/lib/wcagAudit";
import { useInfiniteReveal } from "@/lib/useInfiniteReveal";
import { cn } from "@/lib/utils";

function LevelBadge({ level }: { level: WcagLevel }) {
  return (
    <span className="inline-flex items-center justify-center rounded-[8px] bg-brand-green-20 px-2 py-1 text-[14px] leading-5 text-brand-teal-dark">
      {level}
    </span>
  );
}

export default function PassesPage() {
  const { auditData } = useAuditData();
  const { t } = useLanguage();
  const [activeFilters, setActiveFilters] = useState<WcagLevel[]>([]);
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [selectedPage, setSelectedPage] = useState<string | null>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const items = useMemo(
    () => (auditData ? toPassesRows(auditData) : []),
    [auditData],
  );
  const scannedPages = useMemo(
    () => (auditData ? getScannedPages(auditData) : []),
    [auditData],
  );
  const selectedPageInfo = scannedPages.find((p) => p.page_url === selectedPage) ?? null;

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setDropdownOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  function toggleFilter(level: WcagLevel) {
    setActiveFilters((prev) =>
      prev.includes(level) ? prev.filter((l) => l !== level) : [...prev, level],
    );
  }

  const byPage = selectedPage
    ? items.filter((item) => item.pageUrl === selectedPage)
    : items;

  const filtered =
    activeFilters.length === 0
      ? byPage
      : byPage.filter((item) => activeFilters.includes(item.level));

  const { visibleItems, visibleCount, hasMore, sentinelRef } = useInfiniteReveal(
    filtered,
    activeFilters.join(","),
  );

  const LEVELS: WcagLevel[] = ["A", "AA", "AAA"];

  const headerActions = (
    <>
      <LanguageToggle />
      <DownloadCsvButton />
    </>
  );

  return (
    <>
      <PageHeader
        title="A11Y"
        target={auditData?.url ?? "https://samplesite.com/"}
        actions={headerActions}
      />

      <main className="flex flex-1 flex-col gap-6 min-w-0 px-4 py-6 sm:px-8 sm:py-8 lg:px-16 lg:gap-10 lg:py-10">

        {!auditData ? (
          <div className="flex min-h-[50vh] items-center justify-center rounded-2xl bg-gray-10">
            <p className="text-[16px] leading-6 text-gray-60">
              {t.passes.emptyState}
            </p>
          </div>
        ) : (
        <>
        {/* Filter bar */}
        <div className="flex flex-wrap items-center gap-3">
          <div className="relative" ref={dropdownRef}>
            <button
              type="button"
              onClick={() => setDropdownOpen((v) => !v)}
              className="flex items-center gap-2 rounded-[16px] border border-gray-40 bg-gray-10 px-4 py-2 text-[14px] leading-6 text-gray-100 sm:text-[16px]"
            >
              {t.filters.wcagLevel}
              <ChevronDown
                size={16}
                aria-hidden="true"
                className={cn("transition-transform", dropdownOpen && "rotate-180")}
              />
            </button>
            {dropdownOpen && (
              <div className="absolute left-0 top-full z-10 mt-1 flex flex-col overflow-hidden rounded-[8px] border border-gray-40 bg-white shadow-[0px_0px_3.25px_rgba(0,0,0,0.06)]">
                {LEVELS.map((level) => (
                  <button
                    key={level}
                    type="button"
                    onClick={() => { toggleFilter(level); setDropdownOpen(false); }}
                    className={cn(
                      "border-b border-gray-10 px-6 py-2 text-left text-[14px] leading-5 text-gray-100 last:border-b-0 hover:bg-gray-10",
                      activeFilters.includes(level) && "text-brand-teal-dark underline",
                    )}
                  >
                    {level}
                  </button>
                ))}
              </div>
            )}
          </div>

          {activeFilters.length > 0 && (
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-[14px] leading-6 text-gray-80 sm:text-[16px]">{t.filters.wcagLevel}:</span>
              {activeFilters.map((level) => (
                <span
                  key={level}
                  className="inline-flex h-8 items-center gap-1.5 rounded-[8px] border border-brand-teal-dark bg-brand-green-20 px-2 py-1 text-[14px] leading-6 text-brand-teal-dark"
                >
                  {level}
                  <button
                    type="button"
                    onClick={() => toggleFilter(level)}
                    aria-label={t.filters.removeFilter(level)}
                    className="flex items-center hover:opacity-70"
                  >
                    <X size={14} aria-hidden="true" />
                  </button>
                </span>
              ))}
              <button
                type="button"
                onClick={() => setActiveFilters([])}
                className="text-[14px] leading-6 text-gray-100 underline sm:text-[16px]"
              >
                {t.filters.clearAll}
              </button>
            </div>
          )}

          <PageFilterDropdown
            pages={scannedPages}
            selected={selectedPage}
            onChange={setSelectedPage}
            t={t}
          />
        </div>

        {selectedPageInfo?.status === "failed" ? (
          <div className="flex min-h-[50vh] items-center justify-center rounded-2xl bg-gray-10">
            <p className="text-[16px] leading-6 text-gray-60">
              {t.filters.pageFailedMessage(selectedPageInfo.error)}
            </p>
          </div>
        ) : (
        <>
        <p className="text-[14px] leading-6 text-gray-100 sm:text-[16px]">
          {t.passes.showing(visibleCount, filtered.length, items.length)}
        </p>

        {/* Table — horizontally scrollable, page does not scroll */}
        <div className="w-full overflow-x-auto rounded-[8px]">
        <div className="min-w-[900px]">

          {/* Header */}
          <div className="flex w-full bg-gray-10 text-[14px] font-bold leading-6 text-gray-100">
            <div className="flex-[110] min-w-0 p-4">{t.passes.columns.status}</div>
            <div className="flex-[318] min-w-0 p-4">{t.passes.columns.reason}</div>
            <div className="flex-[76] min-w-0 p-4">{t.passes.columns.sc}</div>
            <div className="flex-[146] min-w-0 p-4">{t.passes.columns.criterion}</div>
            <div className="flex-[76] min-w-0 p-4">{t.passes.columns.level}</div>
            <div className="flex-[76] min-w-0 p-4">{t.passes.columns.tag}</div>
            <div className="flex-[318] min-w-0 p-4">{t.passes.columns.element}</div>
          </div>

          {/* Rows */}
          {visibleItems.map((item) => (
            <div key={item.id} className="flex w-full border-b border-gray-10 bg-white text-[14px] leading-5">

              <div className="flex-[110] min-w-0 border-b border-gray-10 px-4 py-6">
                <span className="inline-flex items-center rounded-[8px] bg-gray-10 px-3 py-1 text-[14px] leading-5 text-gray-100">
                  {t.passes.statusPass}
                </span>
              </div>

              <div className="flex-[318] min-w-0 border-b border-gray-10 px-4 py-6 flex flex-col gap-2">
                <p className="font-bold text-gray-100">{item.reasonTitle}</p>
                <p className="text-gray-80">{item.reasonDescription}</p>
                {/^https?:\/\//.test(item.helpUrl) ? (
                  <a
                    href={item.helpUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1.5 text-brand-teal-dark underline"
                  >
                    {t.passes.learnMore} <ExternalLink size={14} className="shrink-0" aria-hidden="true" />
                  </a>
                ) : (
                  <button type="button" className="inline-flex items-center gap-1.5 text-brand-teal-dark underline">
                    {t.passes.learnMore} <ExternalLink size={14} className="shrink-0" aria-hidden="true" />
                  </button>
                )}
              </div>

              <div className="flex-[76] min-w-0 border-b border-gray-10 px-4 py-6 text-gray-80">
                {item.sc}
              </div>

              <div className="flex-[146] min-w-0 border-b border-gray-10 px-4 py-6 text-gray-80">
                {item.criterion}
              </div>

              <div className="flex-[76] min-w-0 border-b border-gray-10 px-4 py-6">
                <LevelBadge level={item.level} />
              </div>

              <div className="flex-[76] min-w-0 border-b border-gray-10 px-4 py-6 text-gray-80">
                {item.tag}
              </div>

              <div className="flex-[318] min-w-0 border-b border-gray-10 px-4 py-6 flex flex-col gap-4">
                <p className="font-medium text-gray-100">{item.elementFilename}</p>
                <ElementImage srcs={item.imageUrls} className="h-[90px] w-[105px]" />
                <div className="flex flex-col gap-2 text-[12px] leading-5">
                  <div className="flex gap-1">
                    <span className="shrink-0 text-gray-80">{t.passes.foreground}</span>
                    <span className="text-gray-100">{item.foreground}</span>
                  </div>
                  <div className="flex gap-1">
                    <span className="shrink-0 text-gray-80">{t.passes.background}</span>
                    <span className="text-gray-100">{item.background}</span>
                  </div>
                  <div className="flex gap-1">
                    <span className="shrink-0 text-gray-80">{t.passes.ocrText}</span>
                    <span className="text-gray-100">{item.ocrText}</span>
                  </div>
                </div>
                <button type="button" className="inline-flex items-center gap-1.5 text-[14px] leading-5 text-brand-teal-dark underline">
                  {t.passes.viewFullAudit} <ExternalLink size={14} className="shrink-0" aria-hidden="true" />
                </button>
              </div>

            </div>
          ))}
          {hasMore && <div ref={sentinelRef} aria-hidden="true" className="h-1" />}
        </div>
        </div>
        </>
        )}
        </>
        )}

      </main>
    </>
  );
}
