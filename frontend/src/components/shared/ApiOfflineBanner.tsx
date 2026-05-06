import { WifiOff } from "lucide-react";

export function ApiOfflineBanner({ offline }: { offline: boolean }) {
  if (!offline) return null;
  return (
    <div className="flex items-center gap-2 border-b border-amber-400/20 bg-amber-500/10 px-5 py-2 text-sm text-amber-100">
      <WifiOff className="h-4 w-4" />
      Backend unreachable. Start it with <code className="font-mono">python -m ad_classifier api</code>.
    </div>
  );
}
