import { Outlet } from "react-router-dom";
import { SidebarNav } from "./SidebarNav";
import { Topbar } from "./Topbar";
import { ChatPanel } from "./ChatPanel";
import { useChat } from "@/contexts/ChatContext";


export function ShellLayout() {
  const { chatOpen, setChatOpen } = useChat();

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      <SidebarNav />
      <div className="flex flex-1 flex-col overflow-hidden">
        <Topbar />
        <main className="flex-1 overflow-y-auto scrollbar-thin transition-all duration-300">
          <Outlet />
        </main>
      </div>
      <ChatPanel open={chatOpen} onClose={() => setChatOpen(false)} />
    </div>
  );
}
