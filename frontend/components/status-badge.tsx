import type { OrderStatus } from "@/lib/api-types";
import { STATUS_CHIP, STATUS_LABEL } from "@/lib/status";
import { Badge } from "./ui";

export function StatusBadge({ status }: { status: OrderStatus }) {
  return <Badge className={STATUS_CHIP[status]}>{STATUS_LABEL[status]}</Badge>;
}

export function OverdueBadge() {
  return <Badge className="bg-red-500/12 text-red-700 dark:text-red-400">Опаздывает</Badge>;
}

export function NoCommissionBadge() {
  return <Badge className="bg-amber-500/15 text-amber-700 dark:text-amber-400">нет комиссии</Badge>;
}
