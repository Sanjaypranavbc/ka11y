import type { ReactNode } from "react";
import { Card } from "@/components/ui/Card";
import { cn } from "@/lib/utils";

interface ChartCardProps {
  title: string;
  children: ReactNode;
  legend?: ReactNode;
  className?: string;
}

export function ChartCard({ title, children, legend, className }: ChartCardProps) {
  return (
    <Card className={cn("flex flex-col", className)}>
      <h2 className="text-[18px] font-medium leading-[26px] text-gray-100">
        {title}
      </h2>
      <div className="mt-4 flex-1">{children}</div>
      {legend ? <div className="mt-4 flex flex-wrap items-center gap-5">{legend}</div> : null}
    </Card>
  );
}

interface LegendItemProps {
  color: string;
  label: string;
}

export function LegendItem({ color, label }: LegendItemProps) {
  return (
    <span className="inline-flex items-center gap-[11px] text-[16px] leading-6 text-gray-100">
      <span
        aria-hidden="true"
        className="inline-block h-[17px] w-[17px] shrink-0 rounded-full"
        style={{ backgroundColor: color }}
      />
      {label}
    </span>
  );
}
