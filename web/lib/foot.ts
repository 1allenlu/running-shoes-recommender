import type { Foot, FootProfile } from "./api";

export const WIDTHS = ["3A", "2A", "A", "B", "C", "D", "E", "2E", "3E"] as const;

type ScaleKey = "arch_height" | "instep_height" | "heel_width" | "pressure" | "arch_flexibility";
export const SCALES: { key: ScaleKey; label: string; bands: [string, string, string]; optional?: boolean; hint: string }[] = [
  { key: "arch_height", label: "Arch height", bands: ["low", "medium", "high"], hint: "How high your arch sits off the ground" },
  { key: "instep_height", label: "Instep height", bands: ["low", "medium", "high"], hint: "Height of the top of your foot; sets upper volume" },
  { key: "heel_width", label: "Heel width", bands: ["narrow", "medium", "wide"], hint: "Width of your heel; sets heel hold" },
  { key: "pressure", label: "Pressure", bands: ["medial", "centered", "lateral"], optional: true, hint: "Where your weight lands" },
  { key: "arch_flexibility", label: "Arch flexibility", bands: ["flexible", "moderate", "rigid"], optional: true, hint: "How much your arch flattens under load" },
];
export type { ScaleKey };

export const bandAt = (bands: readonly string[], position: number) =>
  bands[Math.min(2, Math.floor(Math.min(0.999, Math.max(0, position)) * 3))];

export function blankFoot(): Foot {
  return {
    us_size: 9,
    width: "D",
    arch_height: { band: "medium", position: 0.5 },
    instep_height: { band: "medium", position: 0.5 },
    heel_width: { band: "medium", position: 0.5 },
    pressure: null,
    arch_flexibility: null,
  };
}

export const blankProfile = (): FootProfile => ({ sex_scale: "men", left: blankFoot(), right: blankFoot() });

export const cap = (s: string) => (s ? s[0].toUpperCase() + s.slice(1) : s);
