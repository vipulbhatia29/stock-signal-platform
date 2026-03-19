import { createContext, useContext, useState, type ReactNode } from "react";

interface ChatContextType {
  chatOpen: boolean;
  setChatOpen: (open: boolean) => void;
  chatMode: "push";
  setChatMode: (mode: "push") => void;
  toggleChat: () => void;
}

const ChatContext = createContext<ChatContextType | null>(null);

export function ChatProvider({ children }: { children: ReactNode }) {
  const [chatOpen, setChatOpen] = useState(false);
  const [chatMode, setChatMode] = useState<"push">("push");

  return (
    <ChatContext.Provider value={{
      chatOpen,
      setChatOpen,
      chatMode,
      setChatMode,
      toggleChat: () => setChatOpen((o) => !o),
    }}>
      {children}
    </ChatContext.Provider>
  );
}

export function useChat() {
  const ctx = useContext(ChatContext);
  if (!ctx) throw new Error("useChat must be used within ChatProvider");
  return ctx;
}
