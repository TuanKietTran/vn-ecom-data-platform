import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = {
  title: "hunt — Good finds, grounded in evidence",
  description: "Explore supplied product and voucher evidence, with checkout costs and cashback kept separate.",
};
export default function Layout({ children }: { children: React.ReactNode }) {
  return <html lang="en"><body>{children}</body></html>;
}
