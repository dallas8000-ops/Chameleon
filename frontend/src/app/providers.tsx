import React, { useEffect } from "react";

import { useSessionStore } from "../lib/auth/session-store";

export default function Providers({ children }: { children: React.ReactNode }) {
  const ensureSession = useSessionStore((state) => state.ensureSession);

  useEffect(() => {
    // Restores an existing Django session on load; failures are kept in the store and shown by
    // pages that need the session.
    void ensureSession();
  }, [ensureSession]);

  return <>{children}</>;
}
