import { createRoot } from "react-dom/client";
import { setAdminSecret } from "@workspace/api-client-react";
import App from "./App";
import "./index.css";

// Configure admin secret for Node write endpoints (mode switch, scheduler, cycle, positions).
// Set VITE_ADMIN_SECRET in Replit Secrets to the same value as MT5_BRIDGE_SECRET.
//
// SECURITY NOTE: VITE_* env vars are embedded in the browser bundle at build time.
// This is acceptable only when the dashboard URL is PRIVATE (personal use, not public).
// If you expose the dashboard on a public URL, add server-side session auth (e.g. Clerk)
// and remove VITE_ADMIN_SECRET — the secret would otherwise be extractable from JS.
const adminSecret = import.meta.env.VITE_ADMIN_SECRET as string | undefined;
if (adminSecret) {
  setAdminSecret(adminSecret);
}

createRoot(document.getElementById("root")!).render(<App />);
