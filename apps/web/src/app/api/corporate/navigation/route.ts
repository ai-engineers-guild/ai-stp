import { NextResponse } from "next/server";
import { readCorporateNavigationSnapshot } from "@/lib/corporate-navigation-server";

export const dynamic = "force-dynamic";

export async function GET(): Promise<NextResponse> {
  const headers = { "Cache-Control": "no-store, private" };
  const snapshot = await readCorporateNavigationSnapshot();
  return NextResponse.json(
    { administration: snapshot.administration, pages: snapshot.pages },
    { headers, status: snapshot.status },
  );
}
