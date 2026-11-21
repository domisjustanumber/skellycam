import React from "react";

/**
 * Reusable Checkbox Component
 * ----------------------------
 * - Entire row clickable
 * - Accessible
 * - Large hit area
 * - Small visual checkbox
 * - Smooth hover/focus states
 */

interface CheckboxProps {
  label: string;
  checked?: boolean;
  onChange?: (event: React.ChangeEvent<HTMLInputElement>) => void;
  inputClassName?: string;
  className?: string;
  disabled?: boolean;
  inputProps?: React.InputHTMLAttributes<HTMLInputElement>;  // e.g. aria-label when the label is empty
}

const Checkbox: React.FC<CheckboxProps> = ({
  label,
  checked = false,
  onChange,
  inputClassName = "",
  className = "",
  disabled = false,
  inputProps,
}) => {
  return (
  <label
  className={`
    checkbox
    text-nowrap
    button
    p-2
    select-none
    cursor-pointer
    ${className}
    ${disabled ? "opacity-50 cursor-not-allowed" : ""}
  `}
>
      <input
        {...inputProps}
        type="checkbox"
        checked={checked}
        onChange={onChange}
        disabled={disabled}
        className={`
          button
          flex-shrink-0
          ${inputClassName}
        `.trim()}
      />

      <p className="text-gray text md text-align-left">
        {label}
      </p>
    </label>
  );
};

export default Checkbox;