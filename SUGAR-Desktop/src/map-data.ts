import type { PostMap, PostPin } from "./research-types";

export type PostStyle = "points" | "density" | "recency" | "valence" | "intensity" | "direction";
export type TimeBin = { start: string; end: string; label: string; count: number };
export const publicationTime = (pin: PostPin): number | null => {
  const time = pin.published_at ? Date.parse(pin.published_at) : NaN;
  return Number.isFinite(time) ? time : null;
};

export function timelineBins(pins: PostPin[]): TimeBin[] {
  const times = pins.map(publicationTime).filter((t): t is number => t !== null);
  if (!times.length) return [];
  let low = Infinity, high = -Infinity;
  for (const t of times) { low = Math.min(low, t); high = Math.max(high, t); }
  const spanDays = (high - low) / 86400000;
  const unit = spanDays <= 90 ? "day" : spanDays <= 3652 ? "month" : "year";
  const key = (t: number) => new Date(t).toISOString().slice(0, unit === "day" ? 10 : unit === "month" ? 7 : 4);
  const counts = new Map<string, number>();
  for (const t of times) counts.set(key(t), (counts.get(key(t)) || 0) + 1);
  const cursor = new Date(low);
  cursor.setUTCHours(0, 0, 0, 0);
  if (unit !== "day") cursor.setUTCDate(1);
  if (unit === "year") cursor.setUTCMonth(0);
  const bins: TimeBin[] = [];
  while (cursor.getTime() <= high) {
    const start = cursor.toISOString().slice(0, 10), k = key(cursor.getTime());
    if (unit === "day") cursor.setUTCDate(cursor.getUTCDate() + 1);
    else if (unit === "month") cursor.setUTCMonth(cursor.getUTCMonth() + 1);
    else cursor.setUTCFullYear(cursor.getUTCFullYear() + 1);
    bins.push({ start, end: new Date(cursor.getTime() - 1).toISOString().slice(0, 10), label: k, count: counts.get(k) || 0 });
  }
  return bins;
}

/** Rebuild counts and flows from the same dated pins rendered on the map. */
export function windowPosts(data: PostMap | null, since: string, until: string, sort: "newest" | "oldest"): PostMap | null {
  if (!data) return null;
  const low = since ? Date.parse(`${since}T00:00:00Z`) : -Infinity;
  const high = until ? Date.parse(`${until}T23:59:59.999Z`) : Infinity;
  const pins = data.pins.filter((p) => {
    const t = publicationTime(p);
    return t === null ? !since && !until : t >= low && t <= high;
  }).sort((a, b) => {
    const at = publicationTime(a), bt = publicationTime(b);
    if (at === null) return bt === null ? a.item_id.localeCompare(b.item_id) : 1;
    if (bt === null) return -1;
    return (sort === "newest" ? bt - at : at - bt) || a.item_id.localeCompare(b.item_id);
  });
  if (!since && !until) return { ...data, pins };
  const targets = new Map<string, PostMap["targets"][number]>();
  const flows = new Map<string, PostMap["flows"][number]>();
  const now = data.as_of ? Date.parse(data.as_of) : Date.now();
  for (const p of pins) {
    for (const t of p.targets) {
      let row = targets.get(t.name);
      if (!row) {
        row = { name: t.name, latitude: t.latitude, longitude: t.longitude, posts: 0, last_24h: 0, verified: 0, last_at: "", item_ids: [], platforms: {}, languages: {}, cities: {} };
        targets.set(t.name, row);
      }
      row.posts++; row.verified += Number(p.verified); row.item_ids.push(p.item_id);
      const time = publicationTime(p);
      if (time !== null && time >= now - 86400000 && time <= now) row.last_24h++;
      if (p.published_at > row.last_at) row.last_at = p.published_at;
      row.platforms[p.platform] = (row.platforms[p.platform] || 0) + 1;
      row.languages[p.language || "und"] = (row.languages[p.language || "und"] || 0) + 1;
      if (t.city) row.cities[t.city] = (row.cities[t.city] || 0) + 1;
      if (p.origin) {
        const k = JSON.stringify([p.origin.longitude, p.origin.latitude, t.name]);
        const flow = flows.get(k) || { from: [p.origin.longitude, p.origin.latitude], to: [t.longitude, t.latitude], target: t.name, posts: 0 };
        flow.posts++; flows.set(k, flow);
      }
    }
  }
  return { ...data, pins, targets: [...targets.values()].sort((a, b) => b.posts - a.posts || a.name.localeCompare(b.name)), flows: [...flows.values()] };
}

export function axisSummary(pins: PostPin[], axis: "valence" | "intensity" | "direction") {
  const values = pins.map((p) => p.sentiment?.[axis]).filter((v): v is number => typeof v === "number" && Number.isFinite(v));
  return { n: values.length, mean: values.length ? values.reduce((a, b) => a + b, 0) / values.length : null };
}
