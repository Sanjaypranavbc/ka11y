import Image from "next/image";
import Link from "next/link";
import { cn } from "@/lib/utils";

type LogoVariant = "color" | "white" | "gray";

interface LogoProps {
  variant?: LogoVariant;
  className?: string;
  /** Accessible name: the image's name, or the link's purpose when `href` is set. */
  label?: string;
  /** When set, the logo is a link (used to send every logo click to New Audit). */
  href?: string;
}

export function Logo({ variant = "color", className, label = "kao", href }: LogoProps) {
  const image = (
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
  );

  if (href) {
    return (
      <Link href={href} aria-label={label} className={cn("inline-flex shrink-0 rounded-md", className)}>
        {image}
      </Link>
    );
  }
  return (
    <span role="img" aria-label={label} className={cn("inline-flex shrink-0", className)}>
      {image}
    </span>
  );
}
