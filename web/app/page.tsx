"use client";

import { ArrowRight, Check, CircleAlert, Ruler, ShieldCheck } from "lucide-react";
import { motion } from "motion/react";
import Link from "next/link";
import { FitMeter, FitScore } from "@/components/fit-meter";
import { Logo } from "@/components/logo";
import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const fade = (delay = 0) => ({
  initial: { opacity: 0, y: 14 },
  whileInView: { opacity: 1, y: 0 },
  viewport: { once: true, margin: "-60px" },
  transition: { delay, duration: 0.55, ease: [0.2, 0.7, 0.2, 1] as const },
});

const SAMPLE = [
  { factor: "width_fit", score: 0.94, weight: 0.3, note: "Roomy toe box for your wide forefoot" },
  { factor: "volume_fit", score: 0.82, weight: 0.2, note: "Low-volume upper suits your low instep" },
  { factor: "heel_fit", score: 0.76, weight: 0.1, note: "Firm heel counter for a narrow heel" },
  { factor: "ride_fit", score: 0.88, weight: 0.1, note: "Balanced cushioning, as you asked" },
];

const STEPS = [
  { n: "01", title: "Add your scan", body: "Upload the screenshots or PDF from an in-store 3D foot scan, or type the numbers in. You check every value before we use it." },
  { n: "02", title: "Tell us how you run", body: "Weekly distance, the feel you like, your budget, and the shoes that have worked for you, or haven't." },
  { n: "03", title: "Get three picks", body: "Each with a fit score, the reasons behind it, what to watch for, and the size and width to order." },
];

const MATCHES = [
  ["Your forefoot width", "Toe box width"],
  ["Your instep height", "Upper volume"],
  ["Your heel width", "Heel counter and lockdown"],
  ["Wide forefoot, low instep", "Room up front without a sloppy midfoot"],
  ["The feel you want", "Midsole softness and stack"],
  ["Shoes you've loved or hated", "Similar or different specs"],
];

const PRINCIPLES = [
  { icon: ShieldCheck, title: "No paid rankings", body: "Retailers can't buy a spot. Links are added after the order is set, and we say when a link earns us a commission." },
  { icon: Ruler, title: "Sized per brand", body: "Your foot length is converted with each brand's own size chart, so “a 10” means the right 10 in that shoe." },
  { icon: CircleAlert, title: "Honest about gaps", body: "When we haven't verified a shoe's measurements, we say so instead of guessing, and tell you to try it on first." },
];

const FAQ = [
  ["Where do I get a 3D foot scan?", "Many specialty running stores scan your feet for free in a few seconds. Ask for a copy of the report, or take screenshots of it. No scan? You can enter your size, width and arch details by hand."],
  ["Do I need an account?", "No. Your progress is remembered in this browser so you can come back to your picks."],
  ["How does LastFit make money?", "Some store links are affiliate links. They never change which shoes we pick or their order, and results that include them say so."],
  ["Is this medical advice?", "No. We recommend on fit and comfort. We don't diagnose, treat or prevent injury. If you have pain, see a professional."],
];

