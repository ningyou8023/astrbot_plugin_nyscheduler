# astrbot_plugin_nyscheduler

## 项目简介

`astrbot_plugin_nyscheduler` 是一个为 [AstrBot](https://github.com/AstrBotDevs/AstrBot) 设计的“定时推送”插件，聚合每日 60 秒新闻、摸鱼日历、今日金价、AI 资讯、历史今日五类内容，并在设定时间自动推送到指定群组。除定时推送与管理员维护命令外，支持普通用户的无参数查询指令（如 `/新闻`、`/60s`、`/摸鱼`、`/金价`、`/AI资讯`、`/历史今日`）。

当前版本：v1.0.3

## 功能特性

- 定时自动推送“每日 60 秒新闻”、“摸鱼日历”、“今日金价”、“AI 资讯”、“历史今日”到指定群组
- 管理员维护命令：状态查询、手动推送、实时拉取更新
- 统一的群组与推送时间配置
- 实时拉取并发送，不进行本地缓存保存
- 兼容 AstrBot 支持的主要平台
- 支持无参数查询指令，直接按配置的 `format` 回复文本或图片

## 安装与部署

1. 克隆或下载本插件到 AstrBot 插件（/data/plugin/）目录：
   ```bash
   git clone https://github.com/ningyou8023/astrbot_plugin_nyscheduler.git
   ```
2. 进入AstrBot网页插件配置界面，调整相关配置，并保存。

只支持AstrBot4.0及以上版本

解释说明：群聊唯一标识符分为: 前缀:中缀:后缀

下面是所有可选的群组唯一标识符前缀:
| 平台                                | 群组唯一标识符前缀     |
|-------------------------------------|------------------------|
| qq, napcat, Lagrange 之类的         | aiocqhttp              |
| qq 官方 bot                         | qq_official            |
| telegram                            | telegram               |
| 钉钉                                | dingtalk               |
| wechatpadpro微信                    | wechatpadpro           |
| gewechat 微信(虽然已经停止维护)     | gewechat               |
| lark                                | lark                   |
| qq webhook 方法                     | qq_official_webhook    |
| astrbot 网页聊天界面                | webchat                |

下面是所有可选的群组唯一标识符中缀:
| 群组唯一标识符中缀   | 描述       |
|----------------------|------------|
| GroupMessage         | 群组消息   |
| FriendMessage        | 私聊消息   |
| OtherMessage         | 其他消息   |

前缀为`机器人名称`，中缀为`GroupMessage`，后缀为`QQ群号或QQ号`
最终组合结果类似：
```text
CoCo机器人:GroupMessage:QQ群号或QQ号
```

## 使用方法

- 自动推送：插件启动后会在配置的时间自动推送到指定群组。
- 普通查询指令（无需参数）：
  - 新闻类：`/新闻`、`/60s`、`/60秒`、`/早报`
  - 摸鱼类：`/摸鱼`、`/摸鱼日历`
  - 金价类：`/金价`、`/黄金`
  - AI 资讯：`/AI资讯`、`/AI新闻`
  - 历史今日：`/历史今日`
- 管理员命令（使用“××管理”命令组）：
  - 新闻管理：`/新闻管理 status`、`/新闻管理 push`、`/新闻管理 update_news`
  - 摸鱼管理：`/摸鱼管理 status`、`/摸鱼管理 push`、`/摸鱼管理 update`
  - 金价管理：`/金价管理 status`、`/金价管理 push`、`/金价管理 update`
  - AI资讯管理：`/AI资讯管理 status`、`/AI资讯管理 push`、`/AI资讯管理 update`
  - 历史今日管理：`/历史今日管理 status`、`/历史今日管理 push`、`/历史今日管理 update`

特别说明：AI 资讯在星期日和星期一不进行自动推送。

## 项目结构说明

- `main.py`：插件主程序，包含两类内容的获取、推送、命令注册、定时任务等核心逻辑。
- `metadata.yaml`：插件元数据配置文件。
- `_conf_schema.json`：插件配置项的 JSON Schema。
- `LICENSE`：开源许可证文件。
- `README.md`：项目说明文档。

## 配置说明

- 通用：
  - `groups`：接收推送的群组唯一标识符列表。
  - `push_time`：定时推送时间，格式 `HH:MM`。
  - `api_key`：全局接口密钥（可留空）。填写后会在所有请求上附加 `apikey` 参数。
  - `timeout`：请求超时时间，单位秒，默认 `30`。

- 新闻：
  - `enable_news`：是否开启新闻推送。
  - `news_api`：新闻接口地址，默认 `https://api.nycnm.cn/API/60s.php`。
  - `format`：接口返回格式，`text`/`image`。

- 摸鱼：
  - `enable_moyu`：是否开启摸鱼推送。
  - `moyu_format`：接口返回格式，`text`/`image`，默认 `image`。
  - `moyu_api`：摸鱼接口地址，默认 `https://api.nycnm.cn/API/moyu.php`。

- 金价：
  - `enable_gold`：是否开启金价推送。
  - `gold_format`：接口返回格式，`text`/`image`，默认 `image`。
  - `gold_api`：金价接口地址，默认 `https://api.nycnm.cn/API/jinjia.php`。

- AI 资讯：
  - `enable_ai`：是否开启 AI 资讯推送。
  - `ai_format`：接口返回格式，`text`/`image`，默认 `image`。
  - `ai_api`：AI 资讯接口地址，默认 `https://api.nycnm.cn/API/aizixun.php`。
  - 自动推送遵循统一的 `push_time`，并在星期日与星期一不推送。

- 历史今日：
  - `enable_history`：是否开启历史今日推送。
  - `history_format`：接口返回格式，`text`/`image`，默认 `image`。
  - `history_api`：历史今日接口地址，默认 `https://api.nycnm.cn/API/history.php`。

接口示例：
- 所有接口均可选附加 `apikey` 参数：`?apikey=YOUR_KEY`
- 新闻 文本：`https://api.nycnm.cn/API/60s.php?format=text`
- 新闻 图片：`https://api.nycnm.cn/API/60s.php?format=image`
- 摸鱼 文本：`https://api.nycnm.cn/API/moyu.php?format=text`
- 摸鱼 图片：`https://api.nycnm.cn/API/moyu.php?format=image`
- 金价 文本：`https://api.nycnm.cn/API/jinjia.php?format=text`
- 金价 图片：`https://api.nycnm.cn/API/jinjia.php?format=image`
- AI 资讯 文本：`https://api.nycnm.cn/API/aizixun.php?format=text`
- AI 资讯 图片：`https://api.nycnm.cn/API/aizixun.php?format=image`
- 历史今日 文本：`https://api.nycnm.cn/API/history.php?format=text`
- 历史今日 图片：`https://api.nycnm.cn/API/history.php?format=image`

## 许可证说明

本项目默认采用 AGPL-3.0 License，详见 LICENSE 文件。
