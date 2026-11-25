import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, NavLink, Route, Routes } from "react-router-dom";
import "./index.css";
import Dashboard from "./pages/Dashboard";
import Topics from "./pages/Topics";
import Pipeline from "./pages/Pipeline";
import Library from "./pages/Library";
import VideoDetail from "./pages/VideoDetail";
import Calendar from "./pages/Calendar";
import Analytics from "./pages/Analytics";
import Settings from "./pages/Settings";
import MemeStudio from "./pages/MemeStudio";
import Clips from "./pages/Clips";
import Login from "./pages/Login";
import { useEffect, useState } from "react";
import { api } from "./api";

const NAV = [
  ["/", "Overview"], ["/topics", "Idea Generator"], ["/memes", "Meme Studio"], ["/pipeline", "Video Production"],
  ["/library", "Video Library"], ["/clips", "My Clips"], ["/calendar", "Content Calendar"], ["/analytics", "Analytics"],
  ["/settings", "Settings"],
];

function App() {
  const [auth, setAuth] = useState<"checking" | "ok" | "login">("checking");
  useEffect(() => {
    api("/api/dashboard").then(() => setAuth("ok")).catch((e) => setAuth(String(e.message).includes("unauthorized") || String(e.message) === "401" ? "login" : "ok"));
  }, []);
  if (auth === "checking") return null;
  if (auth === "login") return <Login onDone={() => setAuth("ok")} />;
  return (
    <BrowserRouter>
      <div className="flex min-h-screen">
        <aside className="sticky top-0 h-screen w-60 shrink-0 border-r border-stone-800 bg-stone-950 p-5">
          <div className="mb-8">
            <div className="font-display text-2xl tracking-wide text-gold">HOOPS SHORTS</div>
            <div className="text-xs text-stone-500">Basketball meme studio</div>
          </div>
          <nav className="space-y-1">
            {NAV.map(([to, label]) => (
              <NavLink key={to} to={to} end={to === "/"}
                className={({ isActive }) => `block rounded-lg px-3 py-2 text-sm ${isActive ? "bg-stone-800 text-parchment" : "text-stone-400 hover:bg-stone-900 hover:text-stone-200"}`}>
                {label}
              </NavLink>
            ))}
          </nav>
        </aside>
        <main className="min-w-0 flex-1 p-8">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/topics" element={<Topics />} />
            <Route path="/memes" element={<MemeStudio />} />
            <Route path="/clips" element={<Clips />} />
            <Route path="/pipeline" element={<Pipeline />} />
            <Route path="/library" element={<Library />} />
            <Route path="/videos/:id" element={<VideoDetail />} />
            <Route path="/calendar" element={<Calendar />} />
            <Route path="/analytics" element={<Analytics />} />
            <Route path="/settings" element={<Settings />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(<React.StrictMode><App /></React.StrictMode>);
