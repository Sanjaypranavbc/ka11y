import { Badge } from "@/components/ui/badge";

export function EngineBadge({ detectedBy }: { detectedBy?: string[] }) {
  if (!detectedBy || detectedBy.length === 0) return null;

  return (
    <div className="flex flex-wrap gap-1 mt-1">
      {detectedBy.map((engine) => {
        let bgColor = "bg-gray-100 text-gray-800 border-gray-200";
        if (engine === "axe-core") bgColor = "bg-blue-100 text-blue-800 border-blue-200";
        if (engine === "accesslint") bgColor = "bg-purple-100 text-purple-800 border-purple-200";
        if (engine === "python") bgColor = "bg-emerald-100 text-emerald-800 border-emerald-200";

        return (
          <Badge key={engine} variant="outline" className={`text-[10px] uppercase tracking-wider ${bgColor}`}>
            {engine}
          </Badge>
        );
      })}
    </div>
  );
}
