"use client";

import { CheckCircle2, X } from "lucide-react";

export function ScanCompleteModal({
  url,
  onViewViolations,
  onViewNeedsReview,
  onClose,
}: {
  url: string;
  onViewViolations: () => void;
  onViewNeedsReview: () => void;
  onClose: () => void;
}) {
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="scan-complete-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4"
    >
      <div className="relative w-full max-w-[440px] rounded-[16px] bg-white px-6 py-8 shadow-[0px_8px_32px_rgba(0,0,0,0.18)] sm:px-10 sm:py-10">
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          className="absolute right-4 top-4 text-gray-60 hover:text-gray-100"
        >
          <X size={20} aria-hidden="true" />
        </button>

        <div className="flex flex-col items-center gap-4 text-center">
          <CheckCircle2 size={48} className="text-brand-teal-dark" aria-hidden="true" />
          <div className="flex flex-col gap-2">
            <h2 id="scan-complete-title" className="text-[20px] font-medium leading-7 text-gray-100">
              Your analysis is completed
            </h2>
            <p className="text-[14px] leading-5 text-gray-80">
              Accessibility scan for <span className="font-medium text-gray-100">{url}</span> finished. Choose where to go next.
            </p>
          </div>

          <div className="mt-2 flex w-full flex-col gap-3">
            <button
              type="button"
              onClick={onViewViolations}
              className="w-full rounded-[16px] bg-brand-green-80 px-6 py-3 text-[16px] font-medium leading-6 text-white hover:opacity-90"
            >
              View Violations
            </button>
            <button
              type="button"
              onClick={onViewNeedsReview}
              className="w-full rounded-[16px] border border-brand-teal bg-white px-6 py-3 text-[16px] font-medium leading-6 text-brand-teal-dark hover:bg-brand-green-20"
            >
              View Needs Review
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
