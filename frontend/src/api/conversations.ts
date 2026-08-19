import client from "./client";

export interface ConversationMessage {
  id: string;
  role: string;
  content: string;
  tool_name: string | null;
  sort_order: number;
  created_at: string;
}

export interface Conversation {
  id: string;
  title: string;
  work_id: string | null;
  persona: string;
  created_at: string;
  updated_at: string;
  messages: ConversationMessage[];
}

export interface ConversationListItem {
  id: string;
  title: string;
  work_id: string | null;
  persona: string;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export async function listConversations(
  workId?: string
): Promise<ConversationListItem[]> {
  const params = workId ? { work_id: workId } : {};
  const { data } = await client.get<ConversationListItem[]>(
    "/conversations",
    { params }
  );
  return data;
}

export async function getConversation(id: string): Promise<Conversation> {
  const { data } = await client.get<Conversation>(`/conversations/${id}`);
  return data;
}

export async function createConversation(payload: {
  work_id?: string;
  persona?: string;
  title?: string;
}): Promise<Conversation> {
  const { data } = await client.post<Conversation>("/conversations", payload);
  return data;
}

export async function updateConversation(
  id: string,
  payload: { title?: string; persona?: string }
): Promise<Conversation> {
  const { data } = await client.patch<Conversation>(
    `/conversations/${id}`,
    payload
  );
  return data;
}

export async function deleteConversation(id: string): Promise<void> {
  await client.delete(`/conversations/${id}`);
}
