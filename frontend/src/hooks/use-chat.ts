import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { get, del } from "@/lib/api";
import type { ChatSession, ChatMessage } from "@/types/api";

export function useChatSessions() {
  return useQuery<ChatSession[]>({
    queryKey: ["chat", "sessions"],
    queryFn: () => get<ChatSession[]>("/chat/sessions"),
    staleTime: 5 * 60 * 1000,
  });
}

export function useChatMessages(sessionId: string | null) {
  return useQuery<ChatMessage[]>({
    queryKey: ["chat", "messages", sessionId],
    queryFn: () => get<ChatMessage[]>(`/chat/sessions/${sessionId}/messages`),
    enabled: !!sessionId,
    staleTime: Infinity,
  });
}

export function useDeleteSession() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (sessionId: string) => del(`/chat/sessions/${sessionId}`),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["chat", "sessions"] }),
  });
}
