import React, { type ReactNode, FormEvent, useCallback, useEffect, useState } from "react";

const DEFAULT_BACKEND_PORT = import.meta.env.VITE_BACKEND_PORT ?? "5000";

const rewriteForwardedHost = (hostname: string, targetPort: string): string | null => {
  const codespaceMatch = hostname.match(/-(\d+)\.app\.github\.dev$/);
  if (codespaceMatch) {
    return hostname.replace(/-(\d+)\.app\.github\.dev$/, `-${targetPort}.app.github.dev`);
  }
  const gitpodMatch = hostname.match(/^(\d+)-(.+\.gitpod\.io)$/);
  if (gitpodMatch) {
    return `${targetPort}-${gitpodMatch[2]}`;
  }
  return null;
};

const resolveApiBase = () => {
  const envUrl = import.meta.env.VITE_BACKEND_URL as string | undefined;
  if (envUrl) {
    return envUrl.replace(/\/$/, "");
  }
  if (typeof window === "undefined") {
    return `http://localhost:${DEFAULT_BACKEND_PORT}`;
  }
  const { protocol, hostname } = window.location;
  if (hostname === "localhost" || hostname === "127.0.0.1") {
    return `${protocol}//${hostname}:${DEFAULT_BACKEND_PORT}`;
  }
  const forwardedHost = rewriteForwardedHost(hostname, DEFAULT_BACKEND_PORT);
  if (forwardedHost) {
    return `${protocol}//${forwardedHost}`;
  }
  return window.location.origin.replace(/\/$/, "");
};

const DEFAULT_API_BASE = resolveApiBase();

