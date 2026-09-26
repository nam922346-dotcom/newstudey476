import os
import requests
import traceback
import logging
from dotenv import load_dotenv

logger = logging.getLogger(__name__)
load_dotenv()

BASE_URL = os.getenv('MT5_API_URL')


def get_account():
    try:
        url = f"{BASE_URL}/account_info"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.Timeout:
        logger.error(f"Timeout fetching account info from {url}")
        return None
    except Exception as e:
        logger.error(f"Exception fetching account info: {e}\n{traceback.format_exc()}")
        return None


def get_equity():
    account = get_account()
    if account is None or account.get('equity') is None:
        logger.error("Account equity not available from MT5 /account_info")
        return None
    return float(account['equity'])