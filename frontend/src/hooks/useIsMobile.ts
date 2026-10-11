import { useEffect, useState } from "react";

/** Below Tailwind's `md` breakpoint (768px): phones, and tablets held upright. */
const QUERY = "(max-width: 767px)";

/**
 * Whether the layout should be the phone layout. Follows the window as it
 * resizes or rotates, so the shell switches between drawers and side columns
 * without a reload.
 */
export function useIsMobile(): boolean {
  const [mobile, setMobile] = useState(() => window.matchMedia(QUERY).matches);
  useEffect(() => {
    const media = window.matchMedia(QUERY);
    const update = () => setMobile(media.matches);
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);
  return mobile;
}
