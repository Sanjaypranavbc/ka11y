"use client";

import { useMemo, useState, useRef, useEffect } from "react";
import { ChevronDown, ChevronUp, X } from "lucide-react";
import { LanguageToggle } from "@/components/dashboard/LanguageToggle";
import { DownloadCsvButton } from "@/components/dashboard/DownloadActions";
import { PageHeader } from "@/components/dashboard/PageHeader";
import { ElementImage } from "@/components/dashboard/ElementImage";
import { PageFilterDropdown } from "@/components/dashboard/PageFilterDropdown";
import { useAuditData } from "@/components/dashboard/AuditDataContext";
import { useLanguage } from "@/components/dashboard/LanguageContext";
import { toNeedsReviewRows, getScannedPages, type ReviewRow, type ReviewStatus, type WcagLevel } from "@/lib/wcagAudit";
import type { Translations } from "@/lib/i18n/translations";
import { useInfiniteReveal } from "@/lib/useInfiniteReveal";
import { cn } from "@/lib/utils";

function LevelBadge({ level }: { level: WcagLevel }) {
  return (
    <span className="inline-flex items-center justify-center rounded-[8px] bg-brand-green-20 px-2 py-1 text-[14px] leading-5 text-brand-teal-dark">
      {level}
    </span>
  );
}

function VerdictPopover({
  onMoveToPass,
  onMoveToViolation,
  onClose,
  t,
}: {
  onMoveToPass: () => void;
  onMoveToViolation: () => void;
  onClose: () => void;
  t: Translations;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [selectedVerdict, setSelectedVerdict] = useState<"pass" | "fail">("pass");

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        onClose();
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [onClose]);

  function handleUpdate() {
    if (selectedVerdict === "pass") {
      onMoveToPass();
    } else {
      onMoveToViolation();
    }
    onClose();
  }

  return (
    <div
      ref={ref}
      className="absolute right-0 top-full z-30 mt-2 w-[320px] sm:w-[350px] rounded-[16px] border border-gray-200 bg-white p-5 shadow-xl text-left"
    >
      <h3 className="text-[16px] font-bold text-gray-900">{t.needsReview.verdictTitle}</h3>
      <p className="mt-1 text-[13px] leading-relaxed text-gray-500">{t.needsReview.verdictSubtitle}</p>

      <div className="mt-4 flex flex-col gap-3">
        {/* Mark as Pass Radio Box */}
        <label
          onClick={() => setSelectedVerdict("pass")}
          className={cn(
            "flex cursor-pointer items-start gap-3 rounded-[12px] p-3.5 border transition-all",
            selectedVerdict === "pass"
              ? "border-brand-teal bg-[#e6f4f1]"
              : "border-transparent hover:border-gray-200"
          )}
        >
          <div className="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full border-2 border-brand-teal">
            {selectedVerdict === "pass" && (
              <div className="h-2 w-2 rounded-full bg-brand-teal" />
            )}
          </div>
          <div className="flex flex-col">
            <span className="text-[14px] font-bold text-brand-teal-dark">{t.needsReview.markAsPass}</span>
            <span className="mt-0.5 text-[12px] text-gray-600">{t.needsReview.markAsPassDesc}</span>
          </div>
        </label>

        {/* Mark as Fail Radio Box */}
        <label
          onClick={() => setSelectedVerdict("fail")}
          className={cn(
            "flex cursor-pointer items-start gap-3 rounded-[12px] p-3.5 border transition-all",
            selectedVerdict === "fail"
              ? "border-red-400 bg-red-50/70"
              : "border-transparent hover:border-gray-200"
          )}
        >
          <div className="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full border-2 border-red-600">
            {selectedVerdict === "fail" && (
              <div className="h-2 w-2 rounded-full bg-red-600" />
            )}
          </div>
          <div className="flex flex-col">
            <span className="text-[14px] font-bold text-[#c00000]">{t.needsReview.markAsFail}</span>
            <span className="mt-0.5 text-[12px] text-gray-600">{t.needsReview.markAsFailDesc}</span>
          </div>
        </label>
      </div>

      {/* Divider */}
      <div className="my-4 border-t border-gray-100" />

      {/* Buttons */}
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={handleUpdate}
          className="rounded-[8px] bg-brand-teal px-5 py-2 text-[14px] font-medium text-white hover:opacity-90 transition-opacity"
        >
          {t.needsReview.update}
        </button>
        <button
          type="button"
          onClick={onClose}
          className="rounded-[8px] border border-gray-300 bg-white px-5 py-2 text-[14px] font-medium text-gray-700 hover:bg-gray-50 transition-colors"
        >
          {t.needsReview.cancel}
        </button>
      </div>
    </div>
  );
}

