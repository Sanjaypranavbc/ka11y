import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  formatCriterionId,
  formatCriterionName,
  formatElementSnippet,
} from "@/lib/audit-format";
import { useLanguage } from "@/i18n/LanguageContext";
import { Copy, Expand } from "lucide-react";
import { toast } from "sonner";

interface FindingElementCellProps {
  elementHtml: string;
  elementSelector?: string | null;
  imageReference?: string | null;
  imageSrc?: string | null;
  imageText?: string | null;
  ruleId?: string | null;
  wcagSc?: string | null;
  criterionName?: string | null;
  reason?: string | null;
}

export function FindingElementCell({
  elementHtml,
  elementSelector,
  imageReference,
  imageSrc,
  imageText,
  ruleId,
  wcagSc,
  criterionName,
  reason,
}: FindingElementCellProps) {
  const { t } = useLanguage();
  const [open, setOpen] = useState(false);
  const snippet = formatElementSnippet(elementHtml);
  const selector = elementSelector?.trim() || "";
  const reference = imageReference?.trim() || "";
  const source = imageSrc?.trim() || "";
  const ocrText = imageText?.trim() || "";
  const rule = ruleId?.trim() || "";
  const findingReason = reason?.trim() || "";
  const hasDetails = Boolean(
    (elementHtml && elementHtml.trim()) || selector || reference || source || ocrText || rule || wcagSc || findingReason,
  );

  function copyText(text: string) {
    if (!text) return;

    function fallbackCopy(value: string) {
      const textarea = document.createElement("textarea");
      textarea.value = value;
      textarea.style.position = "fixed";
      textarea.style.opacity = "0";
      document.body.appendChild(textarea);
      textarea.focus();
      textarea.select();
      try {
        document.execCommand("copy");
        toast.success(t("modal.copied"));
      } catch {
        toast.error(t("modal.copyFailed"));
      }
      document.body.removeChild(textarea);
    }

    if (navigator.clipboard?.writeText) {
      navigator.clipboard.writeText(text)
        .then(() => toast.success(t("modal.copied")))
        .catch(() => fallbackCopy(text));
    } else {
      fallbackCopy(text);
    }
  }

  const copyAll = () => {
    const parts = [
      rule ? `${t("table.ruleId")}\n${rule}` : "",
      wcagSc ? `${t("table.sc")}\n${formatCriterionId(wcagSc)}` : "",
      criterionName || wcagSc ? `${t("table.criterion")}\n${formatCriterionName(criterionName, wcagSc)}` : "",
      findingReason ? `${t("table.reason")}\n${findingReason}` : "",
      elementHtml?.trim() ? `${t("modal.elementHtml")}\n${elementHtml.trim()}` : "",
      selector ? `${t("modal.elementSelector")}\n${selector}` : "",
      reference ? `${t("table.imageRef")}\n${reference}` : "",
      source ? `${t("table.imageSrc")}\n${source}` : "",
      ocrText ? `${t("table.imageText")}\n${ocrText}` : "",
    ].filter(Boolean).join("\n\n");

    copyText(parts);
  };

  const preview = (
    <div className="space-y-1 min-w-[16rem] max-w-[24rem]">
      {reference && (
        <div className="flex items-start gap-1.5">
          <Badge variant="outline" className="h-4 px-1.5 text-[9px] shrink-0">
            {t("table.imageRef")}
          </Badge>
          <span className="text-[10px] font-medium leading-snug break-all">{reference}</span>
        </div>
      )}

      {ocrText && (
        <div className="flex items-start gap-1.5">
          <Badge variant="outline" className="h-4 px-1.5 text-[9px] shrink-0">
            {t("table.imageText")}
          </Badge>
          <span className="text-[10px] text-muted-foreground leading-snug break-words max-h-16 overflow-hidden">
            {ocrText}
          </span>
        </div>
      )}

      <code className="block rounded bg-muted px-1.5 py-1 text-[10px] text-muted-foreground whitespace-pre-wrap break-all max-h-24 overflow-hidden">
        {snippet}
      </code>

      {selector && (
        <code className="block rounded bg-muted/60 px-1.5 py-1 text-[10px] text-muted-foreground whitespace-pre-wrap break-all max-h-16 overflow-hidden">
          {selector}
        </code>
      )}

      {source && source.startsWith("/api/v1/") ? (
        <div className="mt-2 mb-2 rounded-md overflow-hidden border bg-muted/30">
          <img src={source} alt="Violation element" className="max-h-32 w-auto object-contain" loading="lazy" />
        </div>
      ) : source && source !== reference ? (
        <div className="flex items-start gap-1.5">
          <Badge variant="outline" className="h-4 px-1.5 text-[9px] shrink-0">
            {t("table.imageSrc")}
          </Badge>
          <span className="text-[10px] text-muted-foreground leading-snug break-all max-h-12 overflow-hidden">
            {source}
          </span>
        </div>
      ) : null}
    </div>
  );

  return (
    <>
      {hasDetails ? (
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="w-full rounded-lg border border-border/70 bg-background/70 p-2 text-left transition-colors hover:bg-muted/35 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          aria-label={t("modal.fullView")}
        >
          <div className="mb-2 flex items-center justify-between gap-2">
            <span className="text-[9px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
              {t("table.element")}
            </span>
            <span className="inline-flex items-center gap-1 text-[10px] font-medium text-primary">
              <Expand className="h-3 w-3" aria-hidden="true" />
              {t("modal.fullView")}
            </span>
          </div>
          {preview}
        </button>
      ) : (
        preview
      )}

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="w-[min(92vw,72rem)] max-w-4xl max-h-[90vh] overflow-hidden p-0">
          <DialogHeader className="border-b px-6 py-5">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="space-y-2">
                <DialogTitle className="flex flex-wrap items-center gap-2">
                  <span>{t("modal.elementDetails")}</span>
                  {wcagSc && (
                    <Badge variant="outline" className="font-mono">
                      {formatCriterionId(wcagSc)}
                    </Badge>
                  )}
                  {rule && (
                    <Badge variant="secondary" className="font-mono">
                      {rule}
                    </Badge>
                  )}
                </DialogTitle>
                {(criterionName || wcagSc) && (
                  <DialogDescription className="text-left">
                    {formatCriterionName(criterionName, wcagSc)}
                  </DialogDescription>
                )}
              </div>

              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={copyAll}
                className="shrink-0"
              >
                <Copy className="mr-1.5 h-3 w-3" aria-hidden="true" />
                {t("modal.copy")}
              </Button>
            </div>
          </DialogHeader>

          <div className="space-y-4 overflow-y-auto px-6 py-5">
            {findingReason && (
              <section className="space-y-2">
                <h4 className="text-sm font-medium text-foreground">{t("table.reason")}</h4>
                <div className="rounded-md border bg-muted/40 px-3 py-2 text-sm leading-relaxed text-foreground whitespace-pre-wrap break-words">
                  {findingReason}
                </div>
              </section>
            )}

            {elementHtml?.trim() && (
              <section className="space-y-2">
                <h4 className="text-sm font-medium text-foreground">{t("modal.elementHtml")}</h4>
                <div className="rounded-md bg-muted p-3">
                  <pre className="overflow-x-auto whitespace-pre-wrap break-all text-xs leading-relaxed">
                    <code>{elementHtml.trim()}</code>
                  </pre>
                </div>
              </section>
            )}

            {selector && (
              <section className="space-y-2">
                <h4 className="text-sm font-medium text-foreground">{t("modal.elementSelector")}</h4>
                <div className="rounded-md bg-muted/70 p-3">
                  <pre className="overflow-x-auto whitespace-pre-wrap break-all text-xs leading-relaxed">
                    <code>{selector}</code>
                  </pre>
                </div>
              </section>
            )}

            {reference && (
              <section className="space-y-2">
                <h4 className="text-sm font-medium text-foreground">{t("table.imageRef")}</h4>
                <div className="rounded-md border bg-muted/20 px-3 py-2 text-xs leading-relaxed break-all">
                  {reference}
                </div>
              </section>
            )}

            {source && source.startsWith("/api/v1/") ? (
              <section className="space-y-2">
                <h4 className="text-sm font-medium text-foreground">{t("table.imageSrc")}</h4>
                <div className="rounded-md border bg-muted/20 overflow-hidden flex justify-center p-2">
                  <img src={source} alt="Violation element expanded" className="max-h-96 w-auto object-contain" loading="lazy" />
                </div>
              </section>
            ) : source ? (
              <section className="space-y-2">
                <h4 className="text-sm font-medium text-foreground">{t("table.imageSrc")}</h4>
                <div className="rounded-md border bg-muted/20 px-3 py-2 text-xs leading-relaxed break-all">
                  {source}
                </div>
              </section>
            ) : null}

            {ocrText && (
              <section className="space-y-2">
                <h4 className="text-sm font-medium text-foreground">{t("table.imageText")}</h4>
                <div className="rounded-md border bg-muted/20 px-3 py-2 text-xs leading-relaxed whitespace-pre-wrap break-words">
                  {ocrText}
                </div>
              </section>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
