import React, { forwardRef } from "react"
import clsx from "clsx"

function DefaultSpinner({ className = "h-4 w-4" }) {
    return (
        <svg
            className={clsx("animate-spin", className)}
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 24 24"
            aria-hidden="true"
        >
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"></path>
        </svg>
    )
}

const variants = {
    primary: "bg-sky-600 text-white hover:bg-sky-700",
    secondary: "bg-gray-200 text-gray-800 hover:bg-gray-300",
    ghost: "bg-transparent text-gray-800 hover:bg-gray-100",
    outline: "bg-white text-gray-800 border border-gray-300 hover:bg-gray-50",
}

const sizes = {
    sm: "h-8 px-3 text-sm",
    md: "h-10 px-4 text-base",
    lg: "h-12 px-6 text-lg",
}

const Button = forwardRef(function Button(
    {
        children,
        text, // backward-compat string prop
        onClick,
        type = "button",
        variant = "primary",
        size = "md",
        disabled = false,
        isLoading = false,
        loadingText,
        loadingIcon,
        leftIcon,
        rightIcon,
        fullWidth = false,
        className,
        ariaLabel,
        ...props
    },
    ref
) {
    const content = children ?? text
    const isDisabled = disabled || isLoading

    const base = "inline-flex items-center justify-center rounded-md transition-colors duration-150 disabled:opacity-60 disabled:cursor-not-allowed"
    const widthCls = fullWidth ? "w-full" : "inline-flex"

    const cls = clsx(base, widthCls, variants[variant] ?? variants.primary, sizes[size] ?? sizes.md, className)

    return (
        <button
            ref={ref}
            type={type}
            onClick={onClick}
            className={cls}
            disabled={isDisabled}
            aria-label={ariaLabel}
            aria-busy={isLoading ? true : undefined}
            {...props}
        >
            {isLoading ? (
                <>
                    {loadingIcon ? (
                        // custom loading icon
                        loadingIcon
                    ) : (
                        // default spinner
                        <DefaultSpinner className={size === "sm" ? "h-4 w-4 -ml-1 mr-2" : "h-4 w-4 -ml-1 mr-2"} />
                    )}
                    <span className={loadingText ? "" : "sr-only"}>{loadingText ?? content ?? "Loading..."}</span>
                </>
            ) : (
                <>
                    {leftIcon ? <span className="-ml-1 mr-2 inline-flex items-center">{leftIcon}</span> : null}
                    {content}
                    {rightIcon ? <span className="ml-2 inline-flex items-center">{rightIcon}</span> : null}
                </>
            )}
        </button>
    )
})

export default Button