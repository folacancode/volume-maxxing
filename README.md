# volume-maxxing
Chasing volumes
# Meme Buy-Volume Spike Scanner

Watches Solana tokens for sudden buy-volume spikes across 15-minute windows
(your "sell $4k / buy $12k / buy $100k / buy $300k" pattern) and pushes an
alert to Telegram when it fires.

## How it works

1. **Discovery**: combines your fixed watchlist with Birdeye's meme-token
   feed (`/defi/v3/token/meme/list`, sorted by 24h volume) — both available
   on the free "Standard" API tier.
2. **Trade fetch**: pulls recent swaps per token via `/defi/txs/token`.
3. **Bucketing**: groups trades into four trailing 15-min windows and sums
   buy-side USD volume per window (done locally — Birdeye's free tier
   doesn't expose a pre-aggregated buy/sell-volume endpoint, so this is
   built from raw trades).
4. **Spike check**: if the newest bucket's buy volume is `SPIKE_MULTIPLIER`x
   the prior bucket (default 3x) and above `MIN_BUY_VOLUME_USD` (default
   $5,000), it fires — with a 1-hour cooldown per token so you're not
   spammed on every run while a token is still ripping.
5. **Alert**: sent to your Telegram chat via bot API, with a DexScreener
   link.

## Setup

1. Push this folder to your GitHub repo.
2. In repo **Settings → Secrets and variables → Actions → Secrets**, add:
   - `BIRDEYE_API_KEY` — your Birdeye key
   - `TELEGRAM_BOT_TOKEN` — from @BotFather
   - `TELEGRAM_CHAT_ID` — the chat/channel the bot should post into
3. In **Settings → Secrets and variables → Actions → Variables** (optional,
   has defaults if you skip this):
   - `WATCHLIST` — comma-separated token mint addresses you always want
     scanned, e.g. `Es9vMFrz...,DezXAZ8z...`
   - `MAX_DISCOVERY_TOKENS` — how many extra tokens to pull from the meme
     feed each run (default `6`)
   - `SPIKE_MULTIPLIER` — default `3`
   - `MIN_BUY_VOLUME_USD` — default `5000`
4. Commit an empty `state.json` containing `{"alerted": {}}` so the first
   run has something to read/write.
5. The workflow runs every 15 min automatically, or trigger it manually from
   the **Actions** tab (`workflow_dispatch`).

## Read this before you turn it on: the free-tier math

Birdeye's free ("Standard") plan gives you **30,000 compute units/month**
and a hard **1 request/second** rate limit. This is the actual constraint,
not a formality:

- Every run = 1 discovery call + 1 call per candidate token.
- At 15-min intervals that's **2,880 runs/month**. Even at just 6 candidate
  tokens per run, that's ~20,000 API calls/month before you count retries.
- Compute-unit cost per call is dynamic (Birdeye doesn't publish a flat
  per-endpoint number), so you could exhaust your 30k CU budget in days if
  you scan broadly at 15-min resolution.

**Practical choices, pick one:**
- Small watchlist (5-8 tokens you already care about) scanned every 15 min
  — cheapest, most sustainable on free tier.
- Broader discovery scan (`MAX_DISCOVERY_TOKENS` higher) but drop the cron
  to hourly (`0 * * * *` in the workflow file).
- Watch your usage in the Birdeye dashboard the first day or two and tune
  from there — don't guess, check the actual numbers.

If you outgrow this, Birdeye's paid tiers unlock `/defi/v3/token/trade-data`
(pre-aggregated buy/sell volume — no need to bucket raw trades yourself)
and much higher rate limits.

## Known rough edges (verify before trusting the output)

- **Field names**: `blockUnixTime`, `side`, `volumeUSD` in `bucket_buy_volume()`
  are based on Birdeye's documented schema, but I haven't run this against a
  live response. Set `DEBUG=1` as an env var for one manual run
  (`workflow_dispatch`) and check the Action logs — it'll print raw trade
  payloads so you can confirm the field names match, then adjust if not.
- **Cron timing**: GitHub's scheduler is best-effort. Under load, 15-min
  schedules can slip 5-15+ minutes. Fine for catching a runner in progress,
  not fine if you need second-precision entries.
- **State persistence**: alert cooldown state is committed back to the repo
  as `state.json`. This will create a lot of small commits over time — if
  that bothers you, switch to GitHub Actions cache or an external key-value
  store instead.
