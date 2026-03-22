const CLIENT_ID = import.meta.env.PUBLIC_DISCORD_CLIENT_ID;
const SITE_URL = import.meta.env.PUBLIC_SITE_URL;

const REDIRECT_PATH = "/callback";
const TOKEN_KEY = "discord_token";
const EXPIRY_KEY = "discord_token_expiry";

export function getToken(): string | null {
  const token = localStorage.getItem(TOKEN_KEY);
  const expiry = localStorage.getItem(EXPIRY_KEY);
  if (!token || !expiry) return null;
  if (Date.now() > parseInt(expiry, 10)) {
    clearToken();
    return null;
  }
  return token;
}

export function setToken(token: string, expiresIn: number): void {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(EXPIRY_KEY, String(Date.now() + expiresIn * 1000));
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(EXPIRY_KEY);
}

export function login(): void {
  const redirectUri = `${SITE_URL}${REDIRECT_PATH}`;
  const params = new URLSearchParams({
    client_id: CLIENT_ID,
    redirect_uri: redirectUri,
    response_type: "token",
    scope: "identify guilds",
  });
  window.location.href = `https://discord.com/api/oauth2/authorize?${params}`;
}

export function logout(): void {
  clearToken();
  window.location.href = "/";
}