function ReviewButton({
  itemId,
  openId,
  setOpenId,
  onMoveToPass,
  onMoveToViolation,
  t,
}: {
  itemId: string;
  openId: string | null;
  setOpenId: (id: string | null) => void;
  onMoveToPass: () => void;
  onMoveToViolation: () => void;
  t: Translations;
}) {
  const isOpen = openId === itemId;
  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpenId(isOpen ? null : itemId)}
        className="flex items-center gap-2 rounded-[8px] bg-brand-teal-dark px-4 py-2 text-[14px] font-medium leading-5 text-white whitespace-nowrap shrink-0 hover:opacity-90 transition-opacity"
      >
        {t.needsReview.chooseVerdict}
        {isOpen ? <ChevronUp size={16} aria-hidden="true" /> : <ChevronDown size={16} aria-hidden="true" />}
      </button>
      {isOpen && (
        <VerdictPopover
          onMoveToPass={() => { onMoveToPass(); setOpenId(null); }}
          onMoveToViolation={() => { onMoveToViolation(); setOpenId(null); }}
          onClose={() => setOpenId(null)}
          t={t}
        />
      )}
    </div>
  );
}

/** A contrast colour is only meaningful on contrast findings; the adapters
 * fill the rest with an em dash placeholder. */
function hasColor(value: string): boolean {
  return Boolean(value) && value !== "—";
}

