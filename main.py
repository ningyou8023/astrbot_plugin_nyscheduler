import asyncio
import datetime
import os
import tempfile
import traceback
from typing import Any, Tuple

import aiohttp
from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register
from astrbot.core.message.message_event_result import MessageChain


@register(
    "astrbot_nyscheduler",
    "柠柚",
    "这是 AstrBot 的一个定时推送插件。包含60s，摸鱼日历，今日金价，AI资讯。",
    "1.0.0",
)
class Daily60sNewsPlugin(Star):
    """
    AstrBot 每日60s新闻插件，支持定时推送和命令获取。
    """

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.groups = self.config.groups
        self.push_time = self.config.push_time
        self.news_api = getattr(self.config, "news_api", "https://api.nycnm.cn/API/60s.php")
        self.format = getattr(self.config, "format", "image")
        self.moyu_format = getattr(self.config, "moyu_format", "image")
        self.moyu_api = getattr(self.config, "moyu_api", "https://api.nycnm.cn/API/moyu.php")
        self.enable_news = getattr(self.config, "enable_news", True)
        self.enable_moyu = getattr(self.config, "enable_moyu", True)
        self.enable_gold = getattr(self.config, "enable_gold", True)
        self.enable_ai = getattr(self.config, "enable_ai", True)
        self.gold_format = getattr(self.config, "gold_format", "image")
        self.gold_api = getattr(self.config, "gold_api", "https://api.nycnm.cn/API/jinjia.php")
        self.ai_format = getattr(self.config, "ai_format", "image")
        self.ai_api = getattr(self.config, "ai_api", "https://api.nycnm.cn/API/aizixun.php")
        logger.info(f"插件配置: {self.config}")
        self._monitoring_task = asyncio.create_task(self._daily_task())

    @filter.command_group("新闻管理")
    def mnews(self):
        """新闻命令分组"""
        pass

    # 取消普通获取命令，保留管理员与定时推送

    @filter.permission_type(filter.PermissionType.ADMIN)
    @mnews.command("status")
    async def check_status(self, event: AstrMessageEvent):
        """
        检查插件状态（仅管理员）
        """
        sleep_time = self._calculate_sleep_time()
        hours = int(sleep_time / 3600)
        minutes = int((sleep_time % 3600) / 60)

        yield event.plain_result(
            f"每日60s新闻插件正在运行\n"
            f"推送时间: {self.push_time}\n"
            f"接口返回格式: {self.format}\n"
            f"距离下次推送还有: {hours}小时{minutes}分钟"
        )

    

    @filter.permission_type(filter.PermissionType.ADMIN)
    @mnews.command("push")
    async def push_news(self, event: AstrMessageEvent):
        """
        手动向目标群组推送今日60s新闻（仅管理员）
        """
        await self._send_daily_news_to_groups()
        yield event.plain_result(f"{event.get_sender_name()}:已成功向群组推送新闻")

    # 取消普通 text/image 命令

    @filter.permission_type(filter.PermissionType.ADMIN)
    @mnews.command("update_news")
    async def update_news_files(self, event: AstrMessageEvent):
        content, ok = await self._fetch_news_text()
        if ok:
            yield event.plain_result(f"{event.get_sender_name()}:已拉取最新新闻\n{content[:50]}...")
        else:
            yield event.plain_result(f"{event.get_sender_name()}:获取失败 {content}")

    @mnews.command("今日")
    async def get_today_news(self, event: AstrMessageEvent):
        try:
            if self.format == "image":
                path, ok = await self._fetch_news_image_path()
                if ok:
                    await event.send(MessageChain().file_image(path))
                    try:
                        os.remove(path)
                    except Exception:
                        pass
                else:
                    await event.send(event.plain_result(str(path)))
            else:
                content, ok = await self._fetch_news_text()
                if ok:
                    await event.send(event.plain_result(content))
                else:
                    await event.send(event.plain_result(str(content)))
        except Exception as e:
            await event.send(event.plain_result(f"获取新闻失败: {e}"))

    @filter.command("新闻")
    async def cmd_news(self, event: AstrMessageEvent):
        try:
            if self.format == "image":
                path, ok = await self._fetch_news_image_path()
                if ok:
                    await event.send(MessageChain().file_image(path))
                    try:
                        os.remove(path)
                    except Exception:
                        pass
                else:
                    await event.send(event.plain_result(str(path)))
            else:
                content, ok = await self._fetch_news_text()
                if ok:
                    await event.send(event.plain_result(content))
                else:
                    await event.send(event.plain_result(str(content)))
        except Exception as e:
            await event.send(event.plain_result(f"获取新闻失败: {e}"))

    @filter.command("60s")
    async def cmd_60s(self, event: AstrMessageEvent):
        await self.cmd_news(event)

    @filter.command("60秒")
    async def cmd_60sec(self, event: AstrMessageEvent):
        await self.cmd_news(event)

    @filter.command("早报")
    async def cmd_morning_news(self, event: AstrMessageEvent):
        await self.cmd_news(event)

    async def terminate(self):
        """插件卸载时调用"""
        if self._monitoring_task:
            self._monitoring_task.cancel()
        if hasattr(self, "_moyu_task") and self._moyu_task:
            self._moyu_task.cancel()
        if hasattr(self, "_gold_task") and self._gold_task:
            self._gold_task.cancel()
        if hasattr(self, "_ai_task") and self._ai_task:
            self._ai_task.cancel()
        logger.info("每日60s新闻插件: 定时任务已停止")

    async def _fetch_news_text(self) -> Tuple[str, bool]:
        retries = 3
        timeout = 10
        fmt = self.format
        if fmt == "image":
            fmt = "json"
        date = datetime.datetime.now().strftime("%Y-%m-%d")
        for attempt in range(retries):
            try:
                url = f"{self.news_api}?date={date}&format={fmt}"
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, timeout=timeout) as response:
                        if response.status != 200:
                            raise Exception(f"API返回错误代码: {response.status}")
                        if fmt == "json":
                            data = await response.json()
                            payload = data.get("data", {}) if isinstance(data, dict) else {}
                            date_str = payload.get("date") or date
                            tip = payload.get("tip") or ""
                            news_list = payload.get("news") or []
                            lines = [f"{date_str} 每日60秒新闻", *(f"• {item}" for item in news_list)]
                            if tip:
                                lines.append(f"提示：{tip}")
                            return "\n".join(lines), True
                        else:
                            content = await response.read()
                            text = content.decode("utf-8", errors="ignore")
                            return text, True
            except Exception as e:
                logger.error(f"[mnews] 请求失败 {attempt + 1}/{retries}: {e}")
                if attempt == retries - 1:
                    return f"接口报错，请联系管理员:{e}", False
                await asyncio.sleep(1)

    async def _fetch_news_image_path(self) -> Tuple[str, bool]:
        retries = 3
        timeout = 10
        fmt = self.format
        if fmt == "text":
            fmt = "json"
        date = datetime.datetime.now().strftime("%Y-%m-%d")
        for attempt in range(retries):
            try:
                url = f"{self.news_api}?date={date}&format={fmt}"
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, timeout=timeout) as response:
                        if response.status != 200:
                            raise Exception(f"API返回错误代码: {response.status}")
                        if fmt == "json":
                            data = await response.json()
                            payload = data.get("data", {}) if isinstance(data, dict) else {}
                            img_url = payload.get("image") or payload.get("cover")
                            if not img_url:
                                raise Exception("JSON中未找到图片URL")
                            async with session.get(img_url, timeout=timeout) as img_resp:
                                if img_resp.status != 200:
                                    raise Exception(f"图片下载失败，状态码: {img_resp.status}")
                                img_bytes = await img_resp.read()
                                f = tempfile.NamedTemporaryFile(delete=False, suffix=".jpeg")
                                try:
                                    f.write(img_bytes)
                                    f.flush()
                                    return f.name, True
                                finally:
                                    f.close()
                        else:
                            img_bytes = await response.read()
                            f = tempfile.NamedTemporaryFile(delete=False, suffix=".jpeg")
                            try:
                                f.write(img_bytes)
                                f.flush()
                                return f.name, True
                            finally:
                                f.close()
            except Exception as e:
                logger.error(f"[mnews] 请求失败 {attempt + 1}/{retries}: {e}")
                if attempt == retries - 1:
                    return f"接口报错，请联系管理员:{e}", False
                await asyncio.sleep(1)

    async def _send_daily_news_to_groups(self):
        """
        推送新闻到所有目标群组
        """
        try:
            if self.format == "image":
                news_path, ok = await self._fetch_news_image_path()
                if not ok:
                    raise Exception(str(news_path))
                for target in self.config.groups:
                    mc = MessageChain().file_image(news_path)
                    await self.context.send_message(target, mc)
                    await asyncio.sleep(2)
                try:
                    os.remove(news_path)
                except Exception:
                    pass
            else:
                news_content, ok = await self._fetch_news_text()
                if not ok:
                    raise Exception(str(news_content))
                for target in self.config.groups:
                    mc = MessageChain().message(news_content)
                    await self.context.send_message(target, mc)
                    await asyncio.sleep(2)
        except Exception as e:
            error_message = str(e) if str(e) else "未知错误"
            logger.error(f"[每日新闻] 推送新闻失败: {error_message}")
            logger.exception("详细错误信息：")

    def _calculate_sleep_time(self) -> float:
        """
        计算距离下次推送的秒数
        :return: 距离下次推送的秒数
        """
        now = datetime.datetime.now()
        hour, minute = map(int, self.push_time.split(":"))
        next_push = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if next_push <= now:
            next_push += datetime.timedelta(days=1)
        return (next_push - now).total_seconds()

    

    async def _daily_task(self):
        """
        定时任务主循环，定时推送新闻
        """
        while True:
            try:
                sleep_time = self._calculate_sleep_time()
                logger.info(f"[定时推送] 下次推送将在 {sleep_time / 3600:.2f} 小时后")
                await asyncio.sleep(sleep_time)
                if self.enable_news:
                    await self._send_daily_news_to_groups()
                if self.enable_moyu:
                    await self._moyu_send_to_groups()
                if self.enable_gold:
                    await self._gold_send_to_groups()
                if self.enable_ai:
                    _w = datetime.datetime.now().weekday()
                    if _w not in (6, 0):
                        await self._ai_send_to_groups()
                    else:
                        logger.info("[AI资讯] 星期日或星期一不推送")
                await asyncio.sleep(60)
            except Exception as e:
                logger.error(f"[nyscheduler] 定时任务出错: {e}")
                traceback.print_exc()
                await asyncio.sleep(300)

    @filter.command_group("摸鱼管理")
    def moyu(self):
        pass

    # 取消普通摸鱼获取命令，保留管理员与定时推送

    @filter.permission_type(filter.PermissionType.ADMIN)
    @moyu.command("status")
    async def cmd_status(self, event: AstrMessageEvent):
        sleep_time = self._calculate_sleep_time()
        h = int(sleep_time / 3600)
        m = int((sleep_time % 3600) / 60)
        yield event.plain_result(
            f"摸鱼日历运行中\n推送时间: {self.push_time}\n默认格式: {self.moyu_format}\n距离下次推送: {h}小时{m}分钟"
        )

    

    @filter.permission_type(filter.PermissionType.ADMIN)
    @moyu.command("push")
    async def cmd_push(self, event: AstrMessageEvent):
        await self._moyu_send_to_groups()
        yield event.plain_result(f"{event.get_sender_name()}: 已向群组推送摸鱼日历")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @moyu.command("update")
    async def cmd_update(self, event: AstrMessageEvent):
        content, ok = await self._moyu_fetch_text()
        if ok:
            yield event.plain_result(f"{event.get_sender_name()}:已拉取最新摸鱼\n{content[:50]}...")
        else:
            yield event.plain_result(f"{event.get_sender_name()}:获取失败 {content}")

    @moyu.command("今日")
    async def moyu_today(self, event: AstrMessageEvent):
        try:
            fmt = self.moyu_format
            if fmt == "text":
                content, ok = await self._moyu_fetch_text()
                if ok:
                    yield event.plain_result(content)
                else:
                    yield event.plain_result(str(content))
            else:
                path, ok = await self._moyu_fetch_image_path()
                if ok:
                    yield MessageChain().file_image(path)
                    try:
                        os.remove(path)
                    except Exception:
                        pass
                else:
                    yield event.plain_result(str(path))
        except Exception as e:
            yield event.plain_result(f"获取摸鱼日历失败: {e}")
    async def _moyu_fetch_text(self) -> Tuple[str, bool]:
        retries = 3
        timeout = 10
        fmt = self.moyu_format
        if fmt == "image":
            fmt = "json"
        for attempt in range(retries):
            try:
                url = f"{self.moyu_api}?format={fmt}"
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, timeout=timeout) as resp:
                        if resp.status != 200:
                            raise Exception(f"状态码: {resp.status}")
                        if fmt == "json":
                            data = await resp.json(content_type=None)
                            txt = None
                            def walk(v):
                                nonlocal txt
                                if isinstance(v, dict):
                                    for vv in v.values():
                                        walk(vv)
                                elif isinstance(v, list):
                                    for vv in v:
                                        walk(vv)
                                elif isinstance(v, str):
                                    txt = txt or v
                            walk(data)
                            return (txt or str(data)), True
                        else:
                            content = await resp.read()
                            text = content.decode("utf-8", errors="ignore")
                            return text, True
            except Exception as e:
                logger.error(f"[moyu] 请求失败 {attempt + 1}/{retries}: {e}")
                if attempt == retries - 1:
                    return f"接口报错: {e}", False
                await asyncio.sleep(1)

    async def _moyu_fetch_image_path(self) -> Tuple[str, bool]:
        retries = 3
        timeout = 10
        fmt = self.moyu_format
        if fmt == "text":
            fmt = "json"
        for attempt in range(retries):
            try:
                url = f"{self.moyu_api}?format={fmt}"
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, timeout=timeout) as resp:
                        if resp.status != 200:
                            raise Exception(f"状态码: {resp.status}")
                        if fmt == "json":
                            data = await resp.json(content_type=None)
                            img_url = None
                            def walk(v):
                                nonlocal img_url
                                if isinstance(v, dict):
                                    for vv in v.values():
                                        walk(vv)
                                elif isinstance(v, list):
                                    for vv in v:
                                        walk(vv)
                                elif isinstance(v, str):
                                    if v.startswith("http") and (".jpg" in v or ".jpeg" in v or ".png" in v):
                                        img_url = img_url or v
                            walk(data)
                            if not img_url:
                                raise Exception("JSON未找到图片URL")
                            async with session.get(img_url, timeout=timeout) as ir:
                                if ir.status != 200:
                                    raise Exception(f"图片状态码: {ir.status}")
                                b = await ir.read()
                                f = tempfile.NamedTemporaryFile(delete=False, suffix=".jpeg")
                                try:
                                    f.write(b)
                                    f.flush()
                                    return f.name, True
                                finally:
                                    f.close()
                        else:
                            b = await resp.read()
                            f = tempfile.NamedTemporaryFile(delete=False, suffix=".jpeg")
                            try:
                                f.write(b)
                                f.flush()
                                return f.name, True
                            finally:
                                f.close()
            except Exception as e:
                logger.error(f"[moyu] 请求失败 {attempt + 1}/{retries}: {e}")
                if attempt == retries - 1:
                    return f"接口报错: {e}", False
                await asyncio.sleep(1)

    async def _moyu_send_to_groups(self):
        try:
            if self.moyu_format == "text":
                content, ok = await self._moyu_fetch_text()
                if not ok:
                    raise Exception(str(content))
                for target in self.config.groups:
                    mc = MessageChain().message(content)
                    await self.context.send_message(target, mc)
                    await asyncio.sleep(2)
            else:
                path, ok = await self._moyu_fetch_image_path()
                if not ok:
                    raise Exception(str(path))
                for target in self.config.groups:
                    mc = MessageChain().file_image(path)
                    await self.context.send_message(target, mc)
                    await asyncio.sleep(2)
                try:
                    os.remove(path)
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"[moyu] 推送失败: {e}")

    def _moyu_calculate_sleep_time(self) -> float:
        now = datetime.datetime.now()
        h, m = map(int, self.moyu_push_time.split(":"))
        next_push = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if next_push <= now:
            next_push += datetime.timedelta(days=1)
        return (next_push - now).total_seconds()

    

    async def _moyu_daily_task(self):
        pass

    @filter.command_group("金价管理")
    def gold(self):
        pass

    @filter.permission_type(filter.PermissionType.ADMIN)
    @gold.command("status")
    async def gold_status(self, event: AstrMessageEvent):
        sleep_time = self._calculate_sleep_time()
        h = int(sleep_time / 3600)
        m = int((sleep_time % 3600) / 60)
        yield event.plain_result(
            f"今日金价运行中\n推送时间: {self.push_time}\n默认格式: {self.gold_format}\n距离下次推送: {h}小时{m}分钟"
        )

    

    @filter.permission_type(filter.PermissionType.ADMIN)
    @gold.command("push")
    async def gold_push(self, event: AstrMessageEvent):
        await self._gold_send_to_groups()
        yield event.plain_result(f"{event.get_sender_name()}: 已向群组推送今日金价")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @gold.command("update")
    async def gold_update(self, event: AstrMessageEvent):
        content, ok = await self._gold_fetch_text()
        if ok:
            yield event.plain_result(f"{event.get_sender_name()}:已拉取最新金价\n{content[:50]}...")
        else:
            yield event.plain_result(f"{event.get_sender_name()}:获取失败 {content}")

    @gold.command("今日")
    async def gold_today(self, event: AstrMessageEvent):
        try:
            fmt = self.gold_format
            if fmt == "text":
                content, ok = await self._gold_fetch_text()
                if ok:
                    yield event.plain_result(content)
                else:
                    yield event.plain_result(str(content))
            else:
                path, ok = await self._gold_fetch_image_path()
                if ok:
                    yield MessageChain().file_image(path)
                    try:
                        os.remove(path)
                    except Exception:
                        pass
                else:
                    yield event.plain_result(str(path))
        except Exception as e:
            yield event.plain_result(f"获取金价失败: {e}")
    async def _gold_fetch_text(self) -> Tuple[str, bool]:
        retries = 3
        timeout = 10
        fmt = self.gold_format
        if fmt == "image":
            fmt = "json"
        for attempt in range(retries):
            try:
                url = f"{self.gold_api}?format={fmt}"
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, timeout=timeout) as resp:
                        if resp.status != 200:
                            raise Exception(f"状态码: {resp.status}")
                        if fmt == "json":
                            data = await resp.json(content_type=None)
                            txt = None
                            def walk(v):
                                nonlocal txt
                                if isinstance(v, dict):
                                    for vv in v.values():
                                        walk(vv)
                                elif isinstance(v, list):
                                    for vv in v:
                                        walk(vv)
                                elif isinstance(v, str):
                                    txt = txt or v
                            walk(data)
                            return (txt or str(data)), True
                        else:
                            content = await resp.read()
                            text = content.decode("utf-8", errors="ignore")
                            return text, True
            except Exception as e:
                logger.error(f"[gold] 请求失败 {attempt + 1}/{retries}: {e}")
                if attempt == retries - 1:
                    return f"接口报错: {e}", False
                await asyncio.sleep(1)

    async def _gold_fetch_image_path(self) -> Tuple[str, bool]:
        retries = 3
        timeout = 10
        fmt = self.gold_format
        if fmt == "text":
            fmt = "json"
        for attempt in range(retries):
            try:
                url = f"{self.gold_api}?format={fmt}"
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, timeout=timeout) as resp:
                        if resp.status != 200:
                            raise Exception(f"状态码: {resp.status}")
                        if fmt == "json":
                            data = await resp.json(content_type=None)
                            img_url = None
                            def walk(v):
                                nonlocal img_url
                                if isinstance(v, dict):
                                    for vv in v.values():
                                        walk(vv)
                                elif isinstance(v, list):
                                    for vv in v:
                                        walk(vv)
                                elif isinstance(v, str):
                                    if v.startswith("http") and (".jpg" in v or ".jpeg" in v or ".png" in v):
                                        img_url = img_url or v
                            walk(data)
                            if not img_url:
                                raise Exception("JSON未找到图片URL")
                            async with session.get(img_url, timeout=timeout) as ir:
                                if ir.status != 200:
                                    raise Exception(f"图片状态码: {ir.status}")
                                b = await ir.read()
                                f = tempfile.NamedTemporaryFile(delete=False, suffix=".jpeg")
                                try:
                                    f.write(b)
                                    f.flush()
                                    return f.name, True
                                finally:
                                    f.close()
                        else:
                            b = await resp.read()
                            f = tempfile.NamedTemporaryFile(delete=False, suffix=".jpeg")
                            try:
                                f.write(b)
                                f.flush()
                                return f.name, True
                            finally:
                                f.close()
            except Exception as e:
                logger.error(f"[gold] 请求失败 {attempt + 1}/{retries}: {e}")
                if attempt == retries - 1:
                    return f"接口报错: {e}", False
                await asyncio.sleep(1)

    async def _gold_send_to_groups(self):
        try:
            if self.gold_format == "text":
                content, ok = await self._gold_fetch_text()
                if not ok:
                    raise Exception(str(content))
                for target in self.config.groups:
                    mc = MessageChain().message(content)
                    await self.context.send_message(target, mc)
                    await asyncio.sleep(2)
            else:
                path, ok = await self._gold_fetch_image_path()
                if not ok:
                    raise Exception(str(path))
                for target in self.config.groups:
                    mc = MessageChain().file_image(path)
                    await self.context.send_message(target, mc)
                    await asyncio.sleep(2)
                try:
                    os.remove(path)
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"[gold] 推送失败: {e}")

    def _gold_calculate_sleep_time(self) -> float:
        now = datetime.datetime.now()
        h, m = map(int, self.gold_push_time.split(":"))
        next_push = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if next_push <= now:
            next_push += datetime.timedelta(days=1)
        return (next_push - now).total_seconds()

    

    async def _gold_daily_task(self):
        pass

    @filter.command_group("AI资讯管理")
    def ai(self):
        pass

    @filter.permission_type(filter.PermissionType.ADMIN)
    @ai.command("status")
    async def ai_status(self, event: AstrMessageEvent):
        sleep_time = self._calculate_sleep_time()
        h = int(sleep_time / 3600)
        m = int((sleep_time % 3600) / 60)
        yield event.plain_result(
            f"AI资讯运行中\n推送时间: {self.push_time}\n默认格式: {self.ai_format}\n距离下次推送: {h}小时{m}分钟"
        )

    

    @filter.permission_type(filter.PermissionType.ADMIN)
    @ai.command("push")
    async def ai_push(self, event: AstrMessageEvent):
        await self._ai_send_to_groups()
        yield event.plain_result(f"{event.get_sender_name()}: 已向群组推送AI资讯")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @ai.command("update")
    async def ai_update(self, event: AstrMessageEvent):
        content, ok = await self._ai_fetch_text()
        if ok:
            yield event.plain_result(f"{event.get_sender_name()}:已拉取最新AI资讯\n{content[:50]}...")
        else:
            yield event.plain_result(f"{event.get_sender_name()}:获取失败 {content}")

    @ai.command("今日")
    async def ai_today(self, event: AstrMessageEvent):
        try:
            fmt = self.ai_format
            if fmt == "text":
                content, ok = await self._ai_fetch_text()
                if ok:
                    yield event.plain_result(content)
                else:
                    yield event.plain_result(str(content))
            else:
                path, ok = await self._ai_fetch_image_path()
                if ok:
                    yield MessageChain().file_image(path)
                    try:
                        os.remove(path)
                    except Exception:
                        pass
                else:
                    yield event.plain_result(str(path))
        except Exception as e:
            yield event.plain_result(f"获取AI资讯失败: {e}")
    async def _ai_fetch_text(self) -> Tuple[str, bool]:
        retries = 3
        timeout = 10
        fmt = self.ai_format
        if fmt == "image":
            fmt = "json"
        for attempt in range(retries):
            try:
                url = f"{self.ai_api}?format={fmt}"
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, timeout=timeout) as resp:
                        if resp.status != 200:
                            raise Exception(f"状态码: {resp.status}")
                        if fmt == "json":
                            data = await resp.json(content_type=None)
                            txt = None
                            def walk(v):
                                nonlocal txt
                                if isinstance(v, dict):
                                    for vv in v.values():
                                        walk(vv)
                                elif isinstance(v, list):
                                    for vv in v:
                                        walk(vv)
                                elif isinstance(v, str):
                                    txt = txt or v
                            walk(data)
                            return (txt or str(data)), True
                        else:
                            content = await resp.read()
                            text = content.decode("utf-8", errors="ignore")
                            return text, True
            except Exception as e:
                logger.error(f"[ai] 请求失败 {attempt + 1}/{retries}: {e}")
                if attempt == retries - 1:
                    return f"接口报错: {e}", False
                await asyncio.sleep(1)

    async def _ai_fetch_image_path(self) -> Tuple[str, bool]:
        retries = 3
        timeout = 10
        fmt = self.ai_format
        if fmt == "text":
            fmt = "json"
        for attempt in range(retries):
            try:
                url = f"{self.ai_api}?format={fmt}"
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, timeout=timeout) as resp:
                        if resp.status != 200:
                            raise Exception(f"状态码: {resp.status}")
                        if fmt == "json":
                            data = await resp.json(content_type=None)
                            img_url = None
                            def walk(v):
                                nonlocal img_url
                                if isinstance(v, dict):
                                    for vv in v.values():
                                        walk(vv)
                                elif isinstance(v, list):
                                    for vv in v:
                                        walk(vv)
                                elif isinstance(v, str):
                                    if v.startswith("http") and (".jpg" in v or ".jpeg" in v or ".png" in v):
                                        img_url = img_url or v
                            walk(data)
                            if not img_url:
                                raise Exception("JSON未找到图片URL")
                            async with session.get(img_url, timeout=timeout) as ir:
                                if ir.status != 200:
                                    raise Exception(f"图片状态码: {ir.status}")
                                b = await ir.read()
                                f = tempfile.NamedTemporaryFile(delete=False, suffix=".jpeg")
                                try:
                                    f.write(b)
                                    f.flush()
                                    return f.name, True
                                finally:
                                    f.close()
                        else:
                            b = await resp.read()
                            f = tempfile.NamedTemporaryFile(delete=False, suffix=".jpeg")
                            try:
                                f.write(b)
                                f.flush()
                                return f.name, True
                            finally:
                                f.close()
            except Exception as e:
                logger.error(f"[ai] 请求失败 {attempt + 1}/{retries}: {e}")
                if attempt == retries - 1:
                    return f"接口报错: {e}", False
                await asyncio.sleep(1)

    async def _ai_send_to_groups(self):
        try:
            if self.ai_format == "text":
                content, ok = await self._ai_fetch_text()
                if not ok:
                    raise Exception(str(content))
                for target in self.config.groups:
                    mc = MessageChain().message(content)
                    await self.context.send_message(target, mc)
                    await asyncio.sleep(2)
            else:
                path, ok = await self._ai_fetch_image_path()
                if not ok:
                    raise Exception(str(path))
                for target in self.config.groups:
                    mc = MessageChain().file_image(path)
                    await self.context.send_message(target, mc)
                    await asyncio.sleep(2)
                try:
                    os.remove(path)
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"[ai] 推送失败: {e}")

    def _ai_calculate_sleep_time(self) -> float:
        now = datetime.datetime.now()
        h, m = map(int, self.ai_push_time.split(":"))
        next_push = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if next_push <= now:
            next_push += datetime.timedelta(days=1)
        return (next_push - now).total_seconds()

    

    async def _ai_daily_task(self):
        pass
    @filter.command("摸鱼")
    async def cmd_moyu_simple(self, event: AstrMessageEvent):
        try:
            if self.moyu_format == "text":
                content, ok = await self._moyu_fetch_text()
                if ok:
                    await event.send(event.plain_result(content))
                else:
                    await event.send(event.plain_result(str(content)))
            else:
                path, ok = await self._moyu_fetch_image_path()
                if ok:
                    await event.send(MessageChain().file_image(path))
                    try:
                        os.remove(path)
                    except Exception:
                        pass
                else:
                    await event.send(event.plain_result(str(path)))
        except Exception as e:
            await event.send(event.plain_result(f"获取摸鱼日历失败: {e}"))

    @filter.command("摸鱼日历")
    async def cmd_moyu_calendar(self, event: AstrMessageEvent):
        await self.cmd_moyu_simple(event)
    @filter.command("金价")
    async def cmd_gold_simple(self, event: AstrMessageEvent):
        try:
            if self.gold_format == "text":
                content, ok = await self._gold_fetch_text()
                if ok:
                    await event.send(event.plain_result(content))
                else:
                    await event.send(event.plain_result(str(content)))
            else:
                path, ok = await self._gold_fetch_image_path()
                if ok:
                    await event.send(MessageChain().file_image(path))
                    try:
                        os.remove(path)
                    except Exception:
                        pass
                else:
                    await event.send(event.plain_result(str(path)))
        except Exception as e:
            await event.send(event.plain_result(f"获取金价失败: {e}"))

    @filter.command("黄金")
    async def cmd_gold_alt(self, event: AstrMessageEvent):
        await self.cmd_gold_simple(event)
    @filter.command("AI资讯")
    async def cmd_ai_simple(self, event: AstrMessageEvent):
        try:
            if self.ai_format == "text":
                content, ok = await self._ai_fetch_text()
                if ok:
                    await event.send(event.plain_result(content))
                else:
                    await event.send(event.plain_result(str(content)))
            else:
                path, ok = await self._ai_fetch_image_path()
                if ok:
                    await event.send(MessageChain().file_image(path))
                    try:
                        os.remove(path)
                    except Exception:
                        pass
                else:
                    await event.send(event.plain_result(str(path)))
        except Exception as e:
            await event.send(event.plain_result(f"获取AI资讯失败: {e}"))

    @filter.command("AI新闻")
    async def cmd_ai_news(self, event: AstrMessageEvent):
        await self.cmd_ai_simple(event)
