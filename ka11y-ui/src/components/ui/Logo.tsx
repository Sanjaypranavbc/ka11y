import Image from "next/image";
import { cn } from "@/lib/utils";

type LogoVariant = "color" | "white" | "gray";

interface LogoProps {
  variant?: LogoVariant;
  className?: string;
  label?: string;
}

export function Logo({ variant = "color", className, label = "kao" }: LogoProps) {
  return (
    <span
      role="img"
      aria-label={label}
      className={cn("inline-flex shrink-0", className)}
    >
      <Image
        src="/logo.png"
        alt=""
        width={90}
        height={26}
        className={cn(
          "h-[26px] w-[90px] object-contain",
          variant === "white" && "brightness-0 invert",
          variant === "gray" && "brightness-0 opacity-50",
        )}
        priority
      />
    </span>
  );
}
