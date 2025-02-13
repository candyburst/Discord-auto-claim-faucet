import os
import time
import requests
import logging
from dotenv import dotenv_values
import threading
import re
import sys

# Configure logging
logging.basicConfig(filename="bot.log", level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logging.info("Bot started!")

# Load environment variables
def load_config():
    return dotenv_values(".env")

config = load_config()
TOKEN = config.get("DISCORD_TOKEN")
SLOW_MODE_TRACKER = {}

# Function to format user mention
def format_message(message):
    match = re.match(r"@(\d+)\s(.+)", message)
    if match:
        user_id, content = match.groups()
        return f"<@{user_id}> {content}", user_id
    return message, None

# Function to send a message to a channel
def send_message(channel_id, message):
    global SLOW_MODE_TRACKER
    url = f"https://discord.com/api/v9/channels/{channel_id}/messages"
    headers = {"Authorization": f"{TOKEN}", "Content-Type": "application/json"}
    
    message_content, user_id = format_message(message)
    
    data = {
        "content": message_content,
        "allowed_mentions": {"parse": ["users"], "users": [user_id] if user_id else []}
    }
    
    logging.info(f"Sending message to channel {channel_id}: {data}")
    response = requests.post(url, json=data, headers=headers)
    
    if response.status_code == 429:
        retry_after = response.json().get("retry_after", 0)
        SLOW_MODE_TRACKER[channel_id] = time.time() + retry_after
        logging.warning(f"Rate limit! Channel {channel_id} must wait {retry_after} seconds before retrying.")
        return False, retry_after
    
    elif response.status_code in [200, 201]:
        slow_mode_delay = response.json().get("slowmode_delay", 0)
        if slow_mode_delay > 0:
            SLOW_MODE_TRACKER[channel_id] = time.time() + slow_mode_delay
            logging.info(f"Slow mode active for {slow_mode_delay} seconds in channel {channel_id}.")
        logging.info(f"Message successfully sent to channel {channel_id}.")
        return True, 0
    else:
        logging.error(f"Failed to send message to channel {channel_id}. Status: {response.status_code}, Response: {response.text}")
        return False, 0

# Function to get the list of channels from .env
def get_channels():
    config = load_config()
    channels = {key.replace("CHANNEL_", ""): value for key, value in config.items() if key.startswith("CHANNEL_")}
    logging.info(f"Found channels: {list(channels.keys())}")
    return channels

# Function to add a new channel to .env
def add_channel():
    faucet_name = input("Enter Faucet Name: ")  # New input for faucet name
    channel_id = input("Enter Channel ID: ")
    message = input("Enter the message to send: ")
    with open(".env", "a") as f:
        f.write(f"\nCHANNEL_{channel_id}={message} # {faucet_name}")  # Save faucet name as a comment
    logging.info(f"Channel {channel_id} ({faucet_name}) and message saved successfully!")
    print("Channel and message successfully added!")

# Function to send messages to all channels
def send_all_messages():
    channels = get_channels()
    if not channels:
        logging.warning("No saved channels.")
        print("No saved channels.")
        return
    
    pending_channels = {}
    sent_channels = []
    
    # Send messages to each channel, delay only if rate limited
    for channel_id, message in channels.items():
        success, wait_time = send_message(channel_id, message)
        if success:
            sent_channels.append(channel_id)
        if not success and wait_time > 0:
            pending_channels[channel_id] = (message, wait_time)
    
    logging.info(f"Messages sent to channels: {', '.join(sent_channels)}")
    print(f"Messages sent to channels: {', '.join(sent_channels)}")
    
    if pending_channels:
        logging.info("Channels under slow mode:")
        print("Channels under slow mode:")
        for channel_id, (_, wait_time) in pending_channels.items():
            logging.info(f" - {channel_id}: {wait_time} seconds")
            print(f" - {channel_id}: {wait_time} seconds")
    
    # Retry only for channels under slow mode
    def process_pending():
        while pending_channels:
            for channel_id in list(pending_channels.keys()):
                message, wait_time = pending_channels[channel_id]
                time_to_wait = max(0, SLOW_MODE_TRACKER.get(channel_id, 0) - time.time())
                if time_to_wait > 0:
                    logging.info(f"Waiting {time_to_wait} seconds before retrying for channel {channel_id}.")
                    print(f"Waiting {time_to_wait} seconds before retrying for channel {channel_id}.")
                    time.sleep(time_to_wait)
                success, new_wait_time = send_message(channel_id, message)
                if success or new_wait_time == 0:
                    del pending_channels[channel_id]
                    sent_channels.append(channel_id)  # Add to successfully sent list
                    logging.info(f"Message finally sent to channel {channel_id}.")
        
        logging.info(f"All messages successfully sent to channels: {', '.join(sent_channels)}")
        print(f"All messages successfully sent to channels: {', '.join(sent_channels)}")

    slow_mode_thread = threading.Thread(target=process_pending)
    slow_mode_thread.start()

# Main loop
try:
    while True:
        print("\nChoose an option:")
        print("1. Claim faucet")
        print("2. Create a new message for faucet claim")
        print("3. Exit")

        choice = input("Enter your choice (1/2/3): ")

        if choice == "1":
            send_all_messages()
        elif choice == "2":
            add_channel()
            config = load_config()  # Reload config after adding a channel
            send_all_messages()  # Send messages after adding a new channel
        elif choice == "3":
            print("Exiting program.")
            sys.exit(0)  # Terminate the program completely
        else:
            print("Invalid choice, please try again.")

except KeyboardInterrupt:
    print("\nProgram interrupted by user.")
    sys.exit(0)
