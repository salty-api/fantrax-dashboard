// Triggers the "Refresh league data" GitHub Actions workflow on a Cloudflare cron,
// because GitHub's own scheduled workflows are best-effort and often skipped.
const REPO = "salty-api/fantrax-dashboard";
const WORKFLOW = "refresh.yml";

async function dispatch(env) {
  const res = await fetch(
    `https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW}/dispatches`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.GITHUB_TOKEN}`,
        Accept: "application/vnd.github+json",
        "User-Agent": "fantrax-cron",
        "X-GitHub-Api-Version": "2022-11-28",
      },
      body: JSON.stringify({ ref: "main" }),
    }
  );
  if (res.status !== 204) {
    throw new Error(`dispatch failed: ${res.status} ${await res.text()}`);
  }
  return res.status;
}

export default {
  async scheduled(event, env, ctx) {
    ctx.waitUntil(dispatch(env));
  },
  // No public trigger: the URL must not let strangers start runs.
  async fetch() {
    return new Response("fantrax-cron\n");
  },
};
