## Bodhi Frontend

This is the public-facing UI for Bodhi, the AI mock-interview platform. It provides the marketing landing page, Clerk authentication, and a mandatory resume-upload flow that seeds user profiles for resume-based interviews.

## Features

- Clerk sign-in + user profile sync
- Mandatory resume upload modal after sign-in
- Landing page UI with sections for features, pricing, docs, and testimonials
- **Interview Phase Badge**: Real-time display of the active interview segment (Intro, Technical, DSA, etc.) in the session toolbar.
- API proxy to the FastAPI backend at `http://localhost:8000`

## Local Development

Install dependencies:

```bash
npm install
```

Run the app:

```bash
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

## Environment

Create `client/.env.local` with your Clerk publishable key:

```bash
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_test_...
```

The backend must be running on `http://localhost:8000` (see `next.config.ts` rewrite).

## Resume Upload Flow

1. User signs in with Clerk.
2. The app calls `/api/users/me/status`.
3. If no resume is present, a blocking modal requests a PDF/DOCX upload.
4. Uploading creates/updates `user_profiles` and unlocks resume-based interviews.
