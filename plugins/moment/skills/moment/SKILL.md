---
name: moment
description: >
  Operate Moment, the family timeline, over HTTP: chains, moments, feed,
  comments, media, share links, search, and monthly recaps. Use when the
  user mentions Moment, 时刻, 时光链, 那年今日, 月度回顾, or runs /moment.
  Call catalog endpoints with the user's personal access token; do not invent APIs.
---

# Moment

Moment 把此刻记成一条 **moment**，收进可邀请的 **时光链（chain）**。本 skill 用 HTTP 操作**当前用户的实例**。

你是记录入口：用户要记的事写进 Moment。消化、月度回顾、转写由 Moment 后台完成。

接口形状以 `references/` 下**当前意图对应的那一个模块**为准。`api.json` 只给 `scripts/moment.mjs` 读。

## 每个会话

`SKILL_DIR` = 本文件所在目录。

```bash
export MOMENT_BASE_URL="${MOMENT_BASE_URL:-http://localhost:3000}"
node "$SKILL_DIR/scripts/moment.mjs" call GET /api/auth/me
```

`MOMENT_TOKEN` 必须已在环境里。没有时让用户在 Moment 网页「我」页的「接口令牌」里生成一枚，并在 shell 里 `export MOMENT_TOKEN='mmt_…'`。不要向用户要邮箱或密码，不要把令牌写进仓库、shell 配置或回复。

需要 body / query 时：按意图 **Read 下表中的一个 md**，或 `show METHOD PATH`。

## 凭证

| 变量              | 用途                                                                      |
| ----------------- | ------------------------------------------------------------------------- |
| `MOMENT_TOKEN`    | 接口令牌，前缀 `mmt_`。设置里创建，不过期，直到吊销或改密。               |
| `MOMENT_BASE_URL` | API 根。缺省 `http://localhost:3000`。线上是 `https://moment.aimo.plus`。 |
| `MOMENT_BA_TOKEN` | 只给 `auth=ba` 的内部向量接口。日常不设置。                               |

已认证路由带 `Authorization: Bearer $MOMENT_TOKEN`。`auth=optional` 有令牌就带上。`auth=none` 不带。`auth=ba` 用 `MOMENT_BA_TOKEN`。网页登录用的短时 JWT 不给这个 skill 用。

## 领域

| 实体         | 做什么                                                                                                                                                         |
| ------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Chain        | 一条时光链。角色 owner > editor > viewer。创建时必填 `template`（通常 `baby` / `travel` / `daily`，以 `GET /api/templates?scope=official` 为准），之后不可改。 |
| Moment       | 链上的一条记录：`text` / `media` / `video` / `voice`。`happenedAt` 是事件时间，`happenedTzOffset` 同 `Date#getTimezoneOffset()`（东八区为 `-480`）。           |
| Person / Tag | 链内人物和标签。时刻上的关联是提交时的集合。                                                                                                                   |
| Share link   | 只读链接，打开的人不用注册。                                                                                                                                   |
| Recap        | 链的月度回顾。生成是异步任务。                                                                                                                                 |
| Media        | 先申请上传，再把字节 PUT 到返回的预签名 URL。预签名地址会过期，持久引用用 `mediaId`。                                                                          |

链内最低角色写在模块条目的 `role>=` 上。viewer 可读，editor 可写时刻，owner 才能删链、转让和改他人角色。

记时刻直接 `POST /api/chains/:chainId/moments`。用户明确要跟助手对话时才走 agent 模块。

### 写时刻

文字：`type=text`，`content` 非空，`mediaIds` 为空。图片 1–9 张，视频恰好 1 个，语音 1 条音频加最多 8 张图。`kind` 缺省 `standard`。

`PATCH /api/moments/:id` 带 `chainId` 才是换链。换到另一条链时：标签和人物缺省清空；两条链模板不同时，服务端把 `kind` 收成 `standard`、`payload` 收成 null。评论留在原时刻上。`personIds` / `place` / `mediaIds` 缺省表示不变，空数组表示清空。

### 上传