export default function NeedsReviewPage() {
  const { auditData } = useAuditData();
  const { t } = useLanguage();
  const STATUS_LABELS: Record<ReviewStatus, string> = {
    pass: t.needsReview.status.pass,
    violation: t.needsReview.status.violation,
    pending: t.needsReview.status.pending,
  };
  const [activeFilters, setActiveFilters] = useState<WcagLevel[]>([]);
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [openActionId, setOpenActionId] = useState<string | null>(null);
  const [selectedPage, setSelectedPage] = useState<string | null>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const sourceItems = useMemo(
    () => (auditData ? toNeedsReviewRows(auditData) : []),
    [auditData],
  );
  const scannedPages = useMemo(
    () => (auditData ? getScannedPages(auditData) : []),
    [auditData],
  );
  const selectedPageInfo = scannedPages.find((p) => p.page_url === selectedPage) ?? null;
  const [items, setItems] = useState<ReviewRow[]>(sourceItems);
  const [syncedSource, setSyncedSource] = useState(sourceItems);
  if (sourceItems !== syncedSource) {
    setSyncedSource(sourceItems);
    setItems(sourceItems);
  }

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

  function updateStatus(id: string, status: ReviewStatus) {
    setItems((prev) => prev.map((item) => (item.id === id ? { ...item, status } : item)));
  }

  // A row leaves this list the moment it is triaged (Move to Pass / Violation) —
  // no refresh needed. The change is scoped to the current report view and is
  // not persisted; running a new audit rebuilds the list from source. The
  // manual-action copy in translations states this.
  const pending = items.filter((item) => item.status === "pending");

  const byPage = selectedPage
    ? pending.filter((item) => item.pageUrl === selectedPage)
    : pending;

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

      <main className="flex flex-1 flex-col gap-6 min-w-0 px-4 py-6 sm:px-8 sm:py-8 lg:px-16 lg:gap-8 lg:py-10">

        {/* Page heading */}
        <div className="border-b border-gray-40 pb-4">
          <h1 className="text-[24px] font-medium leading-[32px] text-gray-100">{t.needsReview.heading}</h1>
          <p className="mt-2 text-[16px] leading-[24px] text-gray-80">
            {t.needsReview.subheading}
          </p>
        </div>

        {!auditData ? (
          <div className="flex min-h-[50vh] items-center justify-center rounded-2xl bg-gray-10">
            <p className="text-[16px] leading-6 text-gray-60">
              {t.needsReview.emptyState}
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
          {t.needsReview.showing(visibleCount, filtered.length, pending.length)}
        </p>

        {/* Table — horizontally scrollable, page does not scroll */}
        <div className="w-full overflow-x-auto rounded-[8px]">
        <div className="min-w-[1000px]">

          {/* Header */}
          <div className="flex w-full bg-gray-10 text-[14px] font-bold leading-6 text-gray-100">
            <div className="flex-[318] min-w-0 p-4">{t.needsReview.columns.reason}</div>
            <div className="flex-[76] min-w-0 p-4">{t.needsReview.columns.sc}</div>
            <div className="flex-[146] min-w-0 p-4">{t.needsReview.columns.criterion}</div>
            <div className="flex-[76] min-w-0 p-4">{t.needsReview.columns.level}</div>
            <div className="flex-[318] min-w-0 p-4">{t.needsReview.columns.element}</div>
            <div className="flex-[220] min-w-[170px] p-4">{t.needsReview.columns.yourVerdict}</div>
          </div>

          {/* Rows */}
          {visibleItems.map((item) => (
            <div key={item.id} className="flex w-full border-b border-gray-10 bg-white text-[14px] leading-5">

              <div className="flex-[318] min-w-0 border-b border-gray-10 px-4 py-6 flex flex-col gap-2">
                {item.reasonTitle && <p className="font-bold text-gray-100">{item.reasonTitle}</p>}
                <p className="font-bold text-gray-80">{item.reasonDescription}</p>
                {/* Learn More — hidden per review; restore by uncommenting.
                {/^https?:\/\//.test(item.helpUrl) ? (
                  <a
                    href={item.helpUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1.5 text-brand-teal-dark underline"
                  >
                    {t.needsReview.learnMore} <ExternalLink size={14} className="shrink-0" aria-hidden="true" />
                  </a>
                ) : (
                  <button type="button" className="inline-flex items-center gap-1.5 text-brand-teal-dark underline">
                    {t.needsReview.learnMore} <ExternalLink size={14} className="shrink-0" aria-hidden="true" />
                  </button>
                )}
                */}
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

              <div className="flex-[318] min-w-0 border-b border-gray-10 px-4 py-6 flex flex-col gap-4">
                {item.elementFilename && (
                  <p className="font-medium break-words text-gray-100">{item.elementFilename}</p>
                )}
                {/* Image box only for findings that are about an image; non-image
                    rules (media, axe-core) render no placeholder. */}
                {(item.imageUrls.length > 0 || item.elementFilename) && (
                  <ElementImage srcs={item.imageUrls} className="h-[90px] w-[105px]" />
                )}
                {/* Only render the detail lines this finding actually has —
                    contrast colours belong to contrast rules and OCR text to
                    image rules, so showing every label on every row printed a
                    column of "—" placeholders. */}
                <div className="flex flex-col gap-2 text-[12px] leading-5">
                  {hasColor(item.foreground) && (
                    <div className="flex gap-1">
                      <span className="shrink-0 text-gray-80">{t.needsReview.foreground}</span>
                      <span className="text-gray-100">{item.foreground}</span>
                    </div>
                  )}
                  {hasColor(item.background) && (
                    <div className="flex gap-1">
                      <span className="shrink-0 text-gray-80">{t.needsReview.background}</span>
                      <span className="text-gray-100">{item.background}</span>
                    </div>
                  )}
                  {item.altText && (
                    <div className="flex gap-1">
                      <span className="shrink-0 text-gray-80">{t.needsReview.altText}</span>
                      <span className="min-w-0 break-words text-gray-100">{item.altText}</span>
                    </div>
                  )}
                  {item.ocrText && (
                    <div className="flex gap-1">
                      <span className="shrink-0 text-gray-80">{t.needsReview.ocrText}</span>
                      <span className="min-w-0 break-words text-gray-100">{item.ocrText}</span>
                    </div>
                  )}
                </div>
                {/* View Full Audit — hidden per review; restore by uncommenting.
                <button type="button" className="inline-flex items-center gap-1.5 text-[14px] leading-5 text-brand-teal-dark underline">
                  {t.needsReview.viewFullAudit} <ExternalLink size={14} className="shrink-0" aria-hidden="true" />
                </button>
                */}
              </div>

              <div className="flex-[220] min-w-[170px] border-b border-gray-10 px-4 py-6">
                <ReviewButton
                  itemId={item.id}
                  openId={openActionId}
                  setOpenId={setOpenActionId}
                  onMoveToPass={() => updateStatus(item.id, "pass")}
                  onMoveToViolation={() => updateStatus(item.id, "violation")}
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
