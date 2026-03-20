import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ChatProvider } from "@/contexts/ChatContext";
import { StockRefreshProvider } from "@/contexts/StockRefreshContext";
import { ShellLayout } from "@/components/shell/ShellLayout";
import Dashboard from "@/pages/Dashboard";
import Screener from "@/pages/Screener";
import StockDetail from "@/pages/StockDetail";
import Portfolio from "@/pages/Portfolio";
import Sectors from "@/pages/Sectors";
import { Login, Register } from "@/pages/Auth";
import NotFound from "@/pages/NotFound";

const queryClient = new QueryClient();

const App = () => (
  <QueryClientProvider client={queryClient}>
    <TooltipProvider>
      <ChatProvider>
      <StockRefreshProvider>
        <Toaster />
        <Sonner />
        <BrowserRouter>
          <Routes>
            <Route element={<ShellLayout />}>
              <Route path="/" element={<Dashboard />} />
              <Route path="/screener" element={<Screener />} />
              <Route path="/stocks/:ticker" element={<StockDetail />} />
              <Route path="/portfolio" element={<Portfolio />} />
              <Route path="/sectors" element={<Sectors />} />
            </Route>
            <Route path="/login" element={<Login />} />
            <Route path="/register" element={<Register />} />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </BrowserRouter>
      </StockRefreshProvider>
      </ChatProvider>
    </TooltipProvider>
  </QueryClientProvider>
);

export default App;
