import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, type UserView } from "./api";

interface Auth {
  user: UserView | null;
  loading: boolean;
  signIn: (user: UserView) => void;
  signOut: () => Promise<void>;
}

const Context = createContext<Auth | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserView | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.me().then(
      (found) => {
        setUser(found);
        setLoading(false);
      },
      () => setLoading(false),
    );
    // Any request answered with 401 means the session ended; show the sign-in screen.
    const ended = () => setUser(null);
    window.addEventListener("pramana-signed-out", ended);
    return () => window.removeEventListener("pramana-signed-out", ended);
  }, []);

  const signOut = useCallback(async () => {
    await api.logout();
    setUser(null);
    window.location.hash = "#/";
  }, []);

  return (
    <Context.Provider value={{ user, loading, signIn: setUser, signOut }}>
      {children}
    </Context.Provider>
  );
}

export function useAuth(): Auth {
  const value = useContext(Context);
  if (!value) throw new Error("AuthProvider is missing");
  return value;
}
