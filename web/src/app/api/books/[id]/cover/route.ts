import { proxyBookCover } from "@/lib/book-cover-server";

export async function GET(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return proxyBookCover(request, id);
}
