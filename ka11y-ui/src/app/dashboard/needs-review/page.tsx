"use client";

import { useMemo, useState, useRef, useEffect } from "react";
import { ChevronDown, ChevronUp, X, ExternalLink, CheckSquare, AlertTriangle } from "lucide-react";
import { LanguageToggle } from "@/components/dashboard/LanguageToggle";
import { DownloadCsvButton, DownloadPdfButton } from "@/components/dashboard/DownloadActions";
import { PageHeader } from "@/components/dashboard/PageHeader";
import { useAuditData } from "@/components/dashboard/AuditDataContext";
import { toNeedsReviewRows, type ReviewRow, type ReviewStatus, type WcagLevel } from "@/lib/wcagAudit";
import { cn } from "@/lib/utils";

const DEMO_ITEMS: ReviewRow[] = [
  {
    id: "1",
    status: "pass",
    reasonTitle: "Text in img_278b93dcc441.png",
    reasonDescription:
      '"the p" has a contrast ratio of 10.11:1 — meets the AA large text minimum. Foreground #f5f5f3 on background #3c3c3c.',
    sc: "1.4.3",
    criterion: "Contrast (Minimum)",
    level: "AAA",
    tag: "img",
    elementFilename: "img_630bb504868c.png",
    foreground: "#a8ae8a",
    background: "#1f2324",
    ocrText: "flavorful salads right at home;",
    helpUrl: "https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum",
  },
  {
    id: "2",
    status: "pending",
    reasonTitle: "Text in img_278b93dcc441.png",
    reasonDescription:
      '"the p" has a contrast ratio of 10.11:1 — meets the AA large text minimum. Foreground #f5f5f3 on background #3c3c3c.',
    sc: "1.4.3",
    criterion: "Contrast (Minimum)",
    level: "AAA",
    tag: "img",
    elementFilename: "img_nature.png",
    foreground: "#a8ae8a",
    background: "#1f2324",
    ocrText: "Harvest at peak nutrition.",
    helpUrl: "https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum",
  },
  {
    id: "3",
    status: "pending",
    reasonTitle: "Text in img_hero_banner.png",
    reasonDescription:
      '"h1" has a contrast ratio of 3.2:1 — below the AA minimum of 4.5:1. Foreground #cccccc on background #999999.',
    sc: "1.4.3",
    criterion: "Contrast (Minimum)",
    level: "AA",
    tag: "img",
    elementFilename: "img_hero_banner.png",
    foreground: "#cccccc",
    background: "#999999",
    ocrText: "Fresh from the farm.",
    helpUrl: "https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum",
  },
  {
    id: "4",
    status: "violation",
    reasonTitle: "Text in img_product_card.png",
    reasonDescription:
      '"span" has a contrast ratio of 2.1:1 — fails all contrast thresholds. Foreground #e0e0e0 on background #c0c0c0.',
    sc: "1.4.3",
    criterion: "Contrast (Minimum)",
    level: "A",
    tag: "img",
    elementFilename: "img_product_card.png",
    foreground: "#e0e0e0",
    background: "#c0c0c0",
    ocrText: "Organic produce.",
    helpUrl: "https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum",
  },
];

const STATUS_LABELS: Record<ReviewStatus, string> = {
  pass: "Pass",
  violation: "Violation",
  pending: "Pending",
};

const STATUS_STYLES: Record<ReviewStatus, string> = {
  pass: "bg-gray-10 text-gray-100",
  violation: "bg-[#fde8e4] text-[#c00000]",
  pending: "bg-gray-10 text-gray-80",
};

function LevelBadge({ level }: { level: WcagLevel }) {
  return (
    <span className="inline-flex items-center justify-center rounded-[8px] bg-brand-green-20 px-2 py-1 text-[14px] leading-5 text-brand-teal-dark">
      {level}
    </span>
  );
}

