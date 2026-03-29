import Link from 'next/link';
import type { CSSProperties } from 'react';

import { PRODUCT_NAME, PRODUCT_PROMISE } from '@/lib/brand';

type AnimatedPath = {
  d: string;
  length: number;
  delay: string;
  duration: string;
  width: number;
  soft?: boolean;
};

type AnimatedLeaf = {
  cx: number;
  cy: number;
  r: number;
  delay: string;
  gold?: boolean;
};

const HERO_BRANCH_PATHS: AnimatedPath[] = [
  { d: 'M378 486 C374 430 372 374 368 322 C362 252 350 178 332 114', length: 420, delay: '0s', duration: '2.4s', width: 3.2 },
  { d: 'M369 325 C430 302 478 261 520 208 C552 168 574 128 592 86', length: 280, delay: '0.7s', duration: '2s', width: 2.4 },
  { d: 'M366 320 C312 286 266 238 232 188 C207 151 188 110 171 78', length: 260, delay: '0.9s', duration: '2.1s', width: 2.2 },
  { d: 'M503 222 C541 237 581 256 620 280 C658 302 690 330 713 356', length: 238, delay: '1.5s', duration: '1.8s', width: 1.9, soft: true },
  { d: 'M246 205 C211 228 175 252 138 290 C112 318 90 348 70 388', length: 240, delay: '1.6s', duration: '1.9s', width: 1.8, soft: true },
  { d: 'M334 115 C360 93 392 73 428 58 C458 46 492 38 531 34', length: 218, delay: '1.2s', duration: '1.7s', width: 1.8, soft: true },
];

const HERO_LEAVES: AnimatedLeaf[] = [
  { cx: 332, cy: 114, r: 7, delay: '1.8s' },
  { cx: 592, cy: 86, r: 6.5, delay: '2.05s', gold: true },
  { cx: 171, cy: 78, r: 6.2, delay: '2.1s' },
  { cx: 713, cy: 356, r: 5.5, delay: '2.4s' },
  { cx: 70, cy: 388, r: 5.8, delay: '2.45s', gold: true },
  { cx: 531, cy: 34, r: 5.4, delay: '2.25s' },
];

function pathStyle(path: AnimatedPath): CSSProperties {
  return {
    strokeWidth: path.width,
    ['--path-length' as string]: path.length,
    ['--grow-delay' as string]: path.delay,
    ['--grow-duration' as string]: path.duration,
  };
}

function leafStyle(leaf: AnimatedLeaf): CSSProperties {
  return {
    ['--leaf-delay' as string]: leaf.delay,
  };
}

function BranchGrowthHero() {
  return (
    <aside className="branch-hero-frame relative min-h-[430px] p-5 md:min-h-[520px] md:p-7">
      <div className="branch-halo absolute -left-20 top-6 h-52 w-52 rounded-full bg-amber-200/55 blur-3xl" />
      <div className="branch-halo absolute -right-10 bottom-4 h-56 w-56 rounded-full bg-emerald-200/45 blur-3xl" />

      <div className="relative mb-4 flex items-center justify-between">
        <p className="badge">Living Study Tree</p>
        <p className="text-[11px] uppercase tracking-[0.16em] text-black/48">calm adaptive growth</p>
      </div>

      <svg viewBox="0 0 760 540" className="branch-tree-sway h-[360px] w-full md:h-[430px]" aria-hidden="true">
        <defs>
          <linearGradient id="branch-trunk" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="rgba(39,78,63,0.95)" />
            <stop offset="100%" stopColor="rgba(154,122,66,0.78)" />
          </linearGradient>
        </defs>

        <path
          d="M382 525 C377 509 375 499 374 486 C372 444 370 372 365 314 C358 228 346 166 333 124"
          style={{ ...pathStyle({ d: '', length: 452, delay: '0s', duration: '2.2s', width: 3.8 }) }}
          className="branch-path"
          stroke="url(#branch-trunk)"
        />

        {HERO_BRANCH_PATHS.map((path) => (
          <path
            key={`${path.d}-${path.delay}`}
            d={path.d}
            style={pathStyle(path)}
            className={`branch-path ${path.soft ? 'branch-path-soft' : ''}`}
          />
        ))}

        {HERO_LEAVES.map((leaf) => (
          <circle
            key={`${leaf.cx}-${leaf.cy}`}
            cx={leaf.cx}
            cy={leaf.cy}
            r={leaf.r}
            style={leafStyle(leaf)}
            className={`branch-leaf ${leaf.gold ? 'branch-leaf-gold' : ''}`}
          />
        ))}
      </svg>

      <div className="absolute bottom-5 left-5 right-5 rounded-xl border border-black/10 bg-white/75 px-4 py-3 backdrop-blur-sm">
        <p className="text-sm font-medium text-black/85">One trunk. Selective branches. Lasting reflection.</p>
        <p className="mt-1 text-xs text-black/62">Study through exemplars, interpretation, comparison, and creative response.</p>
      </div>
    </aside>
  );
}

