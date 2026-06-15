import os
import json
import requests
from pathlib import Path

BEARER_TOKEN = os.environ["X_BEARER_TOKEN"]
DISCORD_WEBHOOK_URL = os.environ["DISCORD_WEBHOOK_URL"]
USERNAMES = [u.strip() for u in os.environ["TWITTER_USERNAMES"].split(",")]
STATE_FILE = Path("state.json")

HEADERS = {"Authorization": f"Bearer {BEARER_TOKEN}"}


def get_user_info(username: str, state: dict) -> tuple[str, str]:
    user_id = state.setdefault("user_ids", {}).get(username)
    icon_url = state.setdefault("user_icons", {}).get(username)
    if user_id and icon_url:
        return user_id, icon_url

    res = requests.get(
        f"https://api.twitter.com/2/users/by/username/{username}",
        headers=HEADERS,
        params={"user.fields": "profile_image_url"},
    )
    res.raise_for_status()
    data = res.json()["data"]
    user_id = data["id"]
    icon_url = data.get("profile_image_url", "").replace("_normal", "_400x400")
    state["user_ids"][username] = user_id
    state["user_icons"][username] = icon_url
    print(f"Fetched user info for @{username}: {user_id}")
    return user_id, icon_url


def get_new_tweets(user_id: str, since_id: str | None) -> list[dict]:
    params: dict = {
        "max_results": 5,
        "tweet.fields": "created_at,text",
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


def notify_discord(username: str, icon_url: str, tweet: dict) -> None:
    tweet_url = f"https://x.com/{username}/status/{tweet['id']}"
    payload = {
        "embeds": [
            {
                "author": {
                    "name": f"@{username}",
                    "url": f"https://x.com/{username}",
                    "icon_url": icon_url,
                },
                "description": tweet["text"],
                "url": tweet_url,
                "color": 0x1D9BF0,
                "footer": {"text": tweet.get("created_at", "")},
            }
        ]
    }
    res = requests.post(DISCORD_WEBHOOK_URL, json=payload)
    res.raise_for_status()
    print(f"Notified: {tweet_url}")


def main() -> None:
    state: dict = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}

    for username in USERNAMES:
        try:
            user_id, icon_url = get_user_info(username, state)
            since_id = state.setdefault("last_ids", {}).get(username)
            tweets = get_new_tweets(user_id, since_id)

            if not tweets:
                print(f"@{username}: no new tweets")
                continue

            for tweet in reversed(tweets):
                notify_discord(username, icon_url, tweet)

            state["last_ids"][username] = tweets[0]["id"]
        except Exception as e:
            print(f"Error processing @{username}: {e}")

    STATE_FILE.write_text(json.dumps(state))


if __name__ == "__main__":
    main()
