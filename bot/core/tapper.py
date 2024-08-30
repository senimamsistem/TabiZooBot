import asyncio
from datetime import datetime, timezone
import os
import random
import string
import sys
from time import time
from urllib.parse import unquote, quote

import aiohttp
import json
from aiocfscrape import CloudflareScraper
from aiohttp_proxy import ProxyConnector
from better_proxy import Proxy
from pyrogram import Client
from pyrogram.errors import Unauthorized, UserDeactivated, AuthKeyUnregistered, FloodWait
from pyrogram.raw.functions.messages import RequestAppWebView
from pyrogram.raw import types
import requests
from .agents import generate_random_user_agent
from bot.config import settings

from bot.utils import logger
from bot.exceptions import InvalidSession
from .headers import headers

class Tapper:
    def __init__(self, tg_client: Client):
        self.session_name = tg_client.name
        self.tg_client = tg_client
        self.user_id = 0
        self.username = None
        self.first_name = None
        self.last_name = None
        self.fullname = None
        self.start_param = None
        self.peer = None
        self.first_run = None
        self.rf_token = ""
        self.session_ug_dict = self.load_user_agents() or []

        headers['User-Agent'] = self.check_user_agent()

    async def generate_random_user_agent(self):
        return generate_random_user_agent(device_type='android', browser_type='chrome')

    def info(self, message):
        from bot.utils import info
        info(f"<light-yellow>{self.session_name}</light-yellow> | {message}")

    def debug(self, message):
        from bot.utils import debug
        debug(f"<light-yellow>{self.session_name}</light-yellow> | {message}")

    def warning(self, message):
        from bot.utils import warning
        warning(f"<light-yellow>{self.session_name}</light-yellow> | {message}")

    def error(self, message):
        from bot.utils import error
        error(f"<light-yellow>{self.session_name}</light-yellow> | {message}")

    def critical(self, message):
        from bot.utils import critical
        critical(f"<light-yellow>{self.session_name}</light-yellow> | {message}")

    def success(self, message):
        from bot.utils import success
        success(f"<light-yellow>{self.session_name}</light-yellow> | {message}")

    def save_user_agent(self):
        user_agents_file_name = "user_agents.json"

        if not any(session['session_name'] == self.session_name for session in self.session_ug_dict):
            user_agent_str = generate_random_user_agent()

            self.session_ug_dict.append({
                'session_name': self.session_name,
                'user_agent': user_agent_str})

            with open(user_agents_file_name, 'w') as user_agents:
                json.dump(self.session_ug_dict, user_agents, indent=4)

            logger.success(f"<light-yellow>{self.session_name}</light-yellow> | User agent saved successfully")

            return user_agent_str

    def load_user_agents(self):
        user_agents_file_name = "user_agents.json"

        try:
            with open(user_agents_file_name, 'r') as user_agents:
                session_data = json.load(user_agents)
                if isinstance(session_data, list):
                    return session_data

        except FileNotFoundError:
            logger.warning("User agents file not found, creating...")

        except json.JSONDecodeError:
            logger.warning("User agents file is empty or corrupted.")

        return []

    def check_user_agent(self):
        load = next(
            (session['user_agent'] for session in self.session_ug_dict if session['session_name'] == self.session_name),
            None)

        if load is None:
            return self.save_user_agent()

        return load

    async def get_tg_web_data(self, proxy: str | None) -> str:
        if proxy:
            proxy = Proxy.from_str(proxy)
            proxy_dict = dict(
                scheme=proxy.protocol,
                hostname=proxy.host,
                port=proxy.port,
                username=proxy.login,
                password=proxy.password
            )
        else:
            proxy_dict = None

        self.tg_client.proxy = proxy_dict

        try:
            with_tg = True

            if not self.tg_client.is_connected:
                with_tg = False
                try:
                    await self.tg_client.connect()
                except (Unauthorized, UserDeactivated, AuthKeyUnregistered):
                    raise InvalidSession(self.session_name)

            while True:
                try:
                    if self.peer is None:
                        self.peer = await self.tg_client.resolve_peer('tabizoobot')
                    break
                except FloodWait as fl:
                    fls = fl.value

                    logger.warning(f"<light-yellow>{self.session_name}</light-yellow> | FloodWait {fl}")
                    logger.info(f"<light-yellow>{self.session_name}</light-yellow> | Sleep {fls}s")

                    await asyncio.sleep(fls + 3)

            if settings.REF_ID == '':
                self.start_param = '5833041671'
            else:
                self.start_param = settings.REF_ID

            InputBotApp = types.InputBotAppShortName(bot_id=self.peer, short_name="app")

            web_view = await self.tg_client.invoke(RequestAppWebView(
                peer=self.peer,
                app=InputBotApp,
                platform='android',
                write_allowed=True,
                start_param=self.start_param
            ))

            auth_url = web_view.url
            #print(auth_url)
            tg_web_data = unquote(
                string=auth_url.split('tgWebAppData=', maxsplit=1)[1].split('&tgWebAppVersion', maxsplit=1)[0])

            try:
                if self.user_id == 0:
                    information = await self.tg_client.get_me()
                    self.user_id = information.id
                    self.first_name = information.first_name or ''
                    self.last_name = information.last_name or ''
                    self.username = information.username or ''
            except Exception as e:
                print(e)

            if with_tg is False:
                await self.tg_client.disconnect()

            return tg_web_data

        except InvalidSession as error:
            raise error

        except Exception as error:
            logger.error(
                f"<light-yellow>{self.session_name}</light-yellow> | Unknown error during Authorization: {error}")
            await asyncio.sleep(delay=3)

    async def user_info(self, session):
            url = f"https://api.tabibot.com/api/user/v1/profile"
        
            async with session.get(url=url, ssl=False) as response:
                json_res = await response.json()
                return  json_res.get("data","").get("user")

    async def mining_info(self, session):
        url = f"https://api.tabibot.com/api/mining/v1/info"

        async with session.get(url=url, ssl=False) as response:
            return await response.json()

    async def check_in(self, session):
        url = f"https://api.tabibot.com/api/user/v1/check-in"

        async with session.post(url=url, json = {}, ssl=False) as response:
            return await response.json()

    async def level_up(self, session):
        url = f"https://api.tabibot.com/api/user/v1/level-up"

        async with session.post(url=url, json = {}, ssl=False) as response:
            return await response.json()

    async def claim(self, session):
        url = f"https://api.tabibot.com/api/mining/v1/claim"

        async with session.post(url=url, json = {}, ssl=False) as response:
            return await response.json()

    def log(self, msg):
        now = datetime.now().isoformat(" ").split(".")[0]
        print(f"[{now}] {msg}")

    async def run(self,proxy):
        while True:
            session = CloudflareScraper(headers=headers)
            data = await self.get_tg_web_data(proxy=proxy)
            session.headers["Rawdata"] = f"{data}"
            try:
                user_info = await self.user_info(session)
                user_id = user_info["tg_user_id"]
                balance = user_info["coins"]
                level = user_info["level"]
                self.info(f"Account ID: {user_id}")
                self.info(f"Balance: {balance:,}")
                self.info(f"Level: {level}")
            except Exception as e:
                self.error(f"Get user info error!!! - {e}")
            # Claim
            try:
                claim = await self.claim(session)
                if claim:
                    self.success("Claim successful")
                else:
                    self.info("Not time to claim yet")
            except Exception as e:
                self.error(f"Claim error!!! - {e}")

            # Check in
            try:
                check_in = await self.check_in(session)
                if check_in["data"]["check_in_status"] == 1:
                    self.info("Checked in already")
            except Exception as e:
                self.error(f"Check in error!!!- {e}")

            # Level up
            if settings.UPGRADE:
                try:
                    level_up = await self.level_up(session)
                    if level_up.get("message") == "success":
                        current_level = level_up['data']['user']["level"]
                        self.success(f"Upgrade successful | New level: {current_level}") 
                    else:
                        self.info("Not enough point to upgrade")
                except Exception as e:
                    self.error(f"Level up error!!! - {e} ") 

            # Get end time
            try:
                mining_info = await self.mining_info(session)
                end_time = mining_info['data']['mining_data']["next_claim_time"]
                formatted_end_time = end_time.replace("T", " ").replace("Z", "")
                self.info(f"End time: {formatted_end_time} (UTC)")
                now = datetime.now(timezone.utc).timestamp()
                wait_times = []
                end_at = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
                if end_at.timestamp() > now:
                    wait_times.append(end_at.timestamp() - now)

                    if wait_times:
                        wait_time = min(wait_times)
                    else:
                        wait_time = 15 * 60
                else:
                    wait_time = 15 * 60

                await asyncio.sleep(wait_time)
            except Exception as e:
                self.error(f"Get mining info error!!!- {e}")
                await asyncio.sleep(random.randint(30,100))


async def run_tapper(tg_client: Client, proxy: str | None):
    try:
        await Tapper(tg_client=tg_client).run(proxy=proxy)
    except InvalidSession:
        logger.error(f"{tg_client.name} | Invalid Session")
