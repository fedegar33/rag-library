import { proxyCatalog } from "@/lib/catalog-server";

export const runtime = "nodejs";
export async function GET(request: Request) {
  return proxyCatalog(request);
}
