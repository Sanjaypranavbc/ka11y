"use client";

import { useMemo, useState, useRef, useEffect } from "react";
import { ChevronDown, X, ExternalLink } from "lucide-react";
import { LanguageToggle } from "@/components/dashboard/LanguageToggle";
import { DownloadCsvButton, DownloadPdfButton } from "@/components/dashboard/DownloadActions";
import { PageHeader } from "@/components/dashboard/PageHeader";
import { useAuditData } from "@/components/dashboard/AuditDataContext";
import { toViolationRows, type ViolationRow, type WcagLevel } from "@/lib/wcagAudit";
import { cn } from "@/lib/utils";

const DEMO_VIOLATIONS: ViolationRow[] = [
  {
    id: "1",
    title: "Image has no description (alt text)",
    description: "Screen-reader users won't know what it show",
    sc: "1.1.1",
    criterion: "Non-text Content",
    level: "AAA",
    tag: "Button",
    elementTitle: "Missing Alt text on main logo",
    elementFile: "img_8e5d9115102b.png",
    elementOcr: "Croppico alt FARMING",
    fixGuide:
      "Ensure text meets contrast ratios: 4.5:1 for normal text, 3:1 for large text (18pt / 14pt bold). Use a contrast checker tool to verify. Adjust foreground or background colors until the threshold is met.",
  },
  {
    id: "2",
    title: "Image has no description (alt text)",
    description: "Screen-reader users won't know what it show",
    sc: "1.1.1",
    criterion: "Non-text Content",
    level: "AAA",
    tag: "Button",
    elementTitle: "Missing Alt text on main logo",
    elementFile: "img_8e5d9115102b.png",
    elementOcr: "Croppico alt FARMING",
    fixGuide:
      "Ensure text meets contrast ratios: 4.5:1 for normal text, 3:1 for large text (18pt / 14pt bold). Use a contrast checker tool to verify. Adjust foreground or background colors until the threshold is met.",
  },
  {
    id: "3",
    title: "Insufficient color contrast",
    description: "Text does not meet minimum contrast ratio requirements",
    sc: "1.4.3",
    criterion: "Contrast (Minimum)",
    level: "AA",
    tag: "p",
    elementTitle: "Body text on hero section",
    elementFile: "hero_section.png",
    elementOcr: "Welcome to our website",
    fixGuide:
      'Add a descriptive alt attribute to the img element. The alt text should convey the purpose and meaning of the image. For decorative images, use alt="" to hide them from assistive technologies.',
  },
  {
    id: "4",
    title: "Missing form label",
    description: "Input field lacks an associated label",
    sc: "1.3.1",
    criterion: "Info and Relationships",
    level: "A",
    tag: "input",
    elementTitle: "Search input field",
    elementFile: "search_form.png",
    elementOcr: "Search...",
    fixGuide:
      "Associate a label element with the input using the for/id attribute pair, or wrap the input inside a label element. Alternatively, use aria-label or aria-labelledby attributes.",
  },
];

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
}: {
  text: string;
  expanded: boolean;
  onToggle: () => void;
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
          {expanded ? "Show less" : "Read more"}
        </button>
      )}
    </div>
  );
}

export default function ViolationsPage() {
  const { auditData } = useAuditData();
  const [activeFilters, setActiveFilters] = useState<WcagLevel[]>([]);
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set());
  const dropdownRef = useRef<HTMLDivElement>(null);

  const ALL_VIOLATIONS = useMemo(
    () => (auditData ? toViolationRows(auditData) : DEMO_VIOLATIONS),
    [auditData],
  );

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

  const filtered =
    activeFilters.length === 0
      ? ALL_VIOLATIONS
      : ALL_VIOLATIONS.filter((v) => activeFilters.includes(v.level));

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
          Showing {filtered.length} of {filtered.length} violations ({ALL_VIOLATIONS.length} total)
        </p>

        {/* Table — horizontally scrollable, page does not scroll */}
        <div className="w-full overflow-x-auto rounded-[8px]">
        <div className="min-w-[860px]">

          {/* Header row */}
          <div className="flex w-full bg-gray-10 text-[14px] font-bold leading-6 text-gray-100">
            <div className="flex-[227] min-w-0 p-4">Reason</div>
            <div className="flex-[112] min-w-0 p-4">SC</div>
            <div className="flex-[146] min-w-0 p-4">Criterion</div>
            <div className="flex-[112] min-w-0 p-4">Level</div>
            <div className="flex-[112] min-w-0 p-4">Tag</div>
            <div className="flex-[227] min-w-0 border-r border-gray-10 p-4">Element</div>
            <div className="flex-[184] min-w-0 p-4">Fix Guide</div>
          </div>

          {/* Data rows */}
          {filtered.map((violation) => (
            <div key={violation.id} className="flex w-full border-b border-gray-10 bg-white text-[14px] leading-5">

              <div className="flex-[227] min-w-0 border-b border-gray-10 px-4 py-6 flex flex-col gap-2">
                <p className="font-bold text-gray-100">{violation.title}</p>
                <p className="text-gray-80">{violation.description}</p>
                {/^https?:\/\//.test(violation.fixGuide) ? (
                  <a
                    href={violation.fixGuide}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1.5 text-brand-teal-dark underline"
                  >
                    Learn More <LinkIcon />
                  </a>
                ) : (
                  <button type="button" className="inline-flex items-center gap-1.5 text-brand-teal-dark underline">
                    Learn More <LinkIcon />
                  </button>
                )}
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

              <div className="flex-[227] min-w-0 border-b border-r border-gray-10 px-4 py-6 flex flex-col gap-4">
                <p className="text-[14px] font-medium leading-5 text-gray-100">{violation.elementTitle}</p>
                <div className="h-[61px] w-[105px] overflow-hidden rounded-[8px] bg-gray-40 shadow-[0px_0px_18px_0px_rgba(0,0,0,0.09)]" />
                <div className="flex flex-col gap-2 text-[12px] leading-5">
                  <div className="flex gap-1">
                    <span className="w-9 shrink-0 text-gray-80">File:</span>
                    <span className="text-gray-100">{violation.elementFile}</span>
                  </div>
                  <div className="flex gap-1">
                    <span className="w-9 shrink-0 text-gray-80">OCR:</span>
                    <span className="text-gray-100">{violation.elementOcr}</span>
                  </div>
                </div>
                <button type="button" className="inline-flex items-center gap-1.5 text-[14px] leading-5 text-brand-teal-dark underline">
                  View Full Audit <LinkIcon />
                </button>
              </div>

              <div className="flex-[184] min-w-0 border-b border-gray-10 px-4 py-6">
                <FixGuideCell
                  text={violation.fixGuide}
                  expanded={expandedRows.has(violation.id)}
                  onToggle={() => toggleRow(violation.id)}
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
