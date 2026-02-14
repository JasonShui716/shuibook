 "use client";

const TOPICS = [
  "全部",
  "收藏",
  "AI效率/项目管理",
  "具身智能/机器人",
  "AI硬件/应用/实验室发布",
  "育儿/婴幼儿",
  "HiFi音频",
  "音乐推荐",
  "宏观经济/时政",
  "极客小玩意",
  "用户体验/分享",
];

export default function TopicTabs({
  active,
  onSelect,
}: {
  active?: string;
  onSelect: (topic: string) => void;
}) {
  return (
    <div className="flex gap-2 overflow-x-auto md:flex-wrap md:overflow-visible pb-1">
      {TOPICS.map((topic) => {
        const isActive = (active || "全部") === topic;
        return (
          <button
            key={topic}
            type="button"
            onClick={() => onSelect(topic)}
            className={`px-3 py-1 rounded-full text-sm border transition whitespace-nowrap ${
              isActive
                ? "bg-ink-900 text-white border-ink-900"
                : "bg-white/70 text-ink-700 border-ink-300 hover:border-ink-900"
            }`}
          >
            {topic}
          </button>
        );
      })}
    </div>
  );
}
