import os
import json
import requests
from pathlib import Path

BEARER_TOKEN = os.environ["X_BEARER_TOKEN"]
DISCORD_WEBHOOKS = json.loads(os.environ["DISCORD_WEBHOOKS_JSON"])
USERNAMES = [u for u in DISCORD_WEBHOOKS if u != "default"]
STATE_FILE = Path("state.json")

HEADERS = {"Authorization": f"Bearer {BEARER_TOKEN}"}


def get_user_id(username: str, state: dict) -> str:
    user_id = state.setdefault("user_ids", {}).get(username)
    if user_id:
        return user_id

    res = requests.get(
        f"https://api.twitter.com/2/users/by/username/{username}",
        headers=HEADERS,
    )
    res.raise_for_status()
    user_id = res.json()["data"]["id"]
    state["user_ids"][username] = user_id
    print(f"Fetched user info for @{username}: {user_id}")
    return user_id


def get_new_tweets(user_id: str, since_id: str | None) -> list[dict]:
    params: dict = {
        "max_results": 5,
        "exclude": "retweets",
    }
    if since_id:
        params["since_id"] = since_id

    res = requests.get(
        f"https://api.twitter.com/2/users/{user_id}/tweets",
        headers=HEADERS,
        params=params,
    )
    res.raise_for_status()
    return res.json().get("data", [])


def get_webhook_urls(username: str) -> list[str]:
    urls = DISCORD_WEBHOOKS.get(username, DISCORD_WEBHOOKS.get("default"))
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

    for username in USERNAMES:
        try:
            user_id = get_user_id(username, state)
            webhook_urls = get_webhook_urls(username)
            since_id = state.setdefault("last_ids", {}).get(username)
            tweets = get_new_tweets(user_id, since_id)

            if not tweets:
                print(f"@{username}: no new tweets")
                continue

            for tweet in reversed(tweets):
                for webhook_url in webhook_urls:
                    notify_discord(webhook_url, username, tweet)

            state["last_ids"][username] = tweets[0]["id"]
        except Exception as e:
            print(f"Error processing @{username}: {e}")

    STATE_FILE.write_text(json.dumps(state))


if __name__ == "__main__":
    main()
