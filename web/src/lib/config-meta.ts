export type FieldType =
  | "toggle"
  | "text"
  | "number"
  | "channel"
  | "role"
  | "roles"
  | "duration"
  | "textarea";

export interface ConfigField {
  key: string;
  label: string;
  hint: string;
  default: string | null;
  type: FieldType;
}

export interface ConfigCategory {
  key: string;
  label: string;
  icon: string;
  fields: ConfigField[];
}

function infer(hint: string): FieldType {
  if (hint === "true or false") return "toggle";
  if (hint.includes("channel id") && !hint.includes("comma")) return "channel";
  if (/\brole id\b/.test(hint) && !hint.includes("comma")) return "role";
  if (
    hint.includes("comma-separated role ids") ||
    hint.includes("comma-separated channel ids")
  )
    return "roles";
  if (hint.includes("integer") || hint.includes("0-100")) return "number";
  if (/e\.g\.\s*\d+[smhd]/.test(hint)) return "duration";
  if (
    hint.includes("json array") ||
    hint.includes("text — {") ||
    hint.includes("comma-separated") ||
    hint.length > 60
  )
    return "textarea";
  return "text";
}

function f(
  key: string,
  label: string,
  hint: string,
  def: string | null = null,
): ConfigField {
  return { key, label, hint, default: def, type: infer(hint) };
}

