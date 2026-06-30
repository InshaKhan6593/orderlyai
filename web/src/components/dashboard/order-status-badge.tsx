import { Badge } from "@/components/ui/badge";
import { statusLabel, type DashboardOrderStatus } from "@/lib/dashboard";
import { cn } from "@/lib/utils";

/**
 * Soft, dotted status pills shared by every order surface (overview table, board card, detail
 * sheet). One colour per lifecycle stage with a leading status dot — replaces the duplicated
 * outline-badge colour maps that lived in each component.
 */
const STATUS_STYLE: Record<DashboardOrderStatus, { badge: string; dot: string }> = {
  pending: { badge: "bg-blue-100 text-blue-700", dot: "bg-blue-500" },
  accepted: { badge: "bg-indigo-100 text-indigo-700", dot: "bg-indigo-500" },
  preparing: { badge: "bg-amber-100 text-amber-800", dot: "bg-amber-500" },
  ready: { badge: "bg-teal-100 text-teal-700", dot: "bg-teal-500" },
  out_for_delivery: { badge: "bg-violet-100 text-violet-700", dot: "bg-violet-500" },
  completed: { badge: "bg-emerald-100 text-emerald-700", dot: "bg-emerald-500" },
  rejected: { badge: "bg-rose-100 text-rose-700", dot: "bg-rose-500" },
  cancelled: { badge: "bg-slate-200 text-slate-600", dot: "bg-slate-400" },
};

export function OrderStatusBadge({
  status,
  className,
}: {
  status: DashboardOrderStatus;
  className?: string;
}) {
  const style = STATUS_STYLE[status];
  return (
    <Badge
      className={cn(
        "gap-1.5 rounded-md border-transparent px-2 py-0.5 font-medium",
        style.badge,
        className,
      )}
    >
      <span className={cn("size-1.5 shrink-0 rounded-full", style.dot)} aria-hidden="true" />
      {statusLabel(status)}
    </Badge>
  );
}
