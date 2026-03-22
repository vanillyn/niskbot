const BASE = import.meta.env.PUBLIC_API_URL;

export interface Guild {
  id: string;
  name: string;
  icon: string | null;
  in_server: boolean;
}

function authHeaders(): HeadersInit {
  const token = localStorage.getItem("discord_token");
  return token
    ? { authorization: `Bearer ${token}`, "content-type": "application/json" }
    : { "content-type": "application/json" };
}

async function req<T>(path: string, options?: RequestInit): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, {
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
