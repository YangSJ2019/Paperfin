import { Link, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { Film, Library as LibraryIcon } from "lucide-react";

import Library from "./pages/Library";
import PaperDetail from "./pages/PaperDetail";
import { clsx } from "./lib/utils";

function NavLink({ to, icon, children }: { to: string; icon: React.ReactNode; children: React.ReactNode }) {
  const { pathname } = useLocation();
  const active = pathname === to;
  return (
    <Link
      to={to}
      className={clsx(
        "flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition",
        active
          ? "bg-white/10 text-white"
          : "text-slate-400 hover:bg-white/5 hover:text-white"
      )}
    >
      {icon}
      {children}
    </Link>
  );
}

export default function App() {
  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-10 border-b border-white/5 bg-ink-900/80 backdrop-blur">
        <div className="mx-auto flex max-w-[1600px] items-center justify-between px-6 py-3">
          <div className="flex items-center gap-3">
            <Film className="h-6 w-6 text-accent-soft" />
            <span className="text-lg font-semibold tracking-tight">Paperfin</span>
          </div>
          <nav className="flex items-center gap-2">
            <NavLink to="/" icon={<LibraryIcon className="h-4 w-4" />}>
              Library
            </NavLink>
          </nav>
        </div>
      </header>

      <main className="mx-auto max-w-[1600px] px-6 py-8">
        <Routes>
          <Route path="/" element={<Library />} />
          <Route path="/papers/:id" element={<PaperDetail />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}
