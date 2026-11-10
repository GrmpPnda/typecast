import { useEffect, useState } from "react";

const WORD = "Typecast";
const START_DELAY_MS = 350;
const KEY_MS = 115;
// Keystrokes are uneven when typed by hand; a little jitter keeps it from looking mechanical.
const JITTER_MS = 70;
// The cursor keeps blinking this long after the last letter, then goes away.
const LINGER_MS = 3200;

// Types once per page load. Later mounts (a drawer reopening, the login page handing over to the
// app shell) show the finished word, or the animation would replay on every navigation.
let hasTyped = false;

function prefersReducedMotion(): boolean {
  return typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
}

/**
 * The Typecast wordmark, typed out letter by letter behind a blinking block cursor.
 * The full word is laid out invisibly underneath, so the typing never shifts the layout.
 */
export default function TypedLogo({ className = "" }: { className?: string }) {
  // Decided once per mount: re-evaluating on a re-render would read hasTyped as true and cancel the timers.
  const [animate] = useState(() => !hasTyped && !prefersReducedMotion());
  const [count, setCount] = useState(animate ? 0 : WORD.length);
  const [showCursor, setShowCursor] = useState(animate);

  useEffect(() => {
    if (!animate) return;
    hasTyped = true;
    const timers: number[] = [];
    let at = START_DELAY_MS;
    for (let i = 1; i <= WORD.length; i++) {
      at += KEY_MS + Math.random() * JITTER_MS;
      timers.push(window.setTimeout(() => setCount(i), at));
    }
    timers.push(window.setTimeout(() => setShowCursor(false), at + LINGER_MS));
    return () => timers.forEach(clearTimeout);
  }, [animate]);

  return (
    <span className={`font-logo inline-grid ${className}`} aria-label={WORD} role="img">
      <span className="invisible col-start-1 row-start-1" aria-hidden>
        {WORD}
        <span className="inline-block w-[0.6em]" />
      </span>
      <span className="col-start-1 row-start-1 whitespace-pre" aria-hidden>
        {WORD.slice(0, count)}
        {showCursor && (
          <span className="tc-cursor-blink inline-block w-[0.6em] h-[1em] align-[-0.12em] bg-current ml-px" />
        )}
      </span>
    </span>
  );
}
