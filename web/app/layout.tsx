import "./globals.css";
import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Shuibook Feed",
  description: "个人小红书式信息流",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh">
      <body>
        <div className="min-h-screen px-4 pb-16">
          <header className="max-w-6xl mx-auto pt-10 pb-6 hidden md:block">
            <div className="flex items-start justify-between gap-6">
              <div className="flex flex-col gap-2">
                <span className="text-xs uppercase tracking-[0.3em] text-ink-600">
                  Personal Feed Lab
                </span>
                <h1 className="text-3xl md:text-5xl font-display text-ink-900">
                  ShuiBook · 小红书式信息流
                </h1>
              </div>
              <nav className="flex items-center gap-4 text-sm text-ink-600">
                <Link href="/prd" className="hover:text-ink-900">
                  PRD
                </Link>
                <Link href="/admin" className="hover:text-ink-900">
                  管理后台
                </Link>
              </nav>
            </div>
          </header>
          {children}
        </div>
      </body>
    </html>
  );
}
