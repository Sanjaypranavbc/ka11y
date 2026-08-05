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
import { toViolationRows, getScannedPages, type WcagLevel } from "@/lib/wcagAudit";
import type { Translations } from "@/lib/i18n/translations";
import { useInfiniteReveal } from "@/lib/useInfiniteReveal";
import { cn } from "@/lib/utils";

const FIX_GUIDE_PREVIEW_LENGTH = 80;

function LevelBadge({ level }: { level: WcagLevel }) {
  return (
    <span className="inline-flex items-center justify-center rounded-[8px] bg-brand-green-20 px-2 py-1 text-[14px] leading-5 text-brand-teal-dark">
      {level}
    </span>
  );
}

function LinkIcon() {
  return <ExternalLink size={14} className="shrink-0" aria-hidden="true" />;
}

function FixGuideCell({
  text,
  expanded,
  onToggle,
  t,
}: {
  text: string;
  expanded: boolean;
  onToggle: () => void;
  t: Translations;
}) {
  const isLong = text.length > FIX_GUIDE_PREVIEW_LENGTH;
  return (
    <div className="flex flex-col gap-2">
      <p className="text-[14px] leading-5 text-gray-100">
        {expanded || !isLong ? text : `${text.slice(0, FIX_GUIDE_PREVIEW_LENGTH)}…`}
      </p>
      {isLong && (
        <button
          type="button"
          onClick={onToggle}
          className="text-left text-[14px] leading-5 text-brand-teal-dark underline"
        >
          {expanded ? t.violations.showLess : t.violations.readMore}
        </button>
      )}
    </div>
  );
}

export default function ViolationsPage() {
  const { auditData } = useAuditData();
  const { t } = useLanguage();
  const [activeFilters, setActiveFilters] = useState<WcagLevel[]>([]);
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set());
  const [selectedPage, setSelectedPage] = useState<string | null>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const ALL_VIOLATIONS = useMemo(
    () => (auditData ? toViolationRows(auditData) : []),
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

  function toggleRow(id: string) {
    setExpandedRows((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  const byPage = selectedPage
    ? ALL_VIOLATIONS.filter((v) => v.pageUrl === selectedPage)
    : ALL_VIOLATIONS;

  const filtered =
    activeFilters.length === 0
      ? byPage
      : byPage.filter((v) => activeFilters.includes(v.level));

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
              {t.violations.emptyState}
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
              <div className="absolute left-0 top-full z-10 mt-1 flex flex-col overflow-hidden rounded-[8px] border border-gray-40 bg-white shadow-md">
                {LEVELS.map((level) => (
                  <button
                    key={level}
                    type="button"
                    onClick={() => { toggleFilter(level); setDropdownOpen(false); }}
                    className={cn(
                      "px-4 py-2 text-left text-[14px] leading-6 text-gray-100 hover:bg-gray-10 sm:text-[16px]",
                      activeFilters.includes(level) && "bg-brand-green-20 text-brand-teal-dark",
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
          {t.violations.showing(visibleCount, filtered.length, ALL_VIOLATIONS.length)}
        </p>

        {/* Table — horizontally scrollable, page does not scroll */}
        <div className="w-full overflow-x-auto rounded-[8px]">
        <div className="min-w-[860px]">

          {/* Header row */}
          <div className="flex w-full bg-gray-10 text-[14px] font-bold leading-6 text-gray-100">
            <div className="flex-[227] min-w-0 p-4">{t.violations.columns.reason}</div>
            <div className="flex-[112] min-w-0 p-4">{t.violations.columns.sc}</div>
            <div className="flex-[146] min-w-0 p-4">{t.violations.columns.criterion}</div>
            <div className="flex-[112] min-w-0 p-4">{t.violations.columns.level}</div>
            <div className="flex-[112] min-w-0 p-4">{t.violations.columns.tag}</div>
            <div className="flex-[227] min-w-0 p-4">{t.violations.columns.element}</div>
            <div className="flex-[184] min-w-0 p-4">{t.violations.columns.fixGuide}</div>
          </div>

          {/* Data rows */}
          {visibleItems.map((violation) => (
            <div key={violation.id} className="flex w-full border-b border-gray-10 bg-white text-[14px] leading-5">

              <div className="flex-[227] min-w-0 border-b border-gray-10 px-4 py-6 flex flex-col gap-2">
                <p className="font-bold text-gray-100">{violation.title}</p>
                <p className="text-gray-80">{violation.description}</p>
                {/* Learn More — hidden per review; restore by uncommenting.
                {/^https?:\/\//.test(violation.helpUrl) ? (
                  <a
                    href={violation.helpUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1.5 text-brand-teal-dark underline"
                  >
                    {t.violations.learnMore} <LinkIcon />
                  </a>
                ) : (
                  <button type="button" className="inline-flex items-center gap-1.5 text-brand-teal-dark underline">
                    {t.violations.learnMore} <LinkIcon />
                  </button>
                )}
                */}
              </div>

              <div className="flex-[112] min-w-0 border-b border-gray-10 px-4 py-6 text-gray-80">
                {violation.sc}
              </div>

              <div className="flex-[146] min-w-0 border-b border-gray-10 px-4 py-6 text-gray-80">
                {violation.criterion}
              </div>

              <div className="flex-[112] min-w-0 border-b border-gray-10 px-4 py-6">
                <LevelBadge level={violation.level} />
              </div>

              <div className="flex-[112] min-w-0 border-b border-gray-10 px-4 py-6 text-gray-80">
                {violation.tag}
              </div>

              <div className="flex-[227] min-w-0 border-b border-gray-10 px-4 py-6 flex flex-col gap-4">
                <p className="text-[14px] font-medium leading-5 break-words text-gray-100">{violation.elementTitle}</p>
                <ElementImage srcs={violation.imageUrls} className="h-[61px] w-[105px]" />
                <div className="flex flex-col gap-2 text-[12px] leading-5">
                  <div className="flex gap-1">
                    <span className="w-9 shrink-0 text-gray-80">{t.violations.file}</span>
                    <span className="min-w-0 break-words text-gray-100">{violation.elementFile}</span>
                  </div>
                  <div className="flex gap-1">
                    <span className="w-9 shrink-0 text-gray-80">{t.violations.ocr}</span>
                    <span className="min-w-0 break-words text-gray-100">{violation.elementOcr}</span>
                  </div>
                </div>
                {/* View Full Audit — hidden per review; restore by uncommenting.
                <button type="button" className="inline-flex items-center gap-1.5 text-[14px] leading-5 text-brand-teal-dark underline">
                  {t.violations.viewFullAudit} <LinkIcon />
                </button>
                */}
              </div>

              <div className="flex-[184] min-w-0 border-b border-gray-10 px-4 py-6">
                <FixGuideCell
                  text={violation.fixGuide}
                  expanded={expandedRows.has(violation.id)}
                  onToggle={() => toggleRow(violation.id)}
                  t={t}
                />
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
