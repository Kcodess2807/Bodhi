"use client";

interface ConsentNoticeProps {
  accepted: boolean;
  onAccept: (accepted: boolean) => void;
}

export function ConsentNotice({ accepted, onAccept }: ConsentNoticeProps) {
  return (
    <div className="rounded-lg border border-yellow-700/50 bg-yellow-900/10 p-4 space-y-3">
      <div className="flex items-start gap-2">
        <span className="text-yellow-400 text-base mt-0.5">⚠</span>
        <div>
          <h3 className="text-sm font-semibold text-yellow-300">
            Identity Verification Active
          </h3>
          <p className="text-xs text-zinc-400 mt-1 leading-relaxed">
            This session uses real-time face verification to confirm your
            identity. Here is what happens:
          </p>
          <ul className="mt-2 space-y-1 text-xs text-zinc-400 list-disc list-inside">
            <li>Your webcam feed is analyzed locally in your browser.</li>
            <li>
              Your face is compared to your reference photo every ~20 seconds.
            </li>
            <li>
              No video or images are stored — only violation metadata (timestamp
              + confidence score) is sent to the server.
            </li>
            <li>
              3 consecutive mismatches will flag this session for review.
            </li>
          </ul>
        </div>
      </div>
      <label className="flex items-center gap-2.5 cursor-pointer select-none">
        <input
          type="checkbox"
          checked={accepted}
          onChange={(e) => onAccept(e.target.checked)}
          className="h-4 w-4 accent-yellow-400"
        />
        <span className="text-xs text-zinc-300">
          I understand and consent to identity verification during this session.
        </span>
      </label>
    </div>
  );
}
