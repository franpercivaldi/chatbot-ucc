import React, { forwardRef, useLayoutEffect, useRef } from "react";
import clsx from "clsx";

const Textarea = forwardRef(function Textarea(
  { value, onChange, onKeyDown, placeholder = "Escribe tu mensaje…", rows = 1, className, maxHeight, ...props },
  ref
) {
  const innerRef = useRef(null);

  const setRefs = (el) => {
    innerRef.current = el;
    if (!ref) return;
    if (typeof ref === "function") ref(el);
    else ref.current = el;
  };

  const resize = () => {
    const el = innerRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${el.scrollHeight}px`;

    if (maxHeight) {
      el.style.maxHeight = maxHeight;
      const computedMax = parseInt(getComputedStyle(el).maxHeight || "0");
      el.style.overflow = computedMax && el.scrollHeight > computedMax ? "auto" : "hidden";
    } else {
      el.style.overflow = "hidden";
      el.style.maxHeight = "none";
    }
  };

  useLayoutEffect(() => {
    resize();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value, maxHeight]);

  const handleChange = (e) => {
    onChange?.(e);
    requestAnimationFrame(resize);
  };

  return (
    <textarea
      ref={setRefs}
      value={value}
      onChange={handleChange}
      onKeyDown={onKeyDown}
      placeholder={placeholder}
      rows={rows}
      className={clsx(
        "text-black w-full bg-transparent resize-none outline-none border-0 px-0 py-0 " +
          "placeholder:text-gray-500 focus:ring-0 focus:outline-none leading-relaxed",
        className
      )}
      {...props}
    />
  );
});

export default Textarea;
