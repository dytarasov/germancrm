// Типы контракта API shaprivezu. Деньги — строки ("12.50"), даты — ISO.

export type OrderStatus =
  | "purchased"
  | "shipped"
  | "at_warehouse"
  | "in_flight"
  | "delivered"
  | "closed"
  | "cancelled"
  | "refunded";

export type StatusSource = "auto" | "manual";

export interface OrderListItem {
  id: number;
  client_id: number;
  client_name: string;
  store: string;
  store_order_number: string | null; // первый номер подзаказа
  suborders_count: number;
  items: string;
  status: OrderStatus;
  purchase_price_usd: string;
  commission_usd: string | null;
  weight_kg: string | null;
  promised_date: string | null;
  purchased_on: string;
  is_overdue: boolean;
  paid_usd: string;
  due_usd: string | null;
  tracks_count: number;
  /** ожидаемое прибытие едущих к складу посылок (из писем), ориентир */
  eta_on: string | null;
}

export interface StatusChange {
  id: number;
  old_status: OrderStatus | null;
  new_status: OrderStatus;
  source: StatusSource;
  comment: string | null;
  changed_at: string;
  suborder_id: number | null;
}

/** Подзаказ: заказ магазина внутри корзины — номер, справочная сумма, свой статус. */
export interface Suborder {
  id: number;
  order_id: number;
  store_order_number: string | null;
  amount_usd: string | null;
  status: OrderStatus;
  eta_on: string | null;
}

export interface TrackCandidate {
  order_id: number;
  score: number;
  reasons: string[];
  order_label: string;
}

export interface Track {
  id: number;
  tracking_number: string;
  carrier: string | null;
  order_id: number | null;
  suborder_id: number | null;
  email_log_id: number | null;
  source: "manual" | "email";
  match_status: "linked" | "open" | "dismissed";
  candidates: TrackCandidate[] | null;
  note: string | null;
  created_at: string;
}

export interface Payment {
  id: number;
  order_id: number;
  paid_on: string;
  amount_usd: string;
  comment: string | null;
}

export interface OrderFinance {
  revenue_usd: string | null;
  paid_usd: string;
  due_usd: string | null;
}

/** Позиция заказа: название и/или ссылка — хотя бы одно есть всегда. */
export interface OrderItem {
  id: number;
  order_id: number;
  title: string | null;
  url: string | null;
  quantity: number;
  note: string | null;
}

export interface OrderDetail extends OrderListItem {
  est_weight_kg: string | null;
  comment: string | null;
  refunded_amount_usd: string | null;
  refunded_at: string | null;
  flight_id: number | null;
  copied_from: number | null;
  closed_at: string | null;
  created_at: string;
  updated_at: string;
  suborders: Suborder[];
  tracks: Track[];
  payments: Payment[];
  history: StatusChange[];
  finance: OrderFinance;
  order_items: OrderItem[];
}

export interface ClientListItem {
  id: number;
  name: string;
  contacts: string | null;
  telegram_url: string | null;
  active_orders: number;
  debt_usd: string;
}

export interface ClientInfo {
  id: number;
  name: string;
  contacts: string | null;
  telegram_url: string | null;
  note: string | null;
  created_at: string;
}

export interface ClientDetail {
  client: ClientInfo;
  orders: OrderListItem[];
  debt_usd: string;
  earned_usd: string;
}

export interface Flight {
  id: number;
  departed_on: string;
  cost_usd: string;
  description: string | null;
  orders_count?: number;
}

export interface FlightDetail extends Flight {
  orders: OrderListItem[];
}

export interface MailHealth {
  configured: boolean;
  gmail_connected: boolean;
  gmail_email: string | null;
  needs_reauth: boolean;
  last_success_at: string | null;
  llm_degraded: boolean;
  pending_llm: number;
  manual_review: number;
  poison: number;
  open_tracks: number;
  worker_ok: boolean;
}

export interface Dashboard {
  orders_in_progress: number;
  clients_debt_usd: string;
  month_profit_usd: string;
  month_commissions_usd: string;
  month_flights_cost_usd: string;
  attention: {
    no_commission: OrderListItem[];
    overdue: OrderListItem[];
    unmatched_tracks: Track[];
  };
  mail: MailHealth;
}

export interface MoneyReportOrder {
  id: number;
  client_name: string;
  store: string;
  items: string;
  commission_usd: string | null;
  closed_at: string | null;
}

export interface MoneyReportMonth {
  month: string;
  commissions_usd: string;
  flights_cost_usd: string;
  profit_usd: string;
}

export interface MoneyReport {
  from: string;
  to: string;
  commissions_usd: string;
  flights_cost_usd: string;
  profit_usd: string;
  orders: MoneyReportOrder[];
  flights: Flight[];
  months: MoneyReportMonth[];
}

export interface SearchResult {
  clients: ClientListItem[];
  orders: OrderListItem[];
  tracks: Track[];
}

export type MailAction =
  | "status_advanced"
  | "track_added"
  | "track_suggested"
  | "order_no_linked"
  | "ignored_stale"
  | "ignored_terminal"
  | "manual_review"
  | "info";

export interface MailEvent {
  id: number;
  created_at: string;
  action: MailAction;
  event_type: string | null;
  summary: string | null;
  order_id: number | null;
  order_label: string | null;
  subject: string | null;
  from_addr: string | null;
  tracking_number: string | null;
}

export interface EmailRow {
  id: number;
  from_addr: string;
  subject: string | null;
  sent_at: string | null;
  processing_status: string;
  error: string | null;
  snippet: string | null;
  event_type: string | null;
  confidence: number | null;
}

export interface MailReview {
  emails: EmailRow[];
  filtered: EmailRow[];
  open_tracks: Track[];
}

export interface EmailExtracted {
  event_type: string;
  confidence: number;
  store_domain: string | null;
  order_number: string | null;
  tracking_numbers: { number: string; carrier: string | null }[];
  carrier: string | null;
  summary: string;
  reasoning: string | null;
}

export interface EmailDetail extends EmailRow {
  from_domain: string;
  body_text: string | null;
  extracted: EmailExtracted | null;
}

export interface LoginBan {
  ip: string;
  fails: number;
  last_fail_at: string;
  banned_until: string | null;
}

export interface Settings {
  commission_per_kg_usd: number;
  /** наценка для подсказки «цена с комиссией», % */
  markup_pct: number;
  llm_model: string;
  llm_enabled: boolean;
  llm_auto_min_confidence: number;
  poll_interval_sec: number;
  backfill_days: number;
  whitelist_domains: string[];
  forwarder_domains: string[];
  gmail_query: string;
  auto_threshold: number;
  suggest_threshold: number;
  gmail: {
    connected: boolean;
    email: string | null;
    needs_reauth: boolean;
  };
}

export interface TrackSuggestion {
  order_id: number;
  order_label: string;
  client_name: string;
  score: number;
  reasons: string[];
}
