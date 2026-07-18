import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "FaceBlur | Safer photo sharing for schools",
  description:
    "Automatically find and blur students on your no-photo list before school photos are shared.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
