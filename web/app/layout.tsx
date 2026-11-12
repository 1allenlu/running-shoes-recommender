import type { Metadata, Viewport } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import { Toaster } from "@/components/ui/sonner";
import "./globals.css";

const inter = Inter({ variable: "--font-sans", subsets: ["latin"] });
const mono = JetBrains_Mono({ variable: "--font-mono", subsets: ["latin"], weight: ["500"] });

export const metadata: Metadata = {
  title: "LastFit · Running shoes matched to your feet",
  description:
    "Bring the 3D foot scan from your running store. LastFit ranks running shoes on how they fit your feet and tells you the exact size to order.",
  icons: {
    icon: "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='8' fill='%230c0d0e'/%3E%3Cpath d='M9 8v16h14' stroke='%23d4f54a' stroke-width='3.2' fill='none' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E",
  },
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#fafaf9" },
    { media: "(prefers-color-scheme: dark)", color: "#0b0c0d" },
  ],
};

// Follow the OS theme before first paint (no flash).
const themeScript = `try{if(matchMedia('(prefers-color-scheme: dark)').matches)document.documentElement.classList.add('dark')}catch(e){}`;

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body className={`${inter.variable} ${mono.variable} min-h-dvh bg-background font-sans text-foreground antialiased`}>
        {children}
        <Toaster position="bottom-center" />
      </body>
    </html>
  );
}
