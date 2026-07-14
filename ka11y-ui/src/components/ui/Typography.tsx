import { createElement, type ElementType, type ReactNode } from "react";
import { cn } from "@/lib/utils";

type HeadingLevel = 1 | 2 | 3;

const HEADING_CLASS: Record<HeadingLevel, string> = {
  1: "text-h1",
  2: "text-h2",
  3: "text-h3",
};

interface HeadingProps {
  level: HeadingLevel;
  as?: ElementType;
  className?: string;
  children: ReactNode;
  id?: string;
}

export function Heading({ level, as, className, children, id }: HeadingProps) {
  const Tag = as ?? (`h${level}` as ElementType);
  return createElement(
    Tag,
    { id, className: cn("text-brand-gray", HEADING_CLASS[level], className) },
    children,
  );
}

type TextVariant = 1 | 2 | 3 | 4;

const TEXT_CLASS: Record<TextVariant, string> = {
  1: "text-p1",
  2: "text-p2",
  3: "text-p3",
  4: "text-p4",
};

interface TextProps {
  variant?: TextVariant;
  as?: ElementType;
  className?: string;
  children: ReactNode;
}

export function Text({ variant = 3, as = "p", className, children }: TextProps) {
  return createElement(
    as,
    { className: cn("text-gray-80", TEXT_CLASS[variant], className) },
    children,
  );
}
