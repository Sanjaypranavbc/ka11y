import { cn } from "@/lib/utils";

interface MetricCardProps {
  label: string;
  value: number;
  variant?: "default" | "critical" | "serious" | "success";
  icon: React.ReactNode;
}

export function MetricCard({ label, value, variant = "default", icon }: MetricCardProps) {
  return (
    <div
      className={cn(
        "rounded-lg border border-border bg-card p-5 flex items-center gap-4",
        variant === "critical" && "border-destructive/30 bg-destructive/5",
        variant === "serious" && "border-serious/30 bg-serious/5",
        variant === "success" && "border-success/30 bg-success/5"
      )}
    >
      <div
        className={cn(
          "h-10 w-10 rounded-lg flex items-center justify-center shrink-0",
          variant === "default" && "bg-primary/10 text-primary",
          variant === "critical" && "bg-destructive/10 text-destructive",
          variant === "serious" && "bg-serious/10 text-serious",
          variant === "success" && "bg-success/10 text-success"
        )}
      >
        {icon}
      </div>
      <div>
        <p className="text-2xl font-bold text-foreground">{value}</p>
        <p className="text-xs text-muted-foreground">{label}</p>
      </div>
    </div>
  );
}
