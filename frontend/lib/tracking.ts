/** Публичные страницы трекинга перевозчиков — посмотреть, где посылка,
 * в один клик. Неизвестный перевозчик уходит на универсальный 17track. */
export function trackingUrl(number: string, carrier: string | null): string {
  const n = encodeURIComponent(number);
  switch ((carrier ?? "").toLowerCase()) {
    case "ups":
      return `https://www.ups.com/track?tracknum=${n}`;
    case "usps":
      return `https://tools.usps.com/go/TrackConfirmAction?tLabels=${n}`;
    case "fedex":
      return `https://www.fedex.com/fedextrack/?trknbr=${n}`;
    case "dhl":
      return `https://www.dhl.com/us-en/home/tracking.html?tracking-id=${n}`;
    default:
      return `https://t.17track.net/en#nums=${n}`;
  }
}
