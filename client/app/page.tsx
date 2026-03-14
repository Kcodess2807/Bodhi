"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

export default function Home() {
  const [health, setHealth] = useState<string>("checking...");

  useEffect(() => {
    fetch("/api/health")
      .then((r) => (r.ok ? r.json() : Promise.reject(r.statusText)))
      .then(() => setHealth("connected"))
      .catch(() => setHealth("unreachable"));
  }, []);

  return (
    <div className="space-y-8">
      <h1 className="text-3xl font-bold">Bodhi Test Client</h1>
      <p className="text-zinc-400">
        Minimal frontend to test all Bodhi API endpoints.
      </p>

      <div className="rounded-lg border border-[var(--border)] bg-[var(--card)] p-4">
        <span className="text-sm text-zinc-400">API Status: </span>
        <span
          className={
            health === "connected"
              ? "font-semibold text-green-400"
              : health === "unreachable"
                ? "font-semibold text-red-400"
                : "text-yellow-400"
          }
        >
          {health}
        </span>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        {[
          {
            href: "/roles",
            title: "Roles",
            desc: "Manage predefined interview role profiles",
          },
          {
            href: "/companies",
            title: "Companies",
            desc: "Manage company + role profiles",
          },
          {
            href: "/documents",
            title: "Documents",
            desc: "Ingest text, upload files, search RAG",
          },
          {
            href: "/resumes",
            title: "Resumes",
            desc: "Upload resume for personalized interviews",
          },
          {
            href: "/interview",
            title: "Interview",
            desc: "Start and conduct a mock interview",
          },
        ].map((c) => (
          <Link
            key={c.href}
            href={c.href}
            className="rounded-lg border border-[var(--border)] bg-[var(--card)] p-5 transition hover:border-white"
          >
            <h2 className="mb-1 text-lg font-semibold">{c.title}</h2>
            <p className="text-sm text-zinc-400">{c.desc}</p>
          </Link>
        ))}
      </div>
    </div>
  );
}
