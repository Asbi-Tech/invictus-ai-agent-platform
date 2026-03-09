import { Progress } from "@/components/ui/progress";

interface Props {
  label: string;
  used: number;
  limit: number;
}

export default function QuotaBar({ label, used, limit }: Props) {
  const pct = limit > 0 ? Math.min((used / limit) * 100, 100) : 0;
  const color =
    pct >= 90 ? "text-red-500" : pct >= 70 ? "text-yellow-500" : "text-green-500";

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between text-sm">
        <span className="text-muted-foreground">{label}</span>
        <span className={`font-medium ${color}`}>
          {used.toLocaleString()} / {limit.toLocaleString()}
        </span>
      </div>
      <Progress value={pct} className="h-2" />
    </div>
  );
}
