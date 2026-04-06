import { Badge } from "@/components/ui/badge";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { formatElementSnippet } from "@/lib/audit-format";
import { useLanguage } from "@/i18n/LanguageContext";

interface FindingElementCellProps {
  elementHtml: string;
  elementSelector?: string | null;
  imageReference?: string | null;
  imageSrc?: string | null;
  imageText?: string | null;
}

export function FindingElementCell({
  elementHtml,
  elementSelector,
  imageReference,
  imageSrc,
  imageText,
}: FindingElementCellProps) {
  const { t } = useLanguage();
  const snippet = formatElementSnippet(elementHtml);

  return (
    <div className="space-y-1 min-w-[16rem] max-w-[24rem]">
      {imageReference && (
        <div className="flex items-start gap-1.5">
          <Badge variant="outline" className="h-4 px-1.5 text-[9px] shrink-0">
            {t("table.imageRef")}
          </Badge>
          <span className="text-[10px] font-medium leading-snug break-all">{imageReference}</span>
        </div>
      )}

      {imageText && (
        <div className="flex items-start gap-1.5">
          <Badge variant="outline" className="h-4 px-1.5 text-[9px] shrink-0">
            {t("table.imageText")}
          </Badge>
          <span className="text-[10px] text-muted-foreground leading-snug break-words">
            {imageText}
          </span>
        </div>
      )}

      <Tooltip>
        <TooltipTrigger asChild>
          <code
            tabIndex={0}
            className="block rounded bg-muted px-1.5 py-1 text-[10px] text-muted-foreground whitespace-pre-wrap break-all max-h-28 overflow-auto cursor-help"
          >
            {snippet}
          </code>
        </TooltipTrigger>
        <TooltipContent className="max-w-xl text-[10px] whitespace-pre-wrap break-all">
          {snippet}
        </TooltipContent>
      </Tooltip>

      {elementSelector && (
        <Tooltip>
          <TooltipTrigger asChild>
            <code
              tabIndex={0}
              className="block rounded bg-muted/60 px-1.5 py-1 text-[10px] text-muted-foreground whitespace-pre-wrap break-all max-h-20 overflow-auto cursor-help"
            >
              {elementSelector}
            </code>
          </TooltipTrigger>
          <TooltipContent className="max-w-xl text-[10px] whitespace-pre-wrap break-all">
            {elementSelector}
          </TooltipContent>
        </Tooltip>
      )}

      {imageSrc && imageSrc !== imageReference && (
        <div className="flex items-start gap-1.5">
          <Badge variant="outline" className="h-4 px-1.5 text-[9px] shrink-0">
            {t("table.imageSrc")}
          </Badge>
          <span className="text-[10px] text-muted-foreground leading-snug break-all">{imageSrc}</span>
        </div>
      )}
    </div>
  );
}
