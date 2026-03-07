# Invictus Deals Onboarding Frontend

React dashboard for the Invictus Deals Onboarding Platform. Displays deals, document slots, and structured deal fields extracted by the backend worker pipeline.

---

## Tech Stack

| Technology | Purpose |
|------------|---------|
| React 18 | UI framework |
| TypeScript | Type safety |
| Vite | Build tool and dev server |
| TailwindCSS | Utility-first styling |
| shadcn/ui (Radix) | Accessible component library |
| React Router | Client-side routing |
| TanStack React Query | Data fetching and caching |
| React Hook Form + Zod | Form handling and validation |
| Framer Motion | Animations |
| Recharts | Charts and data visualization |

---

## Prerequisites

- **Node.js 18+** and npm, **or** [Bun](https://bun.sh/) (recommended)
- **Backend server running** on `http://localhost:8000` (see [root README](../README.md#backend-setup))

---

## Getting Started

### 1. Install dependencies

```bash
cd frontend
bun install        # or: npm install
```

### 2. Configure environment

```bash
cp .env.example .env
```

The default `.env` works for local development:

```env
VITE_API_URL=http://localhost:8000
```

### 3. Start the development server

```bash
bun dev            # or: npm run dev
```

The app runs at **http://localhost:8080**.

### 4. Open in browser

Navigate to http://localhost:8080 and sign in with Google. Make sure the backend is running first.

---

## API Proxy

The Vite dev server proxies API requests to the backend so you don't need to deal with CORS during development. The following paths are forwarded to `http://localhost:8000`:

| Path Pattern | Backend Route |
|-------------|---------------|
| `/auth/*` | Google OAuth flow |
| `/drive/*` | Drive folder configuration |
| `/documents/(latest\|all\|deals)/*` | Document and deal endpoints |
| `/sync/*` | Sync status |
| `/health` | Liveness probe |

This is configured in [vite.config.ts](vite.config.ts).

---

## Build for Production

```bash
bun run build      # or: npm run build
```

Output is written to `dist/`. Serve with any static file server or deploy to Vercel/Netlify.

---

## Project Structure

```
frontend/
├── src/
│   ├── components/       # Reusable UI components (DocumentCard, Navbar, etc.)
│   ├── pages/            # Route pages (Index, DealDetail, NotFound)
│   ├── lib/
│   │   └── api.ts        # Typed API client with React Query hooks
│   ├── hooks/            # Custom React hooks
│   ├── context/          # React context providers
│   └── App.tsx           # Root component with routing
├── .env.example          # Environment variable template
├── vite.config.ts        # Vite config with proxy rules
├── tailwind.config.ts    # TailwindCSS theme customization
├── tsconfig.json         # TypeScript configuration
└── package.json          # Dependencies and scripts
```

---

## Available Scripts

| Command | Description |
|---------|-------------|
| `bun dev` | Start dev server with hot reload |
| `bun run build` | Build for production |
| `bun run preview` | Preview production build locally |
| `bun run lint` | Run ESLint |

---

## Connecting to the Backend

For the full local development setup (backend + database + frontend), see the [root README](../README.md).

Quick checklist:
1. PostgreSQL is running with the database created and migrations applied
2. Backend is running at `http://localhost:8000` (verify: http://localhost:8000/health)
3. Frontend is running at `http://localhost:8080`
4. Your Google email is added as a test user in the [Google OAuth consent screen](https://console.cloud.google.com/apis/credentials/consent)
