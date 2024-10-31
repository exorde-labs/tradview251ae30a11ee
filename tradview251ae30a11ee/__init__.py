import re
import requests
import random
import asyncio
from bs4 import BeautifulSoup
from typing import AsyncGenerator
from datetime import datetime
from exorde_data import (
    Item,
    Content,
    Author,
    CreatedAt,
    Title,
    Url,
    Domain,
)
import logging
import pytz

logging.basicConfig(level=logging.INFO)

# GLOBAL VARIABLES
USER_AGENT_LIST = [
    'Mozilla/5.0 (iPad; CPU OS 12_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.1 Safari/605.1.15',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 13_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.1 Safari/605.1.15'
]


def request_content_with_timeout(_url):
    """
    Requests the content of the post and returns it under text format
    :param _url: the url of the post
    :return: the content of the post
    """
    try:
        response = requests.get(_url, headers={'User-Agent': random.choice(USER_AGENT_LIST)}, timeout=8.0)
        soup = BeautifulSoup(response.text, 'html.parser')
        bob = soup.find("div", {"class": "description-aqIxarm1"})
        return bob.text
    except Exception as e:
        print("Error:" + str(e))

def remove_time_phrase(text):
    # Define a regex pattern to match the optional time phrase
    pattern = r'^\d+\s+(minute|minutes|hour|hours|second|seconds)\s+ago'
    # Substitute the matched pattern with an empty string
    return re.sub(pattern, '', text).strip()

async def request_entries_with_timeout(_url, _max_age):
    """
    Requests the different entries within the latest items that were published in TradingView
    :param _max_age: the maximum age we will allow for the post in seconds
    :param _url: the url where we will find the latest posts
    :return: the card elements from which we can extract the relevant information
    """
    try:
        response = requests.get(_url, headers={'User-Agent': random.choice(USER_AGENT_LIST)}, timeout=3.0)
        soup = BeautifulSoup(response.text, 'html.parser')
        # entries = soup.find_all("div", {"class": "tv-widget-idea js-userlink-popup-anchor"})
        # find all article elements that have the the substring "card" in their class
        entries = soup.find_all("article", class_=re.compile("card"))
        # print number of entries
        logging.info("Number of entries: %s", len(entries))
        async for item in parse_entry_for_elements(entries, _max_age):
            yield item
    except Exception as e:
        print("Error:" + str(e))


def convert_from_timestamp(_timestamp):
    return datetime.fromtimestamp(_timestamp).strftime("%Y-%m-%dT%H:%M:%S.00Z")


def check_for_max_age(_date, _max_age):
    """
    Checks if the entry is within the max age bracket that we are looking for
    :param _date: the datetime from the entry
    :param _max_age: the max age to which we will be comparing the timestamp
    :return: true if it is within the age bracket, false otherwise
    """
    # apply strptime IF the date is in string format
    if isinstance(_date, str):
        date_to_check = datetime.strptime(_date, "%Y-%m-%dT%H:%M:%S.00Z")
    else:
        date_to_check = _date
    # make the date utc+0 from utc+2
    date_to_check = date_to_check.replace(tzinfo=pytz.timezone('UTC')).astimezone(pytz.utc)
    # now must be UTC+0
    now = datetime.now(pytz.utc)
    delay = now - date_to_check
    if  delay.total_seconds() <= _max_age:
        return True
    else:
        return False
    
def filter_string(input_string):
    filtered_string = input_string.replace('\t', ' ').replace('\r\n', ' ').replace('\n', ' ').replace("Comment:", '')
    filtered_string = re.sub(' +', ' ', filtered_string)
    return filtered_string

async def parse_entry_for_elements(_cards, _max_age):
    """
    Parses every card element to find the information we want
    :param _max_age: The maximum age we will allow for the post in seconds
    :param _cards: The parent card objects from which we will be gathering the information
    :return: All the parameters we need to return an Item instance
    """
    try:
        # 
        for card in _cards:
            print("Parsing card")
            
            # Find timestamp
            timestamp_elem = card.find("time", {"class": "publication-date-CgENjecZ"})
            if timestamp_elem and timestamp_elem.has_attr("datetime"):
                timestamp = timestamp_elem["datetime"]
                date = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            else:
                print("Timestamp not found, skipping card")
                continue

            if not check_for_max_age(date, _max_age):
                print("Card too old, skipping")
                continue

            # Find title and link
            title_elem = card.find("a", {"class": "title-tkslJwxl"})
            if title_elem:
                link = title_elem["href"]
                post_title = title_elem.text
            else:
                continue

            # Find author
            author_elem = card.find("a", {"class": "card-author-link-BhFUdJAZ"})
            if author_elem:
                author = author_elem.text
            else:
                author = "Unknown"

            # Find content
            content_elem = card.find("a", {"class": "paragraph-t3qFZvNN"})
            if content_elem:
                content = content_elem.text
                filtered_content = filter_string(content)
            else:
                filtered_content = ""

            yield Item(
                title=Title(post_title),
                content=Content(filtered_content),
                created_at=CreatedAt(date),
                url=Url(link),
                domain=Domain("tradingview.com")
            )

    except Exception as e:
        logging.exception(f"Error parsing card: {str(e)}")

# default values
DEFAULT_OLDNESS_SECONDS = 360
DEFAULT_MAXIMUM_ITEMS = 25
DEFAULT_MIN_POST_LENGTH = 10

def read_parameters(parameters):
    # Check if parameters is not empty or None
    if parameters and isinstance(parameters, dict):
        try:
            max_oldness_seconds = parameters.get("max_oldness_seconds", DEFAULT_OLDNESS_SECONDS)
        except KeyError:
            max_oldness_seconds = DEFAULT_OLDNESS_SECONDS

        try:
            maximum_items_to_collect = parameters.get("maximum_items_to_collect", DEFAULT_MAXIMUM_ITEMS)
        except KeyError:
            maximum_items_to_collect = DEFAULT_MAXIMUM_ITEMS

        try:
            min_post_length = parameters.get("min_post_length", DEFAULT_MIN_POST_LENGTH)
        except KeyError:
            min_post_length = DEFAULT_MIN_POST_LENGTH

    else:
        # Assign default values if parameters is empty or None
        max_oldness_seconds = DEFAULT_OLDNESS_SECONDS
        maximum_items_to_collect = DEFAULT_MAXIMUM_ITEMS
        min_post_length = DEFAULT_MIN_POST_LENGTH

    return max_oldness_seconds, maximum_items_to_collect, min_post_length

async def query(parameters: dict) -> AsyncGenerator[Item, None]:
    url_main_endpoint = "https://www.tradingview.com/ideas/?sort=recent"
    yielded_items = 0
    max_oldness_seconds, maximum_items_to_collect, min_post_length = read_parameters(parameters)
    logging.info(f"[TradingView] - Scraping ideas posted less than {max_oldness_seconds} seconds ago.")

    async for item in request_entries_with_timeout(url_main_endpoint, max_oldness_seconds):
        yielded_items += 1
        yield item
        logging.info(f"[TradingView] Found new post :\t {item}" )
        if yielded_items >= maximum_items_to_collect:
            break
