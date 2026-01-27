import { useEffect, useLayoutEffect, useMemo, useState } from "react";

const PADDING = 8;

const clamp = (value, min, max) => Math.min(Math.max(value, min), max);

const computeTooltipPosition = (rect) => {
  const viewportWidth = window.innerWidth;
  const viewportHeight = window.innerHeight;
  const width = 320;
  const height = 160;
  if (!rect) {
    return {
      top: viewportHeight / 2 - height / 2,
      left: viewportWidth / 2 - width / 2,
    };
  }
  const spaceBelow = viewportHeight - rect.bottom;
  const spaceAbove = rect.top;
  const preferBelow = spaceBelow >= height + PADDING || spaceBelow >= spaceAbove;
  const top = preferBelow
    ? rect.bottom + PADDING
    : rect.top - height - PADDING;
  const left = clamp(rect.left, PADDING, viewportWidth - width - PADDING);
  return { top, left };
};

export default function TourOverlay({
  steps,
  isOpen,
  onComplete,
  onDismiss,
}) {
  const [index, setIndex] = useState(0);
  const step = useMemo(() => steps[index], [steps, index]);
  const [targetRect, setTargetRect] = useState(null);
  const [tooltipStyle, setTooltipStyle] = useState({});

  useEffect(() => {
    if (isOpen) {
      setIndex(0);
    }
  }, [isOpen]);

  useLayoutEffect(() => {
    if (!isOpen || !step) return;
    const element = document.querySelector(step.selector);
    if (!element) {
      setTargetRect(null);
      setTooltipStyle(computeTooltipPosition(null));
      return;
    }
    element.scrollIntoView({ behavior: "smooth", block: "center" });
    const rect = element.getBoundingClientRect();
    setTargetRect(rect);
    setTooltipStyle(computeTooltipPosition(rect));
  }, [isOpen, step, index]);

  if (!isOpen || !step) return null;

  const isLast = index === steps.length - 1;

  const highlightStyle = targetRect
    ? {
        top: targetRect.top - PADDING,
        left: targetRect.left - PADDING,
        width: targetRect.width + PADDING * 2,
        height: targetRect.height + PADDING * 2,
      }
    : null;

  return (
    <div className="tour-overlay">
      <div className="tour-backdrop" />
      {highlightStyle && <div className="tour-highlight" style={highlightStyle} />}
      <div className="tour-tooltip" style={tooltipStyle}>
        <div className="tour-step-kicker">
          Step {index + 1} of {steps.length}
        </div>
        <h4>{step.title}</h4>
        <p className="subtle">{step.body}</p>
        <div className="tour-actions">
          <button className="btn secondary" onClick={onDismiss}>
            Skip
          </button>
          <button
            className="btn secondary"
            onClick={() => setIndex((prev) => Math.max(0, prev - 1))}
            disabled={index === 0}
          >
            Back
          </button>
          <button
            className="btn primary"
            onClick={() => {
              if (isLast) {
                onComplete();
              } else {
                setIndex((prev) => prev + 1);
              }
            }}
          >
            {isLast ? "Finish" : "Next"}
          </button>
        </div>
      </div>
    </div>
  );
}
