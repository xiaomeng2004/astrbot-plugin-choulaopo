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
wife_stat_today = {}  # {group_id: {被抽user_id: 次数}}

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
            
    def get_draw_limit(self, group_id):
        # 支持按群配置，兼容老格式
        if isinstance(self.config.get("draw_limit"), dict):
            return self.config["draw_limit"].get(str(group_id), 3)
        else:
            return self.config.get("draw_limit", 3)

    def set_draw_limit(self, group_id, limit):
        # 支持按群配置，兼容老格式
        if not isinstance(self.config.get("draw_limit"), dict):
            self.config["draw_limit"] = {}
        self.config["draw_limit"][str(group_id)] = limit
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
        wife_stat_today.clear()
        logger.info("Daily records, counts and today wife stats cleared.")

    # 辅助方法：处理抽取逻辑，根据参数决定是否At被抽取用户
    # daily_records[sender_id] 现为列表，每次抽取追加一条记录，便于用户查询所有抽取结果
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
        draw_limit = self.config_manager.get_draw_limit(group_id)
        user_count = daily_counts.get(sender_id, 0)
        
        if user_count >= draw_limit:
            yield event.plain_result(f"今日已达上限({draw_limit}次,OvO您的后宫已经满啦~)")
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
                Comp.At(qq=user_id),
                Comp.Plain(" UwU快去疼爱ta叭~")
            ]
        else:
            chain = [
                Comp.At(qq=sender_id),
                Comp.Plain(" 你的今日老婆是"),
                Comp.Image.fromURL(avatar_url),
                Comp.Plain(nick_name),
                Comp.Plain(" UwU快去疼爱ta叭~")
            ]

        # 记录抽取结果到daily_records
        # 兼容首次抽取和老数据格式，确保为列表
        if sender_id not in daily_records or not isinstance(daily_records[sender_id], list):
            daily_records[sender_id] = []
        daily_records[sender_id].append({
            "user_id": user_id,
            "nickname": nick_name
        })
        daily_counts[sender_id] = user_count + 1

        # 统计被抽次数，按群隔离
        group_id_str = str(group_id)
        # 今日统计
        if group_id_str not in wife_stat_today:
            wife_stat_today[group_id_str] = {}
        wife_stat_today[group_id_str][str(user_id)] = wife_stat_today[group_id_str].get(str(user_id), 0) + 1
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

    @filter.command("老婆排行", alias={"排行", "老婆榜"})
    async def wife_rank(self, event: AstrMessageEvent):
        group_id = event.get_group_id()
        group_id_str = str(group_id)
        # 兼容不同平台的参数获取
        if hasattr(event, "get_plain_text"):
            text = event.get_plain_text().strip()
        elif hasattr(event, "message"):
            text = str(event.message).strip()
        else:
            text = ""
        # 只统计今日排行，无需参数分支
        # 获取群成员列表，建立user_id到nickname的映射
        user_map = {}
        if event.get_platform_name() == "aiocqhttp":
            client = event.bot
            payloads = {"group_id": group_id, "no_cache": True}
            ret = await client.api.call_action('get_group_member_list', **payloads)
            for member in ret:
                user_map[str(member['user_id'])] = member.get('nickname', '')
        stat = wife_stat_today.get(group_id_str, {})
        if not stat:
            yield event.plain_result(f"本群暂无今日被抽数据")
            return
        # 排序并取前10
        top = sorted(stat.items(), key=lambda x: x[1], reverse=True)[:10]
        msg = f"本群今日老婆被抽排行榜：\n"
        for idx, (uid, count) in enumerate(top, 1):
            nickname = user_map.get(uid, "")
            if nickname:
                msg += f"{idx}. {nickname} 被抽{count}次\n"
            else:
                msg += f"{idx}. [未知成员] 被抽{count}次\n"
        yield event.plain_result(msg)

    # 其他方法保持不变...

    @filter.command("今日记录", alias={'记录'})
    async def today_record(self, event: AstrMessageEvent):
        sender_id = event.get_sender_id()
        records = daily_records.get(sender_id)
        if records:
            if not isinstance(records, list):
                records = [records]
            msg = f"@{sender_id}你今日共抽取了{len(records)}次老婆：\n"
            for idx, record in enumerate(records, 1):
                msg += f"\n第{idx}次：{record['nickname']}(QQ: {record['user_id']})"
            yield event.plain_result(msg)
        else:
            yield event.plain_result("你今日还未抽取老婆")

    @filter.command("帮助", alias={'老婆帮助'})
    async def help(self, event: AstrMessageEvent):
        help_text = (
            "帮助信息：\n"
            "/今日老婆 - 抽取今日老婆（@被抽用户）\n"
            "/今日老婆-@ - 不At被抽取用户\n"
            "/今日记录 - 查看今日所有抽取记录\n"
            "/老婆排行 - 查看本群今日被抽排行榜\n"
            "/帮助 - 查看帮助"
        )
        yield event.plain_result(help_text)