function ManualActionPopup({
  onMoveToPass,
  onMoveToViolation,
  onClose,
}: {
  onMoveToPass: () => void;
  onMoveToViolation: () => void;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        onClose();
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [onClose]);

  return (
    <div
      ref={ref}
      className="absolute right-0 top-full z-20 mt-1 w-[280px] rounded-[8px] bg-white shadow-[0px_0px_8px_rgba(0,0,0,0.12)]"
    >
      <div className="border-b border-gray-10 px-6 py-4">
        <p className="text-[16px] font-medium leading-6 text-gray-100">Manual Action</p>
        <p className="mt-1 text-[14px] leading-5 text-gray-100">Update the status of this item manually.</p>
      </div>
      <div className="flex flex-col gap-4 px-6 py-4">
        <button
          type="button"
          onClick={onMoveToPass}
          className="flex items-start gap-2 rounded-[8px] p-2 text-left hover:bg-gray-10"
        >
          <CheckSquare size={24} className="mt-0.5 shrink-0 text-brand-teal-dark" aria-hidden="true" />
          <div className="flex flex-col gap-2">
            <span className="text-[14px] font-bold leading-5 text-brand-teal-dark underline">Move to Pass</span>
            <span className="text-[14px] leading-5 text-gray-80">
              Mark this item as passed if it no longer exists or is already fixed
            </span>
          </div>
        </button>
        <div className="h-px bg-gray-10" />
        <button
          type="button"
          onClick={onMoveToViolation}
          className="flex items-start gap-2 rounded-[8px] p-2 text-left hover:bg-gray-10"
        >
          <AlertTriangle size={24} className="mt-0.5 shrink-0 text-gray-80" aria-hidden="true" />
          <div className="flex flex-col gap-2">
            <span className="text-[14px] font-bold leading-5 text-gray-100">Move to Violation</span>
            <span className="text-[14px] leading-5 text-gray-80">
              Keep this item as a violation that needs to be fixed.
            </span>
          </div>
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
}: {
  itemId: string;
  openId: string | null;
  setOpenId: (id: string | null) => void;
  onMoveToPass: () => void;
  onMoveToViolation: () => void;
}) {
  const isOpen = openId === itemId;
  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpenId(isOpen ? null : itemId)}
        className="flex items-center gap-2 rounded-[8px] bg-brand-teal px-4 py-2 text-[14px] leading-5 text-white hover:opacity-90"
      >
        Review
        {isOpen ? <ChevronUp size={16} aria-hidden="true" /> : <ChevronDown size={16} aria-hidden="true" />}
      </button>
      {isOpen && (
        <ManualActionPopup
          onMoveToPass={() => { onMoveToPass(); setOpenId(null); }}
          onMoveToViolation={() => { onMoveToViolation(); setOpenId(null); }}
          onClose={() => setOpenId(null)}
        />
      )}
    </div>
  );
}

