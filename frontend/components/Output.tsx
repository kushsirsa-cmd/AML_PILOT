import { Json } from "@/lib/api";
import { Pill, RiskBadge } from "./ui";

const RATING_WORDS = new Set(["LOW", "MEDIUM", "HIGH", "PROHIBITED"]);
const label = (k: string) => k.replace(/_/g, " ").replace(/\b\w/g, (m) => m.toUpperCase());

/** Generic renderer for agent JSON outputs: paragraphs, bullet lists, key/value grids, risk badges. */
export function Output({ data, skip = [] }: { data: Json; skip?: string[] }) {
  if (data === null || data === undefined || data === "") return <span className="text-slate-400">-</span>;
  if (typeof data === "boolean") return <Pill tone={data ? "amber" : "slate"}>{data ? "Yes" : "No"}</Pill>;
  if (typeof data === "number") return <span>{data}</span>;
  if (typeof data === "string") {
    if (RATING_WORDS.has(data)) return <RiskBadge rating={data} />;
    return <span className="whitespace-pre-wrap">{data}</span>;
  }
  if (Array.isArray(data)) {
    if (data.length === 0) return <span className="text-slate-400">None</span>;
    if (data.every((x) => typeof x !== "object" || x === null)) {
      return (
        <ul className="list-disc space-y-1 pl-5">
          {data.map((x, i) => (
            <li key={i}>{String(x)}</li>
          ))}
        </ul>
      );
    }
    return (
      <div className="space-y-2">
        {data.map((x, i) => (
          <div key={i} className="rounded border border-slate-100 bg-slate-50 p-2">
            <Output data={x} skip={skip} />
          </div>
        ))}
      </div>
    );
  }
  const entries = Object.entries(data).filter(([k]) => !skip.includes(k) && k !== "engine");
  return (
    <dl className="grid grid-cols-1 gap-x-4 gap-y-2 sm:grid-cols-[minmax(130px,200px)_1fr]">
      {entries.map(([k, v]) => (
        <div key={k} className="contents">
          <dt className="text-xs font-medium uppercase tracking-wide text-slate-500 sm:pt-0.5">{label(k)}</dt>
          <dd className="text-sm text-slate-800">
            <Output data={v} skip={skip} />
          </dd>
        </div>
      ))}
    </dl>
  );
}
