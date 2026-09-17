import { Logo } from "@/components/ui/Logo";
import { cn } from "@/lib/utils";

/** Kao logo + the A11Y wordmark, used by the sidebar and the mobile header. */
export function AdminBrand({ className, wordmark = true }: { className?: string; wordmark?: boolean }) {
  return (
    <div className={cn("flex items-center gap-3", className)}>
      <Logo variant="color" label="Kao" />
      {wordmark && (
        <span
          className="border-l border-gray-40 pl-3 text-[20px] font-semibold leading-6 tracking-wide text-brand-teal-dark"
          style={{ fontFamily: "var(--font-logo), var(--font-sans)" }}
        >
          A11Y
        </span>
      )}
    </div>
  );
}
