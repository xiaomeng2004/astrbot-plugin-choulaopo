import asyncio
import datetime
import json
import os
import random
from typing import Dict, List, Union

# 导入AstrBot核心API
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.storage import PluginStorage
import astrbot.api.message_components as Comp

# 平台特定导入（保持兼容性）
try:
    from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent
except ImportError:
    AiocqhttpMessageEvent = None

# 配置文件路径
CONFIG_PATH = "choulaopo_config.json"

class ConfigManager:
    """配置管理器，负责加载和保存插件配置"""
    def __init__(self, path):
        self.path = path
        self.config = self.load_config()
        
    def load_config(self):
        """加载配置文件，如果不存在则创建默认配置"""
        if os.path.exists(self.path):
            try:
                with open(self.path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"配置文件加载失败: {e}")
                return self.create_default_config()
        else:
            return self.create_default_config()
            
    def create_default_config(self):
        """创建默认配置"""
        default_config = {"draw_limit": 3}
        self.save_config(default_config)
        return default_config
        
    def save_config(self, config):
        """保存配置到文件"""
        try:
            with open(self.path, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"配置文件保存失败: {e}")
            
    def get_draw_limit(self, group_id):
        """获取群组抽取限制次数（支持按群配置）"""
        # 兼容新旧配置格式
        if isinstance(self.config.get("draw_limit"), dict):
            return self.config["draw_limit"].get(str(group_id), 3)
        else:
            return self.config.get("draw_limit", 3)

    def set_draw_limit(self, group_id, limit):
        """设置群组抽取限制次数"""
        # 转换为按群配置的字典格式
        if not isinstance(self.config.get("draw_limit"), dict):
            self.config["draw_limit"] = {}
        self.config["draw_limit"][str(group_id)] = limit
        self.save_config(self.config)


