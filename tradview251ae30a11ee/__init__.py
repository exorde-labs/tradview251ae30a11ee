"""
In this script we are going to collect data from TradingView. We will navigate to this link:

https://www.tradingview.com/ideas/?sort=recent

Once on it, we can extract all the latest posts.

A simple GET request will return the page. We can then perform a lookup for all the elements following this structure:

<div class="tv-widget-idea js-userlink-popup-anchor"> :: the card class that encompasses what we want
    ...
    <div class="tv-widget-idea__title-row"> :: the subclass that encompasses the link to the post
        <a href=[link to post]/> :: link to post + title
    </div>
    <span data-timestamp=[timestamp]/> :: the timestamp linked to the post
    <span class="tv-card-user-info__name"/> :: the username of the author of the post
    ...
</div>

With this, we can extract the links to every post if any match the time window that we are interested in.

Another GET request on the identified links of interest will yield the relevant posts and their contents.

Once the GET request returns on the link of the post, look for these elements:

<div class="tv-chart-view__description-wrap js-chart-view__description"/> ::  returns the content of the post

"""
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
        bob = soup.find("div", {"class": "tv-chart-view__description selectable"})
        return bob.text
    except Exception as e:
        print("Error:" + str(e))


async def request_entries_with_timeout(_url, _max_age):
    """
    Requests the different entries within the latest items that were published in TradingView
    :param _max_age: the maximum age we will allow for the post in seconds
    :param _url: the url where we will find the latest posts
    :return: the card elements from which we can extract the relevant information
    """
    try:
        response = requests.get(_url, headers={'User-Agent': random.choice(USER_AGENT_LIST)}, timeout=8.0)
        soup = BeautifulSoup(response.text, 'html.parser')
        entries = soup.find_all("div", {"class": "tv-widget-idea js-userlink-popup-anchor"})
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
    date_to_check = datetime.strptime(_date, "%Y-%m-%dT%H:%M:%S.00Z")
    if (datetime.now() - date_to_check).total_seconds() <= _max_age:
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
        for card in _cards:
            timestamp = card.find("span", {"data-timestamp": True})["data-timestamp"]
            date = convert_from_timestamp(int(float(timestamp)))

            if not check_for_max_age(date, _max_age): continue  # check if the post respects the max age we are looking for

            container = card.find("div", {"class": "tv-widget-idea__title-row"})
            container2 = container.find("a",
                                        {"class": "tv-widget-idea__title apply-overflow-tooltip js-widget-idea__popup"})
            link = "https://www.tradingview.com" + container2["href"]
            post_title = container2.text
            author = card.find("span", {"class": "tv-card-user-info__name"}).text

            content = request_content_with_timeout(link)[:800]
            filtered_content = filter_string(content)
            filtered_content = post_title+ ". " + filtered_content

            yield Item(
                title=Title(post_title),
                content=Content(filtered_content),
                created_at=CreatedAt(date),
                url=Url(link),
                domain=Domain("tradingview.com"))
    except Exception as e:
        print("Error:" + str(e))


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
        logging.info(f"[TradingView] Found new post :\t {item.title}, posted at { item.created_at}, URL = {item.url}" )
        if yielded_items >= maximum_items_to_collect:
            break
