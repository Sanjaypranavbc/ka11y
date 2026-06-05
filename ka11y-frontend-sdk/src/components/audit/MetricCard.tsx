import { cn } from "@/lib/utils";

interface MetricCardProps {
  label: string;
  value: number;
  variant?: "default" | "critical" | "serious" | "success";
  icon: React.ReactNode;
}

const stripeColor = {
  default:  "bg-primary",
  critical: "bg-destructive",
  serious:  "bg-serious",
  success:  "bg-success",
};

const valueColor = {
  default:  "text-primary",
  critical: "text-destructive",
  serious:  "text-serious",
  success:  "text-success",
};

export function MetricCard({ label, value, variant = "default", icon }: MetricCardProps) {
  return (
    <div className="relative border border-border bg-card overflow-hidden flex">
      {/* Left accent stripe */}
      <div className={cn("w-[3px] shrink-0 self-stretch", stripeColor[variant])} />

      <div className="flex-1 p-4 pt-3.5">
        <p className="text-[9px] font-semibold tracking-[0.18em] uppercase text-muted-foreground mb-2.5">
          {label}
        </p>
        <p className={cn("text-[2.6rem] font-bold leading-none tabular-nums font-mono", valueColor[variant])}>
          {value.toLocaleString()}
        </p>
      </div>

      {/* Watermark icon */}
      <div className="absolute bottom-2 right-3 text-muted-foreground/8 pointer-events-none" aria-hidden="true">
        <span className="[&_svg]:h-12 [&_svg]:w-12">{icon}</span>
      </div>
    </div>
  );
}