`POST /api/media/presign`。`method=put` 时，用 curl 把文件 PUT 到返回的 `url`，不要把文件塞进 `call`。`method=multipart` 时再要 part URL、分段 PUT、用 ETag 调 complete。图片 ≤10MB，视频 ≤500MB，语音 ≤25MB。语音必须带 `durationSeconds`。上传完成后再把 `mediaId` 写进时刻。

`GET /api/media/:id` 返回 302。脚本不跟随跳转，只打印 `location`。

## 意图 → 只读一个模块

PATH 参数换成实值，然后 `call METHOD PATH`。

| 用户要…                         | 只 Read                                            | 先调                                             |
| ------------------------------- | -------------------------------------------------- | ------------------------------------------------ |
| 服务是否活着                    | [references/health.md](references/health.md)       | `GET /api/health`                                |
| 我是谁 / 令牌 / 通知 / 推送设备 | [references/account.md](references/account.md)     | `GET /api/auth/me`                               |
| 链、成员、邀请、转让            | [references/chains.md](references/chains.md)       | `GET /api/chains`                                |
| 写、改、读一条时刻              | [references/moments.md](references/moments.md)     | `POST /api/chains/:chainId/moments`              |
| 时间线 / 那年今日               | [references/feed.md](references/feed.md)           | `GET /api/feed`                                  |
| 评论 / 表情                     | [references/social.md](references/social.md)       | 见该模块                                         |
| 标签 / 人物                     | [references/people.md](references/people.md)       | 见该模块                                         |
| 上传媒体                        | [references/media.md](references/media.md)         | `POST /api/media/presign`                        |
| 分享链接 / 公开页               | [references/share.md](references/share.md)         | 见该模块                                         |
| 模板 / 聚合                     | [references/templates.md](references/templates.md) | `GET /api/templates`                             |
| 月度回顾                        | [references/recaps.md](references/recaps.md)       | `GET /api/chains/:chainId/recaps`                |
| 搜索                            | [references/search.md](references/search.md)       | `POST /api/search`                               |
| 链上异步任务                    | [references/jobs.md](references/jobs.md)           | `GET /api/chains/:chainId/jobs`                  |
| 坐标换地名                      | [references/geocode.md](references/geocode.md)     | `POST /api/geocode/reverse`                      |
| 跟助手对话                      | [references/agent.md](references/agent.md)         | `POST /api/agent/threads`                        |
| 内部向量                        | [references/internal.md](references/internal.md)   | 不调用，除非用户明确要求并提供 `MOMENT_BA_TOKEN` |

上表没有的新模块见 [references/index.md](references/index.md)。索引只用来找文件名。

Query：`--query chain_ids=<uuid> --query limit=20`。Feed 的查询参数是 snake_case（`chain_ids`、`tag_id`、`happened_from`）。Body 是 camelCase。大段正文用 `--file /tmp/body.json`。

`POST /api/search` 的 body 要 `q` 和 `tzOffset`。那年今日的 `date` 是查看者本地的 `YYYY-MM-DD`。

`POST /api/agent/threads` 的 body 是 `{}`。接着 `POST /api/agent/threads/:id/turns`，响应是 SSE，脚本按事件流原样输出。

## 约束

- 删除链、时刻、评论、标签、人物、分享链接、模板、助手线程，吊销接口令牌，转让链，改角色，改密码，退出登录，重新生成回顾：先说明影响，得到用户确认再调用。
- 时刻和评论是软删除。改密码会吊销全部接口令牌，当前 `MOMENT_TOKEN` 随之失效。用户需要在网页「我」页重新生成，并更新环境变量。退出登录只影响网页会话，不吊销接口令牌。
- 错误体是 `{"error":{"code":"…","message":"…","details":…}}`。把 `code` 和 `message` 告诉用户。
- 非成员访问链内资源得到 `CHAIN_NOT_FOUND`。角色不够是 `CHAIN_ROLE_INSUFFICIENT`。
- 模板在创建链时确定。更新链时 body 里放 `template` 会得到 `TEMPLATE_IMMUTABLE`。
- 预签名 URL 只用于这一次上传或展示。写回 API 的是 `mediaId`。
- `MOMENT_BA_TOKEN` 只在用户点名内部向量接口时使用。
