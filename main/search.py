import os
import time
from pyrogram import Client, filters
from pyrogram.types import InlineQueryResultArticle, InputTextMessageContent
from googleapiclient.discovery import build
import isodate  # To convert ISO 8601 duration format
import re

# Your bot's API credentials and other configurations
YOUTUBE_API_KEY = "AIzaSyDp0oGuQ35JDAW6HBJCg3OBviIlWzLXTn4"

# Initialize YouTube API client
youtube = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY)


def format_duration(duration):
    duration_obj = isodate.parse_duration(duration)
    total_seconds = int(duration_obj.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    if hours > 0:
        return f"{hours}h {minutes}m {seconds}s"
    elif minutes > 0:
        return f"{minutes}m {seconds}s"
    else:
        return f"{seconds}s"


def extract_channel_info(url):
    """Extract the channel handle or ID from a YouTube channel URL."""
    print(f"Extracting channel info from URL: {url}")  # Debug log
    channel_id = None
    if '/channel/' in url:
        match = re.search(r'channel/([^/?]+)', url)
        channel_id = match.group(1) if match else None
    elif '@' in url:  # New YouTube handle format
        match = re.search(r'@([^/?]+)', url)
        channel_id = match.group(1) if match else None

    print(f"Extracted channel ID or handle: {channel_id}")  # Debug log
    return channel_id


@Client.on_inline_query()
async def youtube_search(bot, query):
    search_query = query.query.strip()

    # Check if the query is a YouTube channel URL
    if search_query.startswith('https://youtube.com/'):
        channel_id_or_handle = extract_channel_info(search_query)

        if channel_id_or_handle:
            try:
                # Fetch the channel using search().list with the handle or ID
                # Debug log
                print(f"Fetching channel details for: {channel_id_or_handle}")
                channel_response = youtube.search().list(
                    q=channel_id_or_handle,  # Search using the handle or ID
                    type='channel',
                    part='snippet',
                    maxResults=1
                ).execute()

                # Check if channel data is found
                if 'items' in channel_response and channel_response['items']:
                    channel = channel_response['items'][0]
                    channel_title = channel['snippet']['title']
                    channel_icon = channel['snippet']['thumbnails']['default']['url']
                    channel_id = channel['id']['channelId']

                    # Now fetch all videos from the channel
                    video_response = youtube.search().list(
                        channelId=channel_id,
                        part='snippet',
                        type='video',
                        order='date',
                        maxResults=10
                    ).execute()

                    results = []

                    # Add channel name and icon at the top
                    results.append(
                        InlineQueryResultArticle(
                            title=channel_title,
                            description="Channel Videos",
                            thumb_url=channel_icon,
                            input_message_content=InputTextMessageContent(f"Channel: {channel_title}"),
                        ))

                    # Add videos from the channel (latest to oldest)
                    for item in video_response.get('items', []):
                        video_id = item['id']['videoId']
                        title = item['snippet']['title']
                        thumbnail = item['snippet']['thumbnails']['default']['url']
                        video_url = f"https://www.youtube.com/watch?v={video_id}"

                        # Get video details (duration, views)
                        video_details = youtube.videos().list(
                            id=video_id,
                            part='contentDetails,statistics'
                        ).execute()

                        # Format duration
                        duration_iso = video_details['items'][0]['contentDetails']['duration']
                        duration = format_duration(duration_iso)

                        views = video_details['items'][0]['statistics']['viewCount']

                        # Create an inline result
                        results.append(
                            InlineQueryResultArticle(
                                title=title,
                                description=f"Duration: {duration} | Views: {views}",
                                thumb_url=thumbnail,
                                input_message_content=InputTextMessageContent(video_url),
                                url=video_url,
                            ))

                    await query.answer(results, cache_time=0)
                else:
                    # Channel not found
                    await query.answer([InlineQueryResultArticle(
                        title="Channel not found",
                        description="Please check the URL and try again.",
                        input_message_content=InputTextMessageContent("No channel found for the given URL.")
                    )], cache_time=0)

            except Exception as e:
                print(f"Error fetching channel: {e}")  # Debug log
                await query.answer([InlineQueryResultArticle(
                    title="Error fetching channel",
                    description="There was an error fetching the channel details.",
                    input_message_content=InputTextMessageContent("Error fetching channel details. Please try again.")
                )], cache_time=0)
        return

    # Default search by keywords if no channel URL is provided
    if not search_query:
        return

    search_response = youtube.search().list(
        q=search_query,
        part='snippet',
        type='video',
        maxResults=5
    ).execute()

    results = []
    for item in search_response['items']:
        video_id = item['id']['videoId']
        title = item['snippet']['title']
        thumbnail = item['snippet']['thumbnails']['default']['url']
        video_url = f"https://www.youtube.com/watch?v={video_id}"

        # Get video details like duration and views
        video_details = youtube.videos().list(
            id=video_id,
            part='contentDetails,statistics'
        ).execute()

        # Format duration
        duration_iso = video_details['items'][0]['contentDetails']['duration']
        duration = format_duration(duration_iso)

        views = video_details['items'][0]['statistics']['viewCount']

        # Create an inline result
        results.append(
            InlineQueryResultArticle(
                title=title,
                description=f"Duration: {duration} | Views: {views}",
                thumb_url=thumbnail,
                input_message_content=InputTextMessageContent(video_url),
                url=video_url,
            )
        )

    # Send the inline results
    await query.answer(results, cache_time=0)
