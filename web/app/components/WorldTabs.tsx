"use client";

const WORLDS = [
  { id: "real", label: "真实世界" },
  { id: "link", label: "链接抓取" },
];

export default function WorldTabs({
  active,
  onSelect,
}: {
  active?: string;
  onSelect: (world: string) => void;
}) {
  return (
    <div className="flex gap-2 overflow-x-auto md:flex-wrap md:overflow-visible pb-1">
      {WORLDS.map((world) => {
        const isActive = (active || "real") === world.id;
        return (
          <button
            key={world.id}
            type="button"
            onClick={() => onSelect(world.id)}
            className={`px-3 py-1 rounded-full text-sm border transition whitespace-nowrap ${
              isActive
                ? "bg-ink-900 text-white border-ink-900"
                : "bg-white/70 text-ink-700 border-ink-300 hover:border-ink-900"
            }`}
          >
            {world.label}
          </button>
        );
      })}
    </div>
  );
}
