import os
import json
import requests
from pathlib import Path

BEARER_TOKEN = os.environ["X_BEARER_TOKEN"]
DISCORD_WEBHOOKS = json.loads(os.environ["DISCORD_WEBHOOKS_JSON"])
USERNAMES = [u for u in DISCORD_WEBHOOKS if u != "default"]
STATE_FILE = Path("state.json")

HEADERS = {"Authorization": f"Bearer {BEARER_TOKEN}"}


def search_new_tweets(since_id: str | None) -> list[tuple[str, dict]]:
    """Fetch new tweets from all users in one request. Returns (username, tweet) newest first."""
    query = " OR ".join(f"from:{u}" for u in USERNAMES)
    params: dict = {
        "query": f"({query}) -is:retweet",
        "max_results": 100,
        "expansions": "author_id",
        "user.fields": "username",
    }
    if since_id:
        params["since_id"] = since_id

    res = requests.get(
        "https://api.twitter.com/2/tweets/search/recent",
        headers=HEADERS,
        params=params,
    )
    res.raise_for_status()
    body = res.json()
    authors = {u["id"]: u["username"] for u in body.get("includes", {}).get("users", [])}
    return [(authors.get(t["author_id"], ""), t) for t in body.get("data", [])]


def get_webhook_urls(username: str) -> list[str]:
    # Match config keys case-insensitively since the API returns canonical casing
    key = next((u for u in USERNAMES if u.lower() == username.lower()), None)
    urls = DISCORD_WEBHOOKS.get(key, DISCORD_WEBHOOKS.get("default"))
    if not urls:
        raise RuntimeError(f"No webhook configured for @{username} (and no default)")
    return [urls] if isinstance(urls, str) else urls


def notify_discord(webhook_url: str, username: str, tweet: dict) -> None:
    tweet_url = f"https://fxtwitter.com/{username}/status/{tweet['id']}"
    res = requests.post(webhook_url, json={"content": tweet_url})
    res.raise_for_status()
    print(f"Notified: {tweet_url}")


def main() -> None:
    state: dict = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}

    # Migrate from the old per-user state
    since_id = state.get("since_id")
    if not since_id and state.get("last_ids"):
        since_id = max(state["last_ids"].values(), key=int)

    # Without a since_id, only record the latest ID so a week of old tweets isn't posted
    baseline = since_id is None
    try:
        tweets = search_new_tweets(since_id)
    except requests.HTTPError as e:
        # since_id older than the 7-day search window is rejected; reset the baseline
        if e.response is None or e.response.status_code != 400 or not since_id:
            raise
        print(f"since_id rejected, resetting baseline: {e.response.text}")
        baseline = True
        tweets = search_new_tweets(None)

    if not tweets:
        print("no new tweets")
    elif baseline:
        print(f"Baseline set without notifying ({len(tweets)} recent tweets)")
    else:
        for username, tweet in reversed(tweets):
            try:
                for webhook_url in get_webhook_urls(username):
                    notify_discord(webhook_url, username, tweet)
            except Exception as e:
                print(f"Error notifying @{username} {tweet['id']}: {e}")

    if tweets:
        state["since_id"] = tweets[0]["id"]
    state.pop("last_ids", None)
    state.pop("user_ids", None)
    STATE_FILE.write_text(json.dumps(state))


if __name__ == "__main__":
    main()
