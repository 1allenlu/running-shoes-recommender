import type { IssueTag } from "./api";

export const ISSUE_OPTIONS: { value: IssueTag; label: string }[] = [
  { value: "toe_pressure", label: "Toe pressure" },
  { value: "heel_slip", label: "Heel slip" },
  { value: "too_narrow", label: "Too narrow" },
  { value: "too_much_volume", label: "Too roomy" },
  { value: "arch_discomfort", label: "Arch discomfort" },
  { value: "too_soft", label: "Too soft" },
  { value: "too_firm", label: "Too firm" },
];

export const GOAL_OPTIONS = ["Daily training", "5K / 10K", "Half marathon", "Marathon", "Speed work", "Getting back into running"].map(
  (g) => ({ value: g, label: g }),
);
