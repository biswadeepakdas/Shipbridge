import { NextResponse } from "next/server";

export async function GET() {
  return NextResponse.json({
    data: {
      status: "ok",
      service: "web",
      version: "0.1.0",
      timestamp: new Date().toISOString(),
    },
    error: null,
    meta: {},
  });
}
