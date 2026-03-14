"use client";

import { useAuth } from "@clerk/nextjs";
import { useEffect, useMemo, useState } from "react";

import { getCurrentUserStatus, uploadResume, type CandidateProfile } from "../lib/api";

export default function ResumeUploadModal() {
  const { isSignedIn, getToken } = useAuth();
  const [checking, setChecking] = useState(false);
  const [open, setOpen] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const [file, setFile] = useState<File | null>(null);

  const helpText = useMemo(
    () =>
      "Why you weren’t seeing users: A user profile row was only created when a resume was uploaded. No call happened on sign-in.",
    []
  );

  useEffect(() => {
    let alive = true;
    if (!isSignedIn) {
      setOpen(false);
      return;
    }

    const checkStatus = async () => {
      setChecking(true);
      try {
        const token = await getToken();
        const status = await getCurrentUserStatus(token ?? undefined);
        if (!alive) return;
        setOpen(!status.has_resume);
      } catch (err) {
        if (!alive) return;
        setOpen(true);
        setError(String(err));
      } finally {
        if (alive) setChecking(false);
      }
    };

    void checkStatus();
    return () => {
      alive = false;
    };
  }, [isSignedIn]);

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!file) {
      setError("Please select a PDF or DOCX file.");
      return;
    }

    setUploading(true);
    setError("");
    try {
      const token = await getToken();
      const response = await uploadResume(file, token ?? undefined);
      if (response?.profile) {
        setOpen(false);
      }
    } catch (err) {
      setError(String(err));
    } finally {
      setUploading(false);
    }
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-60 flex items-center justify-center bg-black/70 p-4">
      <div className="w-full max-w-lg rounded-xl border border-white/10 bg-(--card) p-6 shadow-2xl">
        <h2 className="text-xl font-semibold">Upload your resume to continue</h2>
        <p className="mt-2 text-sm text-zinc-400">{helpText}</p>

        {error && (
          <div className="mt-4 rounded border border-red-800 bg-red-900/30 px-4 py-3 text-sm text-red-300">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="mt-5 space-y-4">
          <div>
            <label className="block text-sm font-medium mb-2">
              Resume File (PDF or DOCX)
            </label>
            <input
              type="file"
              accept=".pdf,.docx"
              disabled={uploading}
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              className="w-full rounded border border-(--border) bg-(--background) px-3 py-2 text-sm file:mr-4 file:rounded file:border-0 file:bg-white file:px-3 file:py-1 file:text-xs file:font-medium file:text-black hover:file:bg-zinc-200"
            />
          </div>

          <button
            type="submit"
            disabled={uploading || checking}
            className="w-full rounded border border-white py-2.5 text-sm font-medium text-white transition hover:bg-white hover:text-black disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {uploading ? "Uploading..." : "Upload Resume"}
          </button>
        </form>
      </div>
    </div>
  );
}
