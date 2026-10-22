# League chatbot

Chat bubble on fantrax.whohashim.com that answers questions about the league.

* `docs/chat/chat.js` and `docs/chat/chat.css`: the bubble, loaded by `scripts/template.html`.
* `chatbot/worker/worker.js`: Cloudflare Worker that holds the Anthropic API key, reads `/data.json`, and asks Claude (Haiku) using small lookup tools.
* Data freshness comes for free: the Worker reads the same `data.json` the refresh workflow publishes, cached for 5 minutes.

Deploy: `cd chatbot/worker && npx wrangler deploy`, then `npx wrangler secret put ANTHROPIC_API_KEY`. Put the resulting `*.workers.dev` address in `WORKER_URL` at the top of `docs/chat/chat.js`.

To change what the bot says, edit `SYSTEM_PROMPT` in the Worker. To change the bubble's name, greeting, or suggested questions, edit the top of `chat.js`.
