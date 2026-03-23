export function getApiBase(): string {
  if (typeof localStorage !== "undefined") {
    const stored = localStorage.getItem("api_base_url");
    if (stored) return stored.replace(/\/\$/, "");
  }
  return (import.meta.env.PUBLIC_API_URL ?? "").replace(/\/\$/, "");
}

export function setApiBase(url: string): void {
  localStorage.setItem("api_base_url", url.replace(/\/\$/, ""));
}

export interface Guild {
  id: string;
  name: string;
  icon: string | null;
  in_server: boolean;
}

export interface Channel {
  id: string;
  name: string;
  category: string | null;
}

export interface Role {
  id: string;
  name: string;
  color: string;
}

export interface Resource {
  name: string;
  content: string;
  created_at: number;
}

export interface ContainerItem {
  type: "text" | "sep" | "gallery";
  content?: string;
  large?: boolean;
  items?: { url: string; description?: string }[];
}

export interface Container {
  name: string;
  items: ContainerItem[];
  accent_color: number | null;
}

export interface TwitchAlert {
  streamer: string;
  channel_id: string;
  message: string | null;
}

export interface YoutubeAlert {
  channel_id: string;
  discord_channel_id: string;
  message: string | null;
}

function authHeaders(): HeadersInit {
  const token = localStorage.getItem("discord_token");
  return token
    ? { authorization: `Bearer ${token}`, "content-type": "application/json" }
    : { "content-type": "application/json" };
}

async function req<T>(path: string, options?: RequestInit): Promise<T> {
  const resp = await fetch(`${getApiBase()}${path}`, {
    ...options,
    headers: { ...authHeaders(), ...(options?.headers ?? {}) },
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ error: resp.statusText }));
    throw new Error((err as { error: string }).error ?? resp.statusText);
  }
  return resp.json() as Promise<T>;
}

export async function getGuilds(): Promise<Guild[]> {
  return req<Guild[]>("/api/guilds");
}

export async function getConfig(
  guildId: string,
): Promise<Record<string, string>> {
  return req<Record<string, string>>(`/api/guild/${guildId}/config`);
}

export async function setConfig(
  guildId: string,
  data: Record<string, string | null>,
): Promise<void> {
  await req<{ ok: boolean }>(`/api/guild/${guildId}/config`, {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function getChannels(guildId: string): Promise<Channel[]> {
  return req<Channel[]>(`/api/guild/${guildId}/channels`);
}

export async function getRoles(guildId: string): Promise<Role[]> {
  return req<Role[]>(`/api/guild/${guildId}/roles`);
}

export async function getResources(guildId: string): Promise<Resource[]> {
  return req<Resource[]>(`/api/guild/${guildId}/resources`);
}

export async function saveResource(
  guildId: string,
  name: string,
  content: string,
): Promise<{ ok: boolean; name: string }> {
  return req<{ ok: boolean; name: string }>(`/api/guild/${guildId}/resources`, {
    method: "POST",
    body: JSON.stringify({ name, content }),
  });
}

export async function deleteResource(
  guildId: string,
  name: string,
): Promise<void> {
  await req<{ ok: boolean }>(
    `/api/guild/${guildId}/resources/${encodeURIComponent(name)}`,
    {
      method: "DELETE",
    },
  );
}

export async function getContainers(guildId: string): Promise<Container[]> {
  return req<Container[]>(`/api/guild/${guildId}/containers`);
}

export async function saveContainer(
  guildId: string,
  name: string,
  items: ContainerItem[],
  accentColor: number | null,
): Promise<{ ok: boolean; name: string }> {
  return req<{ ok: boolean; name: string }>(
    `/api/guild/${guildId}/containers`,
    {
      method: "POST",
      body: JSON.stringify({ name, items, accent_color: accentColor }),
    },
  );
}

export async function deleteContainer(
  guildId: string,
  name: string,
): Promise<void> {
  await req<{ ok: boolean }>(
    `/api/guild/${guildId}/containers/${encodeURIComponent(name)}`,
    {
      method: "DELETE",
    },
  );
}

export async function getTwitchAlerts(guildId: string): Promise<TwitchAlert[]> {
  return req<TwitchAlert[]>(`/api/guild/${guildId}/alerts/twitch`);
}

export async function addTwitchAlert(
  guildId: string,
  streamer: string,
  channelId: string,
  message: string | null,
): Promise<void> {
  await req<{ ok: boolean }>(`/api/guild/${guildId}/alerts/twitch`, {
    method: "POST",
    body: JSON.stringify({ streamer, channel_id: channelId, message }),
  });
}

export async function removeTwitchAlert(
  guildId: string,
  streamer: string,
): Promise<void> {
  await req<{ ok: boolean }>(
    `/api/guild/${guildId}/alerts/twitch/${encodeURIComponent(streamer)}`,
    { method: "DELETE" },
  );
}

export async function getYoutubeAlerts(
  guildId: string,
): Promise<YoutubeAlert[]> {
  return req<YoutubeAlert[]>(`/api/guild/${guildId}/alerts/youtube`);
}

export async function addYoutubeAlert(
  guildId: string,
  channelId: string,
  discordChannelId: string,
  message: string | null,
): Promise<void> {
  await req<{ ok: boolean }>(`/api/guild/${guildId}/alerts/youtube`, {
    method: "POST",
    body: JSON.stringify({
      channel_id: channelId,
      discord_channel_id: discordChannelId,
      message,
    }),
  });
}

export async function removeYoutubeAlert(
  guildId: string,
  channelId: string,
): Promise<void> {
  await req<{ ok: boolean }>(
    `/api/guild/${guildId}/alerts/youtube/${encodeURIComponent(channelId)}`,
    { method: "DELETE" },
  );
}
