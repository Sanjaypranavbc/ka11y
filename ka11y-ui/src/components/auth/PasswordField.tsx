"use client";

import { useState } from "react";
import { Eye, EyeOff } from "lucide-react";
import { inputClass, labelClass } from "@/components/auth/AuthShell";

type Props = {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  autoComplete: "current-password" | "new-password";
  showLabel: string;
  hideLabel: string;
  hint?: string;
  error?: string;
  required?: boolean;
  disabled?: boolean;
};

/**
 * Password input with a show/hide toggle (WCAG 3.3.8: the user may reveal
 * what they typed; the toggle is a real button with a state for screen readers).
 * Errors are linked with aria-describedby / aria-invalid (WCAG 3.3.1).
 */
export function PasswordField({
  id,
  label,
  value,
  onChange,
  autoComplete,
  showLabel,
  hideLabel,
  hint,
  error,
  required = true,
  disabled = false,
}: Props) {
  const [visible, setVisible] = useState(false);
  const hintId = hint ? `${id}-hint` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const describedBy = [hintId, errorId].filter(Boolean).join(" ") || undefined;

  return (
    <div>
      <label htmlFor={id} className={labelClass}>
        {label}
      </label>
      <div className="relative">
        <input
          id={id}
          name={id}
          type={visible ? "text" : "password"}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          autoComplete={autoComplete}
          required={required}
          disabled={disabled}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy}
          className={`${inputClass} pr-12`}
        />
        <button
          type="button"
          onClick={() => setVisible((v) => !v)}
          aria-pressed={visible}
          aria-label={visible ? hideLabel : showLabel}
          disabled={disabled}
          className="absolute inset-y-0 right-0 flex w-12 items-center justify-center rounded-r-[8px] text-gray-600 hover:text-gray-900 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-[#005A54]"
        >
          {visible ? <EyeOff size={20} aria-hidden="true" /> : <Eye size={20} aria-hidden="true" />}
        </button>
      </div>
      {hint && (
        <p id={hintId} className="mt-1.5 text-[13px] leading-5 text-gray-600">
          {hint}
        </p>
      )}
      {error && (
        <p id={errorId} className="mt-1.5 text-[13px] leading-5 text-red-700">
          {error}
        </p>
      )}
    </div>
  );
}
