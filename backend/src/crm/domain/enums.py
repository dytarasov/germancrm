from enum import StrEnum


class OrderStatus(StrEnum):
    PURCHASED = "purchased"
    SHIPPED = "shipped"
    AT_WAREHOUSE = "at_warehouse"
    IN_FLIGHT = "in_flight"
    DELIVERED = "delivered"
    CLOSED = "closed"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


class StatusSource(StrEnum):
    AUTO = "auto"
    MANUAL = "manual"


class TrackSource(StrEnum):
    MANUAL = "manual"
    EMAIL = "email"


class TrackMatchStatus(StrEnum):
    LINKED = "linked"
    OPEN = "open"
    DISMISSED = "dismissed"


class EmailProcessingStatus(StrEnum):
    NEW = "new"
    FILTERED = "filtered"
    PENDING_LLM = "pending_llm"
    PROCESSED = "processed"
    MANUAL_REVIEW = "manual_review"
    IGNORED = "ignored"
    POISON = "poison"


class EmailEventType(StrEnum):
    ORDER_CONFIRMATION = "order_confirmation"
    SHIPPED = "shipped"
    ARRIVED_AT_WAREHOUSE = "arrived_at_warehouse"
    DELIVERY_UPDATE = "delivery_update"
    CANCELLATION_OR_REFUND = "cancellation_or_refund"
    OTHER = "other"


class EmailAction(StrEnum):
    STATUS_ADVANCED = "status_advanced"
    TRACK_ADDED = "track_added"
    TRACK_SUGGESTED = "track_suggested"
    ORDER_NO_LINKED = "order_no_linked"
    IGNORED_STALE = "ignored_stale"
    IGNORED_TERMINAL = "ignored_terminal"
    MANUAL_REVIEW = "manual_review"
    INFO = "info"
