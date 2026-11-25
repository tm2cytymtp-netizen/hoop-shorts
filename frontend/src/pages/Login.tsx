import { useState } from "react";
import { post, setToken } from "../api";

export default function Login({ onDone }: { onDone: () => void }) {
  const [pw, setPw] = useState("");
  const [err, setErr] = useState("");
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const r = await post("/api/login", { password: pw });
      setToken(r.token);
      onDone();
    } catch (e: any) {
      setErr(e.message);
    }
  };
  return (
    <div className="flex min-h-screen items-center justify-center">
      <form onSubmit={submit} className="card w-80 space-y-3">
        <div className="font-display text-2xl text-gold">HOOPS SHORTS</div>
        <input className="input" type="password" placeholder="Dashboard password" value={pw} onChange={(e) => setPw(e.target.value)} autoFocus />
        {err && <div className="text-sm text-red-400">{err}</div>}
        <button className="btn-primary w-full justify-center">Sign in</button>
      </form>
    </div>
  );
}
