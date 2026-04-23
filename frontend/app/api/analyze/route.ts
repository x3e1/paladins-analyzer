import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

export async function POST(req: NextRequest) {
  const incoming = await req.formData();
  // Re-forward the multipart payload to the FastAPI backend.
  const outgoing = new FormData();
  for (const [key, value] of incoming.entries()) {
    outgoing.append(key, value as Blob | string);
  }
  // Pass through query params (mode, ai, ...).
  const url = new URL(req.url);
  const target = `${BACKEND_URL}/analyze${url.search}`;
  let resp: Response;
  try {
    resp = await fetch(target, { method: "POST", body: outgoing });
  } catch (e) {
    return NextResponse.json(
      { error: "backend_unreachable", detail: String(e) },
      { status: 502 }
    );
  }
  const body = await resp.text();
  return new NextResponse(body, {
    status: resp.status,
    headers: { "content-type": resp.headers.get("content-type") ?? "application/json" },
  });
}