export const CONFIG_CATEGORIES: ConfigCategory[] = [
  {
    key: "server",
    label: "server",
    icon: "settings",
    fields: [
      f("server.name", "server name", "text"),
      f("server.language", "language", "language code — en, fr, de...", "en"),
      f("server.announcements.channel", "announcements channel", "channel id"),
      f(
        "server.announcements.role",
        "announcement ping roles",
        "comma-separated role ids",
      ),
      f("starboard.channel", "starboard channel", "channel id"),
      f(
        "starboard.react",
        "starboard emoji",
        "emoji char or custom emoji name",
        "star",
      ),
      f("alias", "allow aliases", "true or false", "true"),
      f("alias.role", "alias manager roles", "comma-separated role ids"),
      f("server.alias.prefix", "alias prefix", "e.g. ! or .", "!"),
    ],
  },
  {
    key: "suggestions",
    label: "suggestions",
    icon: "forum",
    fields: [
      f("server.suggestions.channel", "suggestions channel", "channel id"),
      f("server.suggestions.vote.up", "upvote label", "text", "upvote"),
      f("server.suggestions.vote.down", "downvote label", "text", "downvote"),
      f("server.suggestions.vote.cancel", "cancel label", "text", "cancel"),
      f(
        "server.suggestions.threshold.approve",
        "approve threshold %",
        "integer 0-100",
        "70",
      ),
      f(
        "server.suggestions.threshold.disapprove",
        "disapprove threshold %",
        "integer 0-100",
        "30",
      ),
      f(
        "server.suggestions.timeout",
        "suggestion timeout",
        "e.g. 24h, 7d",
        "24h",
      ),
      f(
        "server.suggestions.vote.roles",
        "roles that can vote",
        "comma-separated role ids",
      ),
    ],
  },
  {
    key: "moderation",
    label: "moderation",
    icon: "gavel",
    fields: [
      f(
        "moderation.require_confirm",
        "require confirmation",
        "true or false",
        "true",
      ),
      f("moderation.mod", "moderator role", "role id"),
      f("moderation.admin", "admin role", "role id"),
      f("moderation.trial_mod", "trial mod role", "role id"),
      f(
        "moderation.dangerous_permission",
        "bypass-all user ids",
        "comma-separated user ids",
      ),
      f(
        "moderation.kick.default_reason",
        "kick default reason",
        "text — {user}",
        "{user} was kicked",
      ),
      f(
        "moderation.ban.default_reason",
        "ban default reason",
        "text — {user}",
        "{user} was banned",
      ),
      f(
        "moderation.mute.default_reason",
        "mute default reason",
        "text — {user}",
        "{user} was muted",
      ),
      f(
        "moderation.warn.default_reason",
        "warn default reason",
        "text — {user}",
        "{user} was warned",
      ),
      f(
        "moderation.ban.default_duration",
        "default ban length",
        "e.g. 7d, 1h, forever",
        "forever",
      ),
      f(
        "moderation.mute.default_duration",
        "default mute length",
        "e.g. 7d, 1h, forever",
        "forever",
      ),
      f(
        "moderation.auto.bypass.role",
        "automod bypass roles",
        "comma-separated role ids",
      ),
      f(
        "moderation.auto.bypass.permission",
        "automod bypass perms",
        "comma-separated permissions",
        "administrator",
      ),
    ],
  },
  {
    key: "tickets",
    label: "tickets",
    icon: "confirmation_number",
    fields: [
      f(
        "moderation.tickets.category",
        "tickets category",
        "category channel id",
      ),
      f("moderation.tickets.message", "ticket open message", "text"),
      f(
        "moderation.tickets.voice",
        "allow voice tickets",
        "true or false",
        "false",
      ),
      f(
        "moderation.tickets.creator_permissions",
        "creator can manage",
        "true or false",
        "true",
      ),
      f(
        "moderation.tickets.role",
        "who can open tickets",
        "comma-separated role ids",
      ),
      f("moderation.tickets.admin", "ticket admin role", "role id"),
      f(
        "moderation.tickets.archive",
        "enable archival",
        "true or false",
        "false",
      ),
      f(
        "moderation.tickets.archive.category",
        "archive category",
        "category channel id",
      ),
      f("moderation.tickets.archive.role", "who can archive", "role id"),
      f(
        "moderation.tickets.archive.auto",
        "auto-archive after",
        "e.g. 24h, 7d",
      ),
      f("moderation.mute.role", "mute role", "role id"),
      f("moderation.mute.channel", "mute channel", "channel id"),
    ],
  },
  {
    key: "logging",
    label: "logging",
    icon: "receipt_long",
    fields: [
      f("log.moderation", "log mod actions", "true or false", "false"),
      f("log.moderation.channel", "mod log channel", "channel id"),
      f(
        "log.moderation.message.show_moderator",
        "show moderator in logs",
        "true or false",
        "true",
      ),
      f(
        "log.moderation.message.show_reason",
        "show reason in logs",
        "true or false",
        "true",
      ),
      f(
        "log.moderation.message.kick",
        "kick log message",
        "text — {user}, {reason}, {infraction_id}",
        "[{infraction_id}] {user} was kicked",
      ),
      f(
        "log.moderation.message.ban",
        "ban log message",
        "text — {user}, {reason}, {infraction_id}",
        "[{infraction_id}] {user} was banned",
      ),
      f(
        "log.moderation.message.mute",
        "mute log message",
        "text — {user}, {reason}, {infraction_id}",
        "[{infraction_id}] {user} was muted",
      ),
      f(
        "log.moderation.message.warn",
        "warn log message",
        "text — {user}, {reason}, {infraction_id}",
        "[{infraction_id}] {user} was warned",
      ),
      f(
        "log.moderation.message.slowmode",
        "slowmode log message",
        "text — {user}, {reason}, {infraction_id}",
        "[{infraction_id}] slowmode set by {user}",
      ),
    ],
  },
  {
    key: "alerts",
    label: "alerts",
    icon: "notifications",
    fields: [
      f("log.alerts", "log server events", "true or false", "false"),
      f("log.alerts.channel", "default alerts channel", "channel id"),
      f("log.alerts.joins", "log member joins", "true or false", "true"),
      f("log.alerts.joins.channel", "join alert channel", "channel id"),
      f("log.alerts.joins.message", "join message", "text — {user}, {server}"),
      f("log.alerts.leaves", "log member leaves", "true or false", "true"),
      f("log.alerts.leaves.channel", "leave alert channel", "channel id"),
      f(
        "log.alerts.leaves.message",
        "leave message",
        "text — {user}, {server}",
      ),
      f("log.alerts.twitch", "enable twitch alerts", "true or false", "false"),
      f(
        "log.alerts.youtube",
        "enable youtube alerts",
        "true or false",
        "false",
      ),
      f("log.alerts.free_games", "free game alerts", "true or false", "false"),
      f("log.alerts.free_games.channel", "free games channel", "channel id"),
      f("log.alerts.free_games.message", "free games message", "text"),
    ],
  },
  {
    key: "economy",
    label: "economy",
    icon: "payments",
    fields: [
      f("economy", "enable economy", "true or false", "false"),
      f("economy.currency.name", "currency name", "e.g. coins", "coins"),
      f("economy.currency.symbol", "currency symbol", "e.g. $", "$"),
      f(
        "economy.currency.fractional",
        "fractional unit",
        "e.g. cents",
        "cents",
      ),
      f("economy.pay", "allow payments", "true or false", "true"),
      f("economy.casino", "enable casino", "true or false", "false"),
      f("economy.drop", "enable random drops", "true or false", "false"),
      f(
        "economy.drop.channels",
        "drop channels",
        "comma-separated channel ids",
      ),
      f("economy.shop", "enable shop", "true or false", "false"),
      f("economy.shop.channel", "permanent shop channel", "channel id"),
    ],
  },
  {
    key: "economy-roles",
    label: "economy roles",
    icon: "group",
    fields: [
      f("economy.role", "roles that earn money", "comma-separated role ids"),
      f(
        "economy.permission",
        "perms to earn money",
        "comma-separated perms",
        "send_messages",
      ),
      f("economy.pay.role", "roles that can pay", "comma-separated role ids"),
      f("economy.casino.role", "roles for casino", "comma-separated role ids"),
      f(
        "economy.drop.role",
        "roles to claim drops",
        "comma-separated role ids",
      ),
      f("economy.shop.role", "roles to use shop", "comma-separated role ids"),
    ],
  },
  {
    key: "cookies",
    label: "cookies",
    icon: "cookie",
    fields: [
      f("economy.currency.cookies", "enable cookies", "true or false", "false"),
      f(
        "economy.currency.cookies.name",
        "cookie item name",
        "e.g. cookie, star, gem",
        "cookie",
      ),
      f(
        "economy.currency.cookies.symbol",
        "cookie symbol",
        "short string e.g. c",
        "c",
      ),
      f(
        "economy.currency.cookies.value",
        "sell value per cookie",
        "integer amount of currency",
      ),
      f(
        "economy.currency.cookies.messages",
        "thank-you phrases",
        'json array e.g. ["thank you", "ty"]',
      ),
    ],
  },
  {
    key: "xp-roles",
    label: "xp & roles",
    icon: "stars",
    fields: [
      f("xp.role", "roles that earn xp", "comma-separated role ids"),
      f(
        "xp.achievements.role",
        "roles for achievements",
        "comma-separated role ids",
      ),
      f(
        "xp.cookies.get.role",
        "roles that get cookies",
        "comma-separated role ids",
      ),
      f(
        "xp.cookies.give.role",
        "roles that give cookies",
        "comma-separated role ids",
      ),
      f("starboard.role", "roles on starboard", "comma-separated role ids"),
      f(
        "starboard.add.role",
        "roles that add to starboard",
        "comma-separated role ids",
      ),
    ],
  },
];
