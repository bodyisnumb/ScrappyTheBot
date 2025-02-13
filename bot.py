import os
import json
import logging
from datetime import datetime, UTC
import requests
import praw
from telegram import Bot
from telegram.ext import Application, CommandHandler, CallbackContext
from dotenv import load_dotenv
from typing import TextIO

# Load environment variables
load_dotenv()

# Reddit API Credentials
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET")
REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT")

# Telegram Bot Token & Channel ID
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID")  # Example: "@yourchannel"

# File to store posted images
POSTED_IMAGES_FILE = "posted_images.json"

# Logging setup
LOG_FILE = "bot.log"
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger()

# Reddit API Setup
try:
    reddit = praw.Reddit(
        client_id=REDDIT_CLIENT_ID,
        client_secret=REDDIT_CLIENT_SECRET,
        user_agent=REDDIT_USER_AGENT,
    )
    logger.info("Connected to Reddit API successfully.")
except Exception as reddit_err:
    logger.error(f"Failed to connect to Reddit API: {reddit_err}")
    reddit = None  # Prevent script from running if Reddit API fails


# Load posted images
def load_posted_images() -> tuple[list[str], str]:
    if os.path.exists(POSTED_IMAGES_FILE):
        try:
            with open(POSTED_IMAGES_FILE, "r", encoding="utf-8") as file:
                data = json.load(file)
                return data.get("images", []), data.get("date", "")
        except (json.JSONDecodeError, IOError) as load_err:
            logger.error(f"Error loading posted images file: {load_err}")
    return [], ""


# Save posted images
# noinspection PyTypeChecker
def save_posted_images(images: list[str]) -> None:
    try:
        with open(POSTED_IMAGES_FILE, "w", encoding="utf-8") as file:  # Explicit type hint
            file: TextIO  # Fix the type warning
            json.dump({"images": images, "date": datetime.now(UTC).strftime("%Y-%m-%d")}, file)
    except IOError as save_err:
        logger.error(f"Error saving posted images: {save_err}")


# Clear stored images if the day has changed
def clear_old_images() -> list[str]:
    stored_images, stored_date = load_posted_images()
    current_date = datetime.now(UTC).strftime("%Y-%m-%d")

    if stored_date != current_date:
        logger.info("New day detected. Clearing old image records.")
        save_posted_images([])
        return []

    return stored_images


# Fetch today's images from a subreddit
def fetch_images(subreddit_name: str, upvote_threshold: int = 500, limit: int = 10) -> list[str]:
    if reddit is None:
        logger.error("Reddit API not initialized.")
        return []

    try:
        subreddit = reddit.subreddit(subreddit_name)
        current_day_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()

        images = [
            post.url
            for post in subreddit.hot(limit=limit)
            if post.created_utc >= current_day_start and post.score >= upvote_threshold
               and post.url.endswith((".jpg", ".png", ".jpeg"))
        ]

        logger.info(f"Fetched {len(images)} images from r/{subreddit_name}.")
        return images
    except Exception as fetch_err:
        logger.error(f"Error fetching images from r/{subreddit_name}: {fetch_err}")
        return []


# Send an image to Telegram
async def send_image_to_telegram(bot: Bot, image_url: str, caption: str, posted_images: list[str]) -> None:
    try:
        response = requests.get(image_url, timeout=10)
        if response.status_code == 200:
            await bot.send_photo(chat_id=TELEGRAM_CHANNEL_ID, photo=image_url, caption=caption)
            posted_images.append(image_url)
            save_posted_images(posted_images)
            logger.info(f"Successfully posted image: {image_url}")
        else:
            logger.warning(f"Failed to fetch image: {image_url} (Status Code: {response.status_code})")
    except requests.RequestException as request_err:
        logger.error(f"Request error while fetching image {image_url}: {request_err}")
    except Exception as telegram_err:
        logger.error(f"Error sending image to Telegram: {telegram_err}")


# Command to fetch and post images
async def post_reddit_images(_: object, context: CallbackContext) -> None:
    bot = context.bot
    subreddits = ["EarthPorn", "spaceporn", "Art"]  # Example subreddits
    upvote_threshold = 1000  # Adjust threshold as needed

    posted_images = clear_old_images()

    for subreddit in subreddits:
        images = fetch_images(subreddit, upvote_threshold)
        for img in images:
            if img not in posted_images:
                await send_image_to_telegram(bot, img, f"From r/{subreddit}", posted_images)


# Telegram bot setup
def main() -> None:
    if not TELEGRAM_BOT_TOKEN:
        logger.error("Telegram bot token is missing! Check your .env file.")
        return

    try:
        application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        application.add_handler(CommandHandler("post_images", post_reddit_images))

        logger.info("Bot started successfully.")
        application.run_polling()
    except Exception as bot_err:
        logger.error(f"Error starting the bot: {bot_err}")


if __name__ == "__main__":
    main()