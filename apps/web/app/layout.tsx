import type { Metadata } from "next";
import "@fontsource/barlow-condensed/800.css";
import "./globals.css";
export const metadata: Metadata = {
  title: "ShopLens — Good deals. No guesswork.",
  description:
    "Hunt exact products, combine eligible vouchers and understand your checkout price.",
};
export default function Layout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
