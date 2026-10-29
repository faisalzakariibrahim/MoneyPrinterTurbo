import type { Metadata } from "next";
import "./globals.css";
import { APP_NAME } from "@/lib/format";

export const metadata: Metadata = {
  title: { default: APP_NAME, template: `%s · ${APP_NAME}` },
  description: "Plan, write and render two-to-four hour narrated YouTube videos in your channel's style.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