export default function HomePage() {
  return (
    <main className="min-h-screen">
      <div className="mx-auto w-full max-w-7xl px-6 pb-16 pt-8 md:px-10 md:pt-12">
        <header className="mb-14 flex items-center justify-between gap-3">
          <p className="text-xs font-semibold uppercase tracking-[0.22em] text-black/62">{PRODUCT_NAME}</p>
          <div className="flex items-center gap-2">
            <Link href="/login" className="studio-button-secondary">
              Sign in
            </Link>
            <Link href="/signup" className="studio-button-primary">
              Create account
            </Link>
          </div>
        </header>

        <section className="grid items-center gap-10 lg:grid-cols-[1.1fr_0.9fr]">
          <div className="max-w-2xl">
            <p className="badge mb-4">Cultural + Creative Learning Studio</p>
            <h1 className="text-4xl leading-[1.03] text-black md:text-[3.55rem]">
              Grow your taste through living study paths.
            </h1>
            <p className="mt-5 max-w-xl text-base leading-relaxed text-black/72 md:text-lg">
              {PRODUCT_PROMISE} Begin with one work, follow a clear trunk, and branch only when your inquiry deepens.
            </p>
            <div className="mt-7 flex flex-wrap items-center gap-3">
              <Link href="/login" className="studio-button-primary px-5 py-3 text-sm">
                Enter {PRODUCT_NAME}
              </Link>
              <Link href="/signup" className="studio-button-secondary px-5 py-3 text-sm">
                Start your studio
              </Link>
            </div>

            <div className="mt-7 grid gap-2 sm:grid-cols-3">
              <div className="rounded-xl border border-black/10 bg-white/75 px-3 py-2">
                <p className="text-[10px] uppercase tracking-[0.15em] text-black/55">Exemplar-first</p>
                <p className="mt-1 text-sm text-black/80">Start from real works</p>
              </div>
              <div className="rounded-xl border border-black/10 bg-white/75 px-3 py-2">
                <p className="text-[10px] uppercase tracking-[0.15em] text-black/55">Selective Branching</p>
                <p className="mt-1 text-sm text-black/80">Compare, contextualize, deepen</p>
              </div>
              <div className="rounded-xl border border-black/10 bg-white/75 px-3 py-2">
                <p className="text-[10px] uppercase tracking-[0.15em] text-black/55">Notebook Memory</p>
                <p className="mt-1 text-sm text-black/80">Track shifts in perception</p>
              </div>
            </div>
          </div>

          <BranchGrowthHero />
        </section>

        <section className="mt-14 grid gap-4 md:grid-cols-3">
          <article className="panel p-4">
            <p className="text-xs uppercase tracking-[0.13em] text-black/56">Start from a work</p>
            <p className="mt-2 text-sm text-black/78">Painting, poem, film scene, building, musical piece, design object.</p>
          </article>
          <article className="panel p-4">
            <p className="text-xs uppercase tracking-[0.13em] text-black/56">Learn through form</p>
            <p className="mt-2 text-sm text-black/78">Interpretation, context, comparison, and guided creative response.</p>
          </article>
          <article className="panel p-4">
            <p className="text-xs uppercase tracking-[0.13em] text-black/56">Grow over time</p>
            <p className="mt-2 text-sm text-black/78">Keep a commonplace notebook of turning points and next threads.</p>
          </article>
        </section>

        <section className="mt-10 flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-black/10 bg-white/70 px-5 py-4 shadow-[0_16px_36px_rgba(20,26,24,0.08)] backdrop-blur-sm">
          <div>
            <p className="text-sm font-medium text-black/84">Serious curiosity deserves a better space.</p>
            <p className="mt-1 text-xs uppercase tracking-[0.14em] text-black/52">Calm. Adaptive. Reflective.</p>
          </div>
          <div className="flex gap-2">
            <Link href="/login" className="studio-button-primary">
              Enter {PRODUCT_NAME}
            </Link>
            <Link href="/signup" className="studio-button-secondary">
              Create account
            </Link>
          </div>
        </section>
      </div>
    </main>
  );
}