export default function NeedsReviewPage() {
  const { auditData } = useAuditData();
  const [activeFilters, setActiveFilters] = useState<WcagLevel[]>([]);
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [openActionId, setOpenActionId] = useState<string | null>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const sourceItems = useMemo(
    () => (auditData ? toNeedsReviewRows(auditData) : DEMO_ITEMS),
    [auditData],
  );
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

  const filtered =
    activeFilters.length === 0
      ? items
      : items.filter((item) => activeFilters.includes(item.level));

  const LEVELS: WcagLevel[] = ["A", "AA", "AAA"];

  const headerActions = (
    <>
      <LanguageToggle />
      <DownloadCsvButton />
      <DownloadPdfButton />
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

        {/* Filter bar */}
        <div className="flex flex-wrap items-center gap-3">
          <div className="relative" ref={dropdownRef}>
            <button
              type="button"
              onClick={() => setDropdownOpen((v) => !v)}
              className="flex items-center gap-2 rounded-[16px] border border-gray-40 bg-gray-10 px-4 py-2 text-[14px] leading-6 text-gray-100 sm:text-[16px]"
            >
              WCAG Level
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
              <span className="text-[14px] leading-6 text-gray-80 sm:text-[16px]">WCAG Level:</span>
              {activeFilters.map((level) => (
                <span
                  key={level}
                  className="inline-flex h-8 items-center gap-1.5 rounded-[8px] border border-brand-teal-dark bg-brand-green-20 px-2 py-1 text-[14px] leading-6 text-brand-teal-dark"
                >
                  {level}
                  <button
                    type="button"
                    onClick={() => toggleFilter(level)}
                    aria-label={`Remove ${level} filter`}
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
                Clear All
              </button>
            </div>
          )}
        </div>

        <p className="text-[14px] leading-6 text-gray-100 sm:text-[16px]">
          Showing {filtered.length} of {filtered.length} items ({items.length} total)
        </p>

        {/* Table — horizontally scrollable, page does not scroll */}
        <div className="w-full overflow-x-auto rounded-[8px]">
        <div className="min-w-[1000px]">

          {/* Header */}
          <div className="flex w-full bg-gray-10 text-[14px] font-bold leading-6 text-gray-100">
            <div className="flex-[110] min-w-0 p-4">Status</div>
            <div className="flex-[318] min-w-0 p-4">Reason</div>
            <div className="flex-[76] min-w-0 p-4">SC</div>
            <div className="flex-[146] min-w-0 p-4">Criterion</div>
            <div className="flex-[76] min-w-0 p-4">Level</div>
            <div className="flex-[76] min-w-0 p-4">Tag</div>
            <div className="flex-[318] min-w-0 border-r border-gray-10 p-4">Element</div>
            <div className="flex-[184] min-w-0 p-4">Action</div>
          </div>

          {/* Rows */}
          {filtered.map((item) => (
            <div key={item.id} className="flex w-full border-b border-gray-10 bg-white text-[14px] leading-5">

              <div className="flex-[110] min-w-0 border-b border-gray-10 px-4 py-6">
                <span className={cn("inline-flex items-center rounded-[8px] px-3 py-1 text-[14px] leading-5", STATUS_STYLES[item.status])}>
                  {STATUS_LABELS[item.status]}
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
                    Learn More <ExternalLink size={14} className="shrink-0" aria-hidden="true" />
                  </a>
                ) : (
                  <button type="button" className="inline-flex items-center gap-1.5 text-brand-teal-dark underline">
                    Learn More <ExternalLink size={14} className="shrink-0" aria-hidden="true" />
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

              <div className="flex-[318] min-w-0 border-b border-r border-gray-10 px-4 py-6 flex flex-col gap-4">
                <p className="font-medium text-gray-100">{item.elementFilename}</p>
                <div className="h-[90px] w-[105px] overflow-hidden rounded-[8px] bg-gray-40 shadow-[0px_0px_18px_0px_rgba(0,0,0,0.09)]" />
                <div className="flex flex-col gap-2 text-[12px] leading-5">
                  <div className="flex gap-1">
                    <span className="shrink-0 text-gray-80">Foreground:</span>
                    <span className="text-gray-100">{item.foreground}</span>
                  </div>
                  <div className="flex gap-1">
                    <span className="shrink-0 text-gray-80">Background:</span>
                    <span className="text-gray-100">{item.background}</span>
                  </div>
                  <div className="flex gap-1">
                    <span className="shrink-0 text-gray-80">OCR Text:</span>
                    <span className="text-gray-100">{item.ocrText}</span>
                  </div>
                </div>
                <button type="button" className="inline-flex items-center gap-1.5 text-[14px] leading-5 text-brand-teal-dark underline">
                  View Full Audit <ExternalLink size={14} className="shrink-0" aria-hidden="true" />
                </button>
              </div>

              <div className="flex-[184] min-w-0 border-b border-gray-10 px-4 py-6">
                <ReviewButton
                  itemId={item.id}
                  openId={openActionId}
                  setOpenId={setOpenActionId}
                  onMoveToPass={() => updateStatus(item.id, "pass")}
                  onMoveToViolation={() => updateStatus(item.id, "violation")}
                />
              </div>

            </div>
          ))}
        </div>
        </div>

      </main>
    </>
  );
}
