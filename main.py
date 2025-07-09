from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
import requests
import json
import random
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent
import astrbot.api.message_components as Comp
import datetime
import asyncio
import os

CONFIG_PATH = "choulaopo_config.json"
daily_records = {}
daily_counts = {}

class ConfigManager:
    def __init__(self, path):
        self.path = path
        self.config = self.load_config()
        
    def load_config(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load config: {e}")
                return self.create_default_config()
        else:
            return self.create_default_config()
            
    def create_default_config(self):
        default_config = {"draw_limit": 3}
        self.save_config(default_config)
        return default_config
        
    def save_config(self, config):
        try:
            with open(self.path, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save config: {e}")
            
    def get_draw_limit(self):
        return self.config.get("draw_limit", 3)
        
    def set_draw_limit(self, limit):
        self.config["draw_limit"] = limit
        self.save_config(self.config)

async def daily_reset(config_manager):
    while True:
        now = datetime.datetime.now()
        target_time = now.replace(hour=23, minute=59, second=59, microsecond=0)
        if now > target_time:
            target_time += datetime.timedelta(days=1)
        sleep_time = (target_time - now).total_seconds()
        await asyncio.sleep(sleep_time)
        daily_records.clear()
        daily_counts.clear()
        logger.info("Daily records and counts cleared.")

@register("choulaopo", "糯米茨", "[仅napcat]这是用于抽取QQ群友当老婆的插件。", "1.0.1")
class chouqunyou(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.config_manager = ConfigManager(CONFIG_PATH)
        asyncio.create_task(daily_reset(self.config_manager))

@register("choulaopo_01", "糯米茨", "抽取QQ群友当老婆的插件", "1.0")
class chouqunyou(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.config_manager = ConfigManager(CONFIG_PATH)
        asyncio.create_task(daily_reset(self.config_manager))

    # 辅助方法：处理抽取逻辑，根据参数决定是否At被抽取用户
    async def _draw_wife(self, event: AstrMessageEvent, at_selected_user: bool):
        try:
            group_id = event.get_group_id()
        except:
            yield event.plain_result(f"获取出错!")
            event.stop_event()
            return

        if event.get_platform_name() == "aiocqhttp":
            assert isinstance(event, AiocqhttpMessageEvent)
            client = event.bot
            payloads = {
                "group_id": group_id,
                "no_cache": True
            }
            ret = await client.api.call_action('get_group_member_list', **payloads)

        sender_id = event.get_sender_id()
        draw_limit = self.config_manager.get_draw_limit()
        user_count = daily_counts.get(sender_id, 0)
        
        if user_count >= draw_limit:
            yield event.plain_result(f"今日抽取已达上限({draw_limit}次)")
            event.stop_event()
            return

        length = len(ret)
        num = random.randint(0, length - 1)
        theone = ret[num]
        user_id = theone.get('user_id')
        nick_name = theone.get('nickname')
        avatar_url = f"https://q4.qlogo.cn/headimg_dl?dst_uin={user_id}&spec=640"

        # 根据参数决定消息链结构
        if at_selected_user:
            chain = [
                Comp.At(qq=sender_id),
                Comp.Plain(" 你的今日老婆是"),
                Comp.Image.fromURL(avatar_url),
                Comp.At(qq=user_id)
            ]
        else:
            chain = [
                Comp.At(qq=sender_id),
                Comp.Plain(" 你的今日老婆是"),
                Comp.Image.fromURL(avatar_url),
                Comp.Plain(nick_name)
            ]

        daily_records[sender_id] = {
            "user_id": user_id,
            "nickname": nick_name
        }
        daily_counts[sender_id] = user_count + 1
        yield event.chain_result(chain)

    @filter.command("今日老婆", alias={'抽取', '抽老婆'})
    async def wife_with_at(self, event: AstrMessageEvent):
        # 调用辅助方法，At被抽取用户
        async for result in self._draw_wife(event, True):
            yield result

    @filter.command("今日老婆-@", alias={'抽取-@', '抽老婆-@'})
    async def wife_without_at(self, event: AstrMessageEvent):
        # 调用辅助方法，不At被抽取用户
        async for result in self._draw_wife(event, False):
            yield result

    # 其他方法保持不变...

    @filter.command("今日记录", alias={'记录'})
    async def today_record(self, event: AstrMessageEvent):
        sender_id = event.get_sender_id()
        record = daily_records.get(sender_id)
        if record:
            chain = [
                Comp.At(qq=sender_id),
                Comp.Plain(" 你今日抽到的老婆是："),
                Comp.Plain(record["nickname"]),
                Comp.Plain(f" (QQ: {record['user_id']})")
            ]
            yield event.chain_result(chain)
        else:
            yield event.plain_result("你今日还未抽取老婆")


    @filter.command("帮助", alias={'help'})
    async def help(self, event: AstrMessageEvent):
        help_text = (
            "帮助信息：\n"
            "/今日老婆 - 抽取今日老婆\n"
            "/今日记录 - 查看抽取记录\n"
            "/帮助 - 查看帮助"
        )
        yield event.plain_result(help_text)