class ChoulaopoPlugin(Star):
    """抽老婆插件主类（必须继承Star）"""
    def __init__(self, bot_id: str, manifest: dict):
        super().__init__(bot_id, manifest)
        # 初始化配置管理器
        self.config_manager = ConfigManager(CONFIG_PATH)
        
        # 初始化数据存储
        self.storage = PluginStorage("choulaopo_data")
        
        # 从存储加载数据，如果不存在则初始化
        self.daily_records: Dict[str, List] = self.storage.get("daily_records", {})
        self.daily_counts: Dict[str, int] = self.storage.get("daily_counts", {})
        self.wife_stat_today: Dict[str, Dict[str, int]] = self.storage.get("wife_stat_today", {})
        
        # 启动每日重置定时任务
        self.reset_task = asyncio.create_task(self.daily_reset())
        
        # 缓存群成员列表（减少API调用）
        self.member_cache: Dict[str, List] = {}
        self.cache_time: Dict[str, datetime.datetime] = {}

    async def on_disable(self):
        """插件禁用时调用，清理资源"""
        self.reset_task.cancel()
        try:
            await self.reset_task
        except asyncio.CancelledError:
            logger.info("定时任务已取消")

    def save_data(self):
        """保存数据到持久化存储"""
        self.storage.set("daily_records", self.daily_records)
        self.storage.set("daily_counts", self.daily_counts)
        self.storage.set("wife_stat_today", self.wife_stat_today)

    async def _get_group_members(self, event: AstrMessageEvent, group_id: int):
        """获取群成员列表（带缓存）"""
        group_id_str = str(group_id)
        
        # 检查缓存是否有效（5分钟有效期）
        if group_id_str in self.member_cache:
            last_update = self.cache_time.get(group_id_str)
            if last_update and (datetime.datetime.now() - last_update).total_seconds() < 300:
                return self.member_cache[group_id_str]
        
        members = []
        platform = event.get_platform_name()
        
        # OneBot (aiocqhttp) 平台实现
        if platform == "aiocqhttp" and AiocqhttpMessageEvent:
            client = event.bot
            payloads = {"group_id": group_id, "no_cache": True}
            try:
                ret = await client.api.call_action('get_group_member_list', **payloads)
                members = ret
            except Exception as e:
                logger.error(f"获取群成员失败: {e}")
        
        # 其他平台可以在此扩展
        # elif platform == "other_platform":
        #   ...
        
        # 更新缓存
        if members:
            self.member_cache[group_id_str] = members
            self.cache_time[group_id_str] = datetime.datetime.now()
        
        return members

    async def _draw_wife(self, event: AstrMessageEvent, at_selected_user: bool):
        """抽取老婆的核心逻辑"""
        try:
            group_id = event.get_group_id()
        except:
            yield event.plain_result("获取群组信息失败!")
            return

        sender_id = event.get_sender_id()
        draw_limit = self.config_manager.get_draw_limit(group_id)
        user_count = self.daily_counts.get(sender_id, 0)
        
        # 检查抽取次数限制
        if user_count >= draw_limit:
            yield event.plain_result(f"今日已达上限({draw_limit}次,OvO您的后宫已经满啦~)")
            return

        # 获取群成员列表
        members = await self._get_group_members(event, group_id)
        if not members:
            yield event.plain_result("获取群成员失败，请稍后再试")
            return

        # 随机选择一名成员
        selected = random.choice(members)
        user_id = selected.get('user_id')
        nick_name = selected.get('nickname', '未知用户')
        avatar_url = f"https://q4.qlogo.cn/headimg_dl?dst_uin={user_id}&spec=640"

        # 构建消息链
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

        # 更新抽取记录
        if sender_id not in self.daily_records:
            self.daily_records[sender_id] = []
            
        self.daily_records[sender_id].append({
            "user_id": user_id,
            "nickname": nick_name
        })
        
        # 更新抽取次数
        self.daily_counts[sender_id] = user_count + 1
        
        # 更新群组统计
        group_id_str = str(group_id)
        if group_id_str not in self.wife_stat_today:
            self.wife_stat_today[group_id_str] = {}
            
        self.wife_stat_today[group_id_str][str(user_id)] = self.wife_stat_today[group_id_str].get(str(user_id), 0) + 1
        
        # 保存数据
        self.save_data()
        
        yield event.chain_result(chain)

    @filter.command("今日老婆+@", alias={'抽取+@', '抽老婆+@'})
    async def wife_with_at(self, event: AstrMessageEvent):
        """抽取老婆并@被抽中的用户"""
        async for result in self._draw_wife(event, True):
            yield result

    @filter.command("今日老婆", alias={'抽取', '抽老婆'})
    async def wife_without_at(self, event: AstrMessageEvent):
        """抽取老婆但不@被抽中的用户"""
        async for result in self._draw_wife(event, False):
            yield result

    @filter.command("老婆排行", alias={"排行", "老婆榜"})
    async def wife_rank(self, event: AstrMessageEvent):
        """显示今日被抽次数排行榜"""
        try:
            group_id = event.get_group_id()
        except:
            yield event.plain_result("获取群组信息失败!")
            return
            
        group_id_str = str(group_id)
        stat = self.wife_stat_today.get(group_id_str, {})
        
        if not stat:
            yield event.plain_result("本群今日暂无被抽数据")
            return
            
        # 获取群成员映射（用于显示昵称）
        user_map = {}
        members = await self._get_group_members(event, group_id)
        for member in members:
            user_map[str(member['user_id'])] = member.get('nickname', '未知用户')
        
        # 生成排行榜（前10名）
        top = sorted(stat.items(), key=lambda x: x[1], reverse=True)[:10]
        msg = "👑 本群今日老婆被抽排行榜：\n"
        
        for idx, (uid, count) in enumerate(top, 1):
            nickname = user_map.get(uid, "神秘大佬")
            msg += f"{idx}. {nickname} - 被抽中 {count} 次\n"
            
        yield event.plain_result(msg)

    @filter.command("今日记录", alias={'记录'})
    async def today_record(self, event: AstrMessageEvent):
        """查看用户今日的抽取记录"""
        sender_id = event.get_sender_id()
        records = self.daily_records.get(sender_id, [])
        
        if records:
            msg = f"@{sender_id} 您今日共抽取了 {len(records)} 次老婆：\n"
            for idx, record in enumerate(records, 1):
                msg += f"{idx}. {record['nickname']} (QQ: {record['user_id']})\n"
            yield event.plain_result(msg)
        else:
            yield event.plain_result("您今日还未抽取老婆")

    @filter.command("老婆帮助", alias={'帮助'})
    async def help(self, event: AstrMessageEvent):
        """显示插件帮助信息"""
        help_text = (
            "💖 抽老婆插件使用指南 💖\n"
            "=======================\n"
            "/今日老婆 - 随机抽取一位群友作为老婆（会@对方）\n"
            "/今日老婆-@ - 抽取老婆但不会@对方\n"
            "/今日记录 - 查看您今日的所有抽取记录\n"
            "/老婆排行 - 查看本群今日被抽排行榜\n"
            "/老婆帮助 - 显示本帮助信息\n"
            "\n"
            "⚠️ 每日抽取次数有限制，请珍惜机会哦~"
        )
        yield event.plain_result(help_text)

    async def daily_reset(self):
        """每日数据重置任务"""
        while True:
            # 计算到23:59:59的时间
            now = datetime.datetime.now()
            target_time = now.replace(hour=23, minute=59, second=59, microsecond=0)
            
            # 如果当前时间已过目标时间，则设置为明天的目标时间
            if now > target_time:
                target_time += datetime.timedelta(days=1)
                
            # 计算需要休眠的时间
            sleep_time = (target_time - now).total_seconds()
            await asyncio.sleep(sleep_time)
            
            # 重置数据
            self.daily_records.clear()
            self.daily_counts.clear()
            self.wife_stat_today.clear()
            self.save_data()
            
            # 清除成员缓存
            self.member_cache.clear()
            self.cache_time.clear()
            
            logger.info("每日数据已重置")

# 插件注册函数（必须）
@register
def setup(bot_id: str, manifest: dict) -> Star:
    """插件入口函数，AstrBot调用此函数加载插件"""
    return ChoulaopoPlugin(bot_id, manifest)
