"use client";

import { useRouter } from "next/navigation";
import Toast from "../../components/Toast";
import { useToast } from "../../components/useToast";

export default function DetailMobileBar({ readOriginal }: { readOriginal: string | null }) {
  const router = useRouter();
  const { toast, showToast } = useToast(1800);

  return (
    <>
      <div className="fixed bottom-0 inset-x-0 z-40 bg-white/90 backdrop-blur border-t md:hidden">
        <div className="max-w-4xl mx-auto h-16 px-6 flex items-center justify-between text-sm">
          <button
            type="button"
            onClick={() => router.back()}
            className="px-3 py-2 rounded-full bg-ink-900 text-white"
          >
            返回
          </button>
          <button
            type="button"
            onClick={() => {
              window.scrollTo({ top: 0, behavior: "smooth" });
              showToast("已回到顶部", "info");
            }}
            className="px-3 py-2 rounded-full bg-white text-ink-900 border border-ink-300"
          >
            顶部
          </button>
          {readOriginal && (
            <button
              type="button"
              onClick={() => {
                window.open(readOriginal, "_blank", "noopener,noreferrer");
                showToast("已打开原文", "success");
              }}
              className="px-3 py-2 rounded-full bg-cream-100 text-ink-900"
            >
              原文
            </button>
          )}
        </div>
      </div>
      <Toast toast={toast} className="bottom-24" />
    </>
  );
}