const formatBytes = (value?: number) => {
  const bytes = value ?? 0;
  if (bytes === 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const scaled = bytes / Math.pow(1024, index);
  return `${scaled.toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
};

const StatCard = ({
  title,
  value,
  subtitle,
}: {
  title: string;
  value: string | number;
  subtitle?: string;
}) => (
  <div className="rounded-2xl border border-border bg-card p-6 shadow-sm">
    <p className="text-sm text-muted-foreground">{title}</p>
    <p className="mt-2 text-3xl font-semibold text-foreground">{value}</p>
    {subtitle && <p className="mt-1 text-xs text-muted-foreground">{subtitle}</p>}
  </div>
);

const SectionCard = ({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) => (
  <div className="rounded-2xl border border-border bg-card p-6 shadow-sm">
    <div className="mb-4 flex items-center justify-between">
      <h3 className="text-lg font-semibold">{title}</h3>
    </div>
    {children}
  </div>
);

type AdminStats = {
  total_users: number;
  total_meters: number;
  reminders_enabled: number;
  active_users_24h: number;
  total_storage_bytes: number;
  latest_users: Array<{
    id: number;
    username: string | null;
    telegram_user_id: number;
    created_at: string | null;
  }>;
  latest_meters: Array<{
    id: number;
    name: string;
    number: string;
    owner: string;
    created_at: string | null;
  }>;
  recent_activity: Array<{
    id: number;
    meter_name: string;
    meter_number: string;
    user: string;
    balance: number;
    recorded_at: string | null;
  }>;
};

const EMPTY_STATS: AdminStats = {
  total_users: 0,
  total_meters: 0,
  reminders_enabled: 0,
  active_users_24h: 0,
  total_storage_bytes: 0,
  latest_users: [],
  latest_meters: [],
  recent_activity: [],
};

type StatsResponse = {
  success?: boolean;
  stats?: Partial<AdminStats> | null;
  error?: string;
};

const normalizeStats = (payload?: Partial<AdminStats> | null): AdminStats => ({
  total_users: payload?.total_users ?? EMPTY_STATS.total_users,
  total_meters: payload?.total_meters ?? EMPTY_STATS.total_meters,
  reminders_enabled: payload?.reminders_enabled ?? EMPTY_STATS.reminders_enabled,
  active_users_24h: payload?.active_users_24h ?? EMPTY_STATS.active_users_24h,
  total_storage_bytes: payload?.total_storage_bytes ?? EMPTY_STATS.total_storage_bytes,
  latest_users: payload?.latest_users ?? EMPTY_STATS.latest_users,
  latest_meters: payload?.latest_meters ?? EMPTY_STATS.latest_meters,
  recent_activity: payload?.recent_activity ?? EMPTY_STATS.recent_activity,
});

const formatDate = (value?: string | null) => {
  if (!value) return "—";
  const date = new Date(value);
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
};

const AdminDashboard = () => {
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [broadcastMessage, setBroadcastMessage] = useState("");
  const [broadcastSending, setBroadcastSending] = useState(false);
  const [broadcastStatus, setBroadcastStatus] = useState<string | null>(null);
  const [broadcastError, setBroadcastError] = useState<string | null>(null);

  const fetchStats = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${DEFAULT_API_BASE}/admin/api/stats`);
      if (!response.ok) {
        throw new Error(`Failed to load stats (${response.status})`);
      }
      const payload: StatsResponse = await response.json();
      if (!payload.success && !payload.stats) {
        throw new Error(payload.error ?? "Unexpected dashboard response.");
      }
      setStats(normalizeStats(payload.stats));
    } catch (err) {
      console.error(err);
      setStats(null);
      setError("Unable to reach the admin API. Is the backend running?");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStats();
  }, [fetchStats]);

  const handleBroadcastSubmit = async (event: FormEvent) => {
    event.preventDefault();
    const trimmed = broadcastMessage.trim();
    if (!trimmed) {
      setBroadcastError("Message cannot be empty.");
      return;
    }
    setBroadcastSending(true);
    setBroadcastStatus(null);
    setBroadcastError(null);
    try {
      const response = await fetch(`${DEFAULT_API_BASE}/admin/api/broadcast`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ message: trimmed }),
      });
      if (!response.ok) {
        throw new Error(`Broadcast failed (${response.status})`);
      }
      const payload = await response.json();
      setBroadcastStatus(`Sent to ${payload.sent} of ${payload.requested} users.`);
      setBroadcastMessage("");
    } catch (sendError) {
      console.error(sendError);
      setBroadcastError(sendError instanceof Error ? sendError.message : "Broadcast failed.");
    } finally {
      setBroadcastSending(false);
    }
  };

  if (!stats) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-muted/40 px-4">
        <div className="w-full max-w-md rounded-2xl border border-border bg-card p-8 shadow-xl text-center">
          <h1 className="text-2xl font-semibold">NESCO Admin</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            {loading ? "Loading metrics..." : "Start the backend server to view live stats."}
          </p>
          {error && <p className="mt-4 text-sm text-destructive">{error}</p>}
          <button
            className="mt-6 w-full rounded-lg bg-primary py-2 text-center font-medium text-primary-foreground hover:opacity-90"
            onClick={() => fetchStats()}
            disabled={loading}
          >
            {loading ? "Loading..." : "Retry"}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-muted/40 px-4 py-10">
      <div className="mx-auto flex max-w-6xl flex-col gap-6">
        <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <p className="text-sm uppercase tracking-wide text-muted-foreground">NESCO Admin</p>
            <h1 className="text-3xl font-semibold">Operations Dashboard</h1>
            <p className="text-sm text-muted-foreground">
              Live view of bot adoption, meters, and recent customer activity.
            </p>
          </div>
          <div className="flex items-center gap-3">
            <button
              className="rounded-lg border border-border px-4 py-2 text-sm font-medium hover:bg-background"
              onClick={() => fetchStats()}
              disabled={loading}
            >
              {loading ? "Refreshing..." : "Refresh"}
            </button>
          </div>
        </div>

        <div className="grid gap-6 md:grid-cols-2 xl:grid-cols-4">
          <StatCard title="Total Users" value={stats.total_users} subtitle="Unique Telegram accounts" />
          <StatCard title="Total Meters" value={stats.total_meters} subtitle="Registered prepaid meters" />
          <StatCard title="Reminders Enabled" value={stats.reminders_enabled} subtitle="Daily reminder opt-ins" />
          <StatCard title="Active (24h)" value={stats.active_users_24h} subtitle="Users with recent readings" />
          <StatCard title="Storage Used" value={formatBytes(stats.total_storage_bytes)} subtitle="Database usage" />
        </div>

        <div className="grid gap-6 md:grid-cols-2">
          <SectionCard title="Newest Users">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs uppercase tracking-wide text-muted-foreground">
                    <th className="py-2">User</th>
                    <th className="py-2">Telegram ID</th>
                    <th className="py-2">Joined</th>
                  </tr>
                </thead>
                <tbody>
                  {stats.latest_users.map((user) => (
                    <tr key={user.id} className="border-t border-border">
                      <td className="py-2 font-medium">{user.username ?? `User ${user.telegram_user_id}`}</td>
                      <td className="py-2 text-muted-foreground">{user.telegram_user_id}</td>
                      <td className="py-2 text-muted-foreground">{formatDate(user.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </SectionCard>

          <SectionCard title="Latest Meters">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs uppercase tracking-wide text-muted-foreground">
                    <th className="py-2">Meter</th>
                    <th className="py-2">Owner</th>
                    <th className="py-2">Added</th>
                  </tr>
                </thead>
                <tbody>
                  {stats.latest_meters.map((meter) => (
                    <tr key={meter.id} className="border-t border-border">
                      <td className="py-2 font-medium">
                        {meter.name}
                        <span className="block text-xs text-muted-foreground">#{meter.number}</span>
                      </td>
                      <td className="py-2 text-muted-foreground">{meter.owner}</td>
                      <td className="py-2 text-muted-foreground">{formatDate(meter.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </SectionCard>
        </div>

        <SectionCard title="Recent Balance Activity">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs uppercase tracking-wide text-muted-foreground">
                  <th className="py-2">Meter</th>
                  <th className="py-2">User</th>
                  <th className="py-2">Balance</th>
                  <th className="py-2">Recorded</th>
                </tr>
              </thead>
              <tbody>
                {stats.recent_activity.map((entry) => (
                  <tr key={entry.id} className="border-t border-border">
                    <td className="py-2 font-medium">
                      {entry.meter_name}
                      <span className="block text-xs text-muted-foreground">#{entry.meter_number}</span>
                    </td>
                    <td className="py-2 text-muted-foreground">{entry.user}</td>
                    <td className="py-2 font-semibold text-foreground">{entry.balance.toFixed(2)} BDT</td>
                    <td className="py-2 text-muted-foreground">{formatDate(entry.recorded_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </SectionCard>

        <SectionCard title="Message Portal">
          <form className="space-y-4" onSubmit={handleBroadcastSubmit}>
            <textarea
              className="min-h-[120px] w-full rounded-lg border border-border bg-background px-3 py-2"
              placeholder="Write an announcement to send to all bot users."
              value={broadcastMessage}
              onChange={(event) => setBroadcastMessage(event.target.value)}
            />
            {broadcastError && <p className="text-sm text-destructive">{broadcastError}</p>}
            {broadcastStatus && <p className="text-sm text-emerald-600">{broadcastStatus}</p>}
            <button
              type="submit"
              className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90"
              disabled={broadcastSending}
            >
              {broadcastSending ? "Sending..." : "Send to all users"}
            </button>
          </form>
        </SectionCard>
      </div>
    </div>
  );
};

export default AdminDashboard;
