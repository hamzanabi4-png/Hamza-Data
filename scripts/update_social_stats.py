"""
Fetches follower/subscriber counts from Instagram, Facebook, and YouTube
and appends a dated row to a Google Sheet.

Required environment variables:
    META_ACCESS_TOKEN       - Long-lived Meta Graph API user/page access token
    INSTAGRAM_BUSINESS_ID   - Instagram Business Account ID (numeric)
    FACEBOOK_PAGE_ID        - Facebook Page ID (numeric)
    YOUTUBE_API_KEY         - YouTube Data API v3 key
    YOUTUBE_CHANNEL_ID      - YouTube Channel ID (starts with UC...)
    SPREADSHEET_ID          - Google Sheets spreadsheet ID (from the URL)
    GOOGLE_CREDENTIALS_JSON - Contents of the service account key JSON file
"""

import os
import json
import datetime
import requests
import gspread
from google.oauth2.service_account import Credentials


# ── helpers ──────────────────────────────────────────────────────────────────

def get_instagram_followers(access_token: str, business_id: str) -> int:
    url = f"https://graph.facebook.com/v19.0/{business_id}"
    resp = requests.get(url, params={
        "fields": "followers_count",
        "access_token": access_token,
    }, timeout=15)
    resp.raise_for_status()
    return resp.json()["followers_count"]


def get_facebook_followers(access_token: str, page_id: str) -> int:
    url = f"https://graph.facebook.com/v19.0/{page_id}"
    resp = requests.get(url, params={
        "fields": "followers_count",
        "access_token": access_token,
    }, timeout=15)
    resp.raise_for_status()
    return resp.json()["followers_count"]


def get_youtube_subscribers(api_key: str, channel_id: str) -> int:
    url = "https://www.googleapis.com/youtube/v3/channels"
    resp = requests.get(url, params={
        "part": "statistics",
        "id": channel_id,
        "key": api_key,
    }, timeout=15)
    resp.raise_for_status()
    items = resp.json().get("items", [])
    if not items:
        raise ValueError(f"No YouTube channel found for ID: {channel_id}")
    count = items[0]["statistics"].get("subscriberCount")
    if count is None:
        raise ValueError("Subscriber count is hidden for this channel.")
    return int(count)


def append_to_sheet(
    credentials_json: str,
    spreadsheet_id: str,
    date_str: str,
    instagram: int,
    facebook: int,
    youtube: int,
) -> None:
    creds = Credentials.from_service_account_info(
        json.loads(credentials_json),
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    client = gspread.authorize(creds)
    sheet = client.open_by_key(spreadsheet_id).sheet1

    # Write header row if the sheet is empty
    if not sheet.get_all_values():
        sheet.append_row(["Date", "Instagram Followers", "Facebook Followers", "YouTube Subscribers"])

    sheet.append_row([date_str, instagram, facebook, youtube])
    print(f"Row appended: {date_str} | IG={instagram:,} | FB={facebook:,} | YT={youtube:,}")


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    meta_token = os.environ["META_ACCESS_TOKEN"]
    ig_id = os.environ["INSTAGRAM_BUSINESS_ID"]
    fb_id = os.environ["FACEBOOK_PAGE_ID"]
    yt_key = os.environ["YOUTUBE_API_KEY"]
    yt_channel = os.environ["YOUTUBE_CHANNEL_ID"]
    spreadsheet_id = os.environ["SPREADSHEET_ID"]
    google_creds = os.environ["GOOGLE_CREDENTIALS_JSON"]

    today = datetime.date.today()
    # Record as last day of the previous month when run on the 1st,
    # otherwise record today's date.
    if today.day == 1:
        first_of_month = today
        last_month = first_of_month - datetime.timedelta(days=1)
        date_str = last_month.strftime("%Y-%m-%d")
    else:
        date_str = today.strftime("%Y-%m-%d")

    print(f"Fetching social stats for {date_str} ...")

    instagram = get_instagram_followers(meta_token, ig_id)
    print(f"  Instagram followers : {instagram:,}")

    facebook = get_facebook_followers(meta_token, fb_id)
    print(f"  Facebook followers  : {facebook:,}")

    youtube = get_youtube_subscribers(yt_key, yt_channel)
    print(f"  YouTube subscribers : {youtube:,}")

    append_to_sheet(google_creds, spreadsheet_id, date_str, instagram, facebook, youtube)


if __name__ == "__main__":
    main()
