"use client";

import { AnimatePresence, motion } from "motion/react";

/** One question per screen; slides in the direction of travel. */
export function QuizStep({
  stepKey,
  direction,
  index,
  total,
  title,
  description,
  children,
}: {
  stepKey: string;
  direction: 1 | -1;
  index: number;
  total: number;
  title: string;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="relative overflow-x-clip">
      <AnimatePresence mode="wait" custom={direction} initial={false}>
        <motion.section
          key={stepKey}
          custom={direction}
          variants={{
            enter: (d: number) => ({ opacity: 0, x: d * 36 }),
            center: { opacity: 1, x: 0 },
            exit: (d: number) => ({ opacity: 0, x: d * -36 }),
          }}
          initial="enter"
          animate="center"
          exit="exit"
          transition={{ duration: 0.28, ease: [0.2, 0.7, 0.2, 1] }}
          aria-labelledby={`q-${stepKey}`}
        >
          <p className="eyebrow mb-3">Question {index + 1} of {total}</p>
          <h1 id={`q-${stepKey}`} tabIndex={-1} className="text-[clamp(26px,3.6vw,36px)] leading-tight font-semibold tracking-[-0.03em] text-balance outline-none">
            {title}
          </h1>
          {description && <p className="mt-2.5 text-[15.5px] text-muted-foreground">{description}</p>}
          <div className="mt-8">{children}</div>
        </motion.section>
      </AnimatePresence>
    </div>
  );
}
