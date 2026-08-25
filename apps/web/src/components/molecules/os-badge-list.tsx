import { Badge } from "@/components/atoms/badge";

export function OsBadgeList({
  values,
  empty,
}: {
  values?: readonly string[] | null;
  empty: string;
}) {
  if (!values?.length) return empty;
  return (
    <ul className="flex flex-wrap gap-1">
      {values.map((value) => (
        <li key={value}>
          <Badge variant="outline">{value}</Badge>
        </li>
      ))}
    </ul>
  );
}