export default function Home() {
  return (
    <div className="overflow-x-clip">
      <header className="sticky top-0 z-40 border-b bg-background/80 backdrop-blur-xl backdrop-saturate-150">
        <div className="mx-auto flex h-15 w-[min(1160px,100%-2rem)] items-center gap-7">
          <Logo />
          <nav className="ml-auto flex items-center gap-7 text-[14px] text-muted-foreground" aria-label="Site">
            <a href="#how" className="hidden transition-colors hover:text-foreground md:inline">How it works</a>
            <a href="#match" className="hidden transition-colors hover:text-foreground md:inline">What we match</a>
            <a href="#faq" className="hidden transition-colors hover:text-foreground md:inline">FAQ</a>
            <Link href="/scan/" className={buttonVariants({ size: "sm", className: "h-8 px-3" })}>Get your picks</Link>
          </nav>
        </div>
      </header>

      <main>
        {/* Hero */}
        <section className="mx-auto grid w-[min(1160px,100%-2rem)] items-center gap-14 py-16 sm:py-24 lg:grid-cols-[1.15fr_0.85fr] lg:gap-16">
          <div>
            <motion.p {...fade()} className="mb-7 inline-flex items-center gap-2 rounded-full border bg-card py-1 pr-3 pl-2.5 text-[13px] font-medium text-muted-foreground">
              <span className="size-[7px] rounded-full bg-volt shadow-[0_0_0_3px_var(--volt-soft)]" />
              Fit-first shoe recommendations
            </motion.p>
            <motion.h1 {...fade(0.05)} className="text-[clamp(40px,6.2vw,72px)] leading-[1.02] font-semibold tracking-[-0.045em] text-balance">
              Get scanned once.<br />Never guess on a shoe again.
            </motion.h1>
            <motion.p {...fade(0.1)} className="mt-6 max-w-[34em] text-[clamp(17px,1.5vw,19px)] leading-relaxed text-pretty text-muted-foreground">
              Bring the 3D foot scan from your running store. We rank shoes on how they fit your feet, tell you the exact size to order in each brand, and show where that pair is in stock.
            </motion.p>
            <motion.div {...fade(0.15)} className="mt-9 flex flex-wrap gap-3">
              <Link href="/scan/" className={cn(buttonVariants({ size: "lg" }), "h-12 rounded-xl px-5 text-[15.5px]")}>
                Get your picks <ArrowRight />
              </Link>
              <Link href="/confirm/?manual=1" className={cn(buttonVariants({ variant: "outline", size: "lg" }), "h-12 rounded-xl px-5 text-[15.5px]")}>
                Enter measurements
              </Link>
            </motion.div>
            <motion.ul {...fade(0.2)} className="mt-6 flex flex-wrap gap-x-6 gap-y-2 text-[13.5px] text-muted-foreground">
              {["Free", "No account needed", "About two minutes"].map((t) => (
                <li key={t} className="flex items-center gap-1.5"><Check className="size-3.5 text-good" strokeWidth={3} />{t}</li>
              ))}
            </motion.ul>
          </div>

          <motion.figure
            initial={{ opacity: 0, y: 24, rotate: -1 }}
            animate={{ opacity: 1, y: 0, rotate: 0 }}
            transition={{ delay: 0.2, duration: 0.7, ease: [0.2, 0.7, 0.2, 1] }}
            className="relative m-0 max-w-[460px]"
            aria-label="Example of a LastFit result"
          >
            <div className="stripes absolute inset-[8%_-6%_-6%_10%] -z-10 rounded-3xl opacity-60" aria-hidden />
            <div className="grid gap-5 rounded-[18px] border bg-card p-5 shadow-[0_24px_64px_-16px_rgb(0_0_0/0.18)]">
              <div className="flex justify-between">
                <span className="rounded-md bg-volt px-2 py-1 font-mono text-[11px] font-medium text-volt-foreground">#1 Best fit</span>
                <span className="rounded-md border bg-secondary px-2 py-1 font-mono text-[11px] text-muted-foreground">Example result</span>
              </div>
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="eyebrow">Example brand</p>
                  <p className="text-[22px] font-semibold tracking-[-0.025em]">Daily Trainer 5</p>
                </div>
                <FitScore score={86} size={64} />
              </div>
              <div className="flex items-center justify-between rounded-xl bg-secondary px-4 py-3">
                <div>
                  <p className="eyebrow">Order</p>
                  <p className="text-[20px] font-semibold tracking-[-0.02em]">US 10 <span className="font-medium text-muted-foreground">· Wide</span></p>
                </div>
                <span className="rounded-full bg-good-soft px-2.5 py-0.5 text-[12px] font-medium text-good">Brand chart</span>
              </div>
              <FitMeter factors={SAMPLE} />
            </div>
          </motion.figure>
        </section>

        {/* Facts */}
        <section className="border-y bg-card">
          <div className="mx-auto grid w-[min(1160px,100%-2rem)] sm:grid-cols-3">
            {[["5", "measurements read from each foot"], ["7", "fit factors behind every score"], ["0", "paid placements in the ranking"]].map(([n, t], i) => (
              <motion.div {...fade(i * 0.06)} key={t} className="flex items-baseline gap-4 py-7 text-[14.5px] text-muted-foreground max-sm:border-t max-sm:first:border-t-0 sm:px-8 sm:py-9 sm:not-first:border-l">
                <span className="text-[44px] leading-none font-semibold tracking-[-0.05em] text-foreground tabular-nums">{n}</span>
                {t}
              </motion.div>
            ))}
          </div>
        </section>

        {/* How it works */}
        <section id="how" className="mx-auto w-[min(1160px,100%-2rem)] pt-24 sm:pt-28">
          <motion.div {...fade()} className="mb-12 grid max-w-[640px] gap-3.5">
            <p className="eyebrow">How it works</p>
            <h2 className="text-[clamp(26px,3.2vw,40px)] leading-tight font-semibold tracking-[-0.035em] text-balance">From scan to the right pair in three steps.</h2>
          </motion.div>
          <ol className="grid overflow-hidden rounded-2xl border bg-card md:grid-cols-3">
            {STEPS.map((s, i) => (
              <motion.li {...fade(i * 0.08)} key={s.n} className="grid content-start gap-2.5 p-7 max-md:not-first:border-t md:not-first:border-l">
                <span className="mb-6 font-mono text-[12px] text-muted-foreground">{s.n}</span>
                <h3 className="text-[18px] font-semibold tracking-[-0.02em]">{s.title}</h3>
                <p className="text-[14.5px] text-muted-foreground">{s.body}</p>
              </motion.li>
            ))}
          </ol>
        </section>

        {/* What we match */}
        <section id="match" className="mx-auto grid w-[min(1160px,100%-2rem)] gap-10 pt-24 sm:pt-28 lg:grid-cols-[0.9fr_1.1fr] lg:gap-18">
          <motion.div {...fade()} className="grid content-start gap-3.5 lg:sticky lg:top-24">
            <p className="eyebrow">What we match</p>
            <h2 className="text-[clamp(26px,3.2vw,40px)] leading-tight font-semibold tracking-[-0.035em]">Fit first. Then everything else.</h2>
            <p className="text-[16px] text-muted-foreground">Most shoe finders start with a quiz about your running. We start with your feet: each shoe&apos;s measured shape is scored against your scan, and the order comes only from that score.</p>
          </motion.div>
          <dl className="m-0 border-t border-foreground">
            {MATCHES.map(([a, b], i) => (
              <motion.div {...fade(i * 0.04)} key={a} className="grid grid-cols-2 items-baseline gap-6 border-b py-5">
                <dt className="text-[15px] font-medium">{a}</dt>
                <dd className="m-0 flex gap-2.5 text-[14.5px] text-muted-foreground"><span aria-hidden>→</span>{b}</dd>
              </motion.div>
            ))}
          </dl>
        </section>

        {/* Principles */}
        <section className="mx-auto w-[min(1160px,100%-2rem)] pt-24 sm:pt-28">
          <motion.div {...fade()} className="mb-12 grid max-w-[640px] gap-3.5">
            <p className="eyebrow">Our principles</p>
            <h2 className="text-[clamp(26px,3.2vw,40px)] leading-tight font-semibold tracking-[-0.035em]">Recommendations you can trust.</h2>
          </motion.div>
          <div className="grid gap-4 md:grid-cols-3">
            {PRINCIPLES.map((p, i) => (
              <motion.article {...fade(i * 0.08)} key={p.title} className="grid content-start gap-2.5 rounded-2xl border bg-card p-7">
                <span className="mb-3 grid size-9 place-items-center rounded-[10px] bg-volt text-volt-foreground"><p.icon className="size-[18px]" /></span>
                <h3 className="text-[17px] font-semibold tracking-[-0.02em]">{p.title}</h3>
                <p className="text-[14.5px] text-muted-foreground">{p.body}</p>
              </motion.article>
            ))}
          </div>
        </section>

        {/* FAQ */}
        <section id="faq" className="mx-auto grid w-[min(1160px,100%-2rem)] gap-10 pt-24 sm:pt-28 lg:grid-cols-[0.9fr_1.1fr] lg:gap-18">
          <motion.div {...fade()} className="grid content-start gap-3.5">
            <p className="eyebrow">FAQ</p>
            <h2 className="text-[clamp(26px,3.2vw,40px)] leading-tight font-semibold tracking-[-0.035em]">Questions, answered.</h2>
          </motion.div>
          <div className="border-t">
            {FAQ.map(([q, a]) => (
              <details key={q} className="group border-b">
                <summary className="flex cursor-pointer list-none items-center justify-between gap-4 py-5 text-[16px] font-medium [&::-webkit-details-marker]:hidden">
                  {q}
                  <span className="text-[20px] leading-none font-normal text-muted-foreground transition-transform group-open:rotate-45">+</span>
                </summary>
                <p className="max-w-[36em] pb-5 text-muted-foreground">{a}</p>
              </details>
            ))}
          </div>
        </section>

        {/* CTA */}
        <section className="mx-auto w-[min(1160px,100%-2rem)] pt-24 sm:pt-28">
          <motion.div {...fade()} className="relative flex flex-wrap items-center justify-between gap-8 overflow-hidden rounded-[20px] bg-foreground p-8 text-background sm:p-12">
            <div className="pointer-events-none absolute -top-16 -right-16 size-64 rounded-full border border-background/15 shadow-[0_0_0_40px_color-mix(in_srgb,var(--background)_3%,transparent),0_0_0_80px_color-mix(in_srgb,var(--background)_2%,transparent)]" aria-hidden />
            <div>
              <h2 className="text-[clamp(26px,3.2vw,40px)] leading-tight font-semibold tracking-[-0.035em]">Find the three shoes that fit you.</h2>
              <p className="mt-2 text-background/65">Takes about two minutes. Have your scan handy.</p>
            </div>
            <Link href="/scan/" className="relative inline-flex h-12 items-center gap-2 rounded-xl bg-volt px-5 text-[15.5px] font-medium text-volt-foreground transition hover:brightness-95">
              Get your picks <ArrowRight className="size-4" />
            </Link>
          </motion.div>
        </section>
      </main>

      <footer className="mx-auto mt-16 flex w-[min(1160px,100%-2rem)] flex-wrap justify-between gap-4 border-t py-10 text-[13.5px] text-muted-foreground">
        <p><strong className="text-foreground">LastFit</strong> · Running shoes matched to your feet.</p>
        <p>We recommend on fit and comfort. We don&apos;t diagnose, treat or prevent injury.</p>
      </footer>
    </div>
  );
}
