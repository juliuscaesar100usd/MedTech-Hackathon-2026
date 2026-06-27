import { useLayoutEffect } from 'react';
import { useLocation } from 'react-router-dom';

/* Scroll-reveal: fade + rise content blocks as they enter the viewport.
   Generic + dependency-free (IntersectionObserver). Called once in Layout so
   it applies to every route. Re-scans on navigation (pathname dep).

   - Above-the-fold blocks reveal immediately on load; below-the-fold reveal
     on scroll. The hidden state is added in useLayoutEffect (before paint) so
     there's no flash of visible-then-hidden content.
   - Targets are added the `.reveal` class by JS, so with JS disabled (or for
     reduced-motion users) everything stays fully visible — fail-open.
   - Ancestor de-dup: when a matched block contains another matched block, only
     the inner one reveals (so grid cards / metric tiles cascade individually
     instead of fading in as one slab with their wrapper). */

const SELECTOR = [
  '.page > *',
  '.lp-section',
  '.lp-metric',
  '.lp-cta-band',
  '.card-grid > *',
  '.two-col > *',
].join(',');

// Tight groups stagger; standalone section blocks reveal with no delay.
const STAGGER_PARENTS = ['card-grid', 'lp-metrics', 'two-col'];

export function useScrollReveal() {
  const { pathname } = useLocation();

  useLayoutEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const root = document.querySelector('.route-view');
    if (!root) return;

    let els = Array.from(root.querySelectorAll<HTMLElement>(SELECTOR));
    // Keep only the innermost matches (drop any block that contains another).
    els = els.filter((el) => !els.some((o) => o !== el && el.contains(o)));

    const groupCount = new Map<Element, number>();
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) {
            e.target.classList.add('is-visible');
            io.unobserve(e.target);
          }
        }
      },
      { threshold: 0.08, rootMargin: '0px 0px -8% 0px' },
    );

    for (const el of els) {
      const parent = el.parentElement;
      const staggered = parent && STAGGER_PARENTS.some((c) => parent.classList.contains(c));
      let idx = 0;
      if (staggered && parent) {
        idx = groupCount.get(parent) ?? 0;
        groupCount.set(parent, idx + 1);
      }
      el.style.setProperty('--reveal-i', String(Math.min(idx, 6)));
      el.classList.add('reveal');
      io.observe(el);
    }

    return () => io.disconnect();
  }, [pathname]);
}